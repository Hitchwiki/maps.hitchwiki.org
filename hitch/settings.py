import os
import sys
from datetime import timedelta

from flask_security import utils

baseDir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# SQLite URI compatible
sql_prefix = "sqlite:///" if sys.platform.startswith("win") else "sqlite:////"


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_key")
    EMAIL = os.getenv("EMAIL", "maps@hitchwiki.org")
    MAX_CLAIMS_PER_DAY = os.getenv("MAX_CLAIMS_PER_DAY", 10)

    # User Config
    SECURITY_PASSWORD_HASH = os.getenv("SECURITY_PASSWORD_HASH", "argon2")
    SECURITY_PASSWORD_SALT = os.getenv("SECURITY_PASSWORD_SALT", "146585145368132386173505678016728509634")
    SECURITY_REGISTERABLE = False
    SECURITY_SEND_REGISTER_EMAIL = False

    SECURITY_CONFIRMABLE = False
    SECURITY_RECOVERABLE = False
    SECURITY_CHANGE_EMAIL = False

    SECURITY_USERNAME_ENABLE = True
    SECURITY_USERNAME_REQUIRED = True
    SECURITY_USERNAME_MIN_LENGTH = 1
    SECURITY_USERNAME_MAX_LENGTH = 255
    SECURITY_USER_IDENTITY_ATTRIBUTES = [{"username": {"mapper": utils.uia_username_mapper, "case_insensitive": True}}]

    # Move Flask-Security's built-in views to hidden URLs.
    # Auth is handled via Hitchwiki OAuth in the oauth blueprint at /login, /logout, /register.
    SECURITY_LOGIN_URL = "/_fs/login"
    SECURITY_LOGOUT_URL = "/_fs/logout"
    SECURITY_REGISTER_URL = "/_fs/register"
    SECURITY_POST_LOGIN_VIEW = "/me"
    SECURITY_POST_LOGOUT_VIEW = "/"

    # Hitchwiki OAuth2 config
    HITCHWIKI_OAUTH_CLIENT_ID = os.getenv("HITCHWIKI_OAUTH_CLIENT_ID")
    HITCHWIKI_OAUTH_CLIENT_SECRET = os.getenv("HITCHWIKI_OAUTH_CLIENT_SECRET")
    HITCHWIKI_WIKI_BASE = os.getenv("HITCHWIKI_WIKI_BASE", "https://hitchwiki.org/en")

    # Scheme of the OAuth redirect_uri. It must byte-match the consumer's registered
    # callback: league/oauth2-server (which MediaWiki's OAuth2 extension uses) rejects
    # any mismatch as "Client authentication failed", the same error it gives an unknown
    # client. The dev consumer is registered with http://127.0.0.1:5001/login, so http
    # is the default and only production overrides it.
    HITCHWIKI_OAUTH_REDIRECT_SCHEME = "http"

    # Lax allows the session cookie to be sent on top-level navigations (needed for OAuth redirects).
    # Strict would block the cookie when returning from hitchwiki.org, breaking the OAuth flow.
    SESSION_COOKIE_SAMESITE = "Lax"

    # Keep users logged in across browser restarts via Flask-Login's remember-me cookie.
    REMEMBER_COOKIE_DURATION = timedelta(days=365)
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True

    # Database Config
    DATABASE_NAME = os.getenv("DATABASE_NAME", "hitchhiking.sqlite")
    DATABASE_URI = os.getenv("DATABASE_URI", os.path.join(baseDir, "db", DATABASE_NAME))

    SQLALCHEMY_DATABASE_URI = sql_prefix + DATABASE_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Flask-Mailman configuration
    MAIL_SERVER = os.getenv("MAIL_SERVER", "mail.smtp2go.com")
    MAIL_PORT = os.getenv("MAIL_PORT", 587)  # or 2525 if required
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", True)
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", False)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "hitchwiki.org")  # SMTP2GO username
    MAIL_PASSWORD = os.getenv("HITCHWIKI_MAIL_PASSWORD", "password")  # Load password from env
    MAIL_DEFAULT_SENDER = ("Hitchhiking Map", "no-reply@hitchwiki.org")

    # SparkPost (welcome emails) — shares the hitchwiki account/credentials with the
    # hitchhiking-newsletter project. The first-login welcome email goes out via the
    # SparkPost transmissions API rather than the SMTP2GO/Flask-Mailman path above.
    # FROM must be a SparkPost-verified sender (hi@hitchwiki.org is the verified one).
    SPARKPOST_API_KEY = os.getenv("SPARKPOST_API_KEY")
    SPARKPOST_BASE_URL = os.getenv("SPARKPOST_BASE_URL", "https://api.eu.sparkpost.com/api/v1")
    WELCOME_FROM_EMAIL = os.getenv("WELCOME_FROM_EMAIL", "hi@hitchwiki.org")
    WELCOME_FROM_NAME = os.getenv("WELCOME_FROM_NAME", "Hitchwiki Maps")


class DevelopmentConfig(BaseConfig):
    pass


class ProductionConfig(BaseConfig):
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

    # The prod consumer's callback is https://maps.hitchwiki.org/login, but
    # url_for(_external=True) infers http here: waitress drops X-Forwarded-Proto from
    # untrusted proxies, so the ProxyFix in create_app() never sees it (see deploy/run.sh).
    HITCHWIKI_OAUTH_REDIRECT_SCHEME = "https"


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///"
    WTF_CSRF_ENABLED = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
