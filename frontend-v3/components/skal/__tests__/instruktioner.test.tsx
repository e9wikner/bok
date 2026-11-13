import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { InstruktionerVy } from "@/components/skal/InstruktionerVy";
import { type Omfang, instruktionStatus, korrigeringText } from "@/lib/skal/instruktioner";
import { allaVyer } from "@/lib/skal/vyer";

/** Agentens instruktioner i skalet: företagets regler, en version per sparning. */

const get = vi.fn();
const put = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { get: (...a: unknown[]) => get(...a), put: (...a: unknown[]) => put(...a) },
}));

const V2 = {
  version_id: "v2",
  version: 2,
  content_markdown: "Telia bokförs på 6212.",
  change_summary: "Telia",
  created_by: "admin",
  created_at: "2026-11-10T10:00:00",
};
const V1 = { ...V2, version_id: "v1", version: 1, content_markdown: "", change_summary: null };

function svara(omfang: Omfang) {
  get.mockImplementation((url: string) => {
    if (url === `/api/v1/agent-instructions/${omfang}`)
      return Promise.resolve({ data: { company: V2, system: { content_markdown: "# Systemet\n\nRegler." } } });
    if (url === `/api/v1/agent-instructions/${omfang}/versions`) return Promise.resolve({ data: { versions: [V2, V1] } });
    if (url === "/api/v1/accounting-corrections")
      return Promise.resolve({
        data: {
          corrections: [
            {
              id: "k1",
              correction_reason: "Fel konto",
              corrected_by: "admin",
              created_at: "2026-11-09T10:00:00",
              original_voucher: { series: "A", number: 12 },
              correction_voucher: { series: "B", number: 3 },
            },
          ],
        },
      });
    return Promise.reject(new Error(url));
  });
}

function visa(omfang: Omfang) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <InstruktionerVy titel="Instruktioner" omfang={omfang} variant="desktop" />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  get.mockReset();
  put.mockReset();
});

describe("kartan", () => {
  it("bokföringens regler står i Böcker och faktureringens i Betala, i sidans skrivtråd", () => {
    expect(allaVyer().find((v) => v.key === "bocker.instruktioner")).toMatchObject({ trad: "bocker.verifikationer" });
    expect(allaVyer().find((v) => v.key === "betala.instruktioner")).toMatchObject({ trad: "betala.fakturering" });
  });
});

describe("texterna", () => {
  it("statusraden säger versionen, eller att inga egna regler finns", () => {
    expect(instruktionStatus({ foretaget: V2, system: "", versioner: [V2] }, false).text).toBe("version 2");
    expect(instruktionStatus({ foretaget: null, system: "", versioner: [] }, false).lage).toBe("tomt");
  });

  it("skriver en rättelse med båda verifikationernas nummer", () => {
    const k = { id: "k", correction_reason: null, corrected_by: "a", created_at: "", original: "A-12", rattelse: "B-3" };
    expect(korrigeringText(k)).toBe("A-12 rättad med B-3");
  });
});

describe("vyn", () => {
  it("sparar en ändring som ny version med sin sammanfattning", async () => {
    svara("accounting");
    put.mockResolvedValue({ data: { ...V2, version_id: "v3", version: 3 } });
    visa("accounting");

    const text = await screen.findByLabelText("Företagets regler");
    expect(text).toHaveValue("Telia bokförs på 6212.");
    const spara = screen.getByRole("button", { name: "Spara som ny version" });
    expect(spara).toBeDisabled();

    fireEvent.change(text, { target: { value: "Telia bokförs på 6212. Hyran på 5010." } });
    fireEvent.change(screen.getByLabelText("Vad ändrades"), { target: { value: "Hyran" } });
    fireEvent.click(spara);
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/api/v1/agent-instructions/accounting", {
        content_markdown: "Telia bokförs på 6212. Hyran på 5010.",
        change_summary: "Hyran",
      })
    );
  });

  it("bokföringens vy visar rättelserna och versionerna; systeminstruktionerna fälls ut", async () => {
    svara("accounting");
    visa("accounting");
    expect(await screen.findByText("A-12 rättad med B-3")).toBeInTheDocument();
    expect(screen.getByText("Version 2 · gäller")).toBeInTheDocument();
    expect(screen.queryByText(/Regler\./)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Visa systeminstruktionerna/ }));
    expect(screen.getByText(/Regler\./)).toBeInTheDocument();
  });

  it("faktureringens vy frågar inte efter rättelserna", async () => {
    svara("invoicing");
    visa("invoicing");
    await screen.findByText("Version 2 · gäller");
    expect(get.mock.calls.map((c) => c[0])).not.toContain("/api/v1/accounting-corrections");
  });
});
