import WebSocket from "ws";
import { NostrFetcher } from "nostr-fetch";
import { writeFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname } from "path";

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

// // fetches all text events since 24 hr ago in streaming manner
// const postIter = fetcher.allEventsIterator(
//     relayUrls, 
//     /* filter (kinds, authors, ids, tags) */
//     { kinds: [ 30399] },
//     /* time range filter (since, until) */
//     { since: nHoursAgo(10000) },
//     /* fetch options (optional) */
//     { skipFilterMatching: true }
// );
// for await (const ev of postIter) {
//     console.log(ev.content);
// }

if (!process.env.NOSTR_EVENT_KIND) {
    console.error("NOSTR_EVENT_KIND env var is not set");
    process.exit(1);
}
const eventKind = parseInt(process.env.NOSTR_EVENT_KIND, 10);
console.log("Fetching Nostr event kind (this can take a while):", eventKind);

// Fetch from each relay individually to track which relays have each event
const eventMap = new Map<string, { event: any; relays: string[] }>();

for (const relay of relayUrls) {
    try {
        const events = await fetcher.fetchAllEvents(
            [relay],
            { kinds: [eventKind] },
            { since: nHoursAgo(10000) },
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

// Build final array sorted by created_at, with relay info attached
const allPosts = Array.from(eventMap.values())
    .sort((a, b) => a.event.created_at - b.event.created_at)
    .map(({ event, relays }) => ({ ...event, _relays: relays }));

console.log(allPosts.length, "unique posts fetched across", relayUrls.length, "relays");

// Write JSON to file
const this_file_dir = __dirname;
const jsonFile = this_file_dir + "/../../../../dist/allPosts.json";
writeFileSync(jsonFile, JSON.stringify(allPosts, null, 2));
console.log("JSON written to", jsonFile);

// Prepare CSV header and rows
const header = ["id", "pubkey", "created_at", "content", "tags"];
const rows = allPosts.map(post => [
    post.id,
    post.pubkey,
    post.created_at,
    JSON.stringify(post.content),
    JSON.stringify(post.tags)
]);

// Combine header and rows into CSV string
const csv = [header, ...rows]
    .map(row => row.map(field => `"${String(field).replace(/"/g, '""')}"`).join(","))
    .join("\n");

// Write CSV to file
const file = this_file_dir + "/../../../../dist/allPosts.csv"
writeFileSync(file, csv);
console.log("CSV written to", file);

process.exit(0);