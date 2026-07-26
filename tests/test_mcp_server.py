"""The MCP server at /mcp (hitch/blueprints/mcp.py).

Three things are pinned here.

1. The JSON-RPC/Streamable-HTTP contract. A client that can't complete
   `initialize` -> `tools/list` -> `tools/call` sees no tools at all, and the
   failure mode is silent — the assistant simply never mentions us.
2. The search/fetch payload shape OpenAI requires: the result must appear BOTH
   as `structuredContent` and as a JSON-encoded string in `content[0].text`, and
   every result needs a non-empty `url` or it isn't citable. Emitting one and
   not the other is the usual reason a technically-correct server reads as empty.
3. Intent parsing. `search` gets free text, and deciding "route from X to Y" vs
   "spots around here" is the only genuinely lossy step in the server — "how to
   hitchhike out of Berlin" contains " to " and must NOT split on it.

Geocoding and the routing subprocess are stubbed: the real ones need the network
and a ~190 MB graph build, neither of which belongs in a unit test.
"""

import json

import pytest

from hitch.blueprints import mcp as mcp_mod

# One car leg between two walks — the shape route_query.py emits.
SAMPLE_ITINERARY = {
    "found": True,
    "rank": 0,
    "min_support": 4,
    "total_minutes": 200.0,
    "wait_minutes": 40.0,
    "walk_km": 2.0,
    "car_km": 180.0,
    "num_car_legs": 1,
    "legs": [
        {
            "mode": "walk",
            "from": [47.55811, 7.58783],
            "to": [47.6, 7.6],
            "km": 1.0,
            "via": [],
            "wait_minutes": 0.0,
            "support": None,
            "minutes": 12.0,
        },
        {
            "mode": "car",
            "from": [47.6, 7.6],
            "to": [52.4, 13.3],
            "km": 180.0,
            "via": [[48.0, 8.0]],
            "wait_minutes": 40.0,
            "support": 4,
            "minutes": 108.0,
        },
        {
            "mode": "walk",
            "from": [52.4, 13.3],
            "to": [52.51739, 13.39513],
            "km": 1.0,
            "via": [],
            "wait_minutes": 0.0,
            "support": None,
            "minutes": 12.0,
        },
    ],
}

PLACES = {
    "basel": (47.55811, 7.58783, "Basel, Switzerland"),
    "berlin": (52.51739, 13.39513, "Berlin, Germany"),
    "lisbon": (38.72225, -9.13934, "Lisbon, Portugal"),
    "porto": (41.14961, -8.61099, "Porto, Portugal"),
}


def rpc(client, method, params=None, req_id=1):
    """POST one JSON-RPC message and return (status_code, parsed_body_or_None)."""
    msg = {"jsonrpc": "2.0", "method": method}
    if req_id is not None:
        msg["id"] = req_id
    if params is not None:
        msg["params"] = params
    resp = client.post("/mcp", json=msg)
    return resp.status_code, (resp.get_json() if resp.data else None)


def call_tool(client, name, args):
    """tools/call -> the `result` object."""
    _, body = rpc(client, "tools/call", {"name": name, "arguments": args})
    assert "error" not in body, body
    return body["result"]


@pytest.fixture
def stubbed(monkeypatch):
    """Geocoding, spot data and routing replaced by deterministic stand-ins."""

    def fake_geocode(place):
        return PLACES.get(str(place).strip().lower())

    def fake_reverse(lat, lon):
        for plat, plon, label in PLACES.values():
            if abs(plat - lat) < 1e-4 and abs(plon - lon) < 1e-4:
                return label.split(",")[0]
        return f"{lat:.5f}, {lon:.5f}"

    monkeypatch.setattr(mcp_mod, "_geocode", fake_geocode)
    monkeypatch.setattr(mcp_mod, "_reverse_label", fake_reverse)
    monkeypatch.setattr(mcp_mod, "_run_route", lambda *a, **k: {"found": True, "itineraries": [SAMPLE_ITINERARY]})
    monkeypatch.setattr(
        mcp_mod,
        "_spots_near",
        lambda lat, lon, radius, limit: [(3.2, 52.43408, 13.19135, 4.2, 36), (7.5, 52.64147, 13.24363, 4.0, 26)][:limit],
    )
    monkeypatch.setattr(
        mcp_mod,
        "_spot_detail",
        lambda sid: {"spot": {"name": f"Spot {sid}", "wait": 29, "distance": 229}, "rides": []},
    )


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
def test_initialize_advertises_tools(client):
    status, body = rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    assert status == 200
    result = body["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "hitchwiki-maps"
    assert result["instructions"]


def test_initialize_echoes_older_supported_version(client):
    """Clients pinned to an older spec must not be told a version they can't speak."""
    _, body = rpc(client, "initialize", {"protocolVersion": "2024-11-05"})
    assert body["result"]["protocolVersion"] == "2024-11-05"


def test_initialize_falls_back_for_unknown_version(client):
    _, body = rpc(client, "initialize", {"protocolVersion": "1999-01-01"})
    assert body["result"]["protocolVersion"] == mcp_mod.LATEST_PROTOCOL_VERSION


def test_notification_gets_202_and_no_body(client):
    """A message without an id is a notification; replying to one is a protocol
    violation that strict clients treat as a broken server."""
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp.status_code == 202
    assert resp.data == b""


def test_ping(client):
    _, body = rpc(client, "ping")
    assert body["result"] == {}


def test_unknown_method_is_method_not_found(client):
    _, body = rpc(client, "resources/list")
    assert body["error"]["code"] == mcp_mod.METHOD_NOT_FOUND


def test_malformed_message_rejected(client):
    resp = client.post("/mcp", json={"method": "ping", "id": 1})  # no jsonrpc version
    assert resp.get_json()["error"]["code"] == mcp_mod.INVALID_REQUEST


def test_batch_returns_only_the_requests(client):
    resp = client.post(
        "/mcp",
        json=[
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 7, "method": "ping"},
        ],
    )
    body = resp.get_json()
    assert isinstance(body, list) and len(body) == 1
    assert body[0]["id"] == 7


def test_batch_of_only_notifications_is_202(client):
    resp = client.post("/mcp", json=[{"jsonrpc": "2.0", "method": "notifications/initialized"}])
    assert resp.status_code == 202
    assert resp.data == b""


def test_get_is_405(client):
    """Stateless server: there is no SSE stream to open."""
    assert client.get("/mcp").status_code == 405


def test_cors_preflight(client):
    resp = client.options("/mcp")
    assert resp.status_code == 204
    assert resp.headers["Access-Control-Allow-Origin"] == "*"
    assert "MCP-Protocol-Version" in resp.headers["Access-Control-Allow-Headers"]


def test_discovery_document(client):
    resp = client.get("/.well-known/mcp.json")
    assert resp.status_code == 200
    doc = resp.get_json()
    assert doc["endpoint"].endswith("/mcp")
    assert {t["name"] for t in doc["tools"]} == {"search", "fetch"}


# ---------------------------------------------------------------------------
# tools/list — the exact two tools OpenAI requires, and nothing else
# ---------------------------------------------------------------------------
def test_exposes_exactly_search_and_fetch(client):
    """Deep research calls only these two; extra tools are dead weight and an
    absent one makes ChatGPT reject the server outright."""
    _, body = rpc(client, "tools/list")
    tools = body["result"]["tools"]
    assert [t["name"] for t in tools] == ["search", "fetch"]


def test_tool_schemas_take_a_single_string(client):
    """The single-string constraint is what lets any client drive this server."""
    _, body = rpc(client, "tools/list")
    schemas = {t["name"]: t["inputSchema"] for t in body["result"]["tools"]}
    assert schemas["search"]["required"] == ["query"]
    assert schemas["search"]["properties"]["query"]["type"] == "string"
    assert schemas["fetch"]["required"] == ["id"]
    assert schemas["fetch"]["properties"]["id"]["type"] == "string"
    for tool in body["result"]["tools"]:
        assert "handler" not in tool  # a Python callable would break JSON encoding


# ---------------------------------------------------------------------------
# Payload shape
# ---------------------------------------------------------------------------
def test_search_payload_is_duplicated_into_content_and_structured(client, stubbed):
    """Both halves are required; emitting one is why a correct-looking server
    reads as empty to deep research."""
    result = call_tool(client, "search", {"query": "Basel to Berlin"})
    assert "results" in result["structuredContent"]
    echoed = json.loads(result["content"][0]["text"])
    assert echoed == result["structuredContent"]


def test_fetch_payload_is_duplicated_into_content_and_structured(client, stubbed):
    result = call_tool(client, "fetch", {"id": "spot:52.43408_13.19135"})
    doc = result["structuredContent"]
    assert set(doc) >= {"id", "title", "text", "url"}
    assert json.loads(result["content"][0]["text"]) == doc


def test_every_search_result_is_citable(client, stubbed):
    """A result with an empty url is used but not attributed — the one outcome
    that defeats the purpose of answering at all."""
    result = call_tool(client, "search", {"query": "hitchhiking spots near Berlin"})
    results = result["structuredContent"]["results"]
    assert results
    for r in results:
        assert r["id"] and r["title"]
        assert r["url"].startswith("https://maps.hitchwiki.org/")


# ---------------------------------------------------------------------------
# Intent parsing — the lossy step
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query,expected",
    [
        ("Basel to Berlin", ("Basel", "Berlin")),
        ("basel to berlin", ("basel", "berlin")),
        ("hitchhiking from Lisbon to Porto", ("Lisbon", "Porto")),
        ("how do i get from Basel to Berlin", ("Basel", "Berlin")),
        ("best way to hitchhike from Basel to Berlin", ("Basel", "Berlin")),
        ("route from Paris to Lyon by hitchhiking", ("Paris", "Lyon")),
        ("Basel → Berlin", ("Basel", "Berlin")),
        ("Basel -> Berlin", ("Basel", "Berlin")),
        ("hitchhike Basel to Berlin", ("Basel", "Berlin")),
    ],
)
def test_route_queries_split_into_two_endpoints(query, expected):
    assert mcp_mod._split_route_query(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "how to hitchhike out of Berlin",  # the trap: contains " to "
        "where can i hitchhike out of Berlin",
        "hitchhiking spots near Berlin",
        "spots near Toronto",  # "Toronto" must not read as a separator
        "Berlin",
        "best hitchhiking spots in Lisbon",
    ],
)
def test_place_queries_are_not_mistaken_for_routes(query):
    assert mcp_mod._split_route_query(query) is None


@pytest.mark.parametrize(
    "query,expected",
    [
        ("hitchhiking spots near Berlin", "Berlin"),
        ("spots near Berlin", "Berlin"),
        ("best hitchhiking spots in Lisbon", "Lisbon"),
        ("hitchhike out of Berlin", "Berlin"),
        ("how to hitchhike out of Berlin", "Berlin"),
        ("where can i hitchhike out of Berlin", "Berlin"),
        ("Berlin", "Berlin"),
    ],
)
def test_place_queries_reduce_to_the_place(query, expected):
    assert mcp_mod._place_query(query) == expected


def test_route_query_falls_back_to_spots_when_an_endpoint_is_unknown(client, stubbed):
    """A failed geocode on one half means the split found a stray 'to', so the
    query was really about a place."""
    result = call_tool(client, "search", {"query": "Berlin to Nowherecity"})
    results = result["structuredContent"]["results"]
    assert results
    assert all(r["id"].startswith("spot:") for r in results)


# ---------------------------------------------------------------------------
# search behaviour
# ---------------------------------------------------------------------------
def test_route_search_leads_with_the_route_then_offers_spots(client, stubbed):
    result = call_tool(client, "search", {"query": "Basel to Berlin"})
    results = result["structuredContent"]["results"]
    assert results[0]["id"] == "route:47.55811,7.58783__52.51739,13.39513"
    assert results[0]["url"] == "https://maps.hitchwiki.org/dir/47.55811,7.58783/52.51739,13.39513"
    assert "Basel" in results[0]["title"] and "Berlin" in results[0]["title"]
    # Departure spots come along so the model has more than one citable source.
    assert any(r["id"].startswith("spot:") for r in results[1:])


def test_place_search_returns_only_spots(client, stubbed):
    result = call_tool(client, "search", {"query": "hitchhiking spots near Berlin"})
    results = result["structuredContent"]["results"]
    assert results and all(r["id"].startswith("spot:") for r in results)
    assert "Spot 52.43408_13.19135" in results[0]["title"]


def test_search_does_not_invoke_the_routing_graph(client, monkeypatch, stubbed):
    """The expensive fork belongs in fetch; search must stay cheap."""

    def explode(*a, **k):
        raise AssertionError("search must not route")

    monkeypatch.setattr(mcp_mod, "_run_route", explode)
    call_tool(client, "search", {"query": "Basel to Berlin"})


def test_unresolvable_query_returns_empty_not_an_error(client, stubbed):
    result = call_tool(client, "search", {"query": "Nowherecity"})
    assert result["structuredContent"]["results"] == []
    assert result["isError"] is False


def test_search_rejects_a_missing_query(client, stubbed):
    result = call_tool(client, "search", {})
    assert result["isError"] is True


# ---------------------------------------------------------------------------
# fetch behaviour
# ---------------------------------------------------------------------------
def test_fetch_route_renders_the_itinerary(client, stubbed):
    doc = call_tool(client, "fetch", {"id": "route:47.55811,7.58783__52.51739,13.39513"})["structuredContent"]
    assert "180 km" in doc["text"]
    assert "4 logged rides" in doc["text"]  # evidence is surfaced, not hidden
    # 200 total - 12 - 12 end walks = 176 min: the "core" hitching time the
    # planner's own result card headlines.
    assert "2h56" in doc["text"]
    assert doc["url"] == "https://maps.hitchwiki.org/dir/47.55811,7.58783/52.51739,13.39513"
    assert doc["metadata"]["rides"] == 1
    assert doc["metadata"]["found"] is True


def test_fetch_route_title_names_places_not_coordinates(client, stubbed):
    """The title is the string an assistant reads out and cites, so bare
    coordinates there would be a real cost."""
    doc = call_tool(client, "fetch", {"id": "route:47.55811,7.58783__52.51739,13.39513"})["structuredContent"]
    assert doc["title"] == "Basel → Berlin by hitchhiking"


def test_undated_ride_comment_renders_cleanly(client, monkeypatch):
    """Either half of the parenthetical can be missing; an undated ride must not
    render as 'anonymous (, waited 3 min)'."""
    monkeypatch.setattr(
        mcp_mod,
        "_spot_detail",
        lambda sid: {
            "spot": {"name": "Somewhere", "wait": 10},
            "rides": [
                {"comment": "No date on this one.", "hitchhiker_name": None, "submission_time": None, "wait": 36},
                {"comment": "No date, no wait.", "hitchhiker_name": "Zoe", "submission_time": "", "wait": None},
            ],
        },
    )
    text = call_tool(client, "fetch", {"id": "spot:52.51739_13.39513"})["structuredContent"]["text"]
    assert "anonymous (waited 36 min):" in text
    assert "(, " not in text
    assert 'Zoe: "No date, no wait."' in text


def test_fetch_route_weak_evidence_is_flagged(client, monkeypatch, stubbed):
    weak = json.loads(json.dumps(SAMPLE_ITINERARY))
    weak["legs"][1]["support"] = 1
    monkeypatch.setattr(mcp_mod, "_run_route", lambda *a, **k: {"found": True, "itineraries": [weak]})
    doc = call_tool(client, "fetch", {"id": "route:47.55811,7.58783__52.51739,13.39513"})["structuredContent"]
    assert "weak evidence" in doc["text"]


def test_fetch_route_with_no_result_is_a_document_not_an_error(client, monkeypatch, stubbed):
    """'No route' is a legitimate finding and must not read as 'impossible'."""
    monkeypatch.setattr(mcp_mod, "_run_route", lambda *a, **k: {"found": False, "itineraries": []})
    result = call_tool(client, "fetch", {"id": "route:47.55811,7.58783__52.51739,13.39513"})
    assert result["isError"] is False
    doc = result["structuredContent"]
    assert "isn't evidenced" in doc["text"]
    assert doc["metadata"]["found"] is False


def test_fetch_spot_surfaces_rider_comments(client, monkeypatch):
    monkeypatch.setattr(
        mcp_mod,
        "_spot_detail",
        lambda sid: {
            "spot": {"name": "Autobahn A9 services", "wait": 30, "distance": 120},
            "rides": [
                {
                    "comment": "Stand by the exit of the petrol station.",
                    "hitchhiker_name": "Ada",
                    "submission_time": "2025-03-22T19:11:50",
                    "wait": 15,
                },
                {"comment": "", "hitchhiker_name": "Bob", "submission_time": "2025-03-23T10:00:00", "wait": 5},
            ],
        },
    )
    doc = call_tool(client, "fetch", {"id": "spot:52.51739_13.39513"})["structuredContent"]
    assert "Autobahn A9 services" in doc["text"]
    assert "Stand by the exit" in doc["text"]
    assert "Ada (2025-03-22, waited 15 min)" in doc["text"]
    assert "Bob" not in doc["text"]  # a rating with no comment carries no advice
    assert doc["url"] == "https://maps.hitchwiki.org/spot/52.51739_13.39513"


@pytest.mark.parametrize(
    "ident,expected",
    [
        ("spot:52.51739_13.39513", ("spot", "52.51739_13.39513", None)),
        ("52.51739_13.39513", ("spot", "52.51739_13.39513", None)),  # bare
        ("https://maps.hitchwiki.org/spot/52.51739_13.39513", ("spot", "52.51739_13.39513", None)),
        ("route:47.55811,7.58783__52.51739,13.39513", ("route", (47.55811, 7.58783), (52.51739, 13.39513))),
        (
            "https://maps.hitchwiki.org/dir/47.55811,7.58783/52.51739,13.39513",
            ("route", (47.55811, 7.58783), (52.51739, 13.39513)),
        ),
    ],
)
def test_fetch_accepts_the_id_and_url_forms(ident, expected):
    """Models routinely pass back the `url` field instead of the `id` field."""
    assert mcp_mod._parse_document_id(ident) == expected


@pytest.mark.parametrize("ident", ["", "nonsense", "route:not-coords", "spot:", "route:999,999__0,0"])
def test_fetch_rejects_malformed_ids(ident):
    with pytest.raises(mcp_mod.ToolError):
        mcp_mod._parse_document_id(ident)


def test_fetch_unknown_spot_is_a_tool_error_not_a_protocol_error(client, monkeypatch):
    """The model should read this and retry with a real search result."""
    monkeypatch.setattr(mcp_mod, "_spot_detail", lambda sid: None)
    _, body = rpc(client, "tools/call", {"name": "fetch", "arguments": {"id": "spot:0.00000_0.00000"}})
    assert "error" not in body
    assert body["result"]["isError"] is True
    assert "No hitchhiking spot known" in body["result"]["content"][0]["text"]


def test_unknown_tool_is_a_protocol_error(client):
    _, body = rpc(client, "tools/call", {"name": "plan_hitchhiking_route", "arguments": {}})
    assert body["error"]["code"] == mcp_mod.INVALID_PARAMS


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
def test_spot_id_matches_map_convention():
    """Must equal generate_spot_id() in show.py, or every spot link 404s."""
    assert mcp_mod._spot_id(52.517389, 13.395131) == "52.51739_13.39513"


def test_route_ids_round_trip_through_parse(stubbed):
    """Ids must be self-contained: fetch gets them back with no session."""
    ident = mcp_mod._route_doc_id((47.55811, 7.58783), (52.51739, 13.39513))
    assert mcp_mod._parse_document_id(ident) == ("route", (47.55811, 7.58783), (52.51739, 13.39513))
