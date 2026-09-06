# Data Model

**Layer tags:** `[L0]` ships now. `[L2]` (tasks/leases) and `[L3]` (trust/producer stats) are optional modules — the columns and tables are documented here so adding them later is not a migration surprise, but they are **not built in week 1**. See `docs/08-layers.md`.

## Addressing
```
bb://<workspace>/<topic>/<kind>/<id>[@<version>]
bb-artifact://sha256/<hex>
```
- `workspace` — one run/engagement. Isolation + GC unit.
- `topic` — domain partition. Dotted (`domain.automotive`, `tasks.car`, `run`).
- `kind` — record type, bound to a schema: `task_spec | task_result | decision | fact | artifact_ref | runbook | summary | state | critique | question`.
- `id` — slug, stable across versions.
- `@version` — omit for latest. Pinning a version in a link makes the reference immutable.

## SQL schema (SQLite; Postgres differs only in types/`RETURNING` syntax)

### [L0] core tables
```sql
PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;

CREATE TABLE entry (
  uri           TEXT PRIMARY KEY,        -- bb://ws/topic/kind/id  (latest)
  workspace     TEXT NOT NULL,
  topic         TEXT NOT NULL,
  kind          TEXT NOT NULL,
  id            TEXT NOT NULL,
  version       INTEGER NOT NULL DEFAULT 1,
  schema_id     TEXT,
  status        TEXT NOT NULL DEFAULT 'accepted',
                -- proposed|accepted|contested|superseded|stale|tombstone
  body          TEXT,                    -- canonical JSON; NULL if externalized
  artifact_uri  TEXT,                    -- bb-artifact://sha256/... when body > 10KB
  body_hash     TEXT NOT NULL,           -- sha256 of canonical body/artifact
  digest        TEXT NOT NULL,           -- <=200 tokens. MANDATORY.
  digest_generated INTEGER NOT NULL DEFAULT 0,
  bytes         INTEGER NOT NULL,
  est_tokens    INTEGER NOT NULL,
  producer      TEXT NOT NULL,           -- agent id
  model         TEXT,
  confidence    REAL,                    -- self-reported [0,1]
  trust         REAL NOT NULL DEFAULT 0, -- [L3] computed; 0 and unused in L0
  trust_parts   TEXT,                    -- JSON of the six components
  ttl_at        INTEGER,
  pinned        INTEGER NOT NULL DEFAULT 0,
  reads         INTEGER NOT NULL DEFAULT 0,
  last_read_at  INTEGER,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL
);
CREATE INDEX ix_entry_scope   ON entry(workspace, topic, kind, status);
CREATE INDEX ix_entry_updated ON entry(workspace, updated_at DESC);
CREATE INDEX ix_entry_gc      ON entry(workspace, pinned, last_read_at);

CREATE TABLE entry_history (           -- append-only; never updated
  uri TEXT NOT NULL, version INTEGER NOT NULL,
  body TEXT, artifact_uri TEXT, body_hash TEXT NOT NULL,
  digest TEXT, producer TEXT, trust REAL, status TEXT,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (uri, version)
);

CREATE TABLE link (                    -- the graph (D6)
  src_uri TEXT NOT NULL, rel TEXT NOT NULL, dst_uri TEXT NOT NULL,
  weight REAL DEFAULT 1.0, created_at INTEGER NOT NULL,
  PRIMARY KEY (src_uri, rel, dst_uri)
);
CREATE INDEX ix_link_dst ON link(dst_uri, rel);
-- rel: depends_on | derived_from | contradicts | supersedes | refines | cites | part_of

-- [L2] ---------------------------------------------------------------
CREATE TABLE task (
  task_id TEXT PRIMARY KEY,
  workspace TEXT NOT NULL, topic TEXT NOT NULL,
  spec_uri TEXT NOT NULL, result_uri TEXT,
  status TEXT NOT NULL,   -- blocked|ready|leased|done|failed|cancelled
  priority INTEGER NOT NULL DEFAULT 100,
  capabilities TEXT,      -- JSON array; matched against worker's declared caps
  lease_owner TEXT, lease_expires_at INTEGER,
  attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
  last_error TEXT,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX ix_task_ready ON task(workspace, status, priority, created_at);
CREATE INDEX ix_task_lease ON task(status, lease_expires_at);

CREATE TABLE task_dep (task_id TEXT, depends_on TEXT, PRIMARY KEY(task_id, depends_on));

-- [L0] (append-only; L2 consumes it via watch_events) --------------------
CREATE TABLE event (                   -- the broker (D11)
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL, workspace TEXT NOT NULL, topic TEXT NOT NULL,
  type TEXT NOT NULL,   -- put|patch|claim|complete|fail|contest|compact|lease_expired
  uri TEXT, actor TEXT, payload TEXT
);
CREATE INDEX ix_event_scope ON event(workspace, seq);

-- [L0] ---------------------------------------------------------------
CREATE TABLE grant (                   -- capability tokens (D10)
  token_hash TEXT PRIMARY KEY, agent_id TEXT NOT NULL, role TEXT NOT NULL,
  workspace TEXT NOT NULL, topic_globs TEXT NOT NULL, caps TEXT NOT NULL,
  budget_tokens INTEGER, issued_at INTEGER NOT NULL, expires_at INTEGER
);

-- [L3] ---------------------------------------------------------------
CREATE TABLE producer_stats (          -- feeds Trust.Producer
  agent_id TEXT PRIMARY KEY, writes INTEGER, accepted INTEGER,
  contested INTEGER, reliability REAL DEFAULT 0.5, updated_at INTEGER
);

CREATE TABLE schema_reg (schema_id TEXT PRIMARY KEY, topic_glob TEXT, kind TEXT,
                         json_schema TEXT NOT NULL, version INTEGER, created_at INTEGER);

CREATE VIRTUAL TABLE entry_fts USING fts5(
  uri UNINDEXED, digest, body_text, content='', tokenize='porter');
```

## [L2] Atomic claim (the queue, D11) — not built in week 1
```sql
BEGIN IMMEDIATE;
UPDATE task SET status='leased', lease_owner=:agent,
       lease_expires_at=:now+:lease_s, attempts=attempts+1, updated_at=:now
WHERE task_id = (
  SELECT t.task_id FROM task t
  WHERE t.workspace=:ws AND t.status='ready'
    AND (t.topic GLOB :glob)
    AND NOT EXISTS (SELECT 1 FROM task_dep d JOIN task p ON p.task_id=d.depends_on
                    WHERE d.task_id=t.task_id AND p.status <> 'done')
  ORDER BY t.priority, t.created_at LIMIT 1)
RETURNING task_id, spec_uri;
COMMIT;
```
A reaper pass flips `status='leased' AND lease_expires_at < now` back to `ready` (or `failed` past `max_attempts`) and emits `lease_expired`. This is why leases beat locks (D5): agent death is self-healing.

## [L3] Blast radius of a contested entry — not built in week 1
```sql
WITH RECURSIVE suspect(uri) AS (
  SELECT :bad_uri
  UNION
  SELECT l.src_uri FROM link l JOIN suspect s ON l.dst_uri = s.uri
  WHERE l.rel IN ('derived_from','depends_on','refines')
)
SELECT e.uri, e.kind, e.trust FROM entry e JOIN suspect USING(uri)
WHERE e.status='accepted';
```
One query answers "what else is now doubtful". This is the payoff of D6 and the core of the Q10 caveat answer.
