from pathlib import Path

ROOT = Path(__file__).parents[1]
APP = (ROOT / "hitch" / "__init__.py").read_text()
PAGE = (ROOT / "hitch" / "templates" / "delete_account.html").read_text()
PRIVACY = (ROOT / "hitch" / "templates" / "privacy.html").read_text()
PROFILE = (ROOT / "hitch" / "templates" / "security" / "edit_user.html").read_text()
ACCOUNT_PAGE = (ROOT / "hitch" / "templates" / "security" / "account.html").read_text()
USER_BLUEPRINT = (ROOT / "hitch" / "blueprints" / "user.py").read_text()


assert '@app.route("/delete-account")' in APP
assert "play.hitchwiki@gmail.com" in PAGE
assert "Never send your password" in PAGE
assert "systems we control" in PAGE
assert 'href="/delete-account"' in PRIVACY
assert 'href="/delete-account"' in PROFILE
# The main /account/<username> profile page had its own "Delete my account" link
# still pointing at the old bare-text /delete-user stub after this page shipped --
# every other surface got the real link, this one was missed.
assert 'href="/delete-account"' in ACCOUNT_PAGE
assert 'href="/delete-user"' not in ACCOUNT_PAGE
# The old stub URL stays live (it was bookmarkable/indexable) but must forward to
# the real page rather than dead-ending on a bare one-liner.
assert 'redirect("/delete-account"' in USER_BLUEPRINT
print("account deletion path tests passed")
