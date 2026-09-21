"use client";

import { useState } from "react";

/**
 * `ChattFalt` (komponenter.md): radius 12, streckad kant #c7c7cc,
 * background #fbfbfc, padding 13/16, text 15 #71717a, ↵ mono 12 till höger.
 *
 * REN TEXTINMATNING — INGA FÖRSLAGSCHIPS. README.md och komponenter.md
 * säger det båda ordagrant; v10-prototypen har en påslagen växel som visar
 * två chips, och beställaren avgjorde 2026-09-21 att texten gäller.
 * SPEC-skal.md §2.1. Lägg inte tillbaka dem: ett chip är ett förvalt
 * yttrande, och designens egen regel är att ingenting förväljs.
 *
 * `drop`-varianten (drag och släpp, kamera, urklipp) hör till
 * `flode-underlag` och finns inte här.
 */
export function ChattFalt({
  vyTitel,
  variant = "desktop",
  onSkicka,
}: {
  vyTitel: string;
  variant?: "desktop" | "mobil";
  /** Skalet skickar ingenting. `tradar` kopplar POST /threads/{view_key}/messages. */
  onSkicka?: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const etikett = `Fråga om en post i ${vyTitel.toLowerCase()}`;

  return (
    <form
      className={
        variant === "desktop"
          ? "shrink-0 border-t border-bok-linje px-[38px] pb-5 pt-4"
          : "shrink-0 px-[18px] pb-[18px] pt-3"
      }
      onSubmit={(e) => {
        e.preventDefault();
        if (!text.trim()) return;
        onSkicka?.(text.trim());
        setText("");
      }}
    >
      <div className="flex items-center gap-3 rounded-[12px] border border-dashed border-bok-kant-streckad bg-bok-yta-falt px-4 py-[13px]">
        <label htmlFor="skal-chattfalt" className="sr-only">
          {etikett}
        </label>
        <input
          id="skal-chattfalt"
          name="skal-chattfalt"
          type="text"
          autoComplete="off"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={etikett}
          className="min-w-0 flex-1 bg-transparent text-[15px] text-bok-text outline-none placeholder:text-[#71717a]"
        />
        <span aria-hidden="true" className="bok-mono text-[12px] text-bok-meta">
          ↵
        </span>
      </div>
    </form>
  );
}
