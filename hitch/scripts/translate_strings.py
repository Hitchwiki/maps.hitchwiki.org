"""Translate the UI/SEO strings wrapped in t() (hitch/translations/__init__.py)
into another language via the OpenAI API, writing hitch/translations/<lang>.json.

This does NOT touch database content (ride comments, place names, usernames) --
see CLAUDE.md. It only translates the fixed English strings this codebase wraps
in t(...), which are collected here as SOURCE_STRINGS. When you wrap a new
string in t(), add it to SOURCE_STRINGS and rerun this script; existing
translations already in the target file are kept as-is (not re-sent) unless
--force is passed, so a manual correction to one string survives a rerun that
adds others.

Standalone script (plain python3, not `flask generate`): only needs `requests`
and OPENAI_API_KEY from .env, no app context, no DB.

Usage:
    python3 -m hitch.scripts.translate_strings de
    python3 -m hitch.scripts.translate_strings de --force
"""

import argparse
import json
import os
import sys

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
_TRANSLATIONS_DIR = os.path.join(os.path.dirname(_HERE), "translations")

LANGUAGE_NAMES = {
    "de": "German",
    "fr": "French",
    "pt": "Portuguese",
    "ru": "Russian",
    "pl": "Polish",
    "es": "Spanish",
    "it": "Italian",
    "hr": "Croatian",
    "cs": "Czech",
    "et": "Estonian",
    "hu": "Hungarian",
    "zh": "Chinese (Simplified)",
    "ja": "Japanese",
    "ro": "Romanian",
    "bg": "Bulgarian",
    "da": "Danish",
    "el": "Greek",
    "fi": "Finnish",
    "ka": "Georgian",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mn": "Mongolian",
    "nl": "Dutch",
    "no": "Norwegian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sr": "Serbian",
    "sv": "Swedish",
    "tr": "Turkish",
    "uk": "Ukrainian",
}

# Every string passed to t(...) in the codebase (templates + main.py). Keep this
# in sync by hand -- there's no extraction tool, and duplicating the audit here
# is deliberate: it's the same list of user-facing strings by design.
SOURCE_STRINGS = [
    # Per-city SEO pages (city_template.html, rendered per language by cities.py).
    # These carry the search query itself -- "Trampen in Berlin" only matches the
    # German page because "Hitchhiking in {place}" is translated here -- so keep
    # the hitchhiking verb natural in each language rather than literal.
    "{city} - Hitchhiking - Hitchwiki Map",
    "Hitchhiking spots, community ratings and recent rides for {place}. See where drivers pick up and how long the wait is.",
    "Hitchhiking in {place} – Hitchwiki Map",
    "Community hitchhiking spots, ratings and recent rides for {place} on the Hitchwiki Map.",
    "All cities",
    "Hitchhiking guides to cities worldwide",
    "Browse hitchhiking guides by city: spots, community ratings, waiting times and recent rides.",
    "{city} on Hitchwiki",
    "Hitchhiking from {city}",
    "Hitchhiking to {city}",
    "{city} on Hitchhiking Map",
    "View all spots mentioning {city}",
    "Recent reviews mentioning {city}",
    "Hitchhiking Map",
    "Discover hitchhiking spots worldwide on an interactive map. See community ratings, waiting times, and trip data. Share your "
    "own rides.",
    "Hitchhiking Map – Find & Share Hitchhiking Spots on a Map",
    "Link copied!",
    "Copy this link:",
    "Interactive hitchhiking map: find spots from Hitchwiki, Hitchmap, and the community. Ratings, heatmaps, route planning, "
    "share rides worldwide.",
    "Hitchhiking Map – Find & Share Hitchhiking Spots Globally",
    "ride",
    "rides",
    "Rated {rating:.1f}/5 from {count} {plural}.",
    "Typical wait {wait} min.",
    "Rides average {distance} km.",
    "See the spot on the hitchhiking map.",
    "Hitchhiking ride from {place}",
    "A hitchhiking ride",
    "{km} km",
    "Rated {rating}/5.",
    "Waited {wait} min.",
    "A hitchhiking ride logged on Hitchwiki Maps.",
    "{name} — hitchhiking spot",
    "Hitchhiking spot at {lat:.5f}, {lon:.5f}",
    "Median wait {wait} min across {n} logged rides",
    "typical ride {km} km",
    "Hitchhiking in {name}",
    "Hitchhiking in {name}: {facts}. Read what hitchhiking there is like and see waiting-time statistics.",
    # --- map.js UI strings (client-side tr(), see hitch/static/map.js) ---
    "Add a hitch spot here?",
    "Add a ride to this spot",
    "Add ride",
    "Add spot",
    "Add your ride",
    "A marker cannot be a duplicate of itself.",
    "Anonymous",
    "Are you sure you want to report a duplicate?",
    "Cancel",
    "Check out Hitchwiki Maps — the hitchhiking map",
    "Click on the map or drag the marker to choose your destination location",
    "Click on the map or drag the marker to choose your pickup location",
    "Confirm Location",
    "Copied — paste it anywhere!",
    "Copy this:",
    "Copy this invite link:",
    "Could not get your location:",
    "Country hitchability",
    "Drag the pin to fine-tune, add a short note (optional), then propose.",
    "Drag the pin to fine-tune, then confirm.",
    "Event",
    "Filters",
    "Heatmap",
    "Heatmap data is not available",
    "Hitchhiking event",
    "Hitchhiking in {name} – Hitchwiki Maps",
    "Hitchhiking spot on Hitchwiki Maps",
    "Join me on Hitchwiki Maps",
    "Loading from Hitchwiki…",
    "No comments/ride info.",
    "No description available.",
    "No Hitchwiki summary could be loaded for {name}.",
    "Normal",
    "No summary text available for {name}.",
    "Propose a hitch spot",
    "Propose spot",
    "Read the full {title} article on Hitchwiki",
    "Read this event on Hitchwiki",
    "Rides",
    "Route",
    "Route planning",
    "Search",
    "Select Destination Location",
    "Selection",
    "Select Pickup Location",
    "Share Hitchwiki Maps",
    "Show my location",
    "Sorry, could not save your proposed spot. Please try again.",
    "Spots",
    "Text from {link}, licensed {license}.",
    "This matches an existing hitch spot. Confirm to add your ride here.",
    "Waiting-time heatmap",
    "{wait} min wait",
    "What can I see here?",
    "Why is this a good spot? (optional)",
    "Your account",
    "Your rides were grouped into a trip:",
    "your trip",
    # --- map.html static UI strings (server-side t(), see hitch/templates/map.html) ---
    "1 star",
    "2 stars",
    "3 stars",
    "4 stars",
    "5 stars",
    "Activities",
    "Add Hitchhiking Map to your home screen",
    "Any",
    "As GPX (to import into offline maps)",
    "asking",
    "Attribution",
    "Back to map",
    "boat",
    "bus",
    "By",
    "camper",
    "car",
    "Car pooling",
    "Charts & graphs",
    "Clear",
    "Click on the duplicated marker.",
    "Close",
    "Close filters",
    "Contact",
    "Contribute",
    "Coordinates:",
    "Credits",
    "Data by {a} ({a_license}), {b} ({b_license}), {c} ({c_license}) and {d}.",
    "Data certainty:",
    "Dismiss",
    "Download rides",
    "Do you want to help with anything on this map or help the hitchhiking community in another way?",
    "Drawing your ride…",
    "Failed!",
    "ferry",
    "Filter by user",
    "For deeper analysis you can grab the full {dataset_link} — it includes hitchhiker and driver demographics and many more "
    "details about each ride than are shown here. Share what you find with the {community_link}.",
    "Full dataset",
    "Gas stations",
    "Go to on Google Maps",
    "Go to on OpenStreetMap",
    "here",
    "Histogram of ride distance",
    "Histogram of waiting time",
    "Hitch here",
    "Hitchhiker on a roadside in Luxembourg, 1977",
    "hitchhiking community",
    "Hitchhiking insights – Hitchwiki Maps",
    "Hitchhiking in this country – Hitchwiki Maps",
    "Hitchwiki articles",
    "Hitchwiki Map software is licensed under {agpl}. The Hitchwiki Maps database is licensed under the {odbl}, the license used "
    "by OpenStreetMap. Individual reviews you write — your comment and username — are licensed under {ccbysa}. See "
    "{copyright_link} for details.",
    "horse-cart",
    "If you have ideas for how to push this further, join the conversation in our {link}.",
    "Insights",
    "Install",
    "invited",
    "I want to stay anonymous",
    "Join our {link}",
    "Just your own rides",
    "kilometres",
    "Last 24h",
    "Leaderboard",
    "Less certain",
    "License",
    "Link",
    "Loading",
    "Loading spots",
    "Log a past ride",
    "Log in to track your rides",
    "many hitchhikers",
    "Maps by {a} and {b}",
    "Menu",
    "miles",
    "Min average rating (0–5)",
    "Min ride distance ({unit})",
    "Min rides per spot",
    "minutes",
    "More certain",
    "motorbike",
    "No distance data for these rides.",
    "No distance data for this country.",
    "Not now",
    "No waiting-time data for these rides.",
    "No waiting-time data for this country.",
    "{n} unread notifications",
    "Official spots",
    "Own work",
    "plane",
    "prearranged",
    "Privacy",
    "Races",
    "Rate this spot",
    "Reach out to {a} or {b}",
    "Report bugs",
    "reviews {license}",
    "Ride date from",
    "Ride date to",
    "Ride distance",
    "Ride saved!",
    "Ride saved — thank you! We'd love to hear your thoughts: {link}.",
    "rides dataset on Hugging Face",
    "Route Planning",
    "Route planning is under development.",
    "scooter",
    "Search comments",
    "See full attribution {link}.",
    "See on Google Street View",
    "See our {link} for what data we collect and how ride data is published.",
    "Send invite link",
    "Send them the map of your ride — it's how most hitchhikers find us.",
    "Share",
    "share feedback",
    "Share my ride",
    "Share these insights",
    "Share this map view",
    "Share this spot",
    "Share view",
    "share your thoughts",
    "Show only spots at a gas station",
    "Show your friends",
    "sign",
    "Signal method",
    "Skip",
    "Spot quality",
    "Stats for the rides currently selected by your filters.",
    "Success!",
    "Summary statistics",
    "Tap the <strong>Share</strong> button, then <strong>Add to Home Screen</strong>.",
    "taxi",
    "Thanks for your contribution!",
    "thumb",
    "Toggle legend",
    "tractor",
    "train",
    "truck",
    "Try to submit the review again.",
    "Use it like a normal app right from your home screen.",
    "van",
    "Vehicle",
    "Visit Hitchwiki.org",
    "Waiting time",
    "Waiting time (minutes)",
    "Want to remember your trips? With an account your rides stay yours — you can find them again, edit them, and see everywhere "
    "you've been.",
    "waving",
    "We don't understand hitchhikers' preferences around anonymity well yet. If you tell us what matters to you, we can build "
    "for it — {link}.",
    "We'll copy an invite link you can send them however you like.",
    "Yes, let's sign up",
    "You don't have to give up your privacy: pick a username and an email address that can't be traced back to you personally. "
    "We never show your email, and nothing forces the name to be your real one.",
    "You have unread notifications",
    "You hitchhiked with someone anonymous. Invite them to sign up and the ride shows up on their map too — and you can log "
    "future rides together.",
    "Your duplicate report will be subject to a manual review, or it will be merged automatically within 10 minutes.",
    "You're registered and logged in.",
    "Your hitchhiking ride as a shareable image",
    # --- spot summary (map.js), inride.js start bar, leaderboard.html, races.html ---
    "Rating: {rating}/5",
    "Waiting time: {wait}",
    "Ride distance: {distance}",
    "{n} min",
    "Official hitchhiking spot",
    "Car pooling spot",
    "Gas station",
    "Read about this spot on Hitchwiki",
    "Read about this area on Hitchwiki",
    "Start Hitchhiking",
    "Hitchhiking leaderboard – Hitchwiki Maps",
    "Most rides",
    "Longest ride",
    "Longest 24h",
    "All users ranked by number of rides logged",
    "Want to show up here? {link} and start logging your rides.",
    "Log in",
    "User",
    "The 10 longest rides by start-to-destination distance",
    "No rides with a destination yet.",
    "Most distance covered within a single 24-hour window — only named hitchhikers and rides with both a departure and arrival "
    "time count. Each entry lists every ride in that window.",
    "{n} ride",
    "{n} rides",
    "No qualifying rides yet.",
    "Hitchhiking races – Hitchwiki Maps",
    "starts in {n} day",
    "starts in {n} days",
    "running",
    "Not started yet — the board opens on {date}.",
    "partly estimated",
    "At least one ride logged no arrival time; it was estimated from the distance at 75 km/h.",
    "Nobody has logged this route yet — be the first.",
    "No race is running right now, and none starts within the next month.",
    # --- account.js (on-map account modal) + achievement ladders (user.py) ---
    "Couldn't load your account. Check your connection.",
    "Distance",
    "Every ride is fully logged. Nice.",
    "Finish setting up your profile →",
    "Fully logged — nice one!",
    "gave up",
    "{h} h {m} m",
    "Loading…",
    "Log in to track your hitchhiking, keep your ride history, and see your stats.",
    "Log in with Hitchwiki",
    "{m} m",
    "{m} min",
    "Moving",
    "No destination recorded — add it",
    "No destination recorded for this ride",
    "No destination recorded for this ride. Add it.",
    "Partners",
    "{pct}% complete",
    "{pct}% complete — add driver and vehicle details",
    "{pct}% of driver and vehicle details recorded",
    "Ride fully logged",
    "Ride {pct}% complete. Add driver and vehicle details.",
    "Show all {n}",
    "Showing {shown} of {total} rides",
    "Unknown ride",
    "View full profile →",
    "View ride details",
    "Waiting",
    "Waiting at the roadside",
    "Your rides, saved",
    "{n} ride could use more detail",
    "{n} rides could use more detail",
    "{n} award earned",
    "{n} awards earned",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
    "Thumb Warmer",
    "Logged 5 rides — the thumb is officially calibrated.",
    "Roadside Regular",
    "100 rides. Drivers start to recognise you.",
    "Legend of the Hard Shoulder",
    "1000 rides. Songs will be written.",
    "Out of Town",
    "100 km hitched — further than the bus goes.",
    "Continental Drifter",
    "1000 km hitched, entirely on other people's fuel.",
    "Quarter Way Round the World",
    "10 000 km — a quarter of the equator, thumb first.",
    "Three's Company",
    "Hitchhiked with 3 different partners.",
    "Thumb Collective",
    "Hitchhiked with 10 different partners.",
    # --- inride.js (the in-ride hitching tracker dock/dialogs/sheets) ---
    "Add anonymous",
    "Add co-hitchhiker username…",
    "Add details",
    "Add details · {pct}%",
    "Add driver & vehicle details?",
    "{age} ago",
    "Anonymous ♀",
    "Anonymous ♂",
    "Anybody hitching with you",
    "Anything worth noting about this spot…",
    "Approx. driver age",
    "A rough guess is fine.",
    "Arrival must be after the pickup time.",
    "Arrived",
    "Asking",
    "Cancel journey",
    "Cancel this journey? Your wait won't be saved.",
    "Car",
    "Comment (optional)",
    "Confirm",
    "Confirm Drop-off",
    "Continue anonymously",
    "Couldn't get your location — drag the pin instead.",
    "Couldn't save: {error}",
    "Delete",
    "Delete this ride? It won't be uploaded.",
    "Details complete",
    "Details / edit",
    "Discard",
    "Drag the pin or tap the map, then confirm.",
    "Driver",
    "Driver gender",
    "Driver's country",
    "Driver & vehicle details",
    "e.g. no traffic, bad pull-in spot…",
    "End Hitch",
    "From {from}",
    "Gave up",
    "Gave-up spot",
    "Give Up",
    "Got a Ride!",
    "How did you signal?",
    "How was the spot?",
    "In a ride · {time}",
    "Languages spoken",
    "License plate code (e.g. D, F, GB)…",
    "Locating…",
    "Log in to keep your ride history, or just continue anonymously.",
    "Make (optional)",
    "Model (optional)",
    "Next ride from here",
    "No",
    "{n} to upload",
    "Number-plate country",
    "Offline",
    "One quick question before we save this ride.",
    "Pause",
    "Paused · waited {time}",
    "Picked up",
    "Please choose a rating.",
    "Rejected",
    "Remove",
    "Remove {name}",
    "Resume",
    "Retry now",
    "Ride",
    "Ride details",
    "Ride On!",
    "Ride saved — dropped off here. Waiting for another ride?",
    "Rides to upload",
    "Save",
    "Save changes",
    "Save details",
    "Search country…",
    "Sign",
    "Start hitching",
    "Start Hitching",
    "This ride is {pct}% complete. Help your fellow hitchers?",
    "This spot",
    "Thumb",
    "Track a ride from here now — or log a ride you already got.",
    "Track your rides?",
    "Truck",
    "Type a language…",
    "Van",
    "Waiting for connection…",
    "Waiting · {time}",
    "Wait (minutes)",
    "Wait somewhere else",
    "Welcome back!",
    "What's next?",
    "Where are you waiting?",
    "Where did you get out?",
    "Who picked you up?",
    "Why did they pick you up?",
    "Would you accept this ride again?",
    "Yes",
    "You have a hitching journey from more than 24 hours ago. Continue where you left off?",
    "You're hitching as @{username}",
    "You waited here without a ride — rate the spot so others know.",
    # --- routing.js (the route planner UI) ---
    "1 logged ride",
    "about {time}",
    "Change car here — tap for rides",
    "Choose destination, or click on the map",
    "Choose starting point, or click on the map",
    "Close route planning",
    "Details",
    "fastest",
    "Finding routes…",
    "Get off here — tap for rides",
    "Hide details",
    "Hitchhiking route – Hitchwiki Maps",
    "Includes a leg only one hitchhiker has logged",
    "Loading route data…",
    "Location",
    "{n} min wait",
    "{n} spot on the way",
    "{n} spots on the way",
    "No repeatable route — checking one-off rides…",
    "No route found: both your start and destination are in areas where too few people have hitchhiked. Try points nearer to "
    "major roads or cities.",
    "No route found: your destination is in an area where too few people have hitchhiked. Move it closer to a major road or "
    "city, or search just the earlier part of your trip.",
    "No route found: your starting point is in an area where too few people have hitchhiked. Move it closer to a major road or "
    "city, or search just the later part of your trip.",
    "No route found: we couldn't connect these two points, even using rides only one person has logged. Try searching for part "
    "of the route — e.g. between larger cities along the way.",
    "No route found: we couldn't connect these two points with repeatable rides. Try searching for part of the route — e.g. "
    "between larger cities along the way.",
    "Routes",
    "Start hitchhiking here — tap for rides",
    "{time} walk",
    "+ {time} walk to start &amp; end",
    "+ transit to start &amp; end",
    "Wait",
    "Walk",
    # --- security/*.html + insights.html (profile pages) + forms.py labels ---
    "Accept",
    "Achievements",
    "A few words about this trip…",
    "{age} years",
    "Back to profile",
    "by {link}",
    "Chat",
    "co-hitchhiker",
    "Comment:",
    "Contributions this month",
    "Contributors",
    "create one on hitchwiki.org",
    "Create trip",
    "Delete my account",
    "Delete this trip? This cannot be undone.",
    "Delete trip",
    "Description",
    # --- private per-user export (security/downloads.html, linked from the account page) ---
    "Back to your account",
    "Download GPX",
    "Download JSON",
    "Download your rides",
    "Download your rides (GPX)",
    "Everything logged under the name {name}: {n} rides.",
    "Every detail of a ride — rating, waiting time, driver, vehicle, signals, your comment — "
    "is written into the file, both as readable text and as structured data.",
    "full public dataset",
    "GPX (for offline maps)",
    "Import into OsmAnd, Organic Maps, Garmin or anything else that reads GPX.",
    "JSON (the raw records)",
    "Log a ride",
    "Looking for everyone's rides instead? The {link} covers the whole map.",
    "{n} rides that recorded where you got to become routes; the other {m} become single waypoints.",
    "The signed Nostr events exactly as they were published, signatures included. "
    "Nothing is left out, and anyone can verify them.",
    "This page is only visible to you.",
    "You have not logged any rides yet.",
    "Edit",
    "Edit Account",
    "Edit Ride",
    "Edit trip",
    "Edit your personal data",
    "e.g. Summer 2026 Balkans",
    "Failed action",
    "Follow",
    "Following",
    "From {origin}",
    "Hitchhiker",
    "Hitchhiking since {date}",
    "{link} to see all contributions",
    "log in",
    "Login",
    "Login with Hitchwiki",
    "Log in with your Hitchwiki account. If you don't have one yet, you can {link}. A new account on the Hitchhiking Map will be "
    "created for you automatically on first login.",
    "Logout",
    "Longest wait",
    "Messages",
    "{min} min",
    "min waiting",
    "My rides",
    "My rides for {name}",
    "{name} – Insights",
    "Name: {name}",
    "{name} on Hitchwiki Maps",
    "No date",
    "No rides found.",
    "No rides yet.",
    "Notifications",
    "No trips yet. Create one to group your rides into a journey.",
    "On Hitchwiki:",
    "Only affects how distances are shown to you. Not shown on your public profile.",
    "On Trustroots:",
    "optional",
    "Overall contributions",
    "partners",
    "Pay attention to our {link}",
    "Pickup Location",
    "Please {link} to view your rides.",
    "privacy policy",
    "Privacy Policy.",
    "Public Profile",
    "Reject",
    "Save trip",
    "See all insights and achievements →",
    "See my full insights on the map",
    "See my spots on the map",
    "See their full insights on the map",
    "See their spots on the map",
    "Select the rides that belong to this trip",
    "Signed in",
    "Signed in. You can close this window.",
    "Successful action",
    "The Hitchhiking Map is made for all hitchhikers to learn from each others experiences. Thus all your rides and personal "
    "information (except your email address) will be publicly available. Only share as much as you are comfortable with. Keep in "
    "mind that hitchhikers are a vulnerable group and may face risks while traveling. Read our {link} for more "
    "information on how we handle your data and what you can do to protect yourself.",
    "This personal information will be shown publicly.",
    "This trip has no rides yet.",
    "Trip name",
    "Trips",
    "{unit} travelled",
    "View on map ↗",
    "View spot on map",
    "You have no rides to add yet.",
    "Your Rides",
    "Your Trips",
    "Where are you from?",
    "Which city are you from?",
    "Hitchwiki Username",
    "Trustroots Username",
    "Receive notifications and updates via email",
    "Email me about other hitchhikers who were close by",
    "Let other hitchhikers message me (adds a Chat button to my profile)",
    "Email me when I receive a new message",
    "Distance units",
    "Submit",
    "Year of Birth",
    "Hitchhiking Since",
    "None",
    "Metric (km)",
    "Imperial (miles)",
    "Female",
    "Male",
    "Non-Binary",
    "Prefer not to say",
]


def _load_existing(lang):
    path = os.path.join(_TRANSLATIONS_DIR, f"{lang}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _translate_batch(strings, lang_name, api_key):
    """One OpenAI call for the whole batch, asking for a JSON object mapping
    each source string to its translation. Batching keeps this a single
    request instead of one round-trip per string, and giving the model the
    full list as context helps it keep terminology (e.g. "wait", "rating")
    consistent across strings.
    """
    system_prompt = (
        f"You are a professional UI/UX translator localizing a hitchhiking map website "
        f"into {lang_name}. Translate each string in the JSON array to natural, "
        f"concise {lang_name} appropriate for website UI text and SEO meta descriptions. "
        "Rules:\n"
        "- Preserve every {placeholder} (e.g. {name}, {rating:.1f}) EXACTLY as written, "
        "including any format spec after the colon -- do not translate or reorder them, "
        "but you may move where the placeholder sits in the sentence to fit natural "
        f"{lang_name} grammar.\n"
        "- Preserve capitalization style of proper nouns (Hitchhiking Map, Hitchwiki, "
        "Hitchmap) -- keep those brand names untranslated.\n"
        "- Keep punctuation and sentence-ending periods where the source has them.\n"
        "- Use the informal register throughout (e.g. German 'du', not the formal 'Sie') "
        "-- this is a volunteer hitchhiking community site, not a corporate/government one, "
        "and every string must agree with every other string's register.\n"
        "- Return ONLY a JSON object: {\"<source string>\": \"<translation>\", ...} "
        "with exactly one entry per input string, no other keys, no commentary."
    )
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "gpt-4o",
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(strings, ensure_ascii=False)},
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lang", choices=sorted(LANGUAGE_NAMES), help="Target language code")
    parser.add_argument("--force", action="store_true", help="Re-translate strings that already have an entry")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Scripts run standalone (not through `flask generate`) don't get .env auto-loaded
        # by Flask, so load it ourselves the same way python-dotenv would.
        env_path = os.path.join(os.path.dirname(os.path.dirname(_HERE)), ".env")
        if os.path.isfile(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        os.environ.setdefault(k.strip(), v.strip())
        api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set (checked environment and .env)", file=sys.stderr)
        sys.exit(1)

    existing = _load_existing(args.lang)
    todo = SOURCE_STRINGS if args.force else [s for s in SOURCE_STRINGS if s not in existing]
    if not todo:
        print(f"Nothing to translate for {args.lang}: {len(existing)} strings already cached.")
        return

    lang_name = LANGUAGE_NAMES[args.lang]
    print(f"Translating {len(todo)} string(s) to {lang_name}...")
    translated = _translate_batch(todo, lang_name, api_key)

    missing = [s for s in todo if s not in translated]
    if missing:
        print(f"Warning: model omitted {len(missing)} string(s), leaving them untranslated: {missing}", file=sys.stderr)

    merged = {**existing, **{k: v for k, v in translated.items() if k in todo}}
    # Drop entries for strings no longer in SOURCE_STRINGS so the file doesn't
    # accumulate stale translations for text that was removed from the codebase.
    merged = {k: v for k, v in merged.items() if k in SOURCE_STRINGS}

    out_path = os.path.join(_TRANSLATIONS_DIR, f"{args.lang}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Wrote {len(merged)} translations to {out_path}")


if __name__ == "__main__":
    main()
