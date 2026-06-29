-- KPIs + dev schedules + reporting chain + task assignment hierarchy + process gates.
-- Hierarchy: CTO -> tribe_lead -> squad_lead -> member (no guilds).
-- Process gates per task: documented / tested / audited / qa / devops (booleans).
-- Idempotent: CREATE IF NOT EXISTS, ON CONFLICT DO NOTHING.

-- 1. KPI matrix per scope (tribe | squad | chapter).
CREATE TABLE IF NOT EXISTS kpis (
  id BIGSERIAL PRIMARY KEY,
  scope TEXT NOT NULL,          -- 'tribe' | 'squad' | 'chapter'
  owner TEXT NOT NULL,          -- tribe/squad/chapter name
  metric TEXT NOT NULL,         -- e.g. 'cycle_pass_rate', 'lean_ratio'
  target TEXT NOT NULL,         -- e.g. '>=0.95'
  actual TEXT,                  -- latest measured value (nullable until measured)
  period TEXT NOT NULL DEFAULT 'daily',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kpis_owner ON kpis (scope, owner);

-- 2. Development schedule per squad (milestones with due dates).
CREATE TABLE IF NOT EXISTS schedules (
  id BIGSERIAL PRIMARY KEY,
  squad TEXT NOT NULL,          -- squad name
  milestone TEXT NOT NULL,      -- e.g. 'CI wired', 'MVP endpoints'
  due_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'planned',  -- planned|in_progress|done|blocked
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_schedules_squad ON schedules (squad);

-- 3. Reporting chain: reporter -> recipient + content (escalation/update).
-- CTO<-(chapter_lead); tribe_lead<-(squad_lead); CTO<-(tribe_lead).
CREATE TABLE IF NOT EXISTS reports (
  id BIGSERIAL PRIMARY KEY,
  reporter TEXT NOT NULL,       -- agent_id filing the report
  recipient TEXT NOT NULL,      -- agent_id receiving (next up the chain)
  report_type TEXT NOT NULL DEFAULT 'status',  -- status|escalation|blocker
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reports_recipient ON reports (recipient, created_at DESC);

-- 4. Extend tasks table with hierarchy + process gates.
-- assigner + assignment_scope enforce the chain at the data layer; app code
-- (shared/hierarchy.py) double-checks before insert.
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS assigner_id TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS assignment_scope TEXT;  -- tribe_lead->squad_lead | squad_lead->member
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS squad TEXT;            -- redundant w/ existing squad col? ensure
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS doc_done BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS test_done BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS audit_done BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS qa_done BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS devops_done BOOLEAN NOT NULL DEFAULT false;

-- 5. CTO group (top of hierarchy). Single leader, cross-tribe.
INSERT INTO agent_groups (name, kind) VALUES ('cto','cto')
ON CONFLICT (name) DO NOTHING;
-- ponytail: CTO is currently the operator (human) + auto-supervisor. Assign
-- 'dwizzy_cto' agent_id as placeholder; real CTO agent when built.
INSERT INTO agent_memberships (agent_id, group_id, role)
SELECT 'dwizzy_cto', g.id, 'cto' FROM agent_groups g WHERE g.name='cto'
ON CONFLICT (agent_id, group_id) DO NOTHING;

-- 6. Seed KPIs per tribe (success matrix).
INSERT INTO kpis (scope, owner, metric, target) VALUES
('tribe','sloane','cycle_pass_rate','>=0.95'),
('tribe','sloane','lean_ratio','<=0.15'),
('tribe','sloane','raw_emitted_per_cycle','>=1'),
('tribe','avicenna','cycle_pass_rate','>=0.95'),
('tribe','avicenna','endpoint_health','200'),
('tribe','jawatch','cycle_pass_rate','>=0.95'),
('tribe','jawatch','vercel_deploy','success'),
('tribe','heimdall','cycle_pass_rate','>=0.95'),
('tribe','heimdall','auth_flow_pass','true'),
('tribe','gebelin','container_health','7/7'),
('tribe','gebelin','cycle_pass_rate','>=0.95'),
('tribe','chronos','cycle_pass_rate','>=0.95')
ON CONFLICT DO NOTHING;

-- 7. Seed squad KPIs + dev schedules.
INSERT INTO kpis (scope, owner, metric, target) VALUES
('squad','squad_scraper','valid_entities_per_cycle','>=1'),
('squad','squad_store','orphan_raw','0'),
('squad','squad_avicenna','ci_green','true'),
('squad','squad_infra','containers_up','7/7')
ON CONFLICT DO NOTHING;

INSERT INTO schedules (squad, milestone, status) VALUES
('squad_scraper','scrape oploverz → raw','in_progress'),
('squad_processor','enrich mal_id','planned'),
('squad_store','lean ratio gate','planned'),
('squad_avicenna','CI wired (go vet+build)','done'),
('squad_avicenna','media endpoints','planned'),
('squad_catalog_ui','Next.js CI','done'),
('squad_auth_gateway','Bun CI','done'),
('squad_infra','docker-compose + tunnel','in_progress'),
('squad_timeseries_ui','Go CI','done')
ON CONFLICT DO NOTHING;
