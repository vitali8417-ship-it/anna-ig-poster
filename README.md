# Annas automatisches Instagram-Posting

Schlankes Tool, das **Anna (Hermes-Agent-Bot)** erlaubt, autonom auf Instagram zu posten.
Anna erstellt ihren Content selbst (Marketing-Tipps, Myths Busted, BTS, Wins) — dieses
Repository liefert nur die **Posting-Schnittstelle zur offiziellen Instagram Graph API**.

## Architektur

```
  ┌─────────────────────────── Hetzner-Server (Ubuntu) ───────────────────────────┐
  │                                                                                │
  │   Anna (Hermes-Bot)  ─── HTTP ──▶  127.0.0.1:8765  (FastAPI)  ─── Graph ───▶  Instagram
  │   Content + Caption                ↑   ↑                                       │
  │                          API-Key,  │   │ Bilder ─▶ Imgur (oeff. URL)           │
  │                          systemd ──┘   │                                       │
  │                                                                                │
  └────────────────────────────────────────────────────────────────────────────────┘
                              ❌  Port 8765 NICHT von aussen erreichbar
```

Der API-Server lauscht **nur auf `127.0.0.1`** — er ist aus dem Internet unsichtbar.
Anna spricht ihn über localhost an, mit `X-API-Key`-Header. Sicherer geht es nicht.

Unterstützte Post-Typen: **Feed**, **Karussell** (2–10 Bilder), **Story**, **Reel**.

---

## Schnellstart auf dem Hetzner-Server

```bash
# 1. Repo auf den Server bringen
git clone <dein-repo>  /tmp/anna-poster
cd /tmp/anna-poster

# 2. Installer
sudo bash deploy/install.sh

# 3. Tokens in /opt/anna-ig-poster/.env eintragen
sudo -u anna nano /opt/anna-ig-poster/.env

# 4. Service neu starten
sudo systemctl restart anna-ig-api

# 5. Test
curl http://127.0.0.1:8765/health
```

`install.sh` kümmert sich um:
- Anlage des System-Users `anna`
- Sync nach `/opt/anna-ig-poster/`
- venv + `pip install -r requirements.txt`
- Auto-generierung eines zufälligen `API_KEY`
- systemd-Service `anna-ig-api.service` (Auto-Start, Auto-Restart, gehärtet)
- Health-Check

Updates später einfach mit `sudo bash deploy/update.sh`.

---

## Voraussetzungen (Meta-Setup)

Das ist einmalig nötig und dauert ca. 15 Minuten.

### 1. Instagram-Account auf Business / Creator umstellen
In der Instagram-App: *Einstellungen → Konto → Zu professionellem Konto wechseln → Business*.
Privat-Accounts können die Graph API nicht nutzen.

### 2. App im Meta Developer Portal anlegen
1. https://developers.facebook.com → **My Apps → Create App**
2. Use Case: **Other** → App-Type: **Business** → Name: z. B. `anna-ig-poster`
3. Im Dashboard: Produkt **Instagram Graph API** hinzufügen.

### 3. Instagram-Account mit Facebook-Seite verknüpfen
- Facebook-Seite anlegen (falls noch keine da)
- IG-Konto in der App mit dieser Seite verbinden

### 4. Long-Lived Access Token holen
1. https://developers.facebook.com/tools/explorer/ → eigene App auswählen.
2. **Get User Access Token** mit diesen Permissions:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
   - `business_management`
3. Token in den **Access Token Debugger** → **Extend Access Token** → ~60 Tage gültig.
4. → `.env` als `IG_ACCESS_TOKEN`.

> **Token läuft nach ~60 Tagen ab.** Reminder einplanen oder alle ~50 Tage neu holen.

### 5. Instagram Business Account ID
Im Graph API Explorer:
```
GET /me/accounts
GET /{page-id}?fields=instagram_business_account
```
→ liefert die `IG_BUSINESS_ACCOUNT_ID`.

### 6. Imgur Client-ID (Bild-Hosting)
Die Graph API verlangt **öffentliche Bild-URLs**. Imgur ist kostenlos:
1. https://api.imgur.com/oauth2/addclient
2. „**OAuth 2 authorization without callback URL**"
3. Client-ID → `.env` als `IMGUR_CLIENT_ID`.

(Alternative: wenn Anna bereits öffentlich gehostete Bilder hat, kann sie deren URL direkt mitgeben — Imgur wird übersprungen.)

---

## Wie Anna posten kann

Anna ist ein Bot auf demselben Server. Sie hat drei Optionen — empfohlen ist die HTTP-API:

### A) HTTP-API (empfohlen — der laufende systemd-Service)

```bash
API_KEY=$(grep ^API_KEY= /opt/anna-ig-poster/.env | cut -d= -f2)

# Feed-Post mit lokal vorhandenem Bild (base64)
B64=$(base64 -w0 /pfad/zu/bild.jpg)
curl -X POST http://127.0.0.1:8765/post/feed \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d "{\"image_b64\":\"$B64\",\"caption\":\"Mein Tipp ...\",\"hashtags\":[\"#marketing\"]}"

# Feed-Post mit bereits öffentlich gehostetem Bild
curl -X POST http://127.0.0.1:8765/post/feed \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"image_url":"https://i.imgur.com/abc.jpg","caption":"...","hashtags":["#a"]}'

# Story
curl -X POST http://127.0.0.1:8765/post/story \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"image_url":"https://i.imgur.com/abc.jpg"}'

# Karussell
curl -X POST http://127.0.0.1:8765/post/carousel \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"image_urls":["https://...1.jpg","https://...2.jpg"],"caption":"…","hashtags":["#a"]}'

# Reel (Video muss öffentlich erreichbar sein)
curl -X POST http://127.0.0.1:8765/post/reel \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"video_url":"https://.../reel.mp4","caption":"…","hashtags":["#a"]}'
```

Endpoints:
- `GET  /health`
- `POST /post/feed`     `{ image_url | image_b64, caption, hashtags }`
- `POST /post/carousel` `{ image_urls | images_b64, caption, hashtags }`
- `POST /post/story`    `{ image_url | image_b64 }`
- `POST /post/reel`     `{ video_url, caption, hashtags }`

### B) CLI (für manuelle Tests)
```bash
sudo -u anna /opt/anna-ig-poster/.venv/bin/python /opt/anna-ig-poster/post.py feed \
  --image /pfad/bild.jpg --caption "..." --hashtags "#a #b"
```

### C) Python-Import (falls Anna im selben Python-Prozess läuft)
```python
from main import post_feed
post_feed("bild.jpg", caption="…", hashtags=["#a"])
```

---

## Service verwalten

```bash
sudo systemctl status anna-ig-api          # läuft sie?
sudo systemctl restart anna-ig-api         # nach .env-Änderung
sudo systemctl stop anna-ig-api
sudo journalctl -u anna-ig-api -f          # live-logs
tail -f /var/log/anna-ig-api.log
tail -f /opt/anna-ig-poster/logs/posting.log
```

---

## Sicherheit

- API lauscht **nur auf 127.0.0.1** — kein Port nach außen offen.
- Falls UFW aktiv: kein zusätzlicher Regel-Eintrag nötig (loopback ist immer erlaubt).
- `API_KEY` schützt zusätzlich gegen Angriffe von anderen Prozessen auf demselben Host.
- `.env` hat Mode 600, gehört dem `anna`-User.
- Service läuft als unprivilegierter System-User mit systemd-Hardening (`ProtectSystem=strict`, `NoNewPrivileges`, `PrivateTmp`).
- **Niemals** den Token committen — `.env` steht in `.gitignore`.

---

## Häufige Fehler

| Fehler | Lösung |
|---|---|
| `(#10) Application does not have permission` | App-Permissions fehlen oder Token zu kurzlebig — Long-Lived Token holen |
| `(#100) Object does not exist…` | Falsche `IG_BUSINESS_ACCOUNT_ID` |
| `media url is not accessible` | Bild ist nicht öffentlich erreichbar — Imgur-Client-ID prüfen |
| `Invalid OAuth access token` | Token abgelaufen (>60 Tage) — neu holen |
| Service startet nicht | `sudo journalctl -u anna-ig-api -n 50` — meist `.env` unvollständig |

---

## Dateien im Projekt

```
.
├── README.md
├── requirements.txt
├── config.yaml              # Default-Hashtags, Sprache, Logging
├── .env.example             # Vorlage für Tokens / Keys
├── .gitignore
│
├── instagram_publisher.py   # Kern: spricht die Graph API
├── main.py                  # Importierbare High-Level-API
├── post.py                  # CLI
├── api.py                   # FastAPI-Server (der Hauptweg)
├── content_generator.py     # Optional: KI-Drafts (Anna macht das normalerweise selbst)
│
├── deploy/
│   ├── install.sh           # Ubuntu-Installer
│   ├── update.sh            # Code-Update + Service-Restart
│   └── anna-ig-api.service  # systemd-Unit
│
├── content/                 # Annas Bilder/Videos (vom Bot zu füllen)
└── logs/                    # posting.log
```

---

## Lokale Entwicklung (Windows / macOS)

Für reine Entwicklung ohne den Server:
```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS
pip install -r requirements.txt
copy .env.example .env           # bzw. cp
# DRY_RUN=true lassen → keine echten Posts
python post.py feed --image content/test.jpg --caption "Hallo"
```
