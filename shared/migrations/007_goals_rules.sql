-- Goals (tribe + squad) + chapter rules. HQ dashboard "cubicle" model.
-- Idempotent: CREATE NOT EXISTS, ON CONFLICT DO NOTHING.
-- Goals: a tribe owns its product mission; a squad owns its feature mission.
-- chapter_rules: the org standard text per function (mirrors shared/chapters.py).

CREATE TABLE IF NOT EXISTS goals (
  id BIGSERIAL PRIMARY KEY,
  scope TEXT NOT NULL,          -- 'tribe' | 'squad'
  owner TEXT NOT NULL,          -- tribe name or squad name
  text TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',  -- active|done|dropped
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_goals_owner ON goals (scope, owner);

CREATE TABLE IF NOT EXISTS chapter_rules (
  id BIGSERIAL PRIMARY KEY,
  chapter TEXT NOT NULL UNIQUE,  -- backend|qa|frontend|devops
  rules TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed chapter rules (mirrors shared/chapters.py CHAPTER_* constants).
INSERT INTO chapter_rules (chapter, rules) VALUES
('backend',
 'Functions <50 lines, files <800 lines, no nesting >4. Validate input at trust boundaries; parameterized queries only. Errors handled explicitly, never swallowed. Immutable: new objects, don''t mutate. YAGNI: no speculative abstraction. Delete over add. One repo per product; one PR per feature; CI green before merge.'),
('qa',
 'Every change ships a check (test or assert) that fails if logic breaks. Test behavior, not implementation. Quality gate per scope: assert rows/contract before PASS. Report PASS/FAIL with failing check names. Never auto-fix to green. 80%+ coverage on new logic; trivial one-liners need no test.'),
('frontend',
 'Semantic HTML first; no div-stack when an element exists. Design tokens as CSS variables; no hardcoded palette/spacing. Animate transform/opacity only (compositor-friendly). Explicit image dimensions; lazy below the fold. Accessible by default (keyboard, contrast, reduced-motion). Intentional design — not a default template.'),
('devops',
 'Infra safety-first: validate configs before commit, idempotent migrations, never destroy data. Least-privilege secrets via env/secret manager, never hardcoded. Healthchecks + restart policies on every service. Reproducible builds; pin versions. Surface failures loudly, never silently swallow.')
ON CONFLICT (chapter) DO NOTHING;

-- Seed tribe goals (product mission per tribe).
INSERT INTO goals (scope, owner, text) VALUES
('tribe','sloane','Ingest + normalize external media data (anime/manga/movie/series) into canonical entities; merge dedup; keep lean ratio.'),
('tribe','avicenna','Go API gateway: expose media catalog endpoints (home, by-type, search); consume sloane canonical data.'),
('tribe','jawatch','Next.js+bun media catalog UI; consume avicenna API; ship to Vercel.'),
('tribe','heimdall','Auth/gateway/security middleware; session + cookie + OIDC; protect all dwizzyOS services.'),
('tribe','gebelin','Infra/DB ops: PG17+pgvector, Valkey, Caddy, Cloudflare Tunnel; keep 7 containers healthy.'),
('tribe','chronos','Time/astronomy/weather timeseries UI; consume sloane-ingested timeseries data.')
ON CONFLICT DO NOTHING;

-- Seed squad goals (feature mission per squad).
INSERT INTO goals (scope, owner, text) VALUES
('squad','squad_scraper','Scrape oploverz → raw_entities; emit valid source/external_id/kind/title/url.'),
('squad','squad_processor','Enrich canonical entities with authoritative IDs (MAL via Jikan).'),
('squad','squad_store','DB governance: health, lean ratio, orphan detection; report not fix.'),
('squad','squad_avicenna','Wire Go CI (build+vet); ship media endpoints (home, by-type).'),
('squad','squad_catalog_ui','Next.js+bun CI; catalog pages consuming avicenna API.'),
('squad','squad_auth_gateway','Bun CI; auth middleware + session cookie flow.'),
('squad','squad_infra','docker-compose + Cloudflare Tunnel; all containers up + healthy.'),
('squad','squad_timeseries_ui','Go CI; timeseries data UI (time/astronomy/weather).')
ON CONFLICT DO NOTHING;
