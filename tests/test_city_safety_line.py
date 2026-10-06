"""#640: the city-page safety line shows a published count, only for countries with enough answers."""

from hitch.safety_by_country import counts_by_country, load_counts
from tests.test_city_template_route_link import _render


def _rows(cc, yes, no):
    return [{"cc": cc, "w": 1}] * yes + [{"cc": cc, "w": 0}] * no


def test_counts_drop_thin_countries():
    data = {"rides": _rows("DE", 9, 1) + _rows("FR", 5, 1) + [{"w": 1}]}
    assert counts_by_country(data) == {"DE": {"yes": 9, "total": 10}}


def test_load_counts_never_raises(tmp_path):
    assert load_counts(str(tmp_path)) == {}
    (tmp_path / "hitchhiking_safety.json").write_text("not json")
    assert load_counts(str(tmp_path)) == {}


def test_line_rendered_only_with_data(app):
    assert "city-safety" not in _render(app, "en")
    out = _render(app, "en", safety={"yes": 41, "total": 44})
    assert "41 of 44 hitchhikers" in out and 'href="/hitchhiking-safety"' in out
    assert "city_safety_clicked" in out
    assert "41 von 44 Anhaltern" in _render(app, "de", safety={"yes": 41, "total": 44})
