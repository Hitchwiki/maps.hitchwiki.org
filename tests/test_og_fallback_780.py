"""IDEAS #780: pages that set a meta description must not share the generic map text in og:description."""
from pathlib import Path

import jinja2

T = Path(__file__).resolve().parent.parent / "hitch" / "templates"


def test_og_description_defaults_to_meta_description():
    base = (T / "base.html").read_text()
    assert "{% block og_description %}{{ self.meta_description() }}{% endblock %}" in base
    # Same inheritance rule the template relies on, exercised with real Jinja.
    env = jinja2.Environment(
        loader=jinja2.DictLoader(
            {
                "b": "{% block meta_description %}generic{% endblock %}|"
                "{% block og_description %}{{ self.meta_description() }}{% endblock %}",
                "c": "{% extends 'b' %}{% block meta_description %}safety{% endblock %}",
            }
        )
    )
    assert env.get_template("c").render() == "safety|safety"
    assert env.get_template("b").render() == "generic|generic"


def test_stats_and_safety_pages_set_their_own_preview():
    for name in ("hitchhiking_safety", "statistics", "statistics_index", "ride_collection_statistics"):
        src = (T / f"{name}.html").read_text()
        assert "{% block meta_description %}" in src, name
        assert "{% block og_title %}" in src, name
