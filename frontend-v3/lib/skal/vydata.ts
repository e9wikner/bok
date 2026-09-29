/**
 * Vyernas dataform (modul `skal`).
 *
 * Komponenterna tar `VyData` som props. Innehållet byggs ur API-svar i
 * `bocker.ts`, `betala.ts` och `bokslut.ts`; skalet har ingen påhittad data.
 */

/** De sex lägena i README.md §Tillstånd. En vy ska kunna visa alla sex. */
export type VyLage = "normal" | "vantar" | "pagaende" | "klart" | "fel" | "tomt";

/** `VyRad`-varianterna i komponenter.md. */
export type RadVariant = "normal" | "saknar" | "vantar" | "pagaende" | "ny" | "fel" | "paverkad";

export type BannerTon = "varning" | "neutral" | "fel" | "klart";

export interface VyRadData {
  id: string;
  titel: string;
  meta?: string;
  hoger: string;
  variant?: RadVariant;
  /** Summarad: samma vikt som designens `r.vikt` 500. */
  summa?: boolean;
  /** Serverns `age_days`; färgar metan för `vantar`/`saknar` med `aldersTon`. */
  ageDays?: number;
  /**
   * Radens länk till kvittot (SPEC-flode-underlag.md §10.4, FU23). Källan
   * slås upp först när länken används, inte per rad.
   */
  kvitto?: { voucherId: string; nummer: string };
}

export interface VySektionData {
  titel: string;
  rader: VyRadData[];
}

export interface VyData {
  lage: VyLage;
  /** Kort status, samma sträng i headern och i vyns rubrikrad. */
  status: string;
  period: string;
  banner?: { ton: BannerTon; text: string };
  sektioner: VySektionData[];
  /** Fottexten säger vad agenten gör härnäst. Inget mer. */
  fot: string;
  /**
   * Listan har fler rader på servern (SPEC-lasbarhet.md §4.5). Då står
   * "Laddar fler…" sist, och `hamtaFler` anropas när raden syns. En vy
   * utan dem är hel.
   */
  harFler?: boolean;
  hamtaFler?: () => void;
}

// ─── Vyernas rader ────────────────────────────────────────────────────────

// ─── Lägen som inte beror på vyn ──────────────────────────────────────────

export const LADDAR_VY: VyData = {
  lage: "pagaende",
  status: "hämtar",
  period: "",
  sektioner: [],
  fot: "",
};

export const FEL_VY: VyData = {
  lage: "fel",
  status: "kunde inte läsas",
  period: "",
  banner: { ton: "fel", text: "Uppgifterna kunde inte hämtas från servern. Ladda om sidan." },
  sektioner: [],
  fot: "",
};

export const INGET_AR_VY: VyData = {
  lage: "tomt",
  status: "inget räkenskapsår",
  period: "",
  sektioner: [],
  fot: "Det finns inget räkenskapsår för dagens datum.",
};
