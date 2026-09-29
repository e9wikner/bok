import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ChattFalt } from "@/components/skal/ChattFalt";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import { ChattList } from "@/components/skal/ChattList";
import type { UseTrad } from "@/hooks/useTrad";

/**
 * FU20 — `ChattFalt/drop` (SPEC-flode-underlag.md §10.1–§10.2; testfall 45,
 * 46, 48, 49 och D8). Axios-instansen är mockad; uppladdningens logik är
 * den riktiga (`lib/chattyta/uppladdning.ts`).
 */

const post = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { post: (...a: unknown[]) => post(...a), get: vi.fn() },
}));

const skicka = vi.fn(async (_text: string, _bilagor?: readonly string[]) => true);
const tradSvar = (): UseTrad => ({ inlagg: [], strommande: null, skicka, laddar: false, fel: null, kontextFran: 0, nollstalldVid: null, nollstall: async () => true });
vi.mock("@/hooks/useTrad", () => ({ useTrad: () => tradSvar() }));

beforeEach(() => {
  post.mockReset();
  skicka.mockReset();
  skicka.mockImplementation(async () => true);
});

// ─── Hjälpare ─────────────────────────────────────────────────────────────

const fil = (namn = "kvitto-elektronikhuset.pdf", typ = "application/pdf", storlek = 218_000) =>
  new File([new Uint8Array(storlek)], namn, { type: typ });

/** Ett svar som inte kommit än. */
function uppskjutet<T>() {
  let losa!: (v: T) => void;
  const lofte = new Promise<T>((r) => (losa = r));
  return { lofte, losa };
}

const kalla = (id: string) => ({
  data: { id, status: "pending", original_filename: "k.pdf", mime_type: "application/pdf", size_bytes: 1 },
});

const filvaljare = (container: HTMLElement) =>
  container.querySelector('input[type="file"]') as HTMLInputElement;

const valjFiler = (container: HTMLElement, filer: File[]) =>
  fireEvent.change(filvaljare(container), { target: { files: filer } });

const trycktEnter = (falt: HTMLElement) => fireEvent.submit(falt.closest("form")!);

// ─── Filväljaren ──────────────────────────────────────────────────────────

describe("filväljaren (testfall 45)", () => {
  it("fältet har en knapp som öppnar filväljaren — den enda knappen, inga förslagschips", () => {
    const { container } = render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    const form = container.querySelector("form")!;
    const knappar = within(form).getAllByRole("button");
    expect(knappar).toHaveLength(1);
    expect(knappar[0]).toHaveAccessibleName("Bifoga underlag");

    const klick = vi.spyOn(filvaljare(container), "click");
    fireEvent.click(knappar[0]);
    expect(klick).toHaveBeenCalledTimes(1);
  });

  it("desktop tar serverns typer, flera filer; mobilen öppnar kameran", () => {
    const { container: desktop } = render(<ChattFalt vyTitel="Verifikationer" />);
    const d = filvaljare(desktop);
    expect(d.multiple).toBe(true);
    expect(d.accept.split(",").sort()).toEqual(
      ["application/pdf", "image/gif", "image/jpeg", "image/png", "image/webp"].sort()
    );
    expect(d).not.toHaveAttribute("capture");

    const { container: mobil } = render(<ChattFalt vyTitel="Verifikationer" variant="mobil" />);
    const m = filvaljare(mobil);
    expect(m.accept).toBe("image/*");
    expect(m).toHaveAttribute("capture", "environment");
  });

  it("en vald fil laddas upp direkt och chipet går från `laddar upp…` till `klar`", async () => {
    const svar = uppskjutet<ReturnType<typeof kalla>>();
    post.mockReturnValueOnce(svar.lofte);
    const { container } = render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    valjFiler(container, [fil()]);

    const chip = screen.getByTestId("filchip");
    expect(chip).toHaveTextContent("kvitto-elektronikhuset.pdf");
    expect(chip).toHaveTextContent("218 kB");
    expect(chip).toHaveTextContent("laddar upp…");
    expect(post).toHaveBeenCalledWith("/api/v1/intake", expect.any(FormData), expect.anything());

    await act(async () => svar.losa(kalla("src-1")));
    expect(screen.getByTestId("filchip")).toHaveTextContent("klar");
  });

  it("↵ skickar texten och chipens id:n, och tömmer fältet och de skickade chipen (testfall 45)", async () => {
    post.mockResolvedValueOnce(kalla("src-1"));
    const { container } = render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    valjFiler(container, [fil()]);
    await waitFor(() => expect(screen.getByTestId("filchip")).toHaveTextContent("klar"));

    const falt = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(falt, { target: { value: "  kvittot till A-118  " } });
    trycktEnter(falt);

    await waitFor(() => expect(skicka).toHaveBeenCalledWith("kvittot till A-118", ["src-1"]));
    await waitFor(() => expect(falt.value).toBe(""));
    expect(screen.queryByTestId("filchip")).toBeNull();
  });

  it("utan text skickas meddelandet ändå med bilagan (D8)", async () => {
    post.mockResolvedValueOnce(kalla("src-1"));
    const { container } = render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    valjFiler(container, [fil()]);
    await waitFor(() => expect(screen.getByTestId("filchip")).toHaveTextContent("klar"));

    trycktEnter(screen.getByRole("textbox"));
    await waitFor(() => expect(skicka).toHaveBeenCalledWith("", ["src-1"]));
  });

  it("ett misslyckat meddelande behåller chipen", async () => {
    post.mockResolvedValueOnce(kalla("src-1"));
    skicka.mockImplementation(async () => false);
    const { container } = render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    valjFiler(container, [fil()]);
    await waitFor(() => expect(screen.getByTestId("filchip")).toHaveTextContent("klar"));

    trycktEnter(screen.getByRole("textbox"));
    await waitFor(() => expect(skicka).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("filchip")).toHaveTextContent("klar");
  });

  it("utan chip skickas bara texten, som förut", async () => {
    render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    const falt = screen.getByRole("textbox");
    fireEvent.change(falt, { target: { value: "hej" } });
    trycktEnter(falt);
    await waitFor(() => expect(skicka).toHaveBeenCalledWith("hej"));
  });
});

// ─── Fel ──────────────────────────────────────────────────────────────────

describe("ett chip med fel (testfall 46)", () => {
  it("en otillåten fil blir ett felchip utan uppladdning, och följer inte med", async () => {
    const { container } = render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    valjFiler(container, [fil("arkiv.zip", "application/zip", 10)]);

    const chip = screen.getByTestId("filchip");
    expect(chip).toHaveTextContent("filtypen stöds inte");
    expect(post).not.toHaveBeenCalled();

    const falt = screen.getByRole("textbox");
    fireEvent.change(falt, { target: { value: "hej" } });
    trycktEnter(falt);
    await waitFor(() => expect(skicka).toHaveBeenCalledWith("hej"));
    // Felet står kvar med orsaken tills det tas bort.
    expect(screen.getByTestId("filchip")).toHaveTextContent("filtypen stöds inte");
  });

  it("bara ett felchip och ingen text: ↵ skickar ingenting", () => {
    const { container } = render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    valjFiler(container, [fil("stor.pdf", "application/pdf", 11 * 1024 * 1024)]);
    expect(screen.getByTestId("filchip")).toHaveTextContent("för stor");
    trycktEnter(screen.getByRole("textbox"));
    expect(skicka).not.toHaveBeenCalled();
  });

  it("ett chip tas bort med sin knapp", () => {
    const { container } = render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    valjFiler(container, [fil("arkiv.zip", "application/zip", 10)]);
    fireEvent.click(screen.getByRole("button", { name: "Ta bort arkiv.zip" }));
    expect(screen.queryByTestId("filchip")).toBeNull();
  });
});

// ─── ↵ under uppladdning ──────────────────────────────────────────────────

describe("↵ medan ett chip laddar upp (testfall 48)", () => {
  it("är avstängt, också med text; går när chipet är klart", async () => {
    const svar = uppskjutet<ReturnType<typeof kalla>>();
    post.mockReturnValueOnce(svar.lofte);
    const { container } = render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    valjFiler(container, [fil()]);

    const falt = screen.getByRole("textbox");
    fireEvent.change(falt, { target: { value: "här är kvittot" } });
    trycktEnter(falt);
    expect(skicka).not.toHaveBeenCalled();
    expect(screen.getByTestId("chattfalt-enter")).toHaveAttribute("data-avstangd", "true");

    await act(async () => svar.losa(kalla("src-1")));
    trycktEnter(falt);
    await waitFor(() => expect(skicka).toHaveBeenCalledWith("här är kvittot", ["src-1"]));
  });
});

// ─── Urklipp och dra och släpp ────────────────────────────────────────────

describe("urklipp och dra och släpp går samma väg (testfall 49)", () => {
  it("en fil som klistras in i fältet blir ett chip och laddas upp", async () => {
    post.mockResolvedValueOnce(kalla("src-7"));
    render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    fireEvent.paste(screen.getByRole("textbox"), {
      clipboardData: { files: [fil("urklipp.png", "image/png", 5_000)], types: ["Files"] },
    });
    expect(screen.getByTestId("filchip")).toHaveTextContent("urklipp.png");
    await waitFor(() => expect(screen.getByTestId("filchip")).toHaveTextContent("klar"));
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("text i urklippet klistras in som vanligt", () => {
    render(<ChattFalt vyTitel="Verifikationer" onSkicka={skicka} />);
    fireEvent.paste(screen.getByRole("textbox"), { clipboardData: { files: [], types: ["text/plain"] } });
    expect(screen.queryByTestId("filchip")).toBeNull();
    expect(post).not.toHaveBeenCalled();
  });

  it("en fil släppt var som helst på tråden i desktopkolumnen blir ett chip i fältet", async () => {
    post.mockResolvedValueOnce(kalla("src-3"));
    render(<ChattKolumn vyTitel="Verifikationer" viewKey="bocker.verifikationer" />);
    const trad = screen.getByLabelText("Tråd för Verifikationer");
    fireEvent.dragOver(trad, { dataTransfer: { files: [], types: ["Files"] } });
    fireEvent.drop(trad, { dataTransfer: { files: [fil()], types: ["Files"] } });

    await waitFor(() => expect(screen.getByTestId("filchip")).toHaveTextContent("klar"));
    trycktEnter(screen.getByRole("textbox"));
    // Kolumnens fält skickar genom `useTrad().skicka`.
    await waitFor(() => expect(skicka).toHaveBeenCalledWith("", ["src-3"]));
  });

  it("samma sak i mobilens chattlist", async () => {
    post.mockResolvedValueOnce(kalla("src-4"));
    render(<ChattList vyTitel="Verifikationer" viewKey="bocker.verifikationer" vantandeBeslut={0} />);
    const trad = screen.getByLabelText("Tråd för Verifikationer");
    fireEvent.drop(trad, { dataTransfer: { files: [fil("foto.jpg", "image/jpeg", 900_000)], types: ["Files"] } });
    await waitFor(() => expect(screen.getByTestId("filchip")).toHaveTextContent("klar"));
    trycktEnter(screen.getByRole("textbox"));
    await waitFor(() => expect(skicka).toHaveBeenCalledWith("", ["src-4"]));
  });

  it("en inaktiv vy tar inte emot filer", () => {
    render(<ChattKolumn vyTitel="Verifikationer" viewKey="bocker.verifikationer" aktiv={false} />);
    fireEvent.drop(screen.getByLabelText("Tråd för Verifikationer"), {
      dataTransfer: { files: [fil()], types: ["Files"] },
    });
    expect(screen.queryByTestId("filchip")).toBeNull();
    expect(post).not.toHaveBeenCalled();
  });
});
