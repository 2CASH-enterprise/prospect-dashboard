"""
main.py — API FastAPI du dashboard de prospection
============================================================
Lancement :
    uvicorn main:app --host 0.0.0.0 --port 8001 --reload

En production (avec systemd, voir README) :
    uvicorn main:app --host 0.0.0.0 --port 8001
"""

import csv
import io
import subprocess
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from apscheduler.schedulers.background import BackgroundScheduler

from models import init_db, get_db, Prospect, Campagne, CampagneProspect, EmailLog
from scheduler import lancer_campagne, traiter_relances

app = FastAPI(title="Dashboard Prospection — Agen'C AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# ============================================================
# Scheduler automatique pour J3/J5 — vérifie toutes les heures
# ============================================================
scheduler = BackgroundScheduler()
scheduler.add_job(traiter_relances, "interval", hours=1, id="relances_auto")
scheduler.start()

# Chemin vers le script scraper VPS (voir conversation précédente)
SCRAPER_PATH = os.getenv("SCRAPER_PATH", "/home/votre_user/vps_scraper/scraper.py")
SCRAPER_CONFIG = os.getenv("SCRAPER_CONFIG", "/home/votre_user/vps_scraper/config.json")
EXPORTS_DIR = os.getenv("EXPORTS_DIR", "/home/votre_user/vps_scraper/exports")


# ============================================================
# PROSPECTS
# ============================================================

@app.get("/api/prospects")
def liste_prospects(
    metier: Optional[str] = None,
    ville: Optional[str] = None,
    statut: Optional[str] = None,
    avec_email_uniquement: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Prospect)
    if metier:
        query = query.filter(Prospect.metier == metier)
    if ville:
        query = query.filter(Prospect.ville == ville)
    if statut:
        query = query.filter(Prospect.statut == statut)
    if avec_email_uniquement:
        query = query.filter(Prospect.email.isnot(None), Prospect.email != "")

    prospects = query.order_by(Prospect.date_import.desc()).all()
    return [
        {
            "id": p.id, "nom": p.nom, "metier": p.metier, "ville": p.ville,
            "adresse": p.adresse, "telephone": p.telephone, "whatsapp": p.whatsapp,
            "email": p.email, "site_web": p.site_web, "note": p.note,
            "nb_avis": p.nb_avis, "statut": p.statut,
            "date_import": p.date_import.isoformat() if p.date_import else None,
        }
        for p in prospects
    ]


@app.get("/api/prospects/metiers")
def liste_metiers(db: Session = Depends(get_db)):
    """Liste des métiers distincts présents en base, avec compteur."""
    rows = db.query(Prospect.metier, func.count(Prospect.id)).group_by(Prospect.metier).all()
    return [{"metier": m, "total": c} for m, c in rows]


@app.get("/api/prospects/villes")
def liste_villes(metier: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Prospect.ville, func.count(Prospect.id))
    if metier:
        query = query.filter(Prospect.metier == metier)
    rows = query.group_by(Prospect.ville).all()
    return [{"ville": v, "total": c} for v, c in rows]


def get_field(row: dict, *keys):
    """Retourne la première valeur non vide trouvée parmi plusieurs noms de colonnes possibles."""
    for k in keys:
        val = row.get(k)
        if val:
            return val.strip() if isinstance(val, str) else val
    return ""


@app.post("/api/prospects/import")
async def importer_csv(
    metier: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Importe un CSV et l'associe à un métier.
    Reconnaît automatiquement plusieurs formats :
    - Format simplifié (scraper.py maison) : nom, adresse, telephone, email, site_web, whatsapp, note, nb_avis, ville, place_id
    - Format Apify brut (Google Maps Scraper) : title, address, phoneUnformatted, website, totalScore, reviewsCount, city, placeId
    """
    contenu = await file.read()
    texte = contenu.decode("utf-8-sig")  # utf-8-sig gère le BOM Excel/Apify
    reader = csv.DictReader(io.StringIO(texte))

    nb_importes = 0
    nb_doublons = 0
    nb_erreurs = 0
    erreurs_detail = []

    for i, row in enumerate(reader, start=2):
        try:
            place_id = get_field(row, "place_id", "placeId", "fid", "cid")
            nom = get_field(row, "nom", "name", "title")

            if not nom:
                nb_erreurs += 1
                erreurs_detail.append(f"Ligne {i} : nom manquant, ignorée")
                continue

            if place_id:
                existe = db.query(Prospect).filter(Prospect.place_id == place_id).first()
                if existe:
                    nb_doublons += 1
                    continue
            else:
                place_id = None

            note_raw = get_field(row, "note", "totalScore", "rating")
            nb_avis_raw = get_field(row, "nb_avis", "reviewsCount", "user_ratings_total")

            prospect = Prospect(
                nom=nom,
                metier=metier,
                ville=get_field(row, "ville", "city"),
                adresse=get_field(row, "adresse", "address"),
                telephone=get_field(row, "telephone", "phone", "phoneUnformatted"),
                whatsapp=get_field(row, "whatsapp"),
                email=get_field(row, "email"),
                site_web=get_field(row, "site_web", "website"),
                note=float(note_raw) if note_raw else None,
                nb_avis=int(float(nb_avis_raw)) if nb_avis_raw else None,
                google_maps_url=get_field(row, "google_maps", "url"),
                place_id=place_id,
            )
            db.add(prospect)
            db.flush()
            nb_importes += 1

        except Exception as e:
            db.rollback()
            nb_erreurs += 1
            erreurs_detail.append(f"Ligne {i} : {str(e)}")
            continue

    db.commit()
    return {
        "importes": nb_importes,
        "doublons_ignores": nb_doublons,
        "erreurs": nb_erreurs,
        "detail_erreurs": erreurs_detail[:10],
    }


@app.delete("/api/prospects/{prospect_id}")
def supprimer_prospect(prospect_id: int, db: Session = Depends(get_db)):
    p = db.query(Prospect).filter(Prospect.id == prospect_id).first()
    if not p:
        raise HTTPException(404, "Prospect introuvable")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ============================================================
# SCRAPER — déclenchement depuis le dashboard
# ============================================================

@app.post("/api/scraper/lancer")
def lancer_scraping(profession: str, limit_villes: Optional[int] = None, background_tasks: BackgroundTasks = None):
    """
    Déclenche le scraper.py en arrière-plan sur le VPS.
    Le résultat CSV sera disponible dans exports/ puis importable manuellement,
    ou auto-importé si vous activez l'import auto (voir /api/scraper/resultats).
    """
    cmd = ["python3", SCRAPER_PATH, "--profession", profession]
    if limit_villes:
        cmd += ["--limit-villes", str(limit_villes)]

    try:
        subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return {"statut": "lance", "commande": " ".join(cmd)}
    except Exception as e:
        raise HTTPException(500, f"Erreur lancement scraper : {str(e)}")


@app.get("/api/scraper/resultats")
def lister_exports():
    """Liste les fichiers CSV générés par le scraper, disponibles pour import."""
    if not os.path.exists(EXPORTS_DIR):
        return []
    fichiers = sorted(os.listdir(EXPORTS_DIR), reverse=True)
    return [f for f in fichiers if f.endswith(".csv")]


# ============================================================
# CAMPAGNES
# ============================================================

@app.get("/api/campagnes")
def liste_campagnes(db: Session = Depends(get_db)):
    campagnes = db.query(Campagne).order_by(Campagne.date_creation.desc()).all()
    result = []
    for c in campagnes:
        nb_prospects = db.query(CampagneProspect).filter(CampagneProspect.campagne_id == c.id).count()
        nb_repondus = db.query(CampagneProspect).filter(
            CampagneProspect.campagne_id == c.id, CampagneProspect.a_repondu == True
        ).count()
        result.append({
            "id": c.id, "nom": c.nom, "metier": c.metier, "ville_filtre": c.ville_filtre,
            "statut": c.statut, "nb_prospects": nb_prospects, "nb_repondus": nb_repondus,
            "date_creation": c.date_creation.isoformat() if c.date_creation else None,
            "date_lancement": c.date_lancement.isoformat() if c.date_lancement else None,
        })
    return result


@app.post("/api/campagnes")
def creer_campagne(
    nom: str, metier: str,
    sujet_j0: str, corps_j0: str,
    sujet_j3: str, corps_j3: str,
    sujet_j5: str, corps_j5: str,
    ville_filtre: Optional[str] = None,
    db: Session = Depends(get_db),
):
    campagne = Campagne(
        nom=nom, metier=metier, ville_filtre=ville_filtre,
        sujet_j0=sujet_j0, corps_j0=corps_j0,
        sujet_j3=sujet_j3, corps_j3=corps_j3,
        sujet_j5=sujet_j5, corps_j5=corps_j5,
    )
    db.add(campagne)
    db.commit()
    db.refresh(campagne)
    return {"id": campagne.id, "statut": "creee"}


@app.post("/api/campagnes/{campagne_id}/lancer")
def demarrer_campagne(campagne_id: int, db: Session = Depends(get_db)):
    resultat = lancer_campagne(db, campagne_id)
    return resultat


@app.get("/api/campagnes/{campagne_id}/stats")
def stats_campagne(campagne_id: int, db: Session = Depends(get_db)):
    total = db.query(CampagneProspect).filter(CampagneProspect.campagne_id == campagne_id).count()

    j0_envoyes = db.query(CampagneProspect).filter(
        CampagneProspect.campagne_id == campagne_id, CampagneProspect.date_j0_envoye.isnot(None)
    ).count()
    j3_envoyes = db.query(CampagneProspect).filter(
        CampagneProspect.campagne_id == campagne_id, CampagneProspect.date_j3_envoye.isnot(None)
    ).count()
    j5_envoyes = db.query(CampagneProspect).filter(
        CampagneProspect.campagne_id == campagne_id, CampagneProspect.date_j5_envoye.isnot(None)
    ).count()

    ouverts = db.query(CampagneProspect).filter(
        CampagneProspect.campagne_id == campagne_id,
        (CampagneProspect.j0_ouvert == True) | (CampagneProspect.j3_ouvert == True) | (CampagneProspect.j5_ouvert == True)
    ).count()

    repondus = db.query(CampagneProspect).filter(
        CampagneProspect.campagne_id == campagne_id, CampagneProspect.a_repondu == True
    ).count()

    return {
        "total_prospects": total,
        "j0_envoyes": j0_envoyes, "j3_envoyes": j3_envoyes, "j5_envoyes": j5_envoyes,
        "taux_ouverture": round(ouverts / total * 100, 1) if total else 0,
        "taux_reponse": round(repondus / total * 100, 1) if total else 0,
        "repondus": repondus,
    }


# ============================================================
# TRACKING (pixel d'ouverture + désinscription)
# ============================================================

PIXEL_GIF = bytes.fromhex(
    "47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b"
)


@app.get("/track/open/{email_log_id}")
def track_open(email_log_id: int, db: Session = Depends(get_db)):
    log = db.query(EmailLog).filter(EmailLog.id == email_log_id).first()
    if log:
        cp = db.query(CampagneProspect).filter(
            CampagneProspect.prospect_id == log.prospect_id,
            CampagneProspect.campagne_id == log.campagne_id,
        ).first()
        if cp:
            field = f"{log.etape}_ouvert"
            if hasattr(cp, field):
                setattr(cp, field, True)
                db.commit()

    return Response(content=PIXEL_GIF, media_type="image/gif")


@app.get("/unsubscribe/{prospect_id}")
def unsubscribe(prospect_id: int, db: Session = Depends(get_db)):
    cps = db.query(CampagneProspect).filter(CampagneProspect.prospect_id == prospect_id).all()
    for cp in cps:
        cp.desinscrit = True
    prospect = db.query(Prospect).filter(Prospect.id == prospect_id).first()
    if prospect:
        prospect.statut = "desinscrit"
    db.commit()
    return {"message": "Vous avez été désinscrit avec succès."}


@app.post("/api/prospects/{prospect_id}/marquer-repondu")
def marquer_repondu(prospect_id: int, campagne_id: int, db: Session = Depends(get_db)):
    cp = db.query(CampagneProspect).filter(
        CampagneProspect.prospect_id == prospect_id, CampagneProspect.campagne_id == campagne_id
    ).first()
    if cp:
        cp.a_repondu = True
        cp.date_reponse = datetime.utcnow()
    prospect = db.query(Prospect).filter(Prospect.id == prospect_id).first()
    if prospect:
        prospect.statut = "repondu"
    db.commit()
    return {"ok": True}


# ============================================================
# DASHBOARD STATS GLOBALES
# ============================================================

@app.get("/api/stats/globales")
def stats_globales(db: Session = Depends(get_db)):
    total_prospects = db.query(Prospect).count()
    total_avec_email = db.query(Prospect).filter(Prospect.email.isnot(None), Prospect.email != "").count()
    total_campagnes = db.query(Campagne).count()
    campagnes_actives = db.query(Campagne).filter(Campagne.statut == "active").count()
    total_convertis = db.query(Prospect).filter(Prospect.statut == "converti").count()

    return {
        "total_prospects": total_prospects,
        "total_avec_email": total_avec_email,
        "total_campagnes": total_campagnes,
        "campagnes_actives": campagnes_actives,
        "total_convertis": total_convertis,
    }


# ============================================================
# FRONTEND STATIQUE
# ============================================================

if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
