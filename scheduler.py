"""
scheduler.py — Logique d'automatisation de la séquence J0 / J3 / J5
============================================================
Ce module est appelé par un job périodique (toutes les heures par ex.)
qui vérifie quels prospects doivent recevoir le prochain email de leur séquence.
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import Campagne, CampagneProspect, Prospect, EmailLog
from mailer import send_campaign_step

DELAI_J3 = timedelta(days=3)
DELAI_J5 = timedelta(days=5)


def lancer_campagne(db: Session, campagne_id: int):
    """
    Démarre une campagne : associe tous les prospects correspondants (métier + ville filtre)
    qui ne sont pas déjà dans une campagne active, et envoie le J0 immédiatement.
    """
    campagne = db.query(Campagne).filter(Campagne.id == campagne_id).first()
    if not campagne:
        return {"erreur": "Campagne introuvable"}

    query = db.query(Prospect).filter(
        Prospect.metier == campagne.metier,
        Prospect.email.isnot(None),
        Prospect.email != "",
        Prospect.statut == "nouveau",
    )
    if campagne.ville_filtre:
        query = query.filter(Prospect.ville == campagne.ville_filtre)

    prospects = query.all()

    nb_envoyes = 0
    nb_echecs = 0

    for prospect in prospects:
        cp = CampagneProspect(
            campagne_id=campagne.id,
            prospect_id=prospect.id,
            etape_actuelle="j0",
        )
        db.add(cp)
        db.flush()  # récupère cp.id avant commit

        log = EmailLog(
            prospect_id=prospect.id,
            campagne_id=campagne.id,
            etape="j0",
            sujet=campagne.sujet_j0,
            statut_envoi="en_cours",
        )
        db.add(log)
        db.flush()

        succes, erreur = send_campaign_step(prospect, campagne, "j0", log.id)

        if succes:
            cp.date_j0_envoye = datetime.utcnow()
            log.statut_envoi = "succes"
            prospect.statut = "en_campagne"
            prospect.date_derniere_action = datetime.utcnow()
            nb_envoyes += 1
        else:
            log.statut_envoi = "echec"
            log.erreur = erreur
            nb_echecs += 1

    campagne.statut = "active"
    campagne.date_lancement = datetime.utcnow()
    db.commit()

    return {"prospects_associes": len(prospects), "envoyes": nb_envoyes, "echecs": nb_echecs}


def traiter_relances():
    """
    À appeler périodiquement (cron/scheduler).
    Vérifie tous les CampagneProspect en attente de J3 ou J5 et envoie si le délai est atteint.
    """
    from models import SessionLocal
    db = SessionLocal()

    try:
        maintenant = datetime.utcnow()
        resultats = {"j3_envoyes": 0, "j5_envoyes": 0, "echecs": 0}

        # ----- J3 -----
        en_attente_j3 = db.query(CampagneProspect).filter(
            CampagneProspect.etape_actuelle == "j0",
            CampagneProspect.desinscrit == False,
            CampagneProspect.a_repondu == False,
        ).all()

        for cp in en_attente_j3:
            if not cp.date_j0_envoye:
                continue
            if maintenant - cp.date_j0_envoye >= DELAI_J3:
                prospect = cp.prospect
                campagne = cp.campagne

                log = EmailLog(
                    prospect_id=prospect.id,
                    campagne_id=campagne.id,
                    etape="j3",
                    sujet=campagne.sujet_j3,
                    statut_envoi="en_cours",
                )
                db.add(log)
                db.flush()

                succes, erreur = send_campaign_step(prospect, campagne, "j3", log.id)

                if succes:
                    cp.date_j3_envoye = maintenant
                    cp.etape_actuelle = "j3"
                    log.statut_envoi = "succes"
                    resultats["j3_envoyes"] += 1
                else:
                    log.statut_envoi = "echec"
                    log.erreur = erreur
                    resultats["echecs"] += 1

        # ----- J5 -----
        en_attente_j5 = db.query(CampagneProspect).filter(
            CampagneProspect.etape_actuelle == "j3",
            CampagneProspect.desinscrit == False,
            CampagneProspect.a_repondu == False,
        ).all()

        for cp in en_attente_j5:
            if not cp.date_j3_envoye:
                continue
            if maintenant - cp.date_j3_envoye >= (DELAI_J5 - DELAI_J3):
                prospect = cp.prospect
                campagne = cp.campagne

                log = EmailLog(
                    prospect_id=prospect.id,
                    campagne_id=campagne.id,
                    etape="j5",
                    sujet=campagne.sujet_j5,
                    statut_envoi="en_cours",
                )
                db.add(log)
                db.flush()

                succes, erreur = send_campaign_step(prospect, campagne, "j5", log.id)

                if succes:
                    cp.date_j5_envoye = maintenant
                    cp.etape_actuelle = "termine"
                    log.statut_envoi = "succes"
                    resultats["j5_envoyes"] += 1
                else:
                    log.statut_envoi = "echec"
                    log.erreur = erreur
                    resultats["echecs"] += 1

        db.commit()
        return resultats

    finally:
        db.close()
