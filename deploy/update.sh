#!/usr/bin/env bash
# Update-Skript: holt neuen Code, syncs nach /opt, startet Service neu.
# Aufruf: sudo bash deploy/update.sh
set -euo pipefail

APP_NAME="anna-ig-api"
APP_USER="anna"
APP_DIR="/opt/anna-ig-poster"

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo ausfuehren: sudo bash deploy/update.sh"; exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ">>> Sync Code..."
rsync -a --delete \
  --exclude '.git/' --exclude '.venv/' --exclude '__pycache__/' \
  --exclude '.env' --exclude 'logs/' --exclude 'generated/' \
  "${REPO_ROOT}/" "${APP_DIR}/"

echo ">>> Update Python-Deps..."
"${APP_DIR}/.venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo ">>> Service-Restart..."
systemctl restart "${APP_NAME}.service"
sleep 2
systemctl is-active --quiet "${APP_NAME}.service" \
  && echo ">>> OK" \
  || { journalctl -u "${APP_NAME}" --no-pager -n 30; exit 1; }
