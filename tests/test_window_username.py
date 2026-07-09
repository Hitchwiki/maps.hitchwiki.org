# Anonymous visitors must still get a defined (empty) window.USERNAME so the
# co-hitcher modal's JS can read it unconditionally.
def test_window_username_empty_for_anonymous(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b'window.USERNAME = "";' in resp.data
