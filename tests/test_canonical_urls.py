"""Canonical / hreflang correctness for the 31 language mirrors.

Every main_bp and user_bp route is registered once per language (see
register_blueprints), so each page is reachable at 31 URLs. Search Console reported
the two ways that goes wrong: pages with no canonical at all ("Duplicate without
user-selected canonical") and translated pages canonicalised onto the English
original ("Alternate page with proper canonical tag", which drops the translation).
"""

import re

CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]*)"')
ROBOTS_RE = re.compile(r'<meta name="robots" content="([^"]*)"')


def canonicals(client, path):
    return CANONICAL_RE.findall(client.get(path).get_data(as_text=True))


class TestSelfReferencingCanonical:
    def test_every_page_carries_exactly_one(self, client):
        # Two canonicals in one <head> make Google ignore both, which is how this
        # regressed before: base.html grew a default while map.html still emitted
        # its own.
        for path in ("/", "/recent", "/leaderboard", "/races", "/country/Germany"):
            assert len(canonicals(client, path)) == 1, path

    def test_a_language_mirror_points_at_itself_not_at_english(self, client):
        # The hreflang block declares the mirrors as translations of one another;
        # canonicalising onto English would contradict it and drop the German page.
        assert canonicals(client, "/de/recent") == ["https://localhost/de/recent"]
        assert canonicals(client, "/de/country/Germany") == ["https://localhost/de/country/Germany"]

    def test_it_is_https_even_though_the_request_is_not(self, client):
        # waitress strips the X-Forwarded-Proto that ProxyFix would need, so anything
        # derived from the request scheme comes out http:// in production and search
        # engines discard an insecure canonical on an https page.
        (url,) = canonicals(client, "/recent")
        assert url.startswith("https://")

    def test_a_path_with_a_space_is_percent_encoded(self, client):
        # request.path is percent-decoded, so a raw space would make the canonical an
        # invalid URL that is silently ignored.
        assert canonicals(client, "/country/United%20States") == ["https://localhost/country/United%20States"]


class TestOneMapManyUrls:
    def test_the_variants_all_name_the_map_root(self, client):
        # "/index.html", "/light" and "/with_destination" are views of the same map,
        # not pages of their own -- and the ?heatmap=true toggle changes nothing the
        # server renders.
        for path in ("/index.html", "/light", "/light.html", "/with_destination", "/?heatmap=true"):
            assert canonicals(client, path) == ["https://localhost/"], path

    def test_the_german_map_names_the_german_root(self, client):
        assert canonicals(client, "/de/index.html") == ["https://localhost/de/"]

    def test_the_html_twins_of_the_static_pages_defer_to_the_bare_path(self, client):
        assert canonicals(client, "/copyright.html") == ["https://localhost/copyright"]
        assert canonicals(client, "/privacy.html") == ["https://localhost/privacy"]


class TestHreflang:
    def test_alternates_are_https(self, client):
        # An hreflang pointing at http:// names a URL that only redirects, so the
        # cluster does not reciprocate and the translations are discounted.
        body = client.get("/de/recent").get_data(as_text=True)
        alternates = re.findall(r'<link rel="alternate" hreflang="[^"]*" href="([^"]*)"', body)
        assert alternates, "the language mirrors must advertise each other"
        assert all(href.startswith("https://") for href in alternates)


class TestLanguageMirrorsAreNotIndexable:
    """The mirrors of a page whose content is the same in every language.

    Google had indexed /fi/account/<name> and a scattering of /<lang>/spot/<id>: the
    noindex rules were written as `request.path.startswith("/account/")`, which is true
    of exactly one of the 31 URLs each view answers on.
    """

    def test_an_account_mirror_carries_the_noindex_header(self, client):
        assert client.get("/fi/account/Tyyybu").headers.get("X-Robots-Tag") == "noindex"

    def test_the_english_account_page_still_does(self, client):
        assert client.get("/account/Tyyybu").headers.get("X-Robots-Tag") == "noindex"

    def test_a_noindexed_page_advertises_no_translations(self, client):
        # An hreflang entry pointing at a noindexed URL is a contradiction; search
        # engines drop the entry and may discount the whole cluster.
        body = client.get("/fi/account/Tyyybu").get_data(as_text=True)
        assert '<link rel="alternate" hreflang=' not in body

    def test_an_indexable_page_still_does(self, client):
        assert '<link rel="alternate" hreflang=' in client.get("/de/recent").get_data(as_text=True)

    def test_a_shared_route_link_is_noindex_by_header_too(self, client):
        # /dir/<from>/<to> has always carried the <meta> tag (its URL space is the square
        # of the spot space), but only the tag -- so the mirrors still advertised each
        # other as translations of a page none of them may index.
        response = client.get("/dir/47.55811,7.58783/52.51739,13.39513")
        assert response.headers.get("X-Robots-Tag") == "noindex"
        assert '<link rel="alternate" hreflang=' not in response.get_data(as_text=True)

    def test_a_login_with_a_next_parameter_is_noindex_in_every_language(self, client):
        # ?next= makes a duplicate of /login with a throwaway parameter. Bare /login
        # stays indexable, mirrors included.
        assert client.get("/de/login?next=/me").headers.get("X-Robots-Tag") == "noindex"
        assert client.get("/de/login").headers.get("X-Robots-Tag") is None


class TestUnboundedUrlSpaces:
    def test_an_account_page_with_nothing_on_it_is_noindex(self, client):
        # /account/<anything> answers 200 so that ride nicknames from other sources
        # stay browsable; a name with no user and no rides is a soft 404 and must not
        # invite a crawler into an unbounded space.
        body = client.get("/account/nobody-has-ever-used-this-name").get_data(as_text=True)
        assert ROBOTS_RE.findall(body) == ["noindex"]

    def test_the_legacy_contributors_page_redirects_to_the_leaderboard(self, client):
        # It counted rows in the legacy `points` table, which production no longer
        # has, so it answered 500 on every language mirror.
        response = client.get("/contributors")
        assert response.status_code == 301
        assert response.headers["Location"].endswith("/leaderboard")

    def test_the_redirect_keeps_the_language(self, client):
        assert client.get("/de/contributors").headers["Location"].endswith("/de/leaderboard")
