"""Guard for maps#469: JS-built option buttons must not use the fixed-size circular .wra-btn."""
import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "hitch" / "templates" / "ride_form.html"


def test_js_created_buttons_are_not_circular():
    src = TEMPLATE.read_text()
    assert "className = 'wra-btn'" not in src
    assert re.search(r"\.wra-chip\s*\{[^}]*border-radius:\s*999px", src)
    assert not re.search(r"\.wra-chip\s*\{[^}]*(?<![-\w])width:\s*\d+px", src)
