import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { MOCK_VYER } from "@/lib/skal/mock";
import { allaVyer, sidan } from "@/lib/skal/vyer";

const fakturering = sidan("betala").vyer[0];
const loner = sidan("betala").vyer[1];

describe("Fakturering och Löner är läsvyer utan skrivflöde (testfall 17)", () => {
  it("Fakturering har ingen knapp alls i vyn", () => {
    render(<VyInnehall vy={fakturering} data={MOCK_VYER["betala.fakturering"]} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("Löner har ingen knapp alls i vyn", () => {
    render(<VyInnehall vy={loner} data={MOCK_VYER["betala.loner"]} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("lovar inte en funktion som inte finns", () => {
    render(<VyInnehall vy={fakturering} data={MOCK_VYER["betala.fakturering"]} />);
    // Ingen avstängd knapp, ingen "kommer snart". En yta som lovar en
    // funktion som inte finns är sämre än en yta som inte lovar den.
    expect(screen.queryByText(/kommer snart|snart tillgänglig|ej tillgänglig/i)).toBeNull();
    expect(document.querySelector("button[disabled]")).toBeNull();
  });

  it("säger i stället vad agenten gör och var skrivning sker i dag", () => {
    render(<VyInnehall vy={loner} data={MOCK_VYER["betala.loner"]} />);
    expect(screen.getByText(/Godkännande görs tills vidare i den gamla lönevyn/)).toBeInTheDocument();
  });

  it("är de enda två vyerna som är märkta som läsvyer", () => {
    expect(allaVyer().filter((v) => v.lasvy).map((v) => v.titel)).toEqual([
      "Fakturering",
      "Löner",
    ]);
  });
});
