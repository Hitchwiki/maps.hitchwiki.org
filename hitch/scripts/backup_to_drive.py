"""Weekly off-site backup of the SQLite database to Google Drive, with PII scrubbed.

Pipeline: consistent snapshot -> scrub -> VACUUM -> gzip -> rclone upload -> prune.

Design notes / why it is written this way:
  * Uses sqlite3's online backup API rather than copying the file. The web app and the
    10-minute `show` job write to the DB continuously, so a plain `cp` can capture a
    torn page mid-transaction and produce a backup that won't open.
  * The scrub runs on the *snapshot*, never on the live DB.
  * VACUUM after scrubbing is not an optimisation, it is part of the scrub: an UPDATE
    leaves the old value behind in freelist pages, so the original emails would still be
    recoverable with a hex editor from a file that looks clean via SQL. VACUUM rewrites
    the database and drops those pages. Do not remove it.
  * Password hashes are deliberately KEPT so the backup can actually restore working
    logins. TOTP secrets / recovery codes / phone numbers / login IPs are dropped: they
    are the material an attacker would want if the Drive account is ever compromised,
    and a user who has to re-enrol 2FA after a disaster restore is an acceptable cost.
  * Standalone (plain python3, stdlib only, no Flask app context), like
    build_ride_routes.py, so it runs on the minimal host venv too.

Requires rclone and a configured remote. See deploy/rclone.conf.example.
"""

import argparse
import gzip
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


def _load_env(path=ENV_FILE):
    """Read .env into os.environ without overriding what is already set.

    The in-container cron jobs run with a stripped environment and never see the vars
    Docker injects from env_file; Flask papers over this by loading /app/.env via
    python-dotenv, but this is a standalone script with no app context. Without this,
    BACKUP_RCLONE_REMOTE would be empty under cron and every scheduled run would fail.
    Hand-rolled rather than importing dotenv so the script still runs on the minimal
    host venv.
    """
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip("\"'")


_load_env()

# rclone remote to upload into, e.g. "gdrive:hitchwiki_maps-backups". Configured in .env.
RCLONE_REMOTE = os.environ.get("BACKUP_RCLONE_REMOTE", "")

# Backups older than this are deleted from the remote on every run.
RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "28"))

# Every backup is named like this, so the prune step can match our own files and
# never touches anything else that happens to live in the same Drive folder.
FILENAME_PREFIX = "hitchwiki_maps-"
FILENAME_GLOB = f"{FILENAME_PREFIX}*.sqlite.gz"

# Columns nulled out in the backup copy. `password` is intentionally absent — see module docstring.
SECRET_USER_COLUMNS = [
    "tf_totp_secret",
    "us_totp_secrets",
    "mf_recovery_codes",
    "us_phone_number",
    "tf_phone_number",
    "last_login_ip",
    "current_login_ip",
]


def snapshot(src_path, dst_path):
    """Copy the live DB to dst_path via the online backup API (safe under concurrent writes)."""
    logger.info("snapshotting %s -> %s", src_path, dst_path)
    # uri=True + mode=ro so a bug here can never write to the production database.
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    logger.info("snapshot done (%.1f MB)", os.path.getsize(dst_path) / 1e6)


def scrub(path):
    """Replace emails with placeholders and null out secrets, then VACUUM to purge old pages."""
    conn = sqlite3.connect(path)
    try:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(user)")}

        # Placeholder keyed by id: the email column is UNIQUE, so a constant would
        # collide on the second row. .invalid is reserved by RFC 2606 and can never
        # be delivered to, so a restored backup cannot accidentally mail a real person.
        n = conn.execute("UPDATE user SET email = 'user' || id || '@example.invalid'").rowcount
        logger.info("scrubbed email for %d users", n)

        for col in SECRET_USER_COLUMNS:
            if col not in existing:
                # Tolerate schema drift rather than failing the whole backup.
                logger.warning("user.%s not present, skipping", col)
                continue
            conn.execute(f"UPDATE user SET {col} = NULL")
            logger.info("nulled user.%s", col)

        conn.commit()

        logger.info("vacuuming to purge scrubbed data from free pages...")
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()
    logger.info("scrub done (%.1f MB)", os.path.getsize(path) / 1e6)


def verify(path):
    """Fail loudly rather than uploading a corrupt or unscrubbed backup."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"integrity_check failed: {result}")

        leaked = conn.execute("SELECT count(*) FROM user WHERE email IS NULL OR email NOT LIKE '%@example.invalid'").fetchone()[0]
        if leaked:
            raise RuntimeError(f"{leaked} user rows still hold a real email after scrub")

        users = conn.execute("SELECT count(*) FROM user").fetchone()[0]
        rides = conn.execute("SELECT count(*) FROM ride_event").fetchone()[0]
    finally:
        conn.close()
    logger.info("verified: integrity ok, %d users (all scrubbed), %d rides", users, rides)


def compress(src_path, dst_path):
    logger.info("compressing -> %s", dst_path)
    with open(src_path, "rb") as fin, gzip.open(dst_path, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout, length=8 * 1024 * 1024)
    logger.info("compressed to %.1f MB", os.path.getsize(dst_path) / 1e6)


def rclone(args):
    logger.info("rclone %s", " ".join(args))
    proc = subprocess.run(["rclone", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"rclone {args[0]} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def upload(local_path, remote):
    dest = f"{remote}/{os.path.basename(local_path)}"
    rclone(["copyto", local_path, dest, "--retries", "3", "--low-level-retries", "10"])
    logger.info("uploaded to %s", dest)


def prune(remote, days):
    """Delete our own backups older than `days` from the remote."""
    rclone(["delete", remote, "--include", FILENAME_GLOB, "--min-age", f"{days}d"])
    remaining = rclone(["lsf", remote, "--include", FILENAME_GLOB]).split()
    logger.info("pruned backups older than %dd; %d remaining on remote", days, len(remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=os.path.join(PROJECT_ROOT, "db", os.environ.get("DATABASE_NAME", "hitchhiking-prod.sqlite")),
        help="path to the live SQLite database",
    )
    parser.add_argument("--remote", default=RCLONE_REMOTE, help="rclone remote, e.g. gdrive:hitchwiki_maps-backups")
    parser.add_argument("--retention-days", type=int, default=RETENTION_DAYS)
    parser.add_argument("--keep-local", metavar="PATH", help="also write the scrubbed .gz here")
    parser.add_argument("--no-upload", action="store_true", help="build and verify the backup but skip Drive")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        logger.error("database not found: %s", args.db)
        return 1
    if not args.remote and not args.no_upload:
        logger.error("no remote configured: set BACKUP_RCLONE_REMOTE in .env or pass --remote (or --no-upload)")
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    name = f"{FILENAME_PREFIX}{stamp}.sqlite.gz"

    # The snapshot is a full second copy of a ~400 MB database; keep it in a temp dir
    # that is cleaned up even if a later step raises, so a failed run leaves no debris.
    with tempfile.TemporaryDirectory(prefix="dbbackup-") as tmp:
        raw = os.path.join(tmp, "snapshot.sqlite")
        gz = os.path.join(tmp, name)

        snapshot(args.db, raw)
        scrub(raw)
        verify(raw)
        compress(raw, gz)

        if args.keep_local:
            shutil.copyfile(gz, args.keep_local)
            logger.info("kept local copy at %s", args.keep_local)

        if args.no_upload:
            logger.info("--no-upload set, done")
            return 0

        upload(gz, args.remote)
        prune(args.remote, args.retention_days)

    logger.info("backup complete: %s", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
