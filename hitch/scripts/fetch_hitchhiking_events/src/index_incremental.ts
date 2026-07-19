import WebSocket from "ws";
import { NostrFetcher } from "nostr-fetch";
import { writeFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname } from "path";

// Incremental counterpart of index.ts. index.ts always re-fetches the entire kind-36820 history
// (75k+ events) and re-serialises 100+ MB of JSON + CSV every run, which pins a CPU core for a
// minute+. This script fetches only events at or after a caller-supplied `SINCE` (unix seconds),
// so the routine 30-min refresh transfers and serialises only the handful of new/edited rides.
// It writes a single compact JSON file (`OUT_FILE`, default dist/newPosts.json) — no CSV, and no
// pretty-printing — because the output is a small transient batch consumed immediately by
// fetch_nostr_incremental.py, not the public full export (that stays index.ts / allPosts.json).

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const nHoursAgo = (hrs: number): number =>
  Math.floor((Date.now() - hrs * 60 * 60 * 1000) / 1000);

const fetcher = NostrFetcher.init({
  webSocketConstructor: WebSocket,
});

if (!process.env.RELAYS) {
  console.error("RELAYS env var is not set");
  process.exit(1);
}
const relayUrls: string[] = JSON.parse(process.env.RELAYS);
console.log("Using relays:", relayUrls);

if (!process.env.NOSTR_EVENT_KIND) {
  console.error("NOSTR_EVENT_KIND env var is not set");
  process.exit(1);
}
const eventKind = parseInt(process.env.NOSTR_EVENT_KIND, 10);

// `since` is inclusive in the Nostr filter. The caller passes the newest created_at already in
// the DB; re-seeing the boundary event(s) is harmless because the Python side upserts. With no
// SINCE (empty DB / first run) fall back to the full-history window index.ts uses.
const since = process.env.SINCE ? parseInt(process.env.SINCE, 10) : nHoursAgo(10000);
console.log(`Fetching Nostr event kind ${eventKind} since ${since} (${new Date(since * 1000).toISOString()})`);

// Fetch from each relay individually to track which relays have each event (mirrors index.ts).
const eventMap = new Map<string, { event: any; relays: string[] }>();

for (const relay of relayUrls) {
  try {
    const events = await fetcher.fetchAllEvents(
      [relay],
      { kinds: [eventKind] },
      { since },
      { sort: true }
    );
    console.log(`${events.length} events from ${relay}`);
    for (const ev of events) {
      const existing = eventMap.get(ev.id);
      if (existing) {
        existing.relays.push(relay);
      } else {
        eventMap.set(ev.id, { event: ev, relays: [relay] });
      }
    }
  } catch (e) {
    console.error(`Failed to fetch from ${relay}:`, e);
  }
}

const posts = Array.from(eventMap.values())
  .sort((a, b) => a.event.created_at - b.event.created_at)
  .map(({ event, relays }) => ({ ...event, _relays: relays }));

console.log(posts.length, "unique posts fetched across", relayUrls.length, "relays");

const outFile = process.env.OUT_FILE || __dirname + "/../../../../dist/newPosts.json";
writeFileSync(outFile, JSON.stringify(posts));
console.log("JSON written to", outFile);

// --- NIP-09 deletions (kind 5) ---
// The incremental ride fetch above can't observe deletions: a `since` query only returns
// events that still exist, so a ride deleted since our last run would linger in our DB.
// Deletion events are rare and tiny (a few hundred over the relay's whole life), so we fetch
// ALL of them every run rather than track a separate watermark — that can never miss one, and
// re-applying an already-applied deletion is a no-op on the Python side. Each references the
// deleted event by an `e` tag = its event id (our RideEvent primary key). We keep pubkey so the
// importer can enforce that only the original author may delete their own ride.
const delMap = new Map<string, any>();
for (const relay of relayUrls) {
  try {
    const events = await fetcher.fetchAllEvents([relay], { kinds: [5] }, {}, { sort: true });
    for (const ev of events) delMap.set(ev.id, ev);
  } catch (e) {
    console.error(`Failed to fetch deletions from ${relay}:`, e);
  }
}
const deletions = Array.from(delMap.values()).map((e) => ({
  id: e.id,
  pubkey: e.pubkey,
  created_at: e.created_at,
  tags: e.tags,
}));
console.log(deletions.length, "kind-5 deletion events fetched");

const delFile = process.env.DEL_OUT_FILE || __dirname + "/../../../../dist/newDeletions.json";
writeFileSync(delFile, JSON.stringify(deletions));
console.log("Deletions written to", delFile);

process.exit(0);
