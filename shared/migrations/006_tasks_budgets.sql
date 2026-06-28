-- Kanban tasks + budget tracking for the HQ dashboard.
-- Tasks: squad-scoped work items moving across kanban columns (todo/doing/review/done).
-- Budgets: token/cost budget per tribe, spend tracked per agent run.
-- Idempotent: CREATE IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    tribe TEXT NOT NULL,
    squad TEXT NOT NULL,
    assignee TEXT,
    status TEXT NOT NULL DEFAULT 'todo',  -- todo|doing|review|done
    priority INT NOT NULL DEFAULT 3,
    gh_issue_url TEXT,
    gh_pr_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_tribe_squad ON tasks (tribe, squad);

CREATE TABLE IF NOT EXISTS budgets (
    id BIGSERIAL PRIMARY KEY,
    tribe TEXT NOT NULL,
    period TEXT NOT NULL DEFAULT 'daily',  -- daily|monthly
    limit_tokens BIGINT NOT NULL DEFAULT 0,
    spent_tokens BIGINT NOT NULL DEFAULT 0,
    spent_usd NUMERIC(10,4) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tribe, period)
);

-- seed budgets for known tribes (generous daily defaults; tune later)
INSERT INTO budgets (tribe, period, limit_tokens)
VALUES ('sloane','daily',2000000), ('avicenna','daily',2000000)
ON CONFLICT (tribe, period) DO NOTHING;
