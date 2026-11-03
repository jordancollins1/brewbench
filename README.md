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
