# Dashboard Prospection — Agen'C AI

Mini-CRM pour piloter le scraping, l'import de prospects, et les campagnes
email automatisées J0/J3/J5, multi-métiers.

## Architecture

```
prospect_dashboard/
├── main.py              # API FastAPI (routes)
├── models.py             # Schéma base de données (SQLAlchemy)
├── mailer.py              # Envoi emails via Gmail SMTP
├── scheduler.py           # Logique séquence J0/J3/J5
├── requirements.txt
└── static/
    └── index.html         # Dashboard (frontend)
```

## Installation sur le VPS

```bash
ssh votre_user@votre_ip_vps

mkdir -p ~/prospect_dashboard
cd ~/prospect_dashboard

# Uploadez tous les fichiers (main.py, models.py, mailer.py, scheduler.py,
# requirements.txt, et le dossier static/) ici, via scp ou nano.

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

### 1. Gmail SMTP (mot de passe d'application)

1. Allez sur https://myaccount.google.com/security
2. Activez la validation en 2 étapes
3. "Mots de passe des applications" → générez-en un pour "Mail"
4. Notez ce mot de passe (16 caractères, sans espaces dans le code)

### 2. Variables d'environnement

Créez un fichier `.env` ou exportez directement avant de lancer :

```bash
export GMAIL_ADDRESS="contact@agenc-ai.com"
export GMAIL_APP_PASSWORD="votre_mot_de_passe_application"
export TRACKING_BASE_URL="https://prospection.agenc-ai.com"
export SCRAPER_PATH="/home/votre_user/vps_scraper/scraper.py"
export SCRAPER_CONFIG="/home/votre_user/vps_scraper/config.json"
export EXPORTS_DIR="/home/votre_user/vps_scraper/exports"
```

## Lancer en développement

```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

Accédez au dashboard sur `http://votre_ip_vps:8001`

## Déploiement en production (systemd + Nginx)

### Service systemd

Créez `/etc/systemd/system/prospect-dashboard.service` :

```ini
[Unit]
Description=Dashboard Prospection Agen'C AI
After=network.target

[Service]
User=votre_user
WorkingDirectory=/home/votre_user/prospect_dashboard
Environment="GMAIL_ADDRESS=contact@agenc-ai.com"
Environment="GMAIL_APP_PASSWORD=votre_mot_de_passe_application"
Environment="TRACKING_BASE_URL=https://prospection.agenc-ai.com"
ExecStart=/home/votre_user/prospect_dashboard/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable prospect-dashboard
sudo systemctl start prospect-dashboard
sudo systemctl status prospect-dashboard
```

### Nginx + SSL

```nginx
server {
    listen 80;
    server_name prospection.agenc-ai.com;
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo certbot --nginx -d prospection.agenc-ai.com
```

## Utilisation

### 1. Importer des prospects
Onglet **Scraper** → lancez une recherche, ou utilisez le script `vps_scraper`
(voir conversation précédente) en ligne de commande, puis importez le CSV
généré via le bouton **Importer un CSV** dans l'onglet Prospects.

### 2. Créer une campagne
Onglet **Campagnes** → **Nouvelle campagne** → choisissez le métier, rédigez
les 3 emails (J0, J3, J5). Utilisez `{{nom}}`, `{{ville}}`, `{{metier}}` pour
personnaliser automatiquement chaque message.

### 3. Lancer la campagne
Cliquez **Lancer** sur la campagne. Le J0 part immédiatement à tous les
prospects du métier (et de la ville si filtrée) qui ont un email et le statut
"nouveau". Le scheduler interne vérifie toutes les heures qui doit recevoir
J3 (3 jours après J0) ou J5 (5 jours après J0), et envoie automatiquement.

### 4. Suivre la conversion
Onglet **Conversion** → taux d'ouverture (pixel invisible), taux de réponse
(à marquer manuellement pour l'instant — voir endpoint `/api/prospects/{id}/marquer-repondu`).

## Limites connues / améliorations futures

- Le marquage "a répondu" est manuel via API pour l'instant — une intégration
  avec une boîte mail (IMAP) pour détecter les réponses automatiquement serait
  une amélioration naturelle.
- Le déclenchement du scraper depuis le dashboard suppose que `scraper.py` et
  son `config.json` sont déjà en place sur le VPS (voir conversation précédente).
- Gmail SMTP a une limite d'environ 500 emails/jour pour un compte standard.
  Pour des volumes plus importants, envisagez un service dédié (Brevo, Mailgun).
