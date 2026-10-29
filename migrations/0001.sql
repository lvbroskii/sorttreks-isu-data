PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sources (
 url TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
 first_seen_at TEXT NOT NULL, fetched_at TEXT NOT NULL,
 etag TEXT, last_modified TEXT
);
CREATE TABLE IF NOT EXISTS snapshots (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 state TEXT NOT NULL CHECK(state IN ('candidate','approved','rejected')),
 sha256 TEXT NOT NULL, body TEXT NOT NULL CHECK(json_valid(body)),
 created_at TEXT NOT NULL, reviewed_by TEXT,
 CHECK(state != 'approved' OR reviewed_by IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS snapshots_state_id ON snapshots(state,id DESC);
CREATE TABLE IF NOT EXISTS review_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
 reason TEXT NOT NULL, resolved_at TEXT
);
-- Indexed point reads only; retain last 20 candidates at ingestion, not per read.
