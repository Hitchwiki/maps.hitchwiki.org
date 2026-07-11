"""Initialize the Flask application at flask init."""

import importlib
import mimetypes
import os
import resource
import sys
import time as time_module

import click
from flask import Flask, has_request_context, render_template, request, send_from_directory
from flask.sessions import SecureCookieSessionInterface
from flask_security import SQLAlchemyUserDatastore
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import safe_join

from hitch.blueprints.main import main_bp
from hitch.blueprints.oauth import oauth_bp
from hitch.blueprints.user import user_bp
from hitch.extensions import db, mail, security
from hitch.models import Role, User
from hitch.settings import config

baseDir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
if ENVIRONMENT not in ["prod", "dev"]:
    print("ENVIRONMENT variable must be 'prod' or 'dev'")
    sys.exit(1)


# The endpoints set_public_cache_headers marks publicly cacheable. Their responses are
# identical for every visitor and must never carry per-user state.
_PUBLIC_CACHE_ENDPOINTS = ("static", "catch_all")


class _CacheAwareSessionInterface(SecureCookieSessionInterface):
    """Keeps session state off responses we advertise as publicly cacheable.

    Flask.process_response runs every @app.after_request hook and only *then* calls
    session_interface.save_session() (see flask/app.py: it loops over
    after_request_funcs first, then calls save_session as the final step). So no
    after_request hook can undo what save_session does -- but save_session runs inside
    the request context, so request.endpoint is available here.

    save_session does two things we must prevent on a `public, max-age=...` response:

    1. It emits Set-Cookie whenever the session is modified, or on every request for a
       permanent session (SESSION_REFRESH_EACH_REQUEST defaults to True). A shared cache
       or CDN honouring `public` could store that response *with* the Set-Cookie and hand
       one visitor's session to another. This is the reason we skip, not merely reorder.
    2. It appends Vary: Cookie whenever session.accessed is True -- which
       flask_security/flask_principal cause on EVERY request, including /static and
       dist/* ones, since the identity loader checks login state in before_request. That
       Vary fragments the cache per cookie and defeats the caching entirely.

    Skipping save_session for these endpoints avoids both. It is safe: they serve static
    files and pre-generated data, never mutate the session, and a session created or
    cleared elsewhere is persisted by the very next non-cacheable request.
    """

    def save_session(self, app, session, response):
        if has_request_context() and request.endpoint in _PUBLIC_CACHE_ENDPOINTS:
            return
        super().save_session(app, session, response)


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv("FLASK_CONFIG", "development")

    app = Flask(__name__)
    # Trust X-Forwarded-* headers from Cloudflare/Apache so url_for generates https:// URLs
    # needed fo r correct OAuth callback URLs and to avoid mixed content issues when behind a reverse proxy
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.from_object(config[config_name])
    # See _CacheAwareSessionInterface for why Vary: Cookie needs stripping here,
    # not in an after_request hook.
    app.session_interface = _CacheAwareSessionInterface()

    register_extensions(app)
    register_blueprints(app)
    register_commands(app)
    register_routes(app)
    register_template_globals(app)

    return app


def register_template_globals(app):
    @app.template_global()
    def asset_url(path):
        """Static asset URL with a cache-busting ?v=<mtime> so browsers (notably
        mobile Chrome) pick up CSS/JS changes immediately instead of serving a stale
        cached copy. Falls back to the bare path if the file can't be stat'd."""
        rel = path.lstrip("/")
        fs_path = os.path.join(app.root_path, rel) if rel.startswith("static/") else os.path.join(app.root_path, "static", rel)
        try:
            version = int(os.path.getmtime(fs_path))
        except OSError:
            return path
        sep = "&" if "?" in path else "?"
        return f"{path}{sep}v={version}"


def register_extensions(app):
    db.init_app(app)
    mail.init_app(app)

    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    security.init_app(app, user_datastore)

    # Override Flask-Security/Flask-Login's unauthorized redirect to point to our OAuth login
    app.login_manager.login_view = "oauth.login"


def register_blueprints(app):
    app.register_blueprint(oauth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(user_bp)


def register_commands(app):
    @app.cli.command()
    @click.pass_context
    def init(ctx):
        """Initialize the database."""
        # create necessary sql tables
        security.datastore.db.create_all()

        # define roles - not really needed
        security.datastore.find_or_create_role(
            name="admin",
            permissions={"admin-read", "admin-write", "user-read", "user-write"},
        )
        security.datastore.find_or_create_role(name="monitor", permissions={"admin-read", "user-read"})
        security.datastore.find_or_create_role(name="user", permissions={"user-read", "user-write"})
        security.datastore.find_or_create_role(name="reader", permissions={"user-read"})
        security.datastore.db.session.commit()

        ctx.invoke(generate_all)

    @app.cli.command()
    @click.argument("script", default="show")
    @click.option("--args", default="", help="Arguments for the script")
    @click.option("--no-heatmap", is_flag=True, help="Skip heatmap generation (show script only)")
    @click.option("--force", is_flag=True, help="Force regeneration even if JSON files are up to date")
    def generate(script, args, no_heatmap, force):
        """
        Executes a given script

        USAGE: flask --app hitch generate <script> [OPTIONS]
        EXAMPLE: flask --app hitch generate show --no-heatmap
        """
        try:
            module = f"hitch.scripts.{script}"

            # Sets arguments on the current process (workaround because import_module cannot take args)
            sys.argv.clear()
            sys.argv.append(args)

            # Add generation flags to Flask config for the script to use
            if script == "show":
                if no_heatmap:
                    app.config["GENERATE_HEATMAP"] = False
                if force:
                    app.config["FORCE_REGENERATE"] = True

            # Runs a script automatically through importing it (or reloading so it gets executed again)
            start_time = time_module.time()
            if module not in sys.modules:
                importlib.import_module(module)
            else:
                importlib.reload(sys.modules[module])

            # Log peak memory usage to logs/<script>_ram.log
            elapsed = time_module.time() - start_time
            peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak_mb = peak_kb / 1024
            from datetime import datetime, timezone

            ram_log = os.path.join(app.root_path, "..", "logs", f"{script}_ram.log")
            with open(ram_log, "a") as f:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                f.write(f"{ts} peak_rss={peak_mb:.1f}MB elapsed={elapsed:.1f}s\n")
        except Exception as e:
            print(e)

    @app.cli.command("generate-all")
    @click.pass_context
    def generate_all(ctx):
        """
        Executes all scripts defined in array with given args.
        Only runs a script if its output doesn't already exist (cron keeps them updated after first run).
        """
        from hitch.helpers import get_dirs

        dist_dir = get_dirs()["dist"]

        # Map each script to a file/dir whose existence means "already populated, cron will update"
        output_checks = {
            "fetch_nostr": os.path.join(dist_dir, "allPosts.json"),
            "sync_osm": "__check_db:osm_hitchhiking_spot",
            "sync_car_pooling": "__check_db:osm_car_pooling_spot",
            "sync_fuel": "__check_db:osm_fuel_station_spot",
            "sync_hitchwiki": os.path.join(dist_dir, "hitchwiki_articles.json"),
            "sync_events": os.path.join(dist_dir, "events.json"),
            "show": os.path.join(dist_dir, "spots.json"),
            "dashboard": os.path.join(dist_dir, "dashboard.html"),
            "cities": os.path.join(dist_dir, "city", "index.html"),
        }

        # TODO: include ("dump", "") again when fixed
        scripts = [
            *([("fetch_nostr", "")] if ENVIRONMENT == "prod" else []),
            *([("sync_osm", "")] if ENVIRONMENT == "prod" else []),
            *([("sync_car_pooling", "")] if ENVIRONMENT == "prod" else []),
            *([("sync_fuel", "")] if ENVIRONMENT == "prod" else []),
            *([("sync_hitchwiki", "")] if ENVIRONMENT == "prod" else []),
            *([("sync_events", "")] if ENVIRONMENT == "prod" else []),
            ("show", ""),
            ("dashboard", ""),
            *([("cities", "")] if ENVIRONMENT == "prod" else []),
        ]
        for script, args in scripts:
            check = output_checks.get(script)
            if check and check.startswith("__check_db:"):
                table_name = check.split(":", 1)[1]
                from sqlalchemy import text

                row_count = db.session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                if row_count > 0:
                    print(f"Skipping {script}: table {table_name} already has {row_count} rows")
                    continue
            elif check and os.path.exists(check):
                print(f"Skipping {script}: output already exists ({check})")
                continue
            ctx.invoke(generate, script=script, args=args)


def register_routes(app):
    # Serve dist
    @app.route("/<path:path>")
    def catch_all(path):
        dist_dir = os.path.join(baseDir, "dist")

        # The big JSON files get a precompressed .gz sidecar at generation time
        # (see write_json_file). Serving it with Content-Encoding: gzip means
        # neither Flask nor the reverse proxy compresses multi-MB payloads on
        # every request (Caddy's encode skips already-encoded responses).
        if "gzip" in request.headers.get("Accept-Encoding", "").lower():
            plain_path = safe_join(dist_dir, path)
            gz_path = safe_join(dist_dir, path + ".gz")
            # mtime guard: never serve a sidecar older than the plain file it
            # encodes, e.g. if a regeneration crashed between the two writes.
            if (
                plain_path
                and gz_path
                and os.path.isfile(plain_path)
                and os.path.isfile(gz_path)
                and os.path.getmtime(gz_path) >= os.path.getmtime(plain_path)
            ):
                mimetype = mimetypes.guess_type(path)[0] or "application/octet-stream"
                response = send_from_directory(dist_dir, path + ".gz", mimetype=mimetype)
                response.headers["Content-Encoding"] = "gzip"
                response.headers["Vary"] = "Accept-Encoding"
                return response

        return send_from_directory(os.path.join(baseDir, "dist"), path)

    @app.route("/copyright")
    @app.route("/copyright.html")
    def copyright():
        return render_template("copyright.html")

    # These files are manually served in such a way to conform to web standards of them being in the root
    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            os.path.join(app.root_path, "static"),
            "favicon.ico",
            mimetype="image/vnd.microsoft.icon",
        )

    @app.route("/manifest.json")
    def manifest():
        return send_from_directory(
            os.path.join(app.root_path, "static"),
            "manifest.json",
        )

    @app.route("/sw.js")
    def sw():
        return send_from_directory(
            os.path.join(app.root_path, "static"),
            "sw.js",
        )

    # Cache policy for public, versioned/generated files, in one place so it OVERRIDES
    # the no-cache + Vary: Cookie that Werkzeug (send_from_directory with no max_age) and
    # the session layer inject — both defeat caching of files that are safe to cache.
    # HTML, sw.js, and route endpoints are intentionally left untouched so new ?v= asset
    # links and service-worker updates keep propagating on the next load.
    @app.after_request
    def set_public_cache_headers(response):
        endpoint = request.endpoint
        if endpoint == "static":
            if request.args.get("v"):
                # ?v=<mtime> busting (asset_url) means a content change changes the URL,
                # so the body at THIS url can never change -> cache it for a year.
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                # Plenty of /static/ URLs carry no ?v=: only map.html uses asset_url, so
                # style.css from ride_detail/report_ride/leaderboard/recent, the marker
                # icons and countries.geojson fetched from JS, sw.js's icon and the
                # manifest icons all arrive bare. Their bodies DO change across deploys
                # under a stable URL, so `immutable` would pin them for a year. Cache
                # briefly, then revalidate (ETag turns the recheck into a 304).
                response.headers["Cache-Control"] = "public, max-age=300"
            response.headers["Vary"] = "Accept-Encoding"
        elif endpoint == "catch_all":
            # dist/* regenerates every ~10 min and is already ~40 min stale by design, so
            # a 5-min cache + stale-while-revalidate is invisible and skips the reload
            # revalidation round-trip; ETag/Last-Modified stay for the >15-min case. These
            # files vary only by gzip vs plain, never by cookie — drop Vary: Cookie.
            response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
            response.headers["Vary"] = "Accept-Encoding"
        return response
