"""
mailer.py — Envoi d'emails via Gmail SMTP
============================================================
Pour utiliser Gmail SMTP, vous devez créer un "mot de passe d'application" :
1. Allez sur https://myaccount.google.com/security
2. Activez la validation en 2 étapes si pas déjà fait
3. Cherchez "Mots de passe des applications"
4. Générez un mot de passe pour "Mail"
5. Utilisez ce mot de passe ici (PAS votre mot de passe Gmail normal)
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# ============================================================
# CONFIG — à adapter via variables d'environnement en prod
# ============================================================
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "contact@agenc-ai.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "VOTRE_MOT_DE_PASSE_APPLICATION")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

TRACKING_PIXEL_BASE_URL = os.getenv("TRACKING_BASE_URL", "https://votre-domaine.com")


def build_tracking_pixel(email_log_id: int) -> str:
    """Pixel invisible 1x1 pour détecter l'ouverture de l'email."""
    return f'<img src="{TRACKING_PIXEL_BASE_URL}/track/open/{email_log_id}" width="1" height="1" style="display:none" alt="">'


def build_unsubscribe_link(prospect_id: int) -> str:
    return f'{TRACKING_PIXEL_BASE_URL}/unsubscribe/{prospect_id}'


def personalize(template: str, prospect) -> str:
    """Remplace les variables {{nom}}, {{ville}}, {{metier}} dans le template."""
    return (
        template
        .replace("{{nom}}", prospect.nom or "")
        .replace("{{ville}}", prospect.ville or "")
        .replace("{{metier}}", prospect.metier or "")
    )


def send_email(to_email: str, subject: str, html_body: str) -> tuple[bool, str]:
    """
    Envoie un email via Gmail SMTP.
    Retourne (succes: bool, erreur: str|None)
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = to_email

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())

        return True, ""

    except Exception as e:
        return False, str(e)


def send_campaign_step(prospect, campagne, etape: str, email_log_id: int) -> tuple[bool, str]:
    """Envoie l'email correspondant à une étape (j0, j3, j5) pour un prospect donné."""
    sujet_field = f"sujet_{etape}"
    corps_field = f"corps_{etape}"

    sujet = getattr(campagne, sujet_field, "")
    corps = getattr(campagne, corps_field, "")

    sujet_perso = personalize(sujet, prospect)
    corps_perso = personalize(corps, prospect)

    pixel = build_tracking_pixel(email_log_id)
    unsub = build_unsubscribe_link(prospect.id)

    html_final = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        {corps_perso.replace(chr(10), '<br>')}
        <br><br>
        <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
        <p style="font-size: 11px; color: #999;">
            Vous recevez cet email car votre entreprise est référencée publiquement.
            <a href="{unsub}" style="color: #999;">Se désinscrire</a>
        </p>
        {pixel}
    </body>
    </html>
    """

    return send_email(prospect.email, sujet_perso, html_final)
