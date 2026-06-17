#!/usr/bin/env bash
# dwizzyOS Vault Auto-Commit Watcher
# Watches the vault for changes and auto-commits to git, pushes to GitHub.
#
# Usage: nohup ~/dwizzyOS-vault/vault-watchd.sh &
#        or run inside tmux session OS

VAULT="$HOME/dwizzyOS-vault"
REMOTE="${DWIZZYOS_REMOTE:-git@github.com:dwirijal/dwizzyOS-HQ.git}"
DEBOUNCE_SEC=5
LOG="$VAULT/system/logs/watchd.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

# --- Git helpers ---
commit_and_push() {
  cd "$VAULT" || return

  # Skip if no remote configured
  if ! git remote get-url origin &>/dev/null; then
    log "WARN: No git remote configured"
    return
  fi

  # Pull latest first (rebase to avoid merge commits on docs)
  git pull --rebase origin main 2>/dev/null || true

  git add -A .

  # Only commit if there are staged changes
  if git diff --cached --quiet; then
    return
  fi

  # Build commit message from changed files
  local msg="auto: vault update $(date '+%Y-%m-%d %H:%M')"
  local changed=$(git diff --cached --name-only | head -5 | tr '\n' ' ')
  if [ -n "$changed" ]; then
    msg="auto: ${changed%% }"
  fi

  git commit -m "$msg" 2>&1 | tee -a "$LOG"

  # Push
  git push origin main 2>&1 | tee -a "$LOG"
  log "Pushed to GitHub"
}

# --- Main watch loop ---
log "======== dwizzyOS Vault Watcher Started ========"
log "Vault: $VAULT"
log "Remote: $REMOTE"
log "Debounce: ${DEBOUNCE_SEC}s"

# Ensure remote is set
cd "$VAULT" || exit 1
git remote get-url origin &>/dev/null || {
  git remote add origin "$REMOTE"
  log "Added remote: $REMOTE"
}

last_commit=0

inotifywait -m -r \
  --exclude '.git/|.obsidian/workspace|.trash/|*.tmp|*.swp|*.swx|~$' \
  -e modify -e create -e delete -e move \
  --format '%w%f %e' \
  "$VAULT" 2>/dev/null | while read -r filepath events; do

  # Debounce: only commit every N seconds
  now=$(date +%s)
  diff=$((now - last_commit))

  if [ $diff -lt $DEBOUNCE_SEC ]; then
    continue
  fi

  # Skip pure git internal files
  case "$filepath" in
    */.git/*) continue ;;
  esac

  rel="${filepath#$VAULT/}"
  log "Changed: $rel ($events)"

  last_commit=$now

  # Small delay to let writes finish, then commit
  sleep 1
  commit_and_push &
done