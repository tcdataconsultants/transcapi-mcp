"""MCP server exposing TransCAPI to AI assistants.

Each tool is one TransCAPI endpoint, described so an assistant can chain them:
find a place or stop, then ask what is leaving it, then follow one bus or
train. Responses are the API's own JSON, so every field an assistant sees is
documented at https://www.transcapi.com/docs.

Needs a TransCAPI key in TRANSCAPI_API_KEY (free at
https://www.transcapi.com/signup). TRANSCAPI_BASE_URL overrides the API
address.
"""
import json
import logging
import os

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from transcapi_mcp import __version__

# httpx logs every request at INFO; on an MCP client's log that is noise.
logging.getLogger("httpx").setLevel(logging.WARNING)

BASE_URL = os.environ.get("TRANSCAPI_BASE_URL", "https://api.transcapi.com").rstrip("/")

INSTRUCTIONS = """\
TransCAPI covers public transport in Great Britain (England, Scotland, Wales).

How to use these tools well:
- Resolve names first. Use search_places for a town, postcode or stop name,
  and nearby_stops / nearby_stations for a location. Bus stops are identified
  by `atcocode`, rail stations by 3-letter CRS code (LDS = Leeds).
- Stops sharing a name are told apart by `towards` (where the buses go).
  Mention it when there is more than one.
- Every departure has `source`: `darwin` or `avl` or `siri_vm` means live,
  `gtfs_scheduled` means timetable only. Say which when reporting a time.
- To follow one bus or train, pass its `trip_id` to bus_service or
  train_service.
- `null` means unknown, not zero. A `422 outside_coverage` from plan_journey
  means that area is not covered, not that there is no route.
- Apps showing this data must credit its sources; see
  https://www.transcapi.com/docs/data-sources.
"""

mcp = MCPServer(
    name="transcapi",
    title="TransCAPI",
    description="Live bus and rail departures, vehicles, disruptions and journey "
                "planning for Great Britain.",
    instructions=INSTRUCTIONS,
    website_url="https://www.transcapi.com",
    version=__version__,
)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True, idempotent_hint=True)


class TransCAPIError(ToolError):
    """An API error, carrying the API's own JSON error body.

    A ToolError, so the client gets is_error with this message; any other
    exception would reach the model only as "Error executing tool"."""


def _get(path, **params):
    key = os.environ.get("TRANSCAPI_API_KEY")
    if not key:
        raise TransCAPIError(json.dumps({"error": {
            "code": "missing_api_key",
            "message": "Set TRANSCAPI_API_KEY. Keys are free at https://www.transcapi.com/signup",
        }}))
    params = {k: v for k, v in params.items() if v is not None}
    try:
        resp = httpx.get(
            f"{BASE_URL}{path}",
            params=params,
            headers={"X-Api-Key": key, "User-Agent": f"transcapi-mcp/{__version__}"},
            timeout=45,
        )
    except httpx.HTTPError as exc:
        raise TransCAPIError(json.dumps({"error": {"code": "unreachable", "message": str(exc)}}))
    # Raised rather than returned so the client marks the result as an error;
    # the API's JSON is kept as the message because it says what was wrong
    # ("outside_coverage", "not_found") in a way an assistant can act on.
    if resp.status_code >= 400:
        raise TransCAPIError(resp.text)
    return resp.text


@mcp.tool(annotations=READ_ONLY)
def search_places(query: str, lat: float | None = None, lon: float | None = None,
                  limit: int = 10) -> str:
    """Find towns, villages, postcodes (full or partial, e.g. "S1") and stops by
    name. Places sharing a name are ranked by size. Give lat/lon to sort by
    distance from there."""
    return _get("/v1/places.json", query=query, lat=lat, lon=lon, limit=limit)


@mcp.tool(annotations=READ_ONLY)
def nearby_stops(lat: float, lon: float, radius: int = 400, limit: int = 20) -> str:
    """Bus, tram and rail stops within `radius` metres of a point, nearest first.
    Each has an `atcocode` for bus_departures and `towards` saying which way its
    buses go."""
    return _get("/v1/bus/stops.json", lat=lat, lon=lon, radius=radius, limit=limit)


@mcp.tool(annotations=READ_ONLY)
def nearby_stations(lat: float, lon: float, radius: int = 3000, limit: int = 10) -> str:
    """Rail stations within `radius` metres of a point, with their CRS codes for
    rail_departures."""
    return _get("/v1/rail/stations.json", lat=lat, lon=lon, radius=radius, limit=limit)


@mcp.tool(annotations=READ_ONLY)
def bus_departures(atcocode: str, board: str = "departures", minutes_ahead: int = 60,
                   limit: int = 15) -> str:
    """What is leaving (or, with board="arrivals" or "both", arriving at) a bus
    stop. Tracked buses have an expected time and `delay_seconds`; others show
    the timetabled time with source `gtfs_scheduled`."""
    return _get(f"/v1/bus/stop_timetables/{atcocode}.json", type=board,
                to_offset=minutes_ahead, limit=limit, live="true")


@mcp.tool(annotations=READ_ONLY)
def rail_departures(crs_code: str, board: str = "departures", minutes_ahead: int = 60,
                    limit: int = 15) -> str:
    """Live trains leaving (or arriving at, with board="arrivals" or "both") a
    station: expected times, platforms, cancellations and delay reasons from
    National Rail, plus station messages. `crs_code` is the 3-letter code,
    e.g. LDS for Leeds."""
    return _get(f"/v1/rail/station_timetables/{crs_code.upper()}.json", type=board,
                to_offset=minutes_ahead, limit=limit)


@mcp.tool(annotations=READ_ONLY)
def train_service(trip_id: str) -> str:
    """Every station one train calls at. For a train running today, each call has
    live status, expected and actual times, and the platform at its next
    station. Take `trip_id` from rail_departures."""
    return _get(f"/v1/rail/services/{trip_id}.json")


@mcp.tool(annotations=READ_ONLY)
def bus_service(trip_id: str) -> str:
    """Every stop one bus journey calls at, the days it runs, and where the bus is
    now if it is running. Take `trip_id` from bus_departures or live_buses."""
    return _get(f"/v1/bus/services/{trip_id}.json")


@mcp.tool(annotations=READ_ONLY)
def live_buses(lat: float, lon: float, radius: int = 1000, line: str | None = None,
               operator: str | None = None) -> str:
    """Buses on the road within `radius` metres (up to 10000) of a point, nearest
    first, each linked to the journey it is working (`trip_id`) and with
    `delay_seconds` where tracked. Filter by `line` (e.g. "52") or operator."""
    return _get("/v1/bus/vehicles.json", lat=lat, lon=lon, radius=radius,
                line=line, operator=operator)


@mcp.tool(annotations=READ_ONLY)
def disruptions(lat: float | None = None, lon: float | None = None, radius: int | None = None,
                mode: str | None = None, operator: str | None = None, line: str | None = None,
                path: str | None = None, path_radius: int | None = None,
                limit: int = 20) -> str:
    """Planned works, incidents and line status: bus and tram across Great Britain,
    plus Tube, DLR, Overground, Elizabeth line and London Trams. Filter by area
    (lat/lon/radius), mode, operator or line. To ask what affects a particular
    journey, pass its route as `path` (an encoded polyline, e.g. a leg's
    `leg_geometry` from plan_journey): line numbers repeat across towns, so this
    is more reliable than `line`."""
    return _get("/v1/disruptions.json", lat=lat, lon=lon, radius=radius, mode=mode,
                operator=operator, line=line, path=path, path_radius=path_radius,
                limit=limit)


@mcp.tool(annotations=READ_ONLY)
def plan_journey(from_lat: float, from_lon: float, to_lat: float, to_lon: float,
                 datetime: str | None = None, arrive_by: bool = False,
                 include_steps: bool = False, limit: int = 3) -> str:
    """Public transport journeys between two points, with walking, fares and live
    positions of buses already running. `datetime` is ISO 8601 (default now);
    `arrive_by` treats it as the latest arrival. Currently covers South and West
    Yorkshire and West Sussex: elsewhere it returns 422 outside_coverage, which
    means not covered rather than no route."""
    return _get("/v1/journey.json", from_lat=from_lat, from_lon=from_lon, to_lat=to_lat,
                to_lon=to_lon, datetime=datetime, arrive_by=str(arrive_by).lower(),
                include_steps=str(include_steps).lower(), limit=limit)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
