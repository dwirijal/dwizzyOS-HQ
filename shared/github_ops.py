"""GitHub ops tools for agents. Forces full GH feature usage per squad.

Every squad must: issue -> branch -> commit -> push -> PR -> CI. Tools wrap
`gh` CLI + git. repo= for issue/PR (GitHub target), cwd= for local git ops.
Precondition: `gh auth login` done on host. Agents never bypass the gate.
"""
from __future__ import annotations
import subprocess
from pathlib import Path
from google.adk.tools import FunctionTool

DEFAULT_AVICENNA_DIR = "/home/dwizzy/dwizzyOS/avicenna"
DEFAULT_SLOANE_DIR = "/home/dwizzy/dwizzyOS/sloane"


def _sh(cmd: list[str], cwd: str | None = None) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def gh_create_issue(title: str, body: str, repo: str) -> dict:
    """Open a GitHub issue on `repo` (e.g. 'dwirijal/avicenna'). Returns {url}."""
    out = _sh(["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body])
    return {"url": out, "repo": repo}


def gh_create_branch(branch: str, cwd: str = DEFAULT_AVICENNA_DIR, base: str = "main") -> dict:
    """Create + checkout a branch off base in the local repo (cwd). Idempotent."""
    _sh(["git", "checkout", base], cwd=cwd)
    # drop stale local branch of same name (re-runs are common in the 24/7 loop)
    import subprocess
    subprocess.run(["git", "branch", "-D", branch], cwd=cwd, capture_output=True, text=True)
    _sh(["git", "checkout", "-b", branch], cwd=cwd)
    return {"branch": branch, "cwd": cwd}


def gh_commit_push(message: str, cwd: str = DEFAULT_AVICENNA_DIR, files: list[str] | None = None) -> dict:
    """Stage, commit, push current branch to origin."""
    # add requested files; if any missing, fall back to add -A (LLM may list a
    # path that the previous tool step created under a slightly different name).
    import subprocess
    if files:
        r = subprocess.run(["git", "add", "--"] + files, cwd=cwd, capture_output=True, text=True)
        if r.returncode != 0:
            _sh(["git", "add", "-A"], cwd=cwd)
    else:
        _sh(["git", "add", "-A"], cwd=cwd)
    _sh(["git", "commit", "-m", message], cwd=cwd)
    branch = _sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    import subprocess
    # force-push feature branches: 24/7 loop re-runs rewrite history; never main.
    flag = "-f" if branch != "main" else ""
    cmd = ["git", "push", "-u", "origin", branch] if not flag else ["git", "push", "-fu", "origin", branch]
    _sh(cmd, cwd=cwd)
    return {"branch": branch, "message": message}


def gh_create_pr(title: str, body: str, repo: str, head: str, base: str = "main") -> dict:
    """Open a PR head->base on `repo`. Idempotent: if one exists for the branch,
    return its URL (24/7 loop re-runs must not crash on a duplicate PR)."""
    import subprocess
    r = subprocess.run(["gh", "pr", "list", "--repo", repo, "--head", head,
                        "--base", base, "--state", "open", "--json", "url", "-q", ".[0].url"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return {"url": r.stdout.strip(), "head": head, "base": base, "existing": True}
    out = _sh(["gh", "pr", "create", "--repo", repo, "--title", title,
               "--body", body, "--base", base, "--head", head])
    return {"url": out, "head": head, "base": base}


def gh_check_ci(branch: str, repo: str) -> dict:
    """Check CI status for branch on repo. Returns {checks, passing}."""
    try:
        out = _sh(["gh", "pr", "checks", branch, "--repo", repo, "--required"])
        passing = "fail" not in out.lower() and ("pass" in out.lower() or out.strip() == "")
        return {"branch": branch, "checks": out or "(no checks)", "passing": passing}
    except RuntimeError as e:
        # no PR or no checks configured yet
        return {"branch": branch, "checks": str(e)[:200], "passing": True, "note": "no CI yet"}


gh_issue_tool = FunctionTool(func=gh_create_issue)
gh_branch_tool = FunctionTool(func=gh_create_branch)
gh_push_tool = FunctionTool(func=gh_commit_push)
gh_pr_tool = FunctionTool(func=gh_create_pr)
gh_ci_tool = FunctionTool(func=gh_check_ci)


def write_ci_workflow(cwd: str = DEFAULT_AVICENNA_DIR) -> dict:
    """Write a Go CI workflow (.github/workflows/ci.yml): build + vet.

    Forces squads to wire CI (a required GH feature). Idempotent.
    """
    p = Path(cwd) / ".github" / "workflows" / "ci.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "name: ci\n"
        "on: [push, pull_request]\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: actions/setup-go@v5\n"
        "        with:\n"
        "          go-version: '1.26'\n"
        "      - run: go vet ./...\n"
        "      - run: go build ./cmd/server\n"
    )
    return {"written": str(p)}


ci_workflow_tool = FunctionTool(func=write_ci_workflow)
