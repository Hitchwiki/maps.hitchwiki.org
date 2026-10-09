"""Every literal passed to the client-side tr()/T() helpers must have a key in the
translation files, so a new UI string cannot ship English-only in all languages
(the gap this closes: ~70 journey/pledge/route strings had no key anywhere)."""

import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TRANSLATIONS = os.path.join(ROOT, "hitch", "translations")
CALL = re.compile(r"""\b(?:T|tr)\(\s*(?:"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)')""")


def _literals():
    for path in glob.glob(os.path.join(ROOT, "hitch", "static", "*.js")):
        if path.endswith(".test.js"):
            continue
        with open(path, encoding="utf8") as f:
            src = f.read()
        for m in CALL.finditer(src):
            raw = m.group(1) if m.group(1) is not None else m.group(2)
            # Only plain literals: skip ones followed by string concatenation.
            tail = src[m.end() : m.end() + 3].lstrip()
            if tail.startswith("+"):
                continue
            yield os.path.basename(path), raw.replace("\\'", "'").replace('\\"', '"')


def test_every_js_string_has_a_key_in_every_language():
    langs = sorted(glob.glob(os.path.join(TRANSLATIONS, "*.json")))
    assert len(langs) >= 30
    literals = set(_literals())
    assert literals
    for path in langs:
        with open(path, encoding="utf8") as f:
            keys = json.load(f)
        missing = sorted(f"{name}: {text}" for name, text in literals if text not in keys)
        assert not missing, f"{os.path.basename(path)} lacks keys for: {missing[:5]}"


def test_every_server_side_t_string_in_blueprints_has_a_key_in_every_language():
    """The /hitchhiking-safety page strings were English-only in all 30 languages (IDEAS #672)."""
    import ast

    trees = []
    for bp in glob.glob(os.path.join(ROOT, "hitch", "blueprints", "*.py")):
        with open(bp, encoding="utf8") as f:
            trees.append(ast.parse(f.read()))
    literals = {
        n.args[0].value
        for tree in trees
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) in ("t", "_")
        and n.args
        and isinstance(n.args[0], ast.Constant)
        and isinstance(n.args[0].value, str)
        and " " in n.args[0].value
    }
    assert literals
    for path in sorted(glob.glob(os.path.join(TRANSLATIONS, "*.json"))):
        with open(path, encoding="utf8") as f:
            keys = json.load(f)
        missing = sorted(text for text in literals if text not in keys)
        assert not missing, f"{os.path.basename(path)} lacks keys for: {missing[:5]}"
