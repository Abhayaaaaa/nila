# NILA: architecture and stack

NILA is the Nepal Ice Lake Atlas. What it is built from, and the parts that were
genuinely non-trivial.

There are **two applications** here sharing one scoring model:

1. **The hosted web app** (`page_template.html` compiled into `web/public/` plus
   `web/functions/`): a map-first single page, with a Cloudflare Pages Function
   and a D1 database behind it so community reports are shared between visitors.
   This is the thing you deploy.
2. **The full stack version** (`backend/` + `frontend/`): Flask API, PostgreSQL
   with PostGIS, community reports with a moderation queue. This is where the
   risk scores are computed and where the spatial queries live.

The same scoring model is implemented twice, in Python and in JavaScript, so the
server and the browser produce identical numbers from identical inputs.

---

## 1. Stack

### The hosted app
| Piece | Why |
|---|---|
| Leaflet 1.9 | 2D map engine. Pan, zoom, touch, tile handling |
| MapLibre GL 6 | The 3D terrain view, lazy-loaded on first press |
| Leaflet.markercluster | Groups dense markers, spiderfies on click |
| Cloudflare Pages | Static hosting, free tier |
| Cloudflare Pages Functions | The API. Any file under `functions/` becomes a route |
| Cloudflare D1 | SQLite at the edge, where reports are stored |

No framework and no build step beyond one Python script. Plain HTML, CSS custom
properties and a single IIFE of vanilla JavaScript. Leaflet and MarkerCluster are
vendored and **inlined into the output at build time**, so the page has no
third-party runtime dependency and still works opened straight from disk.

Three basemaps, all from Esri (Terrain, Satellite, Streets), all keyless. No
Google or Apple Maps key, no billing account. A vector outline of Nepal is drawn
from embedded GeoJSON regardless of tiles, so there is always a usable map even
offline or where tile hosts are blocked.

> Note: an earlier version used CARTO for street tiles. CARTO began requiring an
> API key and started returning watermarked tiles, so Streets moved to Esri. The
> app now also listens for `tileerror` and falls back to Terrain if a basemap
> fails outright. That does not catch a provider that still returns a valid but
> watermarked image, which is exactly how the CARTO change slipped through.

### The full stack version
| Piece | Why |
|---|---|
| PostgreSQL 16 + PostGIS 3.4 | Spatial types and indexes. Lakes are `GEOMETRY(Point, 4326)` |
| Flask 3 + psycopg2 | HTTP layer, `RealDictCursor` so rows arrive as dicts |
| APScheduler | Background job that rescores every lake on an interval |
| gunicorn + Docker Compose | Production serving, `postgis/postgis:16-3.4` for the DB |

Tables: `lakes`, `risk_scores` (append-only time series with a `JSONB` breakdown),
`user_reports`, plus a `latest_risk_scores` view using `DISTINCT ON (lake_id)
... ORDER BY lake_id, computed_at DESC`.

Nearby-lake queries cast to geography so distances come out in real metres:

```sql
WHERE ST_DWithin(
  l.geom::geography,
  ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
  %(radius_m)s
)
```

### Data pipeline
| Piece | Why |
|---|---|
| `world-atlas` (npm) | Natural Earth 10m boundaries as TopoJSON |
| `topojson-client` | TopoJSON to GeoJSON |
| `scripts/geo/extract_geo.js` | Clips and simplifies, writes `geo_context.json` |
| `build_page.py` | Injects data and inlines Leaflet, emits all three builds |

### Testing
Playwright driving real Chromium, against the real Wrangler dev server and a real
local D1 database. Not unit tests: this app is almost entirely interaction, so the
tests click actual screen coordinates and assert what happened.

---

## 2. The scoring model

Six weighted inputs producing 0 to 100 (`backend/app/services/risk_engine.py`,
mirrored in the page's JavaScript):

| Factor | Weight | Normalisation |
|---|---:|---|
| Lake-area change | 30 | `pct / 15`, saturating at 15% growth |
| Nearby earthquakes | 20 | `max(count/5, (maxMag-4)/2.5)` |
| Rain and temperature | 20 | `0.6*(precipAnom/60) + 0.4*(tempAnom/3)` |
| Dam type | 15 | moraine 1.0, ice 0.75, bedrock 0.15 |
| Slope steepness | 10 | `deg / 35` |
| Community reports | 5 | severity-weighted, x1.3 for high-signal conditions |

Each factor is clamped to 0..1, multiplied by its weight, summed. Bands: under 25
low, 25-49 medium, 50-74 high, 75+ very high.

**Keeping two implementations in agreement** is the interesting constraint. They
were verified by feeding the browser mocked API responses and checking the
arithmetic matched the Python output exactly.

### External data
- **USGS earthquakes**: free, keyless, CORS-enabled. One bounding-box query for
  the whole region, then each lake counts events within 100 km client-side,
  rather than 24 separate calls.
- **Open-Meteo**: free, keyless, CORS-enabled. Two multi-location calls (all lake
  coordinates comma-separated in one request): the last 30 days, and the same 30
  days five years earlier, to get an anomaly rather than a raw value.
- **Sentinel-2 via Copernicus** (`backend/app/services/sentinel.py`): OAuth2
  client-credentials plus an NDWI water-index evalscript through the Statistical
  API. Wired up but needs credentials you create, so it falls back to stored area
  history.

`Promise.allSettled` is deliberate: one dead API degrades that factor to zero and
labels it, instead of taking down the page.

---

## 2b. The 3D terrain view

Leaflet cannot tilt. It projects to a flat plane and has no camera, so there is
no amount of CSS that turns it into a perspective view of a mountain range.
Adding 3D therefore meant a second map engine running over the same ground.

| Piece | Choice | Why |
|---|---|---|
| Engine | MapLibre GL JS 6 | WebGL, real camera, `setTerrain` on a DEM source, BSD licensed |
| Elevation | Tilezen terrarium tiles on AWS Open Data | Keyless, `elevation_m = (R*256 + G + B/256) - 32768`, zoom 15 max |
| Imagery | Esri World Imagery | Keyless, already trusted by the 2D map |

Three decisions worth recording:

**It is lazy-loaded, not bundled.** MapLibre is about 1.2 MB against a 336 KB
page, and most visits never press the button. It ships as separate files under
`web/public/vendor/maplibre/` and is pulled in with a dynamic `import()` on
first use. The three `.mjs` files have to stay side by side: the entry module
imports the shared chunk by relative path and spawns its worker via
`new URL("./maplibre-gl-worker.mjs", import.meta.url)`.

**Markers are added immediately, not on the map's `load` event.** `load` waits
for every source to finish, so one failing tile host means it never fires and
the lakes never appear at all. Markers do not need the style. MapLibre places
them on the terrain surface and hides them when a ridge comes between the
marker and the camera, which is exactly the behaviour you want here.

**The camera is capped below the DEM's limit.** Terrarium tops out at zoom 15,
so the 3D camera maxes at 15.5 rather than stretching a tile that has no data
behind it.

Both engines share one selection model: clicking a lake pin in 3D runs the same
`selectLake` as clicking a circle in 2D, and `focusOn` flies whichever camera is
currently on screen. Leaving 3D copies the centre and zoom back to Leaflet, so
the flat map picks up where the tilted one left off. Dropping a report pin
forces a return to 2D first, because "where exactly did I click" is ambiguous
under a tilted camera.

---

## 3. The reports system

Reports can be scoped three ways, which is what makes them usable by someone who
may not know exactly where they were:

| Scope | What is stored |
|---|---|
| `point` | lat/lon from clicking the map |
| `site` | a lake or settlement id from the inventory, plus its coordinates |
| `district` | one of Nepal's 77 districts, plus a centroid where known |

A report counts as "near" a lake or village when **any** of these hold: it is
tagged to that exact site, it is in the same district, or it is a point report
within 25 km (haversine). That rule drives both the per-location report list and
the community-reports factor in the score.

### Abuse handling
Four layers, in `web/functions/api/reports.js`:

1. **Honeypot** field hidden off-screen. Bots fill it, people do not. Silently
   accepted and discarded so the bot does not learn it failed.
2. **Rate limit**, 12 submissions per hashed IP per hour. Hashed with SHA-256 and
   a salt, so raw addresses are never stored. Set relatively high because a
   village may share one connection.
3. **Spam heuristics** on the text: URLs, repeated characters, very low character
   variety, known spam keywords. Scoring past 0.6 stores the report with
   `status = 'hidden'` so it never reaches the feed.
4. **Server-side validation** of every field. Unknown condition, missing
   coordinates on a point report and out-of-range severity are all rejected.

Reports are labelled as unverified community observations everywhere they appear.
That framing matters: this is a hazard app, and a stranger could act on it.

---

## 4. The parts that were genuinely fiddly

### Overlapping click targets (three separate bugs)
The single most stubborn class of bug in this project, hit three times:

1. Invisible per-marker hit circles overlapped, so one marker's target covered its
   neighbours and ate their clicks. About half the map was unclickable.
2. The map's text label sat on top of everything and swallowed clicks meant for
   markers underneath it.
3. The search dropdown rendered behind the side panel, so results were
   unclickable whenever the panel was open.

Moving to Leaflet plus MarkerCluster removed the first two by construction. The
third was an explicit `z-index` stack. A fourth variant appears in pin-drop mode:
markers would intercept the click meant for the map, so
`body.picking .leaflet-interactive { pointer-events: none }` hands every click to
the map while picking.

**The testing lesson:** Playwright's `locator.click()` scrolls the element into
view and dispatches straight to it, routing around z-order, overlap and viewport
position, which is exactly where these bugs live. Every one of them was found only
by clicking real screen coordinates.

### Responsive failure mode
Under 920px the layout stacked and the detail panel rendered about 1,400px below
the fold, so selecting a lake looked like nothing happened. The panel is now a
bottom sheet on small screens, and opening it scrolls the map back into view.

### Boundary clipping and simplification
`scripts/geo/extract_geo.js` implements two classic algorithms by hand:

- **Sutherland-Hodgman** to clip polygon rings to a window around Nepal, so the
  neighbour countries do not drag in their whole geometry
- **Douglas-Peucker** to simplify, at a tighter tolerance for Nepal (0.004) than
  its neighbours (0.02)

An earlier attempt used a 110m dataset where Nepal was 23 vertices and looked like
a wrong-shaped blob. The 10m source gives about 550 vertices in roughly 18 KB.

### Colour accessibility
Risk levels use a fixed status palette identical in both themes. The first ramp
failed a colourblind-separation check: medium and high measured Delta E 9.9 apart,
under the 15 floor, meaning two adjacent severity levels were not reliably
distinguishable. On a hazard tool that is a real defect, not a cosmetic one. Every
risk colour is now paired with a written level and a four-bar severity meter, so
nothing rests on colour alone, and the risk list is a full table view of the same
data.

### Theming
Three states, not two: explicit light, explicit dark, and the default where the OS
decides and nothing is stamped on the root element. Every colour is a custom
property defined on bare `:root`, redefined under `@media (prefers-color-scheme:
dark)` guarded by `:root:not([data-theme="light"])`, and again under
`:root[data-theme="dark"]`. A colour defined only inside a media query renders one
theme's text on the other theme's background.

---

## 5. File map

```
nila/
├── page_template.html      the app source (~1,700 lines)
├── build_page.py           injects data, inlines Leaflet, emits three builds
├── data/
│   ├── schema.sql          PostGIS schema
│   ├── sample_lakes.csv    24 lakes from GLOF literature
│   ├── settlements.json    57 downstream villages and towns
│   ├── glof_events.json    7 recorded historical outburst floods
│   └── districts.json      Nepal's 77 districts by province
├── web/                    ← the thing you deploy
│   ├── public/index.html   built app
│   ├── public/vendor/maplibre/   MapLibre, loaded only when 3D is opened
│   ├── functions/api/reports.js   the API
│   ├── schema.sql          D1 schema
│   └── wrangler.toml.cli   Cloudflare config, for CLI deploys only
├── backend/                Flask + PostGIS version
│   └── app/services/risk_engine.py   the scoring model
├── frontend/               Leaflet assets, vendored
├── scripts/
│   ├── import_lakes.py     CSV to PostGIS
│   ├── recompute_risk.py   full rescore
│   └── geo/extract_geo.js  Natural Earth clip and simplify
└── dist/nila.html          standalone single file
```

---

## 6. Running it

```
python build_page.py                       # rebuild from template + data
cd web && npx wrangler pages dev public    # real API + local database
```

Production deploys happen automatically: Cloudflare Pages is connected to the
GitHub repo and rebuilds on every push to `main`. Nothing to run.

Full deployment walkthrough in `DEPLOY.md`.
