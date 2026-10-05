"""Links to a user's profiles elsewhere (Instagram, Mastodon, a personal site, …).

Stored as a JSON list of URLs in `user.profile_links`, at most MAX_LINKS. Each is shown
on the public profile with an icon picked from its host: a brand icon for platforms we
recognise, a plain globe for anything else (personal websites, blogs, unknown sites).

Icons are Font Awesome 6.7 classes — the profile page loads 6.7 rather than the 6.2 the
rest of the app uses, because 6.2 predates the X, Bluesky and Threads marks.
"""

import json
from urllib.parse import urlsplit

MAX_LINKS = 5
MAX_URL_LEN = 500

# (host suffixes, label, icon). First match wins, so put more specific hosts first.
# A host matches a suffix when it equals it or is a subdomain of it ("m.facebook.com").
PLATFORMS = [
    (("instagram.com", "instagr.am"), "Instagram", "fa-brands fa-instagram"),
    (("facebook.com", "fb.com", "fb.me"), "Facebook", "fa-brands fa-facebook"),
    (("x.com", "twitter.com"), "X", "fa-brands fa-x-twitter"),
    (("bsky.app",), "Bluesky", "fa-brands fa-bluesky"),
    (("threads.net", "threads.com"), "Threads", "fa-brands fa-threads"),
    (("youtube.com", "youtu.be"), "YouTube", "fa-brands fa-youtube"),
    (("tiktok.com",), "TikTok", "fa-brands fa-tiktok"),
    (("linkedin.com",), "LinkedIn", "fa-brands fa-linkedin"),
    (("github.com",), "GitHub", "fa-brands fa-github"),
    (("gitlab.com",), "GitLab", "fa-brands fa-gitlab"),
    (("strava.com",), "Strava", "fa-brands fa-strava"),
    (("t.me", "telegram.me"), "Telegram", "fa-brands fa-telegram"),
    (("wa.me", "whatsapp.com"), "WhatsApp", "fa-brands fa-whatsapp"),
    (("reddit.com",), "Reddit", "fa-brands fa-reddit"),
    (("pinterest.com",), "Pinterest", "fa-brands fa-pinterest"),
    (("flickr.com",), "Flickr", "fa-brands fa-flickr"),
    (("vimeo.com",), "Vimeo", "fa-brands fa-vimeo-v"),
    (("twitch.tv",), "Twitch", "fa-brands fa-twitch"),
    (("spotify.com",), "Spotify", "fa-brands fa-spotify"),
    (("soundcloud.com",), "SoundCloud", "fa-brands fa-soundcloud"),
    (("medium.com",), "Medium", "fa-brands fa-medium"),
    (("patreon.com",), "Patreon", "fa-brands fa-patreon"),
    (("paypal.me", "paypal.com"), "PayPal", "fa-brands fa-paypal"),
    (("vk.com",), "VK", "fa-brands fa-vk"),
    (("tumblr.com",), "Tumblr", "fa-brands fa-tumblr"),
    (("discord.gg", "discord.com"), "Discord", "fa-brands fa-discord"),
    (("wikipedia.org",), "Wikipedia", "fa-brands fa-wikipedia-w"),
    # Travel platforms hitchhikers actually use. None has a brand icon in Font Awesome,
    # so each gets the closest plain symbol rather than the anonymous globe.
    (("hitchwiki.org",), "Hitchwiki", "fa-solid fa-thumbs-up"),
    (("trustroots.org",), "Trustroots", "fa-solid fa-tree"),
    (("couchsurfing.com",), "Couchsurfing", "fa-solid fa-couch"),
    (("bewelcome.org",), "BeWelcome", "fa-solid fa-house"),
    (("polarsteps.com",), "Polarsteps", "fa-solid fa-shoe-prints"),
    (("komoot.com", "komoot.de"), "Komoot", "fa-solid fa-route"),
]
MASTODON = ("Mastodon", "fa-brands fa-mastodon")
WEBSITE_ICON = "fa-solid fa-globe"


def normalize_link(raw):
    """Clean one typed link into a storable URL, or raise ValueError.

    People type "instagram.com/me" far more often than the full URL, so a missing scheme
    becomes https://. Only http(s) survives — this ends up in an href on a public page,
    where javascript:/data: would be an XSS vector.
    """
    text = (raw or "").strip()
    if "://" not in text:
        text = "https://" + text
    if len(text) > MAX_URL_LEN or any(c.isspace() for c in text):
        raise ValueError
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() not in ("http", "https") or "." not in host or host.startswith(".") or host.endswith("."):
        raise ValueError
    return text


def load_links(raw):
    """The stored JSON column as a list of URLs; anything malformed reads as no links."""
    try:
        links = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [u for u in links if isinstance(u, str)][:MAX_LINKS] if isinstance(links, list) else []


def describe_link(url):
    """{url, label, icon} for rendering one link on the profile."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    for suffixes, label, icon in PLATFORMS:
        if any(host == s or host.endswith("." + s) for s in suffixes):
            return {"url": url, "label": label, "icon": icon}
    # Mastodon has thousands of instances, so no host list can recognise it; the
    # /@username profile path is the convention it and its fediverse cousins share.
    # Checked after PLATFORMS because YouTube, TikTok, Medium and Threads use /@ too.
    if parts.path.startswith("/@") or "mastodon" in host:
        return {"url": url, "label": MASTODON[0], "icon": MASTODON[1]}
    label = host.removeprefix("www.")
    return {"url": url, "label": label, "icon": WEBSITE_ICON}
