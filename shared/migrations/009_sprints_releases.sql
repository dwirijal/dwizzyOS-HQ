-- Sprints (squad_lead-authored PRD, 1 working-day each) + releases (tribe_lead-owned,
-- weekly cadence to github + production). No-double-role: data fix runs FIRST,
-- then partial unique indexes enforce it. Idempotent.

-- 1. Sprints: a squad_lead writes a PRD broken into N 1-day sprints.
CREATE TABLE IF NOT EXISTS sprints (
  id BIGSERIAL PRIMARY KEY,
  squad TEXT NOT NULL,
  prd_text TEXT NOT NULL,        -- the squad_lead's product requirement doc
  day_index INT NOT NULL,        -- 1-based working-day index (1 day = 1 sprint)
  goal TEXT NOT NULL,            -- what this day-sprint delivers
  status TEXT NOT NULL DEFAULT 'planned',  -- planned|in_progress|done|blocked
  assigner_id TEXT,              -- squad_lead who authored it
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sprints_squad ON sprints (squad, day_index);

-- 2. Releases: tribe_lead sets next-version deadline; weekly cadence to github + prod.
CREATE TABLE IF NOT EXISTS releases (
  id BIGSERIAL PRIMARY KEY,
  tribe TEXT NOT NULL,
  version TEXT NOT NULL,         -- e.g. 'v0.3.0'
  target_at TIMESTAMPTZ,         -- when this version ships
  stage TEXT NOT NULL DEFAULT 'github',  -- github|production
  released_by TEXT,              -- must be tribe_lead (enforced in app)
  status TEXT NOT NULL DEFAULT 'planned',  -- planned|shipped|rolled_back
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_releases_tribe ON releases (tribe, target_at);

-- 3. No-double-role: an agent cannot be squad_lead of >1 squad, nor tribe_lead
-- of >1 tribe. DATA FIX runs FIRST (demote tribe_leads pulling double squad_lead
-- duty, promote a distinct member), THEN the partial unique indexes enforce it.
-- ponytail: DO before index — index creation would otherwise fail on dirty data
-- (sloane_lead = squad_lead of 3 squads, avicenna_lead etc = tribe_lead+squad_lead).
DO $$
DECLARE
  r record; sl text; new_sl text;
BEGIN
  FOR r IN SELECT g.id AS gid FROM agent_groups g
           JOIN agent_memberships m ON m.group_id=g.id WHERE g.kind='squad' LOOP
    SELECT am.agent_id INTO sl FROM agent_memberships am
      WHERE am.group_id=r.gid AND am.role='squad_lead' LIMIT 1;
    IF sl IS NOT NULL AND EXISTS (
       SELECT 1 FROM agent_memberships WHERE agent_id=sl AND role='tribe_lead') THEN
      UPDATE agent_memberships SET role='member'
        WHERE agent_id=sl AND group_id=r.gid AND role='squad_lead';
      SELECT am2.agent_id INTO new_sl FROM agent_memberships am2
        WHERE am2.group_id=r.gid AND am2.role='member' AND am2.agent_id<>sl
          AND am2.agent_id NOT LIKE '%_qa' AND am2.agent_id NOT LIKE '%_lead'
          AND NOT EXISTS (SELECT 1 FROM agent_memberships x
                          WHERE x.agent_id=am2.agent_id AND x.role='squad_lead')
        ORDER BY am2.agent_id LIMIT 1;
      IF new_sl IS NOT NULL THEN
        UPDATE agent_memberships SET role='squad_lead'
          WHERE agent_id=new_sl AND group_id=r.gid;
      END IF;
    END IF;
  END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_squad_lead_per_agent
  ON agent_memberships (agent_id) WHERE role = 'squad_lead';
CREATE UNIQUE INDEX IF NOT EXISTS uniq_tribe_lead_per_agent
  ON agent_memberships (agent_id) WHERE role = 'tribe_lead';

-- 4. Seed weekly release cadence: each tribe targets next-version ship in 7d.
INSERT INTO releases (tribe, version, stage, target_at)
SELECT tribe, 'v0.1.0', 'github', now() + interval '7 days'
FROM (VALUES ('sloane'),('avicenna'),('jawatch'),('heimdall'),('gebelin'),('chronos')) AS v(tribe)
ON CONFLICT DO NOTHING;
