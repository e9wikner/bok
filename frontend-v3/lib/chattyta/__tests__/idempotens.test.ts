import { describe, expect, it } from "vitest";
import { BOK_KLIENT_NS, nyckelForUtkast, uuidV5 } from "@/lib/chattyta/idempotens";

// Kanonisk UUIDv5: gemener, version 5 i tredje gruppen, variant 10xx (8, 9, a, b)
// i fjärde (RFC 4122 §4.1.1, §4.1.3).
const UUID_V5 = /^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

// Serverns namnrymd i `services/agent_tools.py`. Klientens får aldrig vara
// densamma (SPEC-chattyta.md §8 steg 1).
const SERVERNS_BOK_NAMESPACE = "8f2b6e6c-8a2b-4a9a-9f7c-3a0b6f7f0b1a";

describe("nyckelForUtkast — nyckelns härledning (testfall 26)", () => {
  it("samma draft_id ger samma UUID, också vid ett nytt anrop (omladdning) (testfall 26)", async () => {
    const forsta = await nyckelForUtkast("d-1");
    const andra = await nyckelForUtkast("d-1");
    expect(andra).toBe(forsta);
  });

  it("olika draft_id ger olika UUID (testfall 26)", async () => {
    expect(await nyckelForUtkast("d-1")).not.toBe(await nyckelForUtkast("d-2"));
  });

  it("nyckeln är en giltig UUIDv5 i kanonisk form (testfall 26)", async () => {
    for (const id of ["d-1", "", "å-1", "0b7c5a1e-2f7e-4c4b-9d0a-6a1b2c3d4e5f"]) {
      expect(await nyckelForUtkast(id)).toMatch(UUID_V5);
    }
  });
});

describe("nyckelForUtkast — kända testvektorer ur Pythons uuid.uuid5", () => {
  // Räknade med (kör om vid behov; namnrymden måste vara BOK_KLIENT_NS):
  //
  //   python3 -c "import uuid; ns = uuid.UUID('67d43419-c305-4b32-9247-305e346b0398'); \
  //     [print(repr(n), uuid.uuid5(ns, n)) for n in ['draft:d-1', 'draft:d-2', 'draft:å-1', 'draft:']]"
  //
  // Samma värden ur båda sidor betyder att klient och server kan jämföra
  // nycklar om de någon gång behöver det (tasks/chattyta/todo.md, C11).
  it.each([
    ["d-1", "6b8fce5b-d4b0-5eac-8283-ba8fb25e1c87"],
    ["d-2", "3d95018e-9389-5fe0-9cc9-5068e1aec57c"],
    // Icke-ASCII: bevisar att namnet kodas som UTF-8, precis som i Python.
    ["å-1", "9b01787c-6cbc-5a08-82db-7bb28c741712"],
    ["", "5e05ee94-230b-58ca-93db-45455c1a901f"],
  ])("draft:%s → %s", async (draftId, forvantad) => {
    expect(await nyckelForUtkast(draftId)).toBe(forvantad);
  });
});

describe("uuidV5 — algoritmen oberoende av vår namnrymd", () => {
  it("RFC 4122:s DNS-namnrymd och www.example.com ger Pythons värde", async () => {
    // python3 -c "import uuid; print(uuid.uuid5(uuid.NAMESPACE_DNS, 'www.example.com'))"
    expect(await uuidV5("6ba7b810-9dad-11d1-80b4-00c04fd430c8", "www.example.com")).toBe(
      "2ed6657d-e927-568b-95e1-2665a8aea6a2",
    );
  });

  it("tar emot namnrymden med versaler och ger ändå gemener ut", async () => {
    expect(await uuidV5("6BA7B810-9DAD-11D1-80B4-00C04FD430C8", "www.example.com")).toBe(
      "2ed6657d-e927-568b-95e1-2665a8aea6a2",
    );
  });

  it("vägrar en namnrymd som inte är en UUID", async () => {
    await expect(uuidV5("inte-en-uuid", "x")).rejects.toThrow(/namnrymd/);
  });
});

describe("BOK_KLIENT_NS", () => {
  it("är en fast UUID i kanonisk form", () => {
    expect(BOK_KLIENT_NS).toBe("67d43419-c305-4b32-9247-305e346b0398");
  });

  it("är skild från serverns BOK_NAMESPACE, så nycklarna aldrig kan kollidera (§8)", () => {
    expect(BOK_KLIENT_NS).not.toBe(SERVERNS_BOK_NAMESPACE);
  });
});
