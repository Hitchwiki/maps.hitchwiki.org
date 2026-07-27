# This module embeds the dataset card (CARD_BODY) verbatim as markdown prose,
# whose paragraph lines legitimately exceed the code line-length limit.
# ruff: noqa: E501
import json
import logging
import os
from datetime import date

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from huggingface_hub import CommitOperationAdd, HfApi, login
from tqdm import tqdm

from hitch.blueprints.utils.hitchhiking_data_standard_pydantic_model import HitchhikingRecord
from hitch.helpers import get_dirs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

REPO_ID = "Hitchwiki/hitchhiking-rides-dataset"

# Emit one dataset column per top-level field of the ride record, taken straight
# from the Hitchhiking Data Standard model that rides are recorded against
# (post_hitchhiking_ride_to_nostr.py). Deriving the list from the model instead
# of hardcoding it means every field a ride can carry — no_ride, images,
# declined_rides, and anything added to the standard later — reaches the dataset
# automatically, rather than being silently dropped.
RECORD_FIELDS = list(HitchhikingRecord.model_fields.keys())

# The HuggingFace dataset card body — everything after the YAML frontmatter.
# The frontmatter itself is NOT stored here: it is regenerated from the actual
# parquet on every upload (see build_card) and pushed together with the parquet
# in one commit, so the card's declared schema can never drift from the data.
# That drift is exactly what broke the dataset viewer once ("Couldn't cast array
# of type string to List({...})") — the card declared nested Arrow structs while
# the parquet stored JSON strings.
CARD_BODY = """# The Hitchhiking Rides Dataset


![image](https://cdn-uploads.huggingface.co/production/uploads/64e489bd94d56c7ee216c104/dxRyB564hr2JKlHfuF0nv.png)

<!-- Provide a quick summary of the dataset. -->

Here the dataset described in [Hitchhiking Rides Dataset: Two decades of crowd-sourced records on stochastic traveling](https://arxiv.org/abs/2506.21946) is published.

[Download the full dataset.](https://huggingface.co/datasets/Hitchwiki/hitchhiking-rides-dataset/blob/main/rides.parquet) To better understand the format that is used read about the [Hitchhiking Data Standard](https://github.com/Hitchwiki/hitchhiking-data-standard/blob/main/STANDARD.md).

This dataset is updated weekly with the latest rides via [https://github.com/Hitchwiki/maps.hitchwiki.org](https://github.com/Hitchwiki/maps.hitchwiki.org) and contains rides from all hitchhiking apps listed [here](https://github.com/Hitchwiki/hitchhiking-data-standard/blob/main/nostr/README.md).

This is the largest dataset of crowd-sourced real-world hitchhiking rides.
Data has been collected on online platforms such as [`maps.hitchwiki.org`](https://maps.hitchwiki.org/), `liftershalte.info`, `hitchwiki.org` and `hitchmap.com` starting in 2005 until today.

If you found something insightful while looking at this dataset, please share it with the [hitchhiking community](https://hitchwiki.org/en/Hitchwiki:Community_Portal).

## Dataset Details

### Dataset Description

<!-- Provide a longer summary of what this dataset is. -->

- **Curated by:** [Till Wenke](https://huggingface.co/tillwenke)
- **License:** Open Data Commons Open Database License (ODbL)

### Credit

- parts of the data stem from `hitchwiki.org` and were published under CC BY-SA 4.0, see their [home page](https://hitchwiki.org/en/Main_Page)
- parts of the data stem from `hitchmap.com` and were published under ODbL, see their [copyright notice](https://hitchmap.com/copyright.html)

### Dataset Sources

<!-- Provide the basic links for the dataset. -->

Sources are given for each entry in the respective dataset column.

Data was fetched from the different sources and published here running [this script](https://github.com/Hitchwiki/hitchhiking-data/blob/main/analysis/publications/2025%20-%20Wenke/publish_dataset.ipynb).

## Uses

<!-- Address questions around how the dataset is intended to be used. -->

To inform hitchhikers to make more data-based decisions on the road.

General research towards hitchhiking as a cultural phenomenon.

### Data Science Uses

- Waiting time predition - regression task e.g. in [Heatchmap: A Gaussian process approach to predict hitchhiking waiting times](https://tillwenke.github.io/2024/04/21/hitchmap-gp.html)

## Dataset Structure

<!-- This section provides a description of the dataset fields, and additional information about the dataset structure such as criteria used to create the splits, relationships between data points, etc. -->

The structure that this dataset follows is described in the [Hitchhiking Data Standard](https://github.com/Hitchwiki/hitchhiking_data_standard).

Every top-level field of a hitchhiking record is included as a column: `version`, `stops`, `rating`, `hitchhikers`, `comment`, `signals`, `occupants`, `mode_of_transportation`, `ride`, `declined_rides`, `no_ride`, `images`, `source`, `license` and `submission_time`.

The nested fields — `stops`, `hitchhikers`, `signals`, `occupants`, `mode_of_transportation`, `ride`, `declined_rides`, `no_ride` and `images` — are stored as **JSON strings** rather than as Arrow structs. Their keys are optional and evolve across rides, so a fixed nested schema would be inconsistent and would drop fields. Parse them back with `json.loads()`, e.g. in pandas: `df["stops"] = df["stops"].map(json.loads)`. A column whose field is absent from every ride currently present will show as all-null.

## Dataset Creation & Bias, Risks, and Limitations

A dataset paper was published on [arXiv](https://arxiv.org/abs/2506.21946) to address the above questions.


## Citation

<!-- If there is a paper or blog post introducing the dataset, the APA and Bibtex information for that should go in this section. -->

**BibTeX:**

```bibtex
@article{wenke2025hitchhiking,
  title={Hitchhiking Rides Dataset: Two decades of crowd-sourced records on stochastic traveling},
  author={Wenke, Till},
  journal={arXiv},
  year={2025},
  url={https://arxiv.org/abs/2506.21946}
}
```

## Dataset Card Authors

- [Till Wenke](https://huggingface.co/tillwenke)
"""


def _hf_dtype(arrow_type: pa.DataType) -> str:
    """Map a pyarrow scalar type to the HuggingFace `dataset_info` dtype string.

    The parquet only ever contains scalar columns — nested fields are serialized
    to JSON strings before writing — so a flat scalar map is sufficient. A `null`
    column (a field that is None on every ride) becomes the literal string
    "null", which PyYAML quotes as 'null' so it round-trips as a string.
    """
    if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
        return "string"
    if pa.types.is_boolean(arrow_type):
        return "bool"
    if pa.types.is_floating(arrow_type):
        return "float64"
    if pa.types.is_integer(arrow_type):
        return "int64"
    if pa.types.is_null(arrow_type):
        return "null"
    # Fail loudly rather than silently emit a schema the viewer will reject.
    raise ValueError(f"Unmapped Arrow type for HF card: {arrow_type}")


def _size_category(num_rows: int) -> str:
    """HF `size_categories` bucket for a row count, so the tag self-maintains."""
    buckets = [
        (1_000, "n<1K"),
        (10_000, "1K<n<10K"),
        (100_000, "10K<n<100K"),
        (1_000_000, "100K<n<1M"),
        (10_000_000, "1M<n<10M"),
        (100_000_000, "10M<n<100M"),
    ]
    for upper, label in buckets:
        if num_rows < upper:
            return label
    return "100M<n<1B"


def build_card(parquet_path: str, df: pd.DataFrame) -> str:
    """Render README.md: frontmatter derived from the parquet + the static body.

    Generating the frontmatter from the file we are about to upload is the whole
    point — it guarantees `dataset_info.features` matches the uploaded schema, so
    the dataset viewer never fails to cast the parquet against a stale card.
    """
    schema = pq.read_schema(parquet_path)
    features = [{"name": name, "dtype": _hf_dtype(typ)} for name, typ in zip(schema.names, schema.types)]

    num_rows = len(df)
    # num_bytes/dataset_size are the in-memory Arrow size (informational); the
    # viewer recomputes exact counts. download_size is the parquet file on disk.
    dataset_size = int(df.memory_usage(deep=True).sum())
    download_size = os.path.getsize(parquet_path)

    frontmatter = {
        "language": ["en", "fr", "de", "nl"],
        "license": "odbl",
        "size_categories": [_size_category(num_rows)],
        "task_categories": ["time-series-forecasting", "tabular-regression"],
        "pretty_name": "Largest Dataset of Hitchhiking Rides",
        "tags": ["mobility", "hitchhiking", "transport"],
        "dataset_info": {
            "features": features,
            "splits": [{"name": "train", "num_bytes": dataset_size, "num_examples": num_rows}],
            "download_size": download_size,
            "dataset_size": dataset_size,
        },
        "configs": [
            {
                "config_name": "default",
                "data_files": [{"split": "train", "path": "rides.parquet"}],
            }
        ],
    }
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"---\n{fm_yaml}---\n\n{CARD_BODY}"


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

    entry = {field: content_json.get(field) for field in RECORD_FIELDS}

    # Nested objects/arrays (mode_of_transportation, stops, hitchhikers, …) have
    # optional, evolving keys across rides. Letting pandas/pyarrow auto-infer an
    # Arrow struct for them produces inconsistent schemas across Parquet row
    # groups, which makes the HuggingFace viewer fail with
    # "Couldn't cast array of type struct<…> to {…}". Serialize them to JSON
    # strings so each column is a stable `string` type regardless of shape;
    # consumers json.loads() them back. sort_keys keeps output deterministic.
    for key, value in entry.items():
        if isinstance(value, (dict, list)):
            entry[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)

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
parquet_path = os.path.join(dirs["dist"], "rides.parquet")
huggingface_df.to_parquet(parquet_path, index=False)

# Regenerate the dataset card from the parquet we just wrote and upload both in a
# single commit, so the declared schema and the data can never disagree.
readme = build_card(parquet_path, huggingface_df)

HfApi().create_commit(
    repo_id=REPO_ID,
    repo_type="dataset",
    operations=[
        CommitOperationAdd(path_in_repo="rides.parquet", path_or_fileobj=parquet_path),
        CommitOperationAdd(path_in_repo="README.md", path_or_fileobj=readme.encode("utf-8")),
    ],
    commit_message=f"new version {today}",
)
