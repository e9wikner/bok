import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MenySlapp } from "@/components/skal/MenySlapp";
import { fordela, notisRader, utlaggTarEmot } from "@/lib/skal/menySlapp";

/** Sidomenyn som släppyta: Underlag och Utlägg över menyn medan en fil dras. */

const post = vi.fn();
const visaDropzone = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { get: vi.fn(), post: (...a: unknown[]) => post(...a) },
}));

beforeEach(() => {
  post.mockReset();
  visaDropzone.mockReset();
});

const fil = (namn: string, typ = "") => new File(["x"], namn, { type: typ });
const dt = (filer: File[] = []) => ({
  files: filer,
  types: ["Files"],
  items: filer.map((f) => ({ kind: "file", type: f.type })),
});

function visa() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MenySlapp onVisaDropzone={visaDropzone}>
        <nav aria-label="Sidor och vyer">
          <button type="button">Verifikationer</button>
        </nav>
      </MenySlapp>
    </QueryClientProvider>
  );
}

/** En dragning in i fönstret, som från Finder. */
const draIn = (filer: File[] = []) => act(() => void fireEvent.dragEnter(window, { dataTransfer: dt(filer) }));

/** Formdatans mapp och filnamn, per anrop. */
const anrop = () =>
  post.mock.calls.map(([, form]) => ({
    folder: (form as FormData).get("folder"),
    filer: (form as FormData).getAll("files").map((f) => (f as File).name),
  }));

describe("fordela", () => {
  it("Underlag tar allt", () => {
    const { grupper, flyttade } = fordela("underlag", [fil("a.pdf"), fil("1930 okt.csv")]);
    expect(grupper.map((g) => [g.folder, g.filer.map((f) => f.name)])).toEqual([["Underlag", ["a.pdf", "1930 okt.csv"]]]);
    expect(flyttade).toBe(0);
  });

  it("på Utlägg går kontoutdrag och SIE4 till Underlag", () => {
    const { grupper, flyttade } = fordela("utlagg", [fil("kvitto.jpg"), fil("1930.CSV"), fil("ar.se")]);
    expect(grupper.map((g) => [g.folder, g.filer.map((f) => f.name)])).toEqual([
      ["Utlägg", ["kvitto.jpg"]],
      ["Underlag", ["1930.CSV", "ar.se"]],
    ]);
    expect(flyttade).toBe(2);
  });
});

describe("utlaggTarEmot", () => {
  it("en CSV känns igen på MIME-typen under dragningen", () => {
    expect(utlaggTarEmot(dt([fil("a.csv", "text/csv")]) as unknown as DataTransfer)).toBe(false);
    expect(utlaggTarEmot(dt([fil("a.pdf", "application/pdf")]) as unknown as DataTransfer)).toBe(true);
  });
});

describe("notisRader", () => {
  it("säger vad som lades var, vad som flyttades och vad som avvisades", () => {
    expect(
      notisRader(
        {
          laddar: false,
          lagda: [
            { folder: "Utlägg", antal: 1 },
            { folder: "Underlag", antal: 2 },
          ],
          fel: [{ namn: "x.exe", text: "Filtypen tas inte emot." }],
          flyttade: 2,
        },
        4
      )
    ).toEqual([
      "1 fil lagd i Utlägg",
      "2 filer lagda i Underlag",
      "2 filer gick till Underlag: Utlägg tar inte kontoutdrag eller SIE4",
      "x.exe: Filtypen tas inte emot.",
    ]);
  });
});

describe("MenySlapp", () => {
  it("menyn syns tills en fil dras in; då ligger Underlag och Utlägg över den", () => {
    visa();
    expect(screen.queryByTestId("meny-slapp")).toBeNull();
    draIn([fil("a.pdf", "application/pdf")]);
    expect(screen.getByTestId("meny-slapp-underlag")).toBeInTheDocument();
    expect(screen.getByTestId("meny-slapp-utlagg")).toBeInTheDocument();
  });

  it("något som inte är filer (markerad text) byter inte menyn", () => {
    visa();
    act(() => void fireEvent.dragEnter(window, { dataTransfer: { types: ["text/plain"], files: [] } }));
    expect(screen.queryByTestId("meny-slapp")).toBeNull();
  });

  it("menyn kommer tillbaka när dragningen lämnar fönstret", () => {
    visa();
    draIn();
    act(() => void fireEvent.dragLeave(window, { dataTransfer: dt() }));
    expect(screen.queryByTestId("meny-slapp")).toBeNull();
  });

  it("ett släpp på Underlag lägger filen i Underlag och säger det", async () => {
    post.mockResolvedValue({ data: { results: [{ ok: true, original_filename: "a.pdf", folder: "Underlag" }] } });
    visa();
    draIn([fil("a.pdf")]);
    fireEvent.drop(screen.getByTestId("meny-slapp-underlag"), { dataTransfer: dt([fil("a.pdf")]) });
    act(() => void fireEvent.drop(window, { dataTransfer: dt() }));

    expect(await screen.findByText("1 fil lagd i Underlag")).toBeInTheDocument();
    expect(anrop()).toEqual([{ folder: "Underlag", filer: ["a.pdf"] }]);
    expect(screen.queryByTestId("meny-slapp")).toBeNull();
  });

  it("en CSV släppt på Utlägg går till Underlag, kvittot till Utlägg", async () => {
    post.mockImplementation(async (_url: string, form: FormData) => {
      return { data: { results: form.getAll("files").map((f) => ({ ok: true, original_filename: (f as File).name })) } };
    });
    visa();
    const filer = [fil("kvitto.jpg"), fil("1930 okt.csv")];
    draIn(filer);
    fireEvent.drop(screen.getByTestId("meny-slapp-utlagg"), { dataTransfer: dt(filer) });

    expect(await screen.findByText("1 fil gick till Underlag: Utlägg tar inte kontoutdrag eller SIE4")).toBeInTheDocument();
    expect(anrop()).toEqual([
      { folder: "Utlägg", filer: ["kvitto.jpg"] },
      { folder: "Underlag", filer: ["1930 okt.csv"] },
    ]);
  });

  it("Utlägg stänger sig under dragningen av en CSV", () => {
    visa();
    const csv = [fil("a.csv", "text/csv")];
    draIn(csv);
    const zon = screen.getByTestId("meny-slapp-utlagg");
    fireEvent.dragOver(zon, { dataTransfer: dt(csv) });
    expect(zon).toHaveAttribute("data-stangd", "true");
    expect(screen.getByText("Utlägg tar inte kontoutdrag eller SIE4")).toBeInTheDocument();
  });

  it("serverns avvisning står kvar med filnamnet, och notisen leder till Underlag-vyn", async () => {
    post.mockRejectedValue({ response: { data: { detail: { error: "Dropzonen är avstängd." } } } });
    visa();
    draIn([fil("a.pdf")]);
    fireEvent.drop(screen.getByTestId("meny-slapp-underlag"), { dataTransfer: dt([fil("a.pdf")]) });
    act(() => void fireEvent.drop(window, { dataTransfer: dt() }));

    expect(await screen.findByText("a.pdf: Dropzonen är avstängd.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /visa i Underlag/ }));
    expect(visaDropzone).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId("meny-slapp-notis")).toBeNull());
  });
});
