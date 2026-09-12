# Boundary extraction

Regenerates `geo_context.json` (the country outlines the map draws) from the
Natural Earth 10m dataset shipped inside the `world-atlas` npm package.

```
cd scripts/geo
npm install
npm run build      # writes ../../geo_context.json
```

What it does, in order:

1. Converts the TopoJSON in `world-atlas/countries-10m.json` to GeoJSON.
2. Keeps Nepal plus India, China, Bhutan and Bangladesh for context.
3. Clips every ring to a window around Nepal with the Sutherland-Hodgman
   polygon-clipping algorithm, so neighbour polygons do not carry the whole
   country's geometry.
4. Simplifies with Douglas-Peucker, at a tighter tolerance for Nepal (0.004)
   than for neighbours (0.02), since Nepal is the subject.
5. Rounds coordinates to 3 decimal places.

Result: roughly 18 KB of GeoJSON, with Nepal at about 550 vertices.
