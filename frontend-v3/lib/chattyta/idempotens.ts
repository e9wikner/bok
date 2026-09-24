/**
 * Idempotensnyckeln för `Posta` (SPEC-chattyta.md §8 steg 1).
 *
 * Append-only betyder att en dubbelpostning inte kan städas bort — den kräver
 * en korrigeringsverifikation. Därför byggs idempotensen FÖRE något skrivflöde
 * kopplas till en knapp (ANALYS.md §7, "icke förhandlingsbart"); den här filen
 * är den spärren och landas före postningsknappen (C12).
 *
 * Nyckeln är HÄRLEDD, inte slumpad: `uuid5(BOK_KLIENT_NS, "draft:" + draft_id)`.
 * Ett andra tryck, en omladdning, en annan flik och `FelKort`s `Försök igen`
 * ger alla samma nyckel och därmed samma verifikation. En slumpad UUIDv4 per
 * tryck (SPEC-idempotens.md antagande 3) skyddar bara inom ett och samma
 * minne; en härledd nyckel överlever omladdningen. Servern kräver bara att
 * nyckeln är en UUID (`api/deps.py`), så v5 duger lika bra som v4.
 *
 * SHA-1 räknas med `crypto.subtle` — inga beroenden (SPEC-chattyta.md §3).
 * SHA-1 är här ingen säkerhetsfunktion utan det RFC 4122 föreskriver för v5.
 */

/**
 * Klientens namnrymd. Fast, genererad en gång med `uuid.uuid4()`, och får
 * aldrig ändras: en ny namnrymd ger nya nycklar för gamla utkast, och då
 * skyddar nyckeln inte längre mot ett omförsök över en driftsättning.
 *
 * Skild från serverns `BOK_NAMESPACE` (`services/agent_tools.py`,
 * `8f2b6e6c-…`), som härleder agentens nycklar ur `intake:…` och `thread:…`.
 * Med olika namnrymder kan en klientnyckel aldrig sammanfalla med en
 * servernyckel, inte ens om namnen en dag skulle råka bli lika (§8 steg 1).
 */
export const BOK_KLIENT_NS = "67d43419-c305-4b32-9247-305e346b0398";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function uuidTillByte(uuid: string): Uint8Array {
  if (!UUID.test(uuid)) throw new Error(`ogiltig namnrymd: ${uuid}`);
  const hex = uuid.replace(/-/g, "");
  const byte = new Uint8Array(16);
  for (let i = 0; i < 16; i++) byte[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return byte;
}

function byteTillUuid(byte: Uint8Array): string {
  const hex = Array.from(byte, (b) => b.toString(16).padStart(2, "0")).join("");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20, 32),
  ].join("-");
}

/**
 * RFC 4122 UUIDv5: SHA-1 över namnrymdens 16 byte följda av namnet i UTF-8,
 * de första 16 byten av summan, med version- och variantbitarna satta.
 * Exporterad för att algoritmen ska kunna provas mot standardens egna
 * testvektorer, oberoende av vår namnrymd.
 */
export async function uuidV5(namnrymd: string, namn: string): Promise<string> {
  const ns = uuidTillByte(namnrymd);
  // UTF-8, som Pythons `uuid.uuid5` — annars får `å` en annan nyckel än på servern.
  const namnByte = new TextEncoder().encode(namn);
  const indata = new Uint8Array(ns.length + namnByte.length);
  indata.set(ns);
  indata.set(namnByte, ns.length);

  const summa = new Uint8Array(await crypto.subtle.digest("SHA-1", indata));
  const byte = summa.slice(0, 16);
  byte[6] = (byte[6] & 0x0f) | 0x50; // version 5
  byte[8] = (byte[8] & 0x3f) | 0x80; // variant 10xx (RFC 4122)
  return byteTillUuid(byte);
}

/**
 * `Idempotency-Key` för att posta utkastet `draftId`. Samma `draftId` ger
 * alltid samma nyckel (testfall 26); det är hela skyddet — låsningen av
 * knappen i flykt är bara bekvämlighet (§8 steg 2).
 */
export function nyckelForUtkast(draftId: string): Promise<string> {
  return uuidV5(BOK_KLIENT_NS, `draft:${draftId}`);
}
