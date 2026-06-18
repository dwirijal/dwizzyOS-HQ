# dwizzyOS Vault — CLAUDE.md

## You Are In The Documentation Vault

This is the central documentation vault for dwizzyOS. Your primary directive:

**Every action, decision, plan, issue, and change MUST be documented here.**

## Documentation Rules

1. **Daily Notes**: Log all significant actions to `daily/YYYY-MM-DD.md` using the vault-log.sh script or direct markdown
2. **Issues**: Any problem, bug, or blocker goes in `issues/` with a descriptive filename
3. **Plans**: All implementation plans go in `plans/` before writing code
4. **System**: System configuration, infrastructure changes go in `system/`
5. **Projects**: Project-specific docs go in `projects/<project-name>/`

## Auto-Logging

The vault watches all files in dwizzyOS and auto-commits changes. When you work, the system will:
- Watch for edits/adds/deletes across the project
- Auto-commit to git with descriptive messages
- Push to GitHub: https://github.com/dwirijal/dwizzyOS-HQ

## Logging Commands

```bash
# Quick note in daily log
~/dwizzyOS/dwizzyOS-vault/vault-log.sh note "what happened"

# Log a command execution
~/dwizzyOS/dwizzyOS-vault/vault-log.sh cmd "docker compose up -d"

# Log an error
~/dwizzyOS/dwizzyOS-vault/vault-log.sh err "description of error"

# Log a success
~/dwizzyOS/dwizzyOS-vault/vault-log.sh ok "task completed"

# Log session start/end
~/dwizzyOS/dwizzyOS-vault/vault-log.sh session "session context"
```

## Commit Convention

- `docs(daily): ...` — daily notes
- `docs(issue): ...` — new issue
- `docs(plan): ...` — implementation plan
- `docs(system): ...` — system config changes
- `docs(project): ...` — project documentation

## When In Doubt

If unsure whether to document something: DOCUMENT IT. This vault exists to capture everything about dwizzyOS.