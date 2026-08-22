from pathlib import Path

ROOT = Path(__file__).parents[1]
APP = (ROOT / "hitch" / "__init__.py").read_text()
PAGE = (ROOT / "hitch" / "templates" / "delete_account.html").read_text()
PRIVACY = (ROOT / "hitch" / "templates" / "privacy.html").read_text()
PROFILE = (ROOT / "hitch" / "templates" / "security" / "edit_user.html").read_text()


assert '@app.route("/delete-account")' in APP
assert "play.hitchwiki@gmail.com" in PAGE
assert "Never send your password" in PAGE
assert "systems we control" in PAGE
assert 'href="/delete-account"' in PRIVACY
assert 'href="/delete-account"' in PROFILE
print("account deletion path tests passed")
