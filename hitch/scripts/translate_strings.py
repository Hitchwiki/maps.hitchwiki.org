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
    "Please rotate your phone back to portrait",
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
    # Shown above the spot pane's ride list when a ride-level filter hid some of them.
    "No ride here matches your filters (of {total}).",
    "Showing {shown} of {total} rides that match your filters.",
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
    "Account and data",
    "Add Hitchhiking Map to your home screen",
    "Get the Android app",
    "Get the public app from Google Play and keep the hitchhiking map on your phone.",
    "Get it on Google Play",
    "Hitchhiking Map is now an Android app",
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
    # These three menu-sheet links were already wrapped in t() (statistics.html's own
    # title, route_index.html's, why_not_hitchhike.html's) but never added here, so
    # every non-English render fell back to English. Caught while adding two of them
    # as new links from the menu and city pages (route index / why-not-hitchhike).
    "Waiting-time statistics",
    "Hitchhiking routes between cities",
    "Why not hitchhike?",
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
    "Delete your account and data",
    "Download rides",
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
    # Label of the filter pane's weekday picker. Deliberately not "Weekday", which every
    # model reads as "workday" (Будний день / 工作日 / giorno feriale) -- the opposite of
    # the weekend, not "which day of the week". The option labels under it aren't here:
    # they come from the CLDR tables in hitch/translations/weekdays.py.
    "Day of week",
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
    "Help a friend try hitchhiking",
    "Share a real ride and show them where hitchhiking worked for you.",
    "Share this ride",
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
    "If you used other hitchhiking applications such as Hitchmap before whose data can also be seen here, just use the same "
    "username to sign up to claim those rides for you.",
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
    "You have no notifications yet.",
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
    # /help -- the volunteer landing page (help.html) and the menu card that links to it
    # (map.html). These carry the whole recruiting pitch, so they matter most in exactly the
    # languages of the regions we are trying to reach.
    "Help us",
    "Hitchwiki Maps is built by hitchhikers. Help us map regions we know little about, get more hitchhikers logging rides, "
    "or dig into our open hitchhiking dataset.",
    "Help us map hitchhiking — Hitchwiki Maps",
    "Hitchwiki Maps is made by hitchhikers, in their spare time, for free. There is no company behind it — every spot, "
    "every ride and every line of code was added by someone who wanted hitchhiking to be easier for the next person.",
    "If you want to be one of those people: welcome. Below are the three things that would help us most right now. You do "
    "not need to be a developer, and you do not need to commit to anything — most volunteers help with one small thing that "
    "fits their life.",
    "Join our Signal chat",
    "That is where everything happens. Say hi, tell us where you are from, and we will point you at something useful.",
    "Where we need help most",
    "Biggest gap",
    "Put your region on the map",
    "Our map is thick with data in Europe and nearly empty across much of Africa, Latin America, Central, South and "
    "Southeast Asia, the Caucasus and beyond — not because nobody hitchhikes there, but because hardly anyone there has "
    "heard of us. In many of these places catching a ride is completely normal, for travellers and for people going about "
    "their daily lives.",
    "If you are from such a region, or have hitchhiked there a lot, you can change that faster than any of us can. What helps:",
    "Tell local hitchhikers, travellers, backpacker and road-trip communities that this map exists — groups, forums, "
    "hostels, meetups, anywhere people already talk about getting around.",
    "Log the rides you take, and add the spots you know — a handful of good spots in a country with none is a huge difference.",
    "Explain how hitchhiking actually works where you live: how you signal, what is polite, whether money is expected, "
    "where to stand, what is unsafe. This is exactly the knowledge that never leaves a region.",
    "Translate the map, or improve a translation, into a language spoken there.",
    "Introduce us to local groups and communities so we can reach them properly instead of guessing.",
    "Mostly Europe",
    "Get more hitchhikers to log their rides",
    "In Europe the problem is the opposite: plenty of people hitchhike, very few of them record what happened. Every "
    "unlogged ride is a waiting time, a spot and a piece of advice that the next hitchhiker at that on-ramp never gets.",
    "Nudging that ratio up is the single cheapest way to make the map better, and anyone can do it:",
    "Log your own rides — it takes under a minute per ride, and you can do it from the roadside.",
    "Mention the map to the hitchhikers you meet at the on-ramp, at gatherings, and in hitchhiking groups and forums.",
    "Bring it up at hitchhiking gatherings, races and events, or bring stickers and cards to hand out.",
    "Write about it — a post, a video, a thread — wherever the hitchhikers you know already hang out.",
    "Research & thesis",
    "Dig into the data",
    "We hold over {count} logged rides — waiting times, ratings, distances, spots and free-text reports from hitchhikers "
    "all over the world. It is, as far as we know, the largest open dataset on hitchhiking that exists, and it is barely "
    "analysed.",
    "We hold tens of thousands of logged rides — waiting times, ratings, distances, spots and free-text reports from "
    "hitchhikers all over the world. It is, as far as we know, the largest open dataset on hitchhiking that exists, and it "
    "is barely analysed.",
    "What makes a good spot? How long do you really wait, and where? How has hitchhiking changed over the decades? We would "
    "love to know, and we are happy to support you if you want to find out — this fits a university project, a seminar "
    "paper or a full thesis in mobility, geography, data science or the social sciences.",
    "The full dataset is open and downloadable: {link}.",
    "hitchhiking-rides-dataset on Hugging Face",
    "See what we already chart on the {link}.",
    "charts and graphs page",
    "Re-use terms are on our {link} page — in short, it is yours to work with.",
    "Copyright and License",
    "Other ways to help",
    "Those are our priorities, not the whole list. Hitchwiki has many more roles — writing and moderating wiki articles, "
    "design, translation, outreach, community, code and more. They are all described here: {link}.",
    "Roles on Hitchwiki",
    "If you would rather work on the map itself, the code is open source: {contribute} and {bugs}.",
    "contribute on GitHub",
    "report a bug",
    "How to start",
    "Join the {link}.",
    "Signal chat",
    "Say hi, and tell us where you are from and what you would enjoy doing.",
    "We will find something concrete for you — and answer every question you have along the way.",
    "No commitment, no minimum, no experience needed. Even one message from you helps.",
    "Prefer email? Reach out to {a} or {b}.",
    "Help us map hitchhiking",
    "We are volunteers. We especially need people in regions we know little about, hitchhikers who log their rides, and "
    "anyone who wants to analyse our open data.",
    "See how you can help",
    "Or come straight to our {link} — that is where the community talks.",
    # --- ride_form.html: the whole /ride form, server-side t() plus the JS strings
    # it emits via |tojson (see hitch/templates/ride_form.html) ---
    '"{file}" is larger than 12 MB.',
    '"{file}" is not an image.',
    "(select all that apply)",
    "A ride can have at most {max} photos.",
    "About the driver (optional)",
    "Add a photo",
    "Age",
    "Anonymous hitchhiker",
    "Arrival must be later than the pickup time.",
    "Clear destination",
    "Clear pickup location",
    "Click to select destination",
    "Click to select location",
    "Could not get GPS location.",
    "Could not remove that photo. Please try again.",
    "Destination",
    "For map images, use {osm}.",
    "GPS not supported by this browser.",
    "Gender",
    "Getting GPS location...",
    "How do you rate the spot?",
    "How long did you wait? Leave blank if you don't remember.",
    "I did not get a ride here",
    "Is there anything else you want to remember about your rides? {link}.",
    "Kind",
    "Languages spoken by the driver",
    "Let us know here",
    "License plate code (e.g. D (Germany), F (France))",
    "License plate identifier (e.g. B (Berlin), 75 (Paris), California)",
    "Location permission denied.",
    "Location request timed out.",
    "Location set.",
    "Location unavailable.",
    "Make (e.g. Toyota)",
    "Model (e.g. Corolla)",
    "No destination selected",
    "No location selected",
    "No matching user found",
    "No, I would not accept this ride again",
    "Origin country",
    "People hitchhiking with you",
    "Photos (optional, up to {max})",
    # --- security/edit_trip.html: the trip builder's bulk "why are you hitchhiking?"
    # picker, whose other strings it shares with the ride form above ---
    "Saved reasons are added to every ride in this trip. A ride keeps any extra reasons of its own, and removing a "
    "reason here leaves the rides unchanged.",
    "Photos you upload here are published under {ccbysa} — anyone may reuse them, including commercially, as long as they "
    "credit you and share any adaptation under the same licence. Only upload pictures you took yourself, and please avoid "
    "recognisable people and license plates. Location data (EXIF) is stripped on upload.",
    "Planned Destination",
    "Please select a pickup location by clicking on the pickup map thumbnail.",
    "Remove this photo",
    "Ride photo",
    "Rides submitted here will not be saved or published to the map.",
    "Submit Your Ride Experience",
    "Submitting…",
    "Test mode is on.",
    "Type a language and pick from the list…",
    "Type a reason and pick from the list…",
    "Type to search…",
    "Upload failed.",
    "Uploading…",
    "Use GPS",
    'User "{name}" does not exist',
    "Vehicle (optional)",
    "What did your sign say?",
    "When did you arrive at the destination?",
    "When did you get the ride?",
    "When did you stop soliciting rides here?",
    "Why are you hitchhiking?",
    "Why were they on the road?",
    "Yes, I would accept this ride again",
    "You (optional)",
    "You are not logged in. {login} to track your rides — currently you are adding a spot anonymously.",
    "You are not logged in. {login} to track your rides — currently you are reviewing anonymously.",
    "Your ride is published publicly. The database is licensed under the {odbl}; your comment, username and any photos you "
    "upload are licensed under {ccbysa}. By submitting you agree to this. See the {copyright} page.",
    "e.g. 45",
    "e.g. Strasbourg / A5 South",
    "🧪 Test mode is on — this ride was NOT saved or published.",
    # Option labels for the ride form's pickers, rendered through t() from the lists
    # in hitch/blueprints/utils/driver_info_choices.py -- the codes stay English, the
    # labels are what the user reads.
    "Is a hitchhiker themselves",
    "Used to hitchhike in the past",
    "Wanted social interaction / conversation",
    "Interested in cultural exchange",
    "Environmental reasons (reduce empty seats)",
    "Wanted company while driving",
    "Curiosity about hitchhikers",
    "Cultural or personal values around helping strangers",
    "Was in an unusually good mood / feeling generous",
    "Hitchhiker looked non-threatening",
    "Felt pity or concern (weather, appearance, …)",
    "Believed the hitchhiker might be in danger",
    "Opposed the pick-up but was overruled by another occupant",
    "Holiday",
    "Errands",
    "Commute",
    "Business",
    "Recreational",
    "Vacation",
    "Meeting people",
    "Cultural exchange",
    "Saving money",
    "Environmental",
    "Sport",
    "Fundraising",
    "Non-binary",
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
        '- Return ONLY a JSON object: {"<source string>": "<translation>", ...} '
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
    payload = resp.json()
    content = payload["choices"][0]["message"]["content"]
    return json.loads(content), payload.get("usage", {})


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
    translated, usage = _translate_batch(todo, lang_name, api_key)
    print(
        "Usage: "
        f"input={usage.get('prompt_tokens', 0)} "
        f"output={usage.get('completion_tokens', 0)}"
    )

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
