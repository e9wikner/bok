import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import { ChattList } from "@/components/skal/ChattList";
import type { UseTrad } from "@/hooks/useTrad";
import { lasUtkast, sparaUtkast } from "@/lib/chattyta/utkast";

// Osänd text står kvar när fältet monteras om vid vy- och sidbyte.
const skicka = vi.fn<UseTrad["skicka"]>(async () => true);
const tradSvar: UseTrad = {
  inlagg: [],
  strommande: null,
  skicka: (...a) => skicka(...a),
  laddar: false,
  fel: null,
  kontextFran: 0,
  nollstalldVid: null,
  nollstall: async () => true,
};
vi.mock("@/hooks/useTrad", () => ({ useTrad: () => tradSvar }));

const falt = () => screen.getByRole("textbox") as HTMLInputElement;

afterEach(() => {
  skicka.mockClear();
  vi.restoreAllMocks();
});

describe("chattfältets utkast", () => {
  it("står kvar när vyn blir inaktiv och sedan aktiv igen", () => {
    const { rerender } = render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    fireEvent.change(falt(), { target: { value: "vad är 1930?" } });
    rerender(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" aktiv={false} />);
    rerender(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    expect(falt().value).toBe("vad är 1930?");
  });

  it("står kvar när fältet monteras om helt (sidbyte), också på mobil", () => {
    const { unmount } = render(<ChattList vyTitel="Resultat" viewKey="bocker.resultat" vantandeBeslut={0} />);
    fireEvent.change(falt(), { target: { value: "halvskriven" } });
    unmount();
    render(<ChattList vyTitel="Resultat" viewKey="bocker.resultat" vantandeBeslut={0} />);
    expect(falt().value).toBe("halvskriven");
  });

  it("hör till sin vy", () => {
    const { unmount } = render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    fireEvent.change(falt(), { target: { value: "bara här" } });
    unmount();
    render(<ChattKolumn vyTitel="Resultat" viewKey="bocker.resultat" />);
    expect(falt().value).toBe("");
  });

  it("rensas när meddelandet har lagrats", async () => {
    const { unmount } = render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    fireEvent.change(falt(), { target: { value: "skicka mig" } });
    await act(async () => {
      fireEvent.submit(falt().form!);
    });
    expect(skicka).toHaveBeenCalled();
    expect(falt().value).toBe("");
    unmount();
    expect(lasUtkast("bocker.balans")).toBe("");
  });

  it("står kvar när servern inte tog emot meddelandet", async () => {
    skicka.mockResolvedValueOnce(false);
    const { unmount } = render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    fireEvent.change(falt(), { target: { value: "försök igen" } });
    await act(async () => {
      fireEvent.submit(falt().form!);
    });
    unmount();
    expect(lasUtkast("bocker.balans")).toBe("försök igen");
  });
});

describe("lib/chattyta/utkast", () => {
  it("tom text tar bort utkastet", () => {
    sparaUtkast("v", "x");
    sparaUtkast("v", "");
    expect(window.sessionStorage.length).toBe(0);
    expect(lasUtkast("v")).toBe("");
  });

  it("håller utkastet i minnet när storage kastar", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    sparaUtkast("v", "kvar");
    expect(lasUtkast("v")).toBe("kvar");
  });
});
