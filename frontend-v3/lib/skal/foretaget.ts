/**
 * Företagets uppgifter (modul `skal`, vyn `installningar.foretaget`).
 *
 * Namn, organisationsnummer, adress och kontakt, och det som står på
 * fakturan: säte, momsregistreringsnummer, bankgiro eller plusgiro och
 * F-skatt. Samma endpoint som den gamla inställningssidan
 * (`GET`/`PUT /api/v1/company-info`). Agenten kan också föreslå uppgifterna
 * i ett kort (`foresla_bolagsinformation`).
 */

import apiClient from "@/lib/api";
import type { CompanyInfo } from "@/lib/api";
import type { VyLage } from "@/lib/skal/vydata";

export const FORETAGET_NYCKEL = ["skal", "foretaget"] as const;

/** Textfälten, i formulärets ordning. F-skatt är en kryssruta för sig. */
export type Textfalt = Exclude<keyof CompanyInfo, "f_skatt">;

export const FALTEN: readonly { key: Textfalt; etikett: string; grupp: "foretaget" | "fakturan"; hjalp?: string }[] = [
  { key: "name", etikett: "Företagsnamn", grupp: "foretaget" },
  { key: "org_number", etikett: "Organisationsnummer", grupp: "foretaget" },
  { key: "address", etikett: "Adress", grupp: "foretaget" },
  { key: "postnr", etikett: "Postnummer", grupp: "foretaget" },
  { key: "postort", etikett: "Postort", grupp: "foretaget" },
  { key: "contact_name", etikett: "Kontaktperson", grupp: "foretaget" },
  { key: "email", etikett: "E-post", grupp: "foretaget" },
  { key: "phone", etikett: "Telefon", grupp: "foretaget" },
  { key: "website", etikett: "Webbplats", grupp: "foretaget" },
  { key: "seat", etikett: "Säte", grupp: "fakturan", hjalp: "Kommunen där styrelsen har sitt säte." },
  { key: "vat_number", etikett: "Momsregistreringsnummer", grupp: "fakturan", hjalp: "SE, organisationsnumrets tio siffror och 01." },
  { key: "bankgiro", etikett: "Bankgiro", grupp: "fakturan" },
  { key: "plusgiro", etikett: "Plusgiro", grupp: "fakturan" },
];

export type Formular = Record<Textfalt, string> & { f_skatt: boolean };

export const foretagetApi = {
  hamta: async (): Promise<CompanyInfo> => {
    const { data } = await apiClient.get<CompanyInfo>("/api/v1/company-info");
    return data;
  },
  spara: async (f: Formular): Promise<CompanyInfo> => {
    const { data } = await apiClient.put<CompanyInfo>("/api/v1/company-info", tillServer(f));
    return data;
  },
};

/** API-svaret som formulärets värden: tomma strängar i stället för null. */
export function formularFran(info: CompanyInfo | undefined): Formular {
  const f = { f_skatt: !!info?.f_skatt } as Formular;
  for (const { key } of FALTEN) f[key] = (info?.[key] as string | null | undefined) ?? "";
  return f;
}

/** Formuläret till servern: trimmat, och ett tomt fält som `null` (tas bort). */
export function tillServer(f: Formular): CompanyInfo {
  const ut = { f_skatt: f.f_skatt } as CompanyInfo;
  for (const { key } of FALTEN) {
    // Servern läser momsnumret som det står: utan mellanslag, versalt.
    const v = key === "vat_number" ? f[key].replace(/\s/g, "").toUpperCase() : f[key].trim();
    (ut as unknown as Record<string, string | null>)[key] = v === "" && key !== "name" && key !== "org_number" ? null : v;
  }
  return ut;
}

const VAT_NUMBER = /^SE\d{10}01$/;

/** Det som stoppar formuläret innan det skickas, eller null. */
export function formularFel(f: Formular): string | null {
  if (!f.name.trim()) return "Företagsnamnet kan inte vara tomt.";
  if (!f.org_number.trim()) return "Organisationsnumret kan inte vara tomt.";
  const moms = f.vat_number.replace(/\s/g, "").toUpperCase();
  if (moms && !VAT_NUMBER.test(moms)) return "Momsregistreringsnumret ska vara SE, tio siffror och 01.";
  return null;
}

/**
 * Det en faktura kräver och som saknas eller är felformat: samma krav som
 * servern vid utfärdande (`CompanyInfo.missing_for_invoice`).
 */
export function saknasForFaktura(info: CompanyInfo | undefined): string[] {
  if (!info) return [];
  const saknas: string[] = [];
  if (!info.name) saknas.push("företagsnamn");
  if (!info.org_number) saknas.push("organisationsnummer");
  if (!info.address) saknas.push("adress");
  if (!info.seat) saknas.push("säte");
  if (!VAT_NUMBER.test(info.vat_number ?? "")) saknas.push("momsregistreringsnummer");
  if (!info.bankgiro && !info.plusgiro) saknas.push("bankgiro eller plusgiro");
  return saknas;
}

export function foretagetStatus(info: CompanyInfo | undefined, isError: boolean): { text: string; lage: VyLage } {
  if (isError) return { text: "kunde inte läsas", lage: "fel" };
  if (!info) return { text: "hämtar…", lage: "normal" };
  const saknas = saknasForFaktura(info);
  if (saknas.length > 0) return { text: `${saknas.length} uppgift${saknas.length === 1 ? "" : "er"} saknas för fakturor`, lage: "vantar" };
  return { text: "klart för fakturor", lage: "klart" };
}
