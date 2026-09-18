#!/usr/bin/env python3
"""
Builds the NILA (Nepal Ice Lake Atlas) single-page app from:
  - lakes_export.json      lakes + engine-computed risk scores
  - geo_context.json       Natural Earth boundaries clipped around Nepal
  - data/settlements.json  downstream villages and towns
  - data/glof_events.json  recorded historical outburst floods
  - data/districts.json    the 77 districts, for general-area reports
  - page_template.html     markup/CSS/JS with __SLOT__ placeholders
  - frontend/static/vendor Leaflet + MarkerCluster, inlined so the page has
                           no third-party runtime dependency

Emits:
  - dist/artifact.html      body-only, for publishing as an Artifact
  - dist/nila.html          full document, for double-clicking locally
  - web/public/index.html   same document, for Cloudflare Pages
"""
import datetime
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
WEB = os.path.join(HERE, "web", "public")
VENDOR = os.path.join(HERE, "frontend", "static", "vendor")
os.makedirs(DIST, exist_ok=True)
os.makedirs(WEB, exist_ok=True)


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


lakes = json.loads(read(HERE, "lakes_export.json"))
geo = json.loads(read(HERE, "geo_context.json"))
settle = json.loads(read(HERE, "data", "settlements.json"))
events = json.loads(read(HERE, "data", "glof_events.json"))
districts = json.loads(read(HERE, "data", "districts.json"))
template = read(HERE, "page_template.html")

# Leaflet's own CSS references marker images by relative URL. The app uses
# divIcons and circleMarkers only, so strip those rules rather than ship
# broken image requests.
leaflet_css = read(VENDOR, "leaflet", "leaflet.css")
leaflet_js = read(VENDOR, "leaflet", "leaflet.js")
cluster_css = read(VENDOR, "markercluster", "MarkerCluster.css") + "\n" + read(
    VENDOR, "markercluster", "MarkerCluster.Default.css"
)
cluster_js = read(VENDOR, "markercluster", "leaflet.markercluster.js")

# Which risk inputs resolved to live data when the scores were frozen.
srcs = {}
for lk in lakes:
    for k, v in (lk.get("sources") or {}).items():
        srcs.setdefault(k, set()).add(v)


def status(vals):
    vals = {v for v in vals if v}
    if not vals:
        return "unknown"
    if all(v == "error" for v in vals):
        return "unavailable"
    if all(v and v.startswith("mock") for v in vals):
        return "fallback"
    return "live"


meta = {
    "snapshot_date": datetime.date.today().isoformat(),
    "inputs": {k: status(v) for k, v in srcs.items()},
}

places = {"places": settle["places"], "basin_parents": settle["basin_parents"]}

compact = (",", ":")
out = template
for slot, value in [
    ("__LAKES__", json.dumps(lakes, separators=compact)),
    ("__GEO__", json.dumps(geo, separators=compact)),
    ("__META__", json.dumps(meta, separators=compact)),
    ("__PLACES__", json.dumps(places, separators=compact)),
    ("__EVENTS__", json.dumps(events["events"], separators=compact)),
    ("__DISTRICTS__", json.dumps(
        {"provinces": districts["provinces"], "centroids": districts["centroids"]},
        separators=compact)),
    ("__LEAFLET_CSS__", leaflet_css),
    ("__LEAFLET_JS__", leaflet_js),
    ("__CLUSTER_CSS__", cluster_css),
    ("__CLUSTER_JS__", cluster_js),
]:
    if slot not in out:
        raise SystemExit(f"template is missing the {slot} slot")
    out = out.replace(slot, value)

# Artifact build: body content only, the tool supplies the page skeleton.
with open(os.path.join(DIST, "artifact.html"), "w", encoding="utf-8") as f:
    f.write(out)

standalone = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5">
<meta name="description" content="NILA, the Nepal Ice Lake Atlas: glacial lake outburst flood (GLOF) risk screening for Nepal. A demonstration prototype, not a warning system.">
<meta name="author" content="Abhaya Shrestha">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%8F%94%EF%B8%8F%3C/text%3E%3C/svg%3E">
<style>
  *{{box-sizing:border-box}}
  html,body{{margin:0;padding:0;height:100%}}
  img{{max-width:100%}}
  [hidden]{{display:none!important}}
</style>
{out}
</body>
</html>
"""
for path in (os.path.join(DIST, "nila.html"), os.path.join(WEB, "index.html")):
    with open(path, "w", encoding="utf-8") as f:
        f.write(standalone)

# MapLibre powers the 3D terrain view. It is ~1.2 MB, and most visits never open
# 3D, so it is served as separate files and imported on first use rather than
# inlined like Leaflet. The three .mjs files must stay side by side: the entry
# module imports the shared chunk by relative path and spawns its worker with
# new URL("./maplibre-gl-worker.mjs", import.meta.url).
ml_src = os.path.join(VENDOR, "maplibre")
ml_dst = os.path.join(WEB, "vendor", "maplibre")
os.makedirs(ml_dst, exist_ok=True)
for name in ("maplibre-gl.mjs", "maplibre-gl-shared.mjs",
             "maplibre-gl-worker.mjs", "maplibre-gl.css"):
    shutil.copyfile(os.path.join(ml_src, name), os.path.join(ml_dst, name))

print(f"lakes {len(lakes)} | places {len(settle['places'])} | events {len(events['events'])} "
      f"| districts {sum(len(p['districts']) for p in districts['provinces'])}")
print("input status:", meta["inputs"])
for p in (os.path.join(DIST, "artifact.html"),
          os.path.join(DIST, "nila.html"),
          os.path.join(WEB, "index.html")):
    print(f"  {os.path.relpath(p, HERE):28s} {os.path.getsize(p):,} bytes")
