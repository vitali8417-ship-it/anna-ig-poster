#!/usr/bin/env bash
# ============================================================
# Anna's Instagram Posting API - Ubuntu Installer
# ============================================================
# Installiert das Tool als systemd-Service auf einem Hetzner-
# Ubuntu-Server (22.04 / 24.04). Bindet die API auf 127.0.0.1
# (localhost-only) - aus dem Internet nicht erreichbar.
#
# Aufruf (als root oder mit sudo, im Repo-Verzeichnis):
#   sudo bash deploy/install.sh
# ============================================================
set -euo pipefail

APP_NAME="anna-ig-api"
APP_USER="anna"
APP_DIR="/opt/anna-ig-poster"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
LOG_FILE="/var/log/${APP_NAME}.log"

# ---------- 0. Vorbedingungen --------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo ausfuehren: sudo bash deploy/install.sh"
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "${REPO_ROOT}/api.py" ]]; then
  echo "Fehler: api.py nicht in ${REPO_ROOT} gefunden. Bitte aus dem Repo-Root ausfuehren."
  exit 1
fi

echo ">>> Installiere Anna's IG Posting API"
echo "    Repo-Quelle: ${REPO_ROOT}"
echo "    Ziel:        ${APP_DIR}"
echo "    Service:     ${APP_NAME}.service"

# ---------- 1. System-Pakete ---------------------------------
echo ">>> apt update + Pakete..."
apt-get update -qq
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip \
  ca-certificates curl rsync >/dev/null

# ---------- 2. App-User --------------------------------------
if ! id "${APP_USER}" >/dev/null 2>&1; then
  echo ">>> Lege System-User '${APP_USER}' an..."
  useradd --system --create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

# ---------- 3. Code nach /opt syncen -------------------------
echo ">>> Sync Code nach ${APP_DIR}..."
mkdir -p "${APP_DIR}"
rsync -a --delete \
  --exclude '.git/' --exclude '.venv/' --exclude '__pycache__/' \
  --exclude '.env' --exclude 'logs/' --exclude 'generated/' \
  "${REPO_ROOT}/" "${APP_DIR}/"

mkdir -p "${APP_DIR}/logs" "${APP_DIR}/content" "${APP_DIR}/generated"
touch "${LOG_FILE}"

# ---------- 4. Virtualenv + Deps -----------------------------
echo ">>> Virtualenv aufbauen..."
if [[ ! -d "${APP_DIR}/.venv" ]]; then
  python3 -m venv "${APP_DIR}/.venv"
fi
"${APP_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${APP_DIR}/.venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

# ---------- 5. .env vorbereiten ------------------------------
if [[ ! -f "${APP_DIR}/.env" ]]; then
  echo ">>> Lege ${APP_DIR}/.env aus .env.example an (Werte musst du noch eintragen)"
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  # Generiere zufaelligen API-Key
  RANDOM_KEY="$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 40)"
  sed -i "s|^API_KEY=.*|API_KEY=${RANDOM_KEY}|" "${APP_DIR}/.env"
  echo "    -> API_KEY automatisch gesetzt: ${RANDOM_KEY}"
  echo "    -> Diesen Key muss Anna im Header 'X-API-Key' mitschicken."
fi

# ---------- 6. Permissions -----------------------------------
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}" "${LOG_FILE}"
chmod 600 "${APP_DIR}/.env"

# ---------- 7. systemd-Unit installieren ---------------------
echo ">>> systemd-Service installieren..."
install -m 644 "${APP_DIR}/deploy/anna-ig-api.service" "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable "${APP_NAME}.service"
systemctl restart "${APP_NAME}.service"

sleep 2
if systemctl is-active --quiet "${APP_NAME}.service"; then
  echo ">>> Service laeuft."
else
  echo "!!! Service startet nicht. Logs:"
  journalctl -u "${APP_NAME}.service" --no-pager -n 30
  exit 1
fi

# ---------- 8. Health-Check ----------------------------------
echo ">>> Health-Check..."
if curl -fsS http://127.0.0.1:8765/health >/dev/null; then
  echo "    -> /health antwortet auf 127.0.0.1:8765"
else
  echo "!!! /health antwortet nicht. Pruefe: journalctl -u ${APP_NAME} -f"
fi

cat <<EOF

=================================================================
 Installation fertig.
=================================================================

Naechste Schritte:

  1. .env auf dem Server befuellen (IG_ACCESS_TOKEN, IG_BUSINESS_ACCOUNT_ID,
     IMGUR_CLIENT_ID, ggf. DRY_RUN=false):
       sudo -u ${APP_USER} nano ${APP_DIR}/.env

  2. Service neu starten:
       sudo systemctl restart ${APP_NAME}

  3. Logs ansehen:
       sudo journalctl -u ${APP_NAME} -f
       # oder: tail -f ${LOG_FILE}

  4. Test-Aufruf von Anna (oder manuell):
       curl -X POST http://127.0.0.1:8765/health
       curl -X POST http://127.0.0.1:8765/post/feed \\
         -H "X-API-Key: \$(grep ^API_KEY= ${APP_DIR}/.env | cut -d= -f2)" \\
         -H "Content-Type: application/json" \\
         -d '{"image_url":"https://example.com/bild.jpg","caption":"Test","hashtags":["#test"]}'

Die API ist NUR auf 127.0.0.1:8765 erreichbar - aus dem Internet
unsichtbar. Anna spricht ueber localhost mit ihr.

=================================================================
EOF
