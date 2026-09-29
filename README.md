# TransCAPI MCP server

Lets AI assistants such as Claude answer questions about public transport in
Great Britain with live data: *"When's the next train from Leeds to York, and
is it on time?"*, *"Where's the 52 bus?"*, *"Is anything disrupting my route
home?"*

It connects an assistant to [TransCAPI](https://www.transcapi.com), which
covers England, Scotland and Wales: stops and places, bus and rail departures
with live running, live bus positions, disruptions and journey planning.

## Setup

1. Get a free API key at <https://www.transcapi.com/signup> (1,000 requests a
   day, every endpoint).
2. Add the server to your MCP client. For Claude Desktop, in
   `claude_desktop_config.json`:

   ```json
   {
     "mcpServers": {
       "transcapi": {
         "command": "uvx",
         "args": ["transcapi-mcp"],
         "env": { "TRANSCAPI_API_KEY": "your-key" }
       }
     }
   }
   ```

   For Claude Code:

   ```bash
   claude mcp add transcapi --env TRANSCAPI_API_KEY=your-key -- uvx transcapi-mcp
   ```

   Or install it yourself with `pip install transcapi-mcp` and run
   `transcapi-mcp`.

## Tools

| Tool | What it answers |
|---|---|
| `search_places` | Find a town, village, postcode or stop by name |
| `nearby_stops` | Bus, tram and rail stops near a point, with which way the buses go |
| `nearby_stations` | Rail stations near a point |
| `bus_departures` | What's leaving (or arriving at) a bus stop, with live times for tracked buses |
| `rail_departures` | Live trains at a station: expected times, platforms, cancellations, delay reasons |
| `train_service` | Every station one train calls at, live for today |
| `bus_service` | Every stop one bus journey calls at, and where the bus is now |
| `live_buses` | Buses on the road near a point, with delays where tracked |
| `disruptions` | Planned works, incidents and line status, by area, line or a journey's route |
| `plan_journey` | Public transport journeys between two points (South and West Yorkshire and West Sussex for now) |

All tools are read-only.

## Configuration

| Variable | |
|---|---|
| `TRANSCAPI_API_KEY` | Required. Your TransCAPI key. |
| `TRANSCAPI_BASE_URL` | Optional. Defaults to `https://api.transcapi.com`. |

## Attribution

TransCAPI is built on official open data. If you show its data to other
people, credit the sources as described at
<https://www.transcapi.com/docs/data-sources>.

## Licence

MIT.
