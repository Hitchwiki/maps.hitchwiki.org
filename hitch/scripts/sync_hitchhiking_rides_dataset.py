import json
import logging
import os
from datetime import date

import pandas as pd
from datasets import Dataset
from huggingface_hub import login
from tqdm import tqdm

from hitch.helpers import get_dirs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

dirs = get_dirs()

with open(os.path.join(dirs["dist"], "allPosts.json")) as f:
    all_posts = json.load(f)

entries = []
skipped = 0
for post in tqdm(all_posts, total=len(all_posts)):
    raw_content = post.get("content", "")
    if not isinstance(raw_content, str) or not raw_content.strip():
        skipped += 1
        continue
    try:
        content_json = json.loads(raw_content)
    except json.JSONDecodeError:
        skipped += 1
        continue

    tags_dict = {tag[0]: tag[1] for tag in post.get("tags", []) if len(tag) == 2}

    entry = {
        "submission_time": content_json.get("submission_time"),
        "rating": content_json.get("rating"),
        "comment": content_json.get("comment"),
        "stops": content_json.get("stops"),
        "hitchhikers": content_json.get("hitchhikers"),
        "signals": content_json.get("signals"),
        "occupants": content_json.get("occupants"),
        "ride": content_json.get("ride"),
        "mode_of_transportation": content_json.get("mode_of_transportation"),
        "declined_rides": content_json.get("declined_rides"),
        "license": content_json.get("license"),
        "source": content_json.get("source"),
        "version": content_json.get("version"),
    }
    entries.append(entry)

logger.info(f"Skipped {skipped} posts with empty or invalid content")

# Sort by submission_time descending (newest first)
def _submission_time_key(e):
    # submission_time is an ISO 8601 string (e.g. "2026-01-24T11:25:38");
    # ISO 8601 sorts lexicographically. Nulls sort to the bottom in desc order.
    v = e.get("submission_time")
    if v is None:
        return ""
    return str(v)


entries.sort(key=_submission_time_key, reverse=True)

print(json.dumps(entries[0], indent=2, default=str))

huggingface_df = pd.DataFrame(entries)

HF_TOKEN = os.getenv("HF_TOKEN")
login(token=HF_TOKEN)

today = date.today().isoformat()

hf_dataset = Dataset.from_pandas(huggingface_df)
hf_dataset.push_to_hub(
    "Hitchwiki/hitchhiking-rides-dataset",
    commit_message=f"new version {today}",
)
