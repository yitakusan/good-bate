#!/bin/sh
# Backup Stockgood SQLite DBs (Linux / Docker).
# Usage: backup-db.sh [reason]
set -eu
REASON="${1:-manual}"
KEEP="${KEEP:-30}"
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
DATA_DIR="${STOCKGOOD_DATA_DIR:-$ROOT/backend/data}"
BACKUP_DIR="$DATA_DIR/backups"
mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
backed=0

backup_one() {
  name="$1"
  src="$2"
  if [ ! -f "$src" ]; then
    return 0
  fi
  dest="$BACKUP_DIR/${name}.${STAMP}.${REASON}.sqlite"
  python - <<PY
import sqlite3
from pathlib import Path
src = Path(r"""$src""")
dst = Path(r"""$dest""")
src_conn = sqlite3.connect(str(src))
try:
    src_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
except Exception:
    pass
dst_conn = sqlite3.connect(str(dst))
try:
    with dst_conn:
        src_conn.backup(dst_conn)
finally:
    dst_conn.close()
    src_conn.close()
print(dst.name)
PY
  echo "[backup] $REASON -> $(basename "$dest")"
  backed=$((backed + 1))
  # prune
  ls -1t "$BACKUP_DIR"/"$name".*.sqlite 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f "$old"
    echo "[backup] pruned $(basename "$old")"
  done
}

backup_one "stockgood" "$DATA_DIR/stockgood.sqlite"
backup_one "stockgood.shadow" "$DATA_DIR/stockgood.shadow.sqlite"

if [ "$backed" -eq 0 ]; then
  echo "[backup] nothing to backup"
fi
