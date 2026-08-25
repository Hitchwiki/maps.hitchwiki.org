"""GPX 1.1 serialisation, shared by the two export paths.

Both exports (the per-user "download my rides" file and the pre-generated
`dist/spots.gpx` behind the menu's "Download rides") go through here so they
speak the same dialect and carry the same namespaces.

Stdlib only and no Flask import: `hitch/scripts/show.py` runs this outside an
app context, and the standalone scripts must be able to import it too.

Three things are worth knowing before editing this:

* **Element order inside `<wpt>`/`<rte>` is part of the schema**, not a style
  choice — GPX 1.1 declares them as `xsd:sequence`, so a validator (and some
  importers) reject a file that puts `<name>` after `<desc>`. `_append_text` is
  always called in schema order below; keep it that way.
* **Anything GPX has no field for goes in `<extensions>`**, under our own
  namespace. That is the mechanism by which "all information we have about the
  ride" survives the export: a whole ride record is mirrored there by
  `_fill_extension`, so an importer that understands nothing but coordinates
  still reads the file, while the data is not silently dropped.
* **Tag names are literal strings ("wpt", "hw:ride"), not ElementTree's
  `{uri}local` form.** The namespaces are declared once, as plain attributes on
  the root, which is what lets `GpxStream` serialise one waypoint at a time:
  ET would otherwise re-declare `xmlns` on every element it serialises
  standalone. The document is still namespace-correct — a parser reading it
  back resolves `wpt` and `hw:ride` through the root's declarations.
"""

import re
from xml.etree import ElementTree as ET

GPX_NS = "http://www.topografix.com/GPX/1/1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
# Our own extension namespace. Not resolvable to a schema on purpose: GPX
# consumers are required to ignore extension elements they don't know, and
# publishing an .xsd we'd have to version alongside the ride standard buys
# nothing here.
HW_NS = "https://maps.hitchwiki.org/gpx/1"

CREATOR = "Hitchwiki Maps - https://maps.hitchwiki.org"

XML_DECLARATION = b'<?xml version="1.0" encoding="UTF-8"?>\n'

# XML element names can't start with a digit and allow a much narrower character
# set than JSON keys do. Ride records are nested free-form JSON, so every key is
# run through this before it becomes a tag.
_INVALID_NAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _tag_name(key):
    """A JSON key turned into a legal XML element name, in our extension namespace."""
    name = _INVALID_NAME_CHARS.sub("_", str(key))
    if not name or not (name[0].isalpha() or name[0] == "_"):
        name = "_" + name
    return f"hw:{name}"


def _append_text(parent, tag, value):
    """Append `<tag>value</tag>` unless the value is empty.

    Empty children are skipped rather than written blank: a `<desc/>` with no
    text shows up as an empty line in most importers' detail panes.
    """
    if value is None or value == "":
        return None
    child = ET.SubElement(parent, tag)
    child.text = str(value)
    return child


def _append_link(parent, link):
    """`<link href="…"><text>…</text></link>`, accepting a bare URL or a dict."""
    if not link:
        return
    href, text = (link, None) if isinstance(link, str) else (link.get("href"), link.get("text"))
    if not href:
        return
    element = ET.SubElement(parent, "link", {"href": href})
    _append_text(element, "text", text)


def _fill_extension(element, value):
    """Mirror an arbitrary JSON-ish structure into `element`.

    Lists repeat the element (`<hw:hitchhikers>` once per hitchhiker) rather than
    inventing index attributes, which is how XML normally models a sequence and
    what an XPath over the result would expect.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            if item is None or item == [] or item == {}:
                continue
            if isinstance(item, list):
                for entry in item:
                    _fill_extension(ET.SubElement(element, _tag_name(key)), entry)
            else:
                _fill_extension(ET.SubElement(element, _tag_name(key)), item)
    elif isinstance(value, list):
        for entry in value:
            _fill_extension(ET.SubElement(element, _tag_name("item")), entry)
    elif isinstance(value, bool):
        # Python's "True"/"False" is not how xsd:boolean spells it, and consumers
        # that do parse these expect the lowercase form.
        element.text = "true" if value else "false"
    else:
        element.text = str(value)


def _coord(value):
    """Latitude/longitude as a plain decimal string.

    `str(float)` can produce scientific notation for coordinates very close to
    zero ("1e-05"), which is not a valid `xsd:decimal` and which several parsers
    read as 0. Formatting to 7 decimals (~1 cm) avoids that and is finer than
    anything we store.
    """
    text = f"{float(value):.7f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"


def build_waypoint(wpt):
    """A `<wpt>` element. `wpt` is {lat, lon, name, desc, cmt, time, link, sym, type, extensions}."""
    element = ET.Element("wpt", {"lat": _coord(wpt["lat"]), "lon": _coord(wpt["lon"])})
    _fill_common(element, wpt)
    return element


def build_route(rte):
    """A `<rte>` element. `rte` adds `points` ([{lat, lon, name}]) to the waypoint fields.

    A route rather than a track: a hitchhiked leg is "I got in here and out
    there", not a recording of where the car actually went, and `<rte>` is GPX's
    element for an ordered list of points you pass through.
    """
    element = ET.Element("rte")
    _fill_common(element, rte, points=rte.get("points") or [])
    return element


def _fill_common(element, data, points=None):
    """The `<time>/<name>/<cmt>/<desc>/<src>/<link>/<sym>/<type>/<extensions>` run, in schema order.

    `<time>` and `<sym>` are waypoint-only in GPX 1.1, so they're skipped for a
    route (which is what `points is not None` means here).
    """
    is_route = points is not None
    if not is_route:
        _append_text(element, "time", data.get("time"))
    _append_text(element, "name", data.get("name"))
    _append_text(element, "cmt", data.get("cmt"))
    _append_text(element, "desc", data.get("desc"))
    _append_text(element, "src", data.get("src"))
    _append_link(element, data.get("link"))
    if not is_route:
        _append_text(element, "sym", data.get("sym"))
    _append_text(element, "type", data.get("type"))

    extensions = data.get("extensions")
    if extensions:
        container = ET.SubElement(element, "extensions")
        for tag, payload in extensions.items():
            if payload is None:
                continue
            _fill_extension(ET.SubElement(container, _tag_name(tag)), payload)

    for point in points or []:
        rtept = ET.SubElement(element, "rtept", {"lat": _coord(point["lat"]), "lon": _coord(point["lon"])})
        _append_text(rtept, "time", point.get("time"))
        _append_text(rtept, "name", point.get("name"))
        _append_text(rtept, "desc", point.get("desc"))


def gpx_root(name=None, desc=None, time=None, link=None, keywords=None, author=None):
    """A `<gpx>` element with its `<metadata>` filled in, ready for wpt/rte children."""
    root = ET.Element(
        "gpx",
        {
            "version": "1.1",
            "creator": CREATOR,
            "xmlns": GPX_NS,
            "xmlns:xsi": XSI_NS,
            "xmlns:hw": HW_NS,
            "xsi:schemaLocation": f"{GPX_NS} http://www.topografix.com/GPX/1/1/gpx.xsd",
        },
    )
    metadata = ET.SubElement(root, "metadata")
    _append_text(metadata, "name", name)
    _append_text(metadata, "desc", desc)
    if author:
        _append_text(ET.SubElement(metadata, "author"), "name", author)
    _append_link(metadata, link)
    _append_text(metadata, "time", time)
    _append_text(metadata, "keywords", keywords)
    return root


def serialize(root):
    """The finished document as bytes. For documents small enough to hold in memory."""
    return XML_DECLARATION + ET.tostring(root, encoding="utf-8", xml_declaration=False)


class GpxStream:
    """Write a GPX document one waypoint at a time, never holding the whole tree.

    `show.py` writes ~35k waypoints, which as a single ElementTree is on the order
    of a hundred MB of Element objects — added right at the end of a run that
    already holds the whole ride table in pandas, on a host the OOM killer has
    visited before (see CLAUDE.md). Each element is built, serialised and dropped
    instead, so memory stays flat regardless of how many spots there are.

    Used as a context manager; the closing `</gpx>` is written on exit.
    """

    def __init__(self, fileobj, **metadata):
        self._file = fileobj
        head = ET.tostring(gpx_root(**metadata), encoding="utf-8", xml_declaration=False)
        # The root always has a <metadata> child, so ET always closes it with a
        # real </gpx> rather than emitting a self-closing <gpx/> — which is what
        # makes chopping the tail off safe.
        assert head.endswith(b"</gpx>")
        self._file.write(XML_DECLARATION + head[: -len(b"</gpx>")] + b"\n")

    def waypoint(self, wpt):
        self.write(build_waypoint(wpt))

    def route(self, rte):
        self.write(build_route(rte))

    def write(self, element):
        self._file.write(ET.tostring(element, encoding="utf-8", xml_declaration=False) + b"\n")

    def close(self):
        self._file.write(b"</gpx>\n")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        # Only close a document that isn't already being abandoned to an exception:
        # a truncated file with a valid closing tag looks complete, and would be
        # served as if it were.
        if exc[0] is None:
            self.close()
        return False
