import { redirect } from "next/navigation";

/**
 * Skalet låg på `/v4` medan de gamla sidorna fanns kvar. En sparad länk dit
 * landar på samma sida och vy under `/`.
 */
export default async function V4({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = new URLSearchParams();
  for (const [nyckel, varde] of Object.entries(await searchParams)) {
    for (const v of Array.isArray(varde) ? varde : varde === undefined ? [] : [varde]) params.append(nyckel, v);
  }
  const fraga = params.toString();
  redirect(fraga ? `/?${fraga}` : "/");
}
