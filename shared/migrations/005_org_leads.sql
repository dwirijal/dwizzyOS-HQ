-- Chapter leads + tribe lead roles. Each chapter has a lead agent (horizontal
-- function owner cross-tribe); each tribe has a tribe_lead (distinct from
-- squad_lead). Closes the "all roles filled" gap.
-- Idempotent: ON CONFLICT DO NOTHING on re-runs.

-- chapter lead groups (one per chapter) — siblings of chapter_* member groups
INSERT INTO agent_groups (name, kind, parent_id)
SELECT 'chapter_lead_' || replace(name,'chapter_',''), 'chapter_lead', NULL
FROM agent_groups WHERE kind='chapter'
ON CONFLICT DO NOTHING;

-- assign leads: backend->sloane_lead (python-strongest), qa->avicenna_qa,
-- frontend->avicenna_frontend. ponytail: 1 lead/chapter from existing agents;
-- promote dedicated lead agents when squad count grows.
INSERT INTO agent_memberships (agent_id, group_id, role)
SELECT 'sloane_lead', g.id, 'chapter_lead' FROM agent_groups g WHERE g.name='chapter_lead_backend'
ON CONFLICT DO NOTHING;
INSERT INTO agent_memberships (agent_id, group_id, role)
SELECT 'avicenna_qa', g.id, 'chapter_lead' FROM agent_groups g WHERE g.name='chapter_lead_qa'
ON CONFLICT DO NOTHING;
INSERT INTO agent_memberships (agent_id, group_id, role)
SELECT 'avicenna_frontend', g.id, 'chapter_lead' FROM agent_groups g WHERE g.name='chapter_lead_frontend'
ON CONFLICT DO NOTHING;

-- tribe_lead role on each tribe (distinct from squad_lead)
UPDATE agent_memberships SET role='tribe_lead'
WHERE group_id IN (SELECT id FROM agent_groups WHERE kind='tribe')
  AND role='squad_lead' AND agent_id LIKE '%_lead';
