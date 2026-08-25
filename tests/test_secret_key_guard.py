"""ENVIRONMENT and SECRET_KEY/SECURITY_PASSWORD_SALT are read at import time
(hitch/__init__.py sets the ENVIRONMENT module constant when the module is first
imported, and create_app() reads os.environ directly), so this guard can't be exercised
by reloading the already-imported hitch module inside the main test process without
risking other tests observing a different ENVIRONMENT than they expect. Each case runs
in its own subprocess instead, exactly like a fresh `flask run` would see it.
"""

import subprocess
import sys

_BASE_ENV = {"RELAYS": '["wss://relay.maps.hitchwiki.org"]'}


def _run(extra_env):
    import os

    env = dict(os.environ)
    env.update(_BASE_ENV)
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", "from hitch import create_app; create_app()"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_prod_refuses_default_secret_key():
    result = _run(
        {
            "ENVIRONMENT": "prod",
            "FLASK_CONFIG": "production",
            "SECRET_KEY": "super_secret_key",
            "SECURITY_PASSWORD_SALT": "a_real_random_value",
        }
    )
    assert result.returncode != 0
    assert "default SECRET_KEY" in result.stderr


def test_prod_refuses_default_password_salt():
    result = _run(
        {
            "ENVIRONMENT": "prod",
            "FLASK_CONFIG": "production",
            "SECRET_KEY": "a_real_random_value",
        }
    )
    assert result.returncode != 0
    assert "default SECURITY_PASSWORD_SALT" in result.stderr


def test_prod_boots_with_real_values():
    result = _run(
        {
            "ENVIRONMENT": "prod",
            "FLASK_CONFIG": "production",
            "SECRET_KEY": "a_real_random_value",
            "SECURITY_PASSWORD_SALT": "another_real_random_value",
        }
    )
    assert result.returncode == 0, result.stderr


def test_dev_boots_with_default_secret_key():
    """Unchanged behavior: local dev must still boot with nothing but example.env."""
    result = _run({"ENVIRONMENT": "dev"})
    assert result.returncode == 0, result.stderr
