/**
 * Sant när tangenttrycket hör till ett fält där någon skriver: input,
 * textarea, select eller contentEditable. Skalets tangentgenvägar (piltangent
 * byter vy, Escape stänger lagret) ska då låta bli — markören ska flytta sig
 * i texten, inte sidan (#57).
 */
export function arRedigerbartMal(mal: EventTarget | null): boolean {
  if (!(mal instanceof HTMLElement)) return false;
  const tagg = mal.tagName;
  if (tagg === "INPUT" || tagg === "TEXTAREA" || tagg === "SELECT") return true;
  // jsdom saknar `isContentEditable`; attributet räcker som reserv.
  return mal.isContentEditable || mal.closest('[contenteditable]:not([contenteditable="false"])') !== null;
}
