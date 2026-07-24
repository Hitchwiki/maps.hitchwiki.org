"""Choice lists used by the driver-info form section: reasons to pick up,
country names (with ISO 3166-1 alpha-2 codes), and language names (with
ISO 639-3 codes). Built once at import time."""

import pycountry

# Short, user-facing descriptions for each ReasonToPickUpEnum value. Keys must
# stay in sync with hitchhiking_data_standard_pydantic_model.ReasonToPickUpEnum.
REASON_TO_PICK_UP_CHOICES = [
    ("is_hitchhiker", "Is a hitchhiker themselves"),
    ("was_hitchhiker", "Used to hitchhike in the past"),
    ("social_exchange", "Wanted social interaction / conversation"),
    ("cultural_exchange", "Interested in cultural exchange"),
    ("environmental", "Environmental reasons (reduce empty seats)"),
    ("wanted_driver", "Wanted company while driving"),
    ("curiosity", "Curiosity about hitchhikers"),
    ("hospitality_norm", "Cultural or personal values around helping strangers"),
    ("elevated_mood", "Was in an unusually good mood / feeling generous"),
    ("nonthreatening_appearance", "Hitchhiker looked non-threatening"),
    ("sympathy", "Felt pity or concern (weather, appearance, …)"),
    ("safety_concern", "Believed the hitchhiker might be in danger"),
    ("opposed", "Opposed the pick-up but was overruled by another occupant"),
]
ALLOWED_REASONS_TO_PICK_UP = [code for code, _ in REASON_TO_PICK_UP_CHOICES]
REASON_DESCRIPTION_BY_CODE = {code: desc for code, desc in REASON_TO_PICK_UP_CHOICES}

# (alpha_2, name) — sorted alphabetically by name.
COUNTRY_CHOICES = sorted(
    [(c.alpha_2, c.name) for c in pycountry.countries],
    key=lambda x: x[1].lower(),
)
COUNTRY_CODE_BY_NAME = {name.lower(): code for code, name in COUNTRY_CHOICES}
COUNTRY_NAME_BY_CODE = {code: name for code, name in COUNTRY_CHOICES}
COUNTRY_CODES = {code for code, _ in COUNTRY_CHOICES}

# Curated list of widely spoken languages (ISO 639-3). The full ~7000-entry
# pycountry list is too noisy for a driver-info picker; pick the ones most
# users will need.
MAJOR_LANGUAGE_CODES = {
    "eng",
    "spa",
    "fra",
    "deu",
    "ita",
    "por",
    "rus",
    "zho",
    "jpn",
    "kor",
    "ara",
    "hin",
    "ben",
    "urd",
    "fas",
    "tur",
    "nld",
    "pol",
    "ukr",
    "ron",
    "ces",
    "ell",
    "swe",
    "nor",
    "dan",
    "fin",
    "hun",
    "bul",
    "srp",
    "hrv",
    "slk",
    "slv",
    "lit",
    "lav",
    "est",
    "heb",
    "tha",
    "vie",
    "ind",
    "msa",
    "tgl",
    "swa",
    "afr",
    "cat",
    "eus",
    "isl",
    "sqi",
    "mkd",
    "bos",
    "kat",
    "hye",
    "aze",
    "kaz",
    "uzb",
    "mon",
    "nep",
    "sin",
    "tam",
    "tel",
    "mal",
    "kan",
    "mar",
    "guj",
    "pan",
    "ori",
    "asm",
    "amh",
    "som",
    "yor",
    "ibo",
    "hau",
    "zul",
    "xho",
    "mlt",
    "gle",
    "cym",
    "epo",
    "lat",
}
# (alpha_3, name) — ISO 639-3 since the data standard example uses 3-letter codes.
# Skip languages without a name; sort alphabetically by name. Filter to majors.
LANGUAGE_CHOICES = sorted(
    [
        (getattr(lang, "alpha_3", None), lang.name)
        for lang in pycountry.languages
        if getattr(lang, "alpha_3", None) in MAJOR_LANGUAGE_CODES and getattr(lang, "name", None)
    ],
    key=lambda x: x[1].lower(),
)
LANGUAGE_CODE_BY_NAME = {name.lower(): code for code, name in LANGUAGE_CHOICES}
LANGUAGE_NAME_BY_CODE = {code: name for code, name in LANGUAGE_CHOICES}
LANGUAGE_CODES = {code for code, _ in LANGUAGE_CHOICES}

GENDER_CHOICES = [
    ("male", "Male"),
    ("female", "Female"),
    ("non_binary", "Non-binary"),
    ("prefer_not_to_say", "Prefer not to say"),
]
ALLOWED_GENDERS = [code for code, _ in GENDER_CHOICES]
