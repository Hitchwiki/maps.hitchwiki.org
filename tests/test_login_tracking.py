"""#823: the login page reports a bounded source/next pair and tags the Hitchwiki button."""


def _page(client, qs):
    resp = client.get("/login" + qs)
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_login_page_tracks_view_and_button(client):
    html = _page(client, "")
    assert 'id="login-oauth-link"' in html
    assert "login_page_viewed" in html and "login_oauth_clicked" in html
    assert 'source: "none"' in html and 'next: "map"' in html


def test_known_source_and_next_bucket(client):
    html = _page(client, "?source=anon-signup&next=/ride/abc")
    assert 'source: "anon-signup"' in html
    assert 'next: "ride"' in html


def test_unknown_source_cannot_mint_new_values(client):
    html = _page(client, "?source=<script>x&next=/evil")
    assert "<script>x" not in html
    assert 'source: "none"' in html and 'next: "other"' in html


def test_invite_param_buckets_to_invite(client):
    assert 'source: "invite"' in _page(client, "?invite=someone")
