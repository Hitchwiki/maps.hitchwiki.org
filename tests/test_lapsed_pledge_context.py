"""#821: map.html exposes the logged-in user's last ride time (or "") for the lapsed prompt."""


def test_anonymous_gets_empty_last_ride(client):
    html = client.get("/").get_data(as_text=True)
    assert 'window.HM_LAST_RIDE_AT = ""' in html
