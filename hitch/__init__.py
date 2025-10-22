"""Initialize the Flask application at flask init."""
import importlib
import os
import sys

import click
from flask import Flask, render_template, send_from_directory
from flask_security import SQLAlchemyUserDatastore

from hitch.blueprints.main import main_bp
from hitch.blueprints.user import user_bp
from hitch.extensions import db, mail, security
from hitch.models import Role, User
from hitch.settings import config

baseDir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
if ENVIRONMENT not in ["prod", "dev"]:
    print("ENVIRONMENT variable must be 'prod' or 'dev'")
    sys.exit(1)


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv("FLASK_CONFIG", "development")

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    register_extensions(app)
    register_blueprints(app)
    register_commands(app)
    register_routes(app)

    return app


def register_extensions(app):
    db.init_app(app)
    mail.init_app(app)

    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    security.init_app(app, user_datastore)


def register_blueprints(app):
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
            if module not in sys.modules:
                importlib.import_module(module)
            else:
                importlib.reload(sys.modules[module])
        except Exception as e:
            print(e)

    @app.cli.command("generate-all")
    @click.pass_context
    def generate_all(ctx):
        """
        Executes all scripts defined in array with given args
        """
        # TODO: include ("dashboard", ""), ("dump", "") again when fixed
        scripts = [
            *([("fetch_nostr", "")] if ENVIRONMENT == "prod" else []),
            *([("sync_osm", "")] if ENVIRONMENT == "prod" else []),
            *([("sync_hitchwiki", "")] if ENVIRONMENT == "prod" else []),
            *([("sync_upstream", "")] if ENVIRONMENT == "prod" else []),
            ("show", ""),
            *([("cities", "")] if ENVIRONMENT == "prod" else []),
        ]
        for script, args in scripts:
            ctx.invoke(generate, script=script, args=args)


def register_routes(app):
    # Serve dist
    @app.route("/<path:path>")
    def catch_all(path):
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
