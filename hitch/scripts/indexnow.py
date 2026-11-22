"""Tell Bing-family search engines (IndexNow) which sitemap URLs are new.

Runs after cities.py (which writes dist/sitemap.xml). The first run submits
every URL; later runs submit only URLs not in dist/indexnow_seen.txt. The key
file is served from the dist root by the catch-all route, as IndexNow requires.
The key is public by design (it only proves we control the host).
"""
import json
import os
import re
import urllib.request

from hitch.scripts.cities import SITE_URL, dist_dir

KEY = "98ba641c7ed74378ecbcdf219383b5c5"
ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10000
MAX_NEW_PER_RUN = 50000


def new_urls(sitemap_text, seen):
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap_text)
    return [u for u in urls if u not in seen]


def submit(batch):
    body = json.dumps(
        {
            "host": SITE_URL.split("//")[1],
            "key": KEY,
            "keyLocation": f"{SITE_URL}/{KEY}.txt",
            "urlList": batch,
        }
    ).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body, headers={"Content-Type": "application/json; charset=utf-8"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status


def main():
    with open(os.path.join(dist_dir, f"{KEY}.txt"), "w") as f:
        f.write(KEY)
    sm = os.path.join(dist_dir, "sitemap.xml")
    seen_path = os.path.join(dist_dir, "indexnow_seen.txt")
    if not os.path.exists(sm):
        print("no sitemap.xml, nothing to do")
        return
    seen = set()
    if os.path.exists(seen_path):
        with open(seen_path) as f:
            seen = {l.strip() for l in f if l.strip()}
    with open(sm, encoding="utf-8") as f:
        todo = new_urls(f.read(), seen)[:MAX_NEW_PER_RUN]
    print(f"{len(todo)} new urls")
    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        try:
            status = submit(batch)
        except Exception as e:  # keep seen-state untouched so the next run retries
            print(f"batch {i} failed: {e}")
            break
        print(f"batch {i}: HTTP {status}")
        with open(seen_path, "a") as f:
            f.write("\n".join(batch) + "\n")


main()
