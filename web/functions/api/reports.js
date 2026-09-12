/**
 * GET  /api/reports  -> recent published reports
 * POST /api/reports  -> submit one
 *
 * Cloudflare Pages Function. `env.DB` is the D1 binding declared in
 * wrangler.toml. If D1 is not bound the endpoints return 503 and the
 * frontend quietly falls back to browser-local storage.
 */

const CONDITIONS = new Set([
  "normal", "rising_water", "new_cracks", "seepage", "debris", "noise", "other",
]);

const MAX_BODY = 1200;
const RATE_LIMIT = 12;          // submissions per IP per hour (villages may share one connection)
const RATE_WINDOW_MS = 60 * 60 * 1000;

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "content-type",
      "access-control-allow-methods": "GET,POST,OPTIONS",
    },
  });

export const onRequestOptions = () => json({ ok: true });

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Cheap heuristics. Anything scoring high is stored but hidden from the feed. */
function spamScore(body, reporter) {
  const text = `${body || ""} ${reporter || ""}`;
  let score = 0;
  if (/https?:\/\/|www\./i.test(text)) score += 0.5;
  if (/(.)\1{7,}/.test(text)) score += 0.3;
  if (text.length > 4000) score += 0.3;
  if (text && new Set(text.toLowerCase().replace(/\s/g, "")).size < 4) score += 0.3;
  if (/\b(viagra|casino|crypto airdrop|free money|loan offer)\b/i.test(text)) score += 0.6;
  return Math.min(score, 1);
}

export async function onRequestGet({ env, request }) {
  if (!env.DB) return json({ error: "database not configured" }, 503);

  const url = new URL(request.url);
  const limit = Math.min(parseInt(url.searchParams.get("limit") || "300", 10) || 300, 500);

  try {
    const { results } = await env.DB.prepare(
      `SELECT id, scope, target_kind, target_id, target_name, district,
              lat, lon, reporter, condition, severity, body, created_at
         FROM reports
        WHERE status = 'published'
        ORDER BY created_at DESC
        LIMIT ?1`
    ).bind(limit).all();
    return json({ reports: results || [] });
  } catch (err) {
    return json({ error: "query failed", detail: String(err) }, 500);
  }
}

export async function onRequestPost({ env, request }) {
  if (!env.DB) return json({ error: "database not configured" }, 503);

  let data;
  try {
    data = await request.json();
  } catch {
    return json({ error: "expected JSON" }, 400);
  }

  // Hidden field. Real people never fill it in; bots usually do.
  if (data.website && String(data.website).trim()) {
    return json({ ok: true, skipped: true });
  }

  const scope = String(data.scope || "");
  if (!["point", "site", "district"].includes(scope)) {
    return json({ error: "scope must be point, site or district" }, 400);
  }

  const condition = String(data.condition || "");
  if (!CONDITIONS.has(condition)) {
    return json({ error: "unknown condition" }, 400);
  }

  let severity = parseInt(data.severity, 10);
  if (!Number.isFinite(severity)) severity = 1;
  severity = Math.max(1, Math.min(5, severity));

  let lat = data.lat == null ? null : Number(data.lat);
  let lon = data.lon == null ? null : Number(data.lon);
  if (lat != null && (!Number.isFinite(lat) || lat < -90 || lat > 90)) lat = null;
  if (lon != null && (!Number.isFinite(lon) || lon < -180 || lon > 180)) lon = null;
  if (scope === "point" && (lat == null || lon == null)) {
    return json({ error: "a point report needs coordinates" }, 400);
  }
  if (scope === "district" && !data.district) {
    return json({ error: "a district report needs a district" }, 400);
  }
  if (scope === "site" && !data.target_id) {
    return json({ error: "a site report needs a target" }, 400);
  }

  const body = String(data.body || "").slice(0, MAX_BODY);
  const reporter = String(data.reporter || "").slice(0, 80) || null;
  const ipHash = await sha256(
    (request.headers.get("CF-Connecting-IP") || "unknown") + "|nila"
  );

  // Rate limit per IP hash.
  try {
    const since = new Date(Date.now() - RATE_WINDOW_MS).toISOString();
    const row = await env.DB.prepare(
      `SELECT COUNT(*) AS n FROM reports WHERE ip_hash = ?1 AND created_at > ?2`
    ).bind(ipHash, since).first();
    if (row && row.n >= RATE_LIMIT) {
      return json({ error: "too many reports from here in the last hour" }, 429);
    }
  } catch {
    // if the count fails, let the write proceed rather than blocking reports
  }

  const score = spamScore(body, reporter);
  const status = score >= 0.6 ? "hidden" : "published";
  const id = crypto.randomUUID();
  const created = new Date().toISOString();

  try {
    await env.DB.prepare(
      `INSERT INTO reports
        (id, scope, target_kind, target_id, target_name, district, lat, lon,
         reporter, condition, severity, body, status, spam_score, ip_hash, created_at)
       VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?16)`
    ).bind(
      id, scope,
      data.target_kind || null,
      data.target_id ? String(data.target_id) : null,
      data.target_name ? String(data.target_name).slice(0, 120) : null,
      data.district ? String(data.district).slice(0, 60) : null,
      lat, lon, reporter, condition, severity, body, status, score, ipHash, created
    ).run();
  } catch (err) {
    return json({ error: "could not save report", detail: String(err) }, 500);
  }

  return json({
    ok: true,
    published: status === "published",
    report: {
      id, scope,
      target_kind: data.target_kind || null,
      target_id: data.target_id || null,
      target_name: data.target_name || null,
      district: data.district || null,
      lat, lon, reporter, condition, severity, body, created_at: created,
    },
  }, 201);
}
