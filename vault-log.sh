#!/usr/bin/env bash
# dwizzyOS Vault Logger — called by Claude Code hooks or manually.
# Logs all operations: file changes, issues, plans, session events.

VAULT="$HOME/dwizzyOS-vault"
DAILY="$VAULT/daily/$(date +%Y-%m-%d).md"

ensure_daily() {
  if [ ! -f "$DAILY" ]; then
    mkdir -p "$(dirname "$DAILY")"
    cat > "$DAILY" << EOF
---
date: $(date +%Y-%m-%d)
tags: [daily]
---

# $(date +%A), $(date +%B) $(date +%d) $(date +%Y)
EOF
  fi
}

# Log a file operation from hooks
# Usage: vault-log.sh file_op <created|edited|deleted> <filepath>
file_op() {
  local op="$1"
  local file="$2"
  local ts
  ts=$(date '+%H:%M:%S')
  ensure_daily

  case "$op" in
    created) echo "- [${ts}] ✨ **Created**: \`${file}\`" >> "$DAILY" ;;
    edited)  echo "- [${ts}] ✏️ **Edited**: \`${file}\`" >> "$DAILY" ;;
    deleted) echo "- [${ts}] 🗑️ **Deleted**: \`${file}\`" >> "$DAILY" ;;
    *)       echo "- [${ts}] **${op}**: \`${file}\`" >> "$DAILY" ;;
  esac
}

# Log a free-form entry
# Usage: vault-log.sh <note|issue|plan|system|session|cmd|err|ok> "message"
log_entry() {
  local level="${1:-note}"
  shift
  local msg="$*"
  local ts
  ts=$(date '+%H:%M:%S')
  ensure_daily

  case "$level" in
    issue)   echo "- [${ts}] 🚨 **ISSUE**: ${msg}" >> "$DAILY" ;;
    plan)    echo "- [${ts}] 📋 **PLAN**: ${msg}" >> "$DAILY" ;;
    system)  echo "- [${ts}] ⚙️ **SYSTEM**: ${msg}" >> "$DAILY" ;;
    session) echo "- [${ts}] 🔄 **SESSION**: ${msg}" >> "$DAILY" ;;
    cmd)     echo "- [${ts}] 💻 **CMD**: \`${msg}\`" >> "$DAILY" ;;
    err)     echo "- [${ts}] ❌ **ERROR**: ${msg}" >> "$DAILY" ;;
    ok)      echo "- [${ts}] ✅ **DONE**: ${msg}" >> "$DAILY" ;;
    note)    echo "- [${ts}] 📝 ${msg}" >> "$DAILY" ;;
    *)       echo "- [${ts}] ${msg}" >> "$DAILY" ;;
  esac
}

"$@"