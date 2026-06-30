"""
whatsapp_sender.py — Envoi de messages WhatsApp via Meta Cloud API
============================================================
Utilise des templates pré-approuvés par Meta (catégorie Marketing).

Phone Number ID actuel : 1071508352718942 (numéro de TEST Meta)
⚠️ En mode test, seuls les numéros enregistrés dans la liste de test
   Meta peuvent recevoir des messages (max 5 numéros).
   Basculez vers le Phone Number ID définitif une fois le numéro
   de production validé.
"""

import requests
import os

# ============================================================
# CONFIG
# ============================================================
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "1071508352718942")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "VOTRE_ACCESS_TOKEN_META")
WHATSAPP_API_VERSION = "v21.0"

BASE_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"


def clean_phone(phone: str) -> str:
    """Nettoie un numéro de téléphone au format international sans espaces/symboles."""
    if not phone:
        return ""
    cleaned = phone.replace(" ", "").replace("-", "").replace(".", "").replace("(", "").replace(")", "")
    if cleaned.startswith("0"):
        cleaned = "+33" + cleaned[1:]  # adapte le préfixe France par défaut
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


def send_template_message(
    to_phone: str,
    template_name: str,
    language_code: str = "fr",
    body_params: list[str] = None,
) -> tuple[bool, str]:
    """
    Envoie un message template WhatsApp approuvé.

    to_phone : numéro destinataire (sera nettoyé automatiquement)
    template_name : nom exact du template tel qu'approuvé dans Meta Business Manager
    body_params : liste des valeurs pour les variables {{1}}, {{2}}, etc. du template

    Retourne (succes: bool, erreur_ou_message_id: str)
    """
    phone = clean_phone(to_phone)
    if not phone:
        return False, "Numéro de téléphone invalide ou vide"

    components = []
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in body_params]
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    }

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(BASE_URL, json=payload, headers=headers, timeout=15)
        data = response.json()

        if response.status_code == 200 and "messages" in data:
            message_id = data["messages"][0]["id"]
            return True, message_id
        else:
            erreur = data.get("error", {}).get("message", str(data))
            return False, erreur

    except Exception as e:
        return False, str(e)


def send_campaign_step_whatsapp(prospect, etape: str) -> tuple[bool, str]:
    """
    Envoie le template correspondant à une étape de campagne (j0, j3, j5)
    pour un prospect donné. Les noms de templates doivent exister et être
    approuvés dans Meta Business Manager.
    """
    template_map = {
        "j0": "prospection_j0",
        "j3": "prospection_j3",
        "j5": "prospection_j5",
    }

    template_name = template_map.get(etape)
    if not template_name:
        return False, f"Étape inconnue : {etape}"

    numero = prospect.whatsapp or prospect.telephone
    if not numero:
        return False, "Aucun numéro WhatsApp ou téléphone disponible"

    body_params = [
        prospect.nom or "",
        prospect.ville or "votre établissement",
    ]

    return send_template_message(numero, template_name, body_params=body_params)
