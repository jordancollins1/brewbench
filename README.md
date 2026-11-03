# BrewBench

BrewBench is a self-hosted brewing planner for beer, cider, and seltzer. It includes recipe storage, equipment-aware water planning, mash profiles, brew-day timers, additives, an editable hop catalog, style targets, and an optional AI recipe builder.

## Run with Docker Compose

1. Change `API_TOKEN` in `docker-compose.yml`.
2. Add an `ANTHROPIC_API_KEY` if you want to use the AI recipe builder.
3. Pull and start the published image:

```bash
docker compose pull
docker compose up -d
```

Open [http://localhost:1212](http://localhost:1212).

The published image is [ghcr.io/jordancollins1/brewbench:latest](https://ghcr.io/jordancollins1/brewbench).
GitHub Actions rebuilds and publishes it automatically whenever `main` changes.

### Unraid container settings

When creating the container manually in Unraid, add a port mapping. The application
listens on container port `1212`; publish it to any available host port:

```text
Host port: 1212
Container port: 1212
Protocol: TCP
```

Then open `http://UNRAID_IP:1212`. The port shown in the container log is the
container-side port; it is not reachable from the LAN unless the Unraid port
mapping is present. If host port `1212` is already in use, map `1213:1212` and
open `http://UNRAID_IP:1213`.

The health check is available at `/api/health` and should return
`{"status":"ok"}`.

The port defaults to `1212`. To use another port, set `PORT` and update the host-side mapping in `docker-compose.yml`, for example:

```yaml
ports: ["8080:8080"]
environment:
  PORT: 8080
```

Recipe data is stored in the mounted `data/` directory.

## Features

- Beer, cider, and seltzer recipes
- BeerSmith-inspired recipe calculations and style targets
- BrewZilla, Grainfather, Anvil Foundry, BrewEasy, BIAB, and traditional system presets
- Mash profiles with generated timers
- Equipment-aware mash, sparge, pre-boil, and kettle-capacity calculations
- US and metric display units
- Editable hop catalog with default alpha acids
- Honey, sugar, DME, lactose, maple syrup, yeast nutrient, Whirlfloc, Irish moss, and pectic enzyme additions
- Optional Anthropic-powered AI recipe builder
