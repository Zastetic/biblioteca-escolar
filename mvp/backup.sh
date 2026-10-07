#!/usr/bin/env bash
# Backup do banco da Biblioteca Escolar — mantém os 14 backups mais recentes.
# Silencioso em sucesso (watchdog): só imprime algo se algo der errado.
set -euo pipefail

MVPDIR="$(cd "$(dirname "$0")" && pwd)"
DB="$MVPDIR/biblioteca.db"
DEST="$MVPDIR/backups"

if [ ! -f "$DB" ]; then
  echo "ERRO: banco não encontrado em $DB" >&2
  exit 1
fi

mkdir -p "$DEST"
STAMP="$(date +%Y%m%d_%H%M%S)"
cp "$DB" "$DEST/biblioteca_$STAMP.db"

# remove backups antigos além dos 14 mais recentes
ls -1t "$DEST"/biblioteca_*.db 2>/dev/null | tail -n +15 | xargs -r rm -f

# integridade: sqlite quick_check no backup recém-criado
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DEST/biblioteca_$STAMP.db" "PRAGMA quick_check;" | grep -q '^ok$' || {
    echo "ERRO: backup $STAMP reprovou no quick_check" >&2
    exit 1
  }
fi
