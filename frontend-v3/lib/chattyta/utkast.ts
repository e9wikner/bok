/**
 * Chattfältets osända text, per vy.
 *
 * `ChattFalt` monteras om vid varje vybyte (den aktiva vyn läser tråden i en
 * egen komponent) och vid varje sidbyte (svepraden har sidans nyckel), så
 * texten kan inte bo i fältets state ensam. Här står den kvar tills den
 * skickats eller suddats.
 *
 * `sessionStorage`: utkastet överlever en omladdning i fliken men följer
 * inte med till en annan flik. Storage kan saknas eller kasta (privat läge,
 * blockerad webbplatsdata); då håller en modul-`Map` utkastet så länge
 * sidan lever.
 */

const PREFIX = "bok:chattutkast:";
const reserv = new Map<string, string>();

function lagring(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function lasUtkast(viewKey: string): string {
  try {
    const s = lagring();
    if (s) return s.getItem(PREFIX + viewKey) ?? "";
  } catch {
    // Reserven nedan.
  }
  return reserv.get(viewKey) ?? "";
}

/** Tom text tar bort utkastet i stället för att lagra en tom sträng. */
export function sparaUtkast(viewKey: string, text: string): void {
  try {
    const s = lagring();
    if (s) {
      if (text === "") s.removeItem(PREFIX + viewKey);
      else s.setItem(PREFIX + viewKey, text);
      return;
    }
  } catch {
    // Reserven nedan.
  }
  if (text === "") reserv.delete(viewKey);
  else reserv.set(viewKey, text);
}
