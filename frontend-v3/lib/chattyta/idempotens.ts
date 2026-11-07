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
 * SHA-1 räknas här i filen, inte med `crypto.subtle` — inga beroenden
 * (SPEC-chattyta.md §3). `crypto.subtle` finns bara i en säker kontext (https
 * eller localhost); på `http://hubbabubba:3000` är det `undefined`, och då föll
 * varje `Posta` på ett TypeError innan något anrop gick iväg (`okänt fel`).
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

/** SHA-1 (FIPS 180-4) över `data`. Liten och långsam nog; nyckeln är ett par hundra byte. */
function sha1(data: Uint8Array): Uint8Array {
  const bitar = data.length * 8;
  const block = Math.ceil((data.length + 9) / 64) * 64;
  const buf = new Uint8Array(block);
  buf.set(data);
  buf[data.length] = 0x80;
  const vy = new DataView(buf.buffer);
  vy.setUint32(block - 8, Math.floor(bitar / 0x100000000));
  vy.setUint32(block - 4, bitar >>> 0);

  let h0 = 0x67452301, h1 = 0xefcdab89, h2 = 0x98badcfe, h3 = 0x10325476, h4 = 0xc3d2e1f0;
  const w = new Uint32Array(80);
  const rotl = (x: number, n: number) => (x << n) | (x >>> (32 - n));
  for (let off = 0; off < block; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = vy.getUint32(off + i * 4);
    for (let i = 16; i < 80; i++) w[i] = rotl(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    let a = h0, b = h1, c = h2, d = h3, e = h4;
    for (let i = 0; i < 80; i++) {
      const [f, k] =
        i < 20 ? [(b & c) | (~b & d), 0x5a827999]
        : i < 40 ? [b ^ c ^ d, 0x6ed9eba1]
        : i < 60 ? [(b & c) | (b & d) | (c & d), 0x8f1bbcdc]
        : [b ^ c ^ d, 0xca62c1d6];
      const t = (rotl(a, 5) + f + e + k + w[i]) >>> 0;
      e = d;
      d = c;
      c = rotl(b, 30) >>> 0;
      b = a;
      a = t;
    }
    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
  }
  const ut = new Uint8Array(20);
  const utVy = new DataView(ut.buffer);
  [h0, h1, h2, h3, h4].forEach((h, i) => utVy.setUint32(i * 4, h));
  return ut;
}

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

  const summa = sha1(indata);
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
