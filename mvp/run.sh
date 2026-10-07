#!/usr/bin/env bash
# Biblioteca Escolar — MVP
# Uso: ./run.sh  (porta padrão 8123; mude com PORTA=9000 ./run.sh)
set -e
cd "$(dirname "$0")"
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet -r requirements.txt
# Carrega segredos locais (não versionados): SED_SUBSCRIPTION_KEY, SED_ENABLED...
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi
export PORTA="${PORTA:-8123}"
exec ./venv/bin/python server/main.py
