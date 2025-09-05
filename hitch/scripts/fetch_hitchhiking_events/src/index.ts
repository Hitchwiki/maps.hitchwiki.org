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
const relayUrls = [
    "wss://relay.trustroots.org", "wss://nos.lol"
];

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

// fetches all text events since 10000 hr ago, as a single array
const allPosts = await fetcher.fetchAllEvents(
    relayUrls,
    /* filter */
    { kinds: [ 36820 ] },
    /* time range filter */
    { since: nHoursAgo(10000) },
    /* fetch options (optional) */
    { sort: true }
)

console.log(allPosts.length, "posts fetched");

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