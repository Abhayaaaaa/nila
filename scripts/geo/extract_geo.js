const topo = require('world-atlas/countries-10m.json');
const { feature } = require('topojson-client');

const fc = feature(topo, topo.objects.countries);
const want = new Set(['Nepal','India','China','Bhutan','Bangladesh']);
const WIN = { w: 78.5, e: 91.5, s: 24.5, n: 32.2 };

// Clip rings to the window with Sutherland-Hodgman, then round coords.
function clipRing(ring) {
  const edges = [
    { inside: p => p[0] >= WIN.w, x: WIN.w, axis: 0 },
    { inside: p => p[0] <= WIN.e, x: WIN.e, axis: 0 },
    { inside: p => p[1] >= WIN.s, x: WIN.s, axis: 1 },
    { inside: p => p[1] <= WIN.n, x: WIN.n, axis: 1 },
  ];
  let out = ring;
  for (const e of edges) {
    const input = out; out = [];
    for (let i = 0; i < input.length; i++) {
      const cur = input[i], prev = input[(i + input.length - 1) % input.length];
      const ci = e.inside(cur), pi = e.inside(prev);
      const cross = () => {
        const t = (e.x - prev[e.axis]) / (cur[e.axis] - prev[e.axis]);
        return e.axis === 0
          ? [e.x, prev[1] + t * (cur[1] - prev[1])]
          : [prev[0] + t * (cur[0] - prev[0]), e.x];
      };
      if (ci) { if (!pi) out.push(cross()); out.push(cur); }
      else if (pi) out.push(cross());
    }
    if (!out.length) return null;
  }
  return out;
}

// Douglas-Peucker so the file stays small without going blocky.
function simplify(pts, tol) {
  if (pts.length < 3) return pts;
  const sq = (a,b) => (a[0]-b[0])**2 + (a[1]-b[1])**2;
  function seg(p, a, b) {
    let t = 0; const d = sq(a,b);
    if (d) t = Math.max(0, Math.min(1, ((p[0]-a[0])*(b[0]-a[0]) + (p[1]-a[1])*(b[1]-a[1])) / d));
    return sq(p, [a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])]);
  }
  function dp(s, e, keep) {
    let maxD = 0, idx = -1;
    for (let i = s+1; i < e; i++) { const d = seg(pts[i], pts[s], pts[e]); if (d > maxD) { maxD = d; idx = i; } }
    if (maxD > tol*tol) { dp(s, idx, keep); keep.add(idx); dp(idx, e, keep); }
  }
  const keep = new Set([0, pts.length-1]);
  dp(0, pts.length-1, keep);
  return pts.filter((_, i) => keep.has(i));
}

const r = n => [Math.round(n[0]*1000)/1000, Math.round(n[1]*1000)/1000];
const out = { type:'FeatureCollection', features: [] };

for (const f of fc.features) {
  if (!want.has(f.properties.name)) continue;
  const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
  const kept = [];
  for (const poly of polys) {
    const rings = [];
    for (const ring of poly) {
      const c = clipRing(ring);
      if (!c || c.length < 4) continue;
      // Nepal is the subject: keep it crisper than the neighbours.
      const tol = f.properties.name === 'Nepal' ? 0.004 : 0.02;
      let s = simplify(c, tol).map(r);
      if (s.length >= 4) rings.push(s);
    }
    if (rings.length) kept.push(rings);
  }
  if (!kept.length) continue;
  out.features.push({
    type:'Feature',
    properties:{ name: f.properties.name },
    geometry: kept.length === 1
      ? { type:'Polygon', coordinates: kept[0] }
      : { type:'MultiPolygon', coordinates: kept }
  });
}

const s = JSON.stringify(out);
require('fs').writeFileSync('/home/claude/glof-app/geo_context.json', s);
console.log('bytes', s.length);
for (const f of out.features) {
  let n = 0; const walk = c => Array.isArray(c[0]) ? c.forEach(walk) : n++;
  walk(f.geometry.coordinates);
  const pts = []; const w2 = c => Array.isArray(c[0]) ? c.forEach(w2) : pts.push(c);
  w2(f.geometry.coordinates);
  const lo = pts.map(p=>p[0]), la = pts.map(p=>p[1]);
  console.log(f.properties.name.padEnd(11), f.geometry.type.padEnd(12), 'pts', String(n).padStart(4),
    'lon', Math.min(...lo).toFixed(2), Math.max(...lo).toFixed(2),
    'lat', Math.min(...la).toFixed(2), Math.max(...la).toFixed(2));
}
