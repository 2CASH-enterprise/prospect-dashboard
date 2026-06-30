"""
models.py — Schéma de base de données (SQLAlchemy + SQLite)
============================================================
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

DATABASE_URL = "sqlite:///./prospects.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Prospect(Base):
    __tablename__ = "prospects"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String, nullable=False)
    metier = Column(String, index=True)          # coiffeurs, avocats, restaurants...
    ville = Column(String, index=True)
    adresse = Column(String)
    telephone = Column(String)
    whatsapp = Column(String)
    email = Column(String, index=True)
    site_web = Column(String)
    note = Column(Float)
    nb_avis = Column(Integer)
    google_maps_url = Column(String)
    place_id = Column(String, unique=True, index=True, nullable=True)

    statut = Column(String, default="nouveau")
    # nouveau | en_campagne | repondu | converti | desinscrit | injoignable

    date_import = Column(DateTime, default=datetime.utcnow)
    date_derniere_action = Column(DateTime, nullable=True)
    notes = Column(Text, default="")

    campagnes = relationship("CampagneProspect", back_populates="prospect")


class Campagne(Base):
    __tablename__ = "campagnes"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String, nullable=False)
    metier = Column(String, index=True)
    ville_filtre = Column(String, nullable=True)   # optionnel, filtre par ville

    sujet_j0 = Column(String, default="")
    corps_j0 = Column(Text, default="")
    sujet_j3 = Column(String, default="")
    corps_j3 = Column(Text, default="")
    sujet_j5 = Column(String, default="")
    corps_j5 = Column(Text, default="")

    statut = Column(String, default="brouillon")    # brouillon | active | terminee | pause
    date_creation = Column(DateTime, default=datetime.utcnow)
    date_lancement = Column(DateTime, nullable=True)

    prospects_lies = relationship("CampagneProspect", back_populates="campagne")


class CampagneProspect(Base):
    """Table de liaison — suit l'avancement de chaque prospect dans une campagne."""
    __tablename__ = "campagne_prospects"

    id = Column(Integer, primary_key=True, index=True)
    campagne_id = Column(Integer, ForeignKey("campagnes.id"))
    prospect_id = Column(Integer, ForeignKey("prospects.id"))

    etape_actuelle = Column(String, default="j0")   # j0 | j3 | j5 | termine
    date_j0_envoye = Column(DateTime, nullable=True)
    date_j3_envoye = Column(DateTime, nullable=True)
    date_j5_envoye = Column(DateTime, nullable=True)

    j0_ouvert = Column(Boolean, default=False)
    j3_ouvert = Column(Boolean, default=False)
    j5_ouvert = Column(Boolean, default=False)

    a_repondu = Column(Boolean, default=False)
    date_reponse = Column(DateTime, nullable=True)

    desinscrit = Column(Boolean, default=False)

    campagne = relationship("Campagne", back_populates="prospects_lies")
    prospect = relationship("Prospect", back_populates="campagnes")


class EmailLog(Base):
    """Historique brut de chaque email envoyé, pour debug/audit."""
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, index=True)
    prospect_id = Column(Integer, ForeignKey("prospects.id"))
    campagne_id = Column(Integer, ForeignKey("campagnes.id"))
    etape = Column(String)               # j0, j3, j5
    sujet = Column(String)
    statut_envoi = Column(String)        # succes | echec
    erreur = Column(Text, nullable=True)
    date_envoi = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
