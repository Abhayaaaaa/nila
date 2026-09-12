-- Cloudflare D1 (SQLite) schema for shared community reports.
-- Apply with:
--   wrangler d1 execute nila-reports --remote --file=./schema.sql

CREATE TABLE IF NOT EXISTS reports (
  id           TEXT PRIMARY KEY,
  -- how the reporter told us where: an exact clicked point, a named lake or
  -- settlement from the inventory, or a whole district
  scope        TEXT NOT NULL CHECK (scope IN ('point', 'site', 'district')),
  target_kind  TEXT CHECK (target_kind IN ('lake', 'place')),
  target_id    TEXT,
  target_name  TEXT,
  district     TEXT,
  lat          REAL,
  lon          REAL,

  reporter     TEXT,
  condition    TEXT NOT NULL,
  severity     INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 5),
  body         TEXT,

  -- 'published' shows in the feed, 'hidden' is soft-deleted by a moderator
  status       TEXT NOT NULL DEFAULT 'published',
  spam_score   REAL NOT NULL DEFAULT 0,
  ip_hash      TEXT,
  created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_created ON reports (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_target  ON reports (target_kind, target_id);
CREATE INDEX IF NOT EXISTS idx_reports_dist    ON reports (district);
CREATE INDEX IF NOT EXISTS idx_reports_status  ON reports (status);
CREATE INDEX IF NOT EXISTS idx_reports_ip      ON reports (ip_hash, created_at);
