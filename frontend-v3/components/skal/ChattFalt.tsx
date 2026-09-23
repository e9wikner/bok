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
  /**
   * `useTrad().skicka` (chattyta C5): POST /threads/{view_key}/messages.
   * Fältet töms bara när den svarar `true` — servern har då lagrat texten.
   * `false` (POST misslyckades) eller `void` lämnar texten kvar, så att
   * människan inte behöver skriva om den (tasks/chattyta/todo.md, C3).
   */
  onSkicka?: (text: string) => Promise<boolean> | boolean | void;
}) {
  const [text, setText] = useState("");
  // Ett andra Enter medan det första är i flykt skickar inte igen: texten
  // står ju kvar i fältet tills servern svarat, och samma fråga två gånger
  // är två turer för agenten.
  const [skickar, setSkickar] = useState(false);
  const etikett = `Fråga om en post i ${vyTitel.toLowerCase()}`;

  return (
    <form
      className={
        variant === "desktop"
          ? "shrink-0 border-t border-bok-linje px-[38px] pb-5 pt-4"
          : "shrink-0 px-[18px] pb-[18px] pt-3"
      }
      onSubmit={async (e) => {
        e.preventDefault();
        const skickad = text.trim();
        if (!skickad || skickar || !onSkicka) return;
        setSkickar(true);
        try {
          if (await onSkicka(skickad)) {
            // Har människan hunnit skriva något nytt medan anropet var i
            // flykt är det hennes nästa fråga, inte den som skickades.
            setText((nu) => (nu.trim() === skickad ? "" : nu));
          }
        } finally {
          setSkickar(false);
        }
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
