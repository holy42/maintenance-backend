from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import utilisateur_courant
from app.database import get_db
from app.main import app
from app.models import Notification, PreferenceCanalNotification


class SessionMemoire:
    def __init__(self):
        self.preferences = {}

    def get(self, modele, cle):
        assert modele is PreferenceCanalNotification
        return self.preferences.get(cle)

    def add(self, preference):
        self.preferences[preference.utilisateur_id] = preference


@pytest.fixture
def client():
    db = SessionMemoire()
    utilisateur = [SimpleNamespace(id=10)]
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[utilisateur_courant] = lambda: utilisateur[0]
    try:
        yield TestClient(app), utilisateur
    finally:
        app.dependency_overrides.clear()


def test_preferences_canaux_activees_par_defaut_et_personnelles(client):
    test_client, utilisateur = client
    url = "/api/v1/notifications/preferences-canaux"

    assert test_client.get(url).json() == {"son": True, "navigateur": True}
    assert test_client.put(url, json={"son": False, "navigateur": True}).status_code == 200
    assert test_client.get(url).json() == {"son": False, "navigateur": True}

    utilisateur[0] = SimpleNamespace(id=11)
    assert test_client.get(url).json() == {"son": True, "navigateur": True}


def test_notifications_depuis_id_ne_retourne_que_les_arrivees_du_destinataire():
    moteur = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Notification.__table__.create(moteur)
    db = Session(moteur)
    db.add_all([
        Notification(id=5, destinataire_id=10, type_evenement="probleme_cree", message="Ancienne", lu=True),
        Notification(id=7, destinataire_id=10, type_evenement="probleme_cree", message="Nouvelle", lu=False),
        Notification(id=8, destinataire_id=11, type_evenement="probleme_cree", message="Autre utilisateur", lu=False),
    ])
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[utilisateur_courant] = lambda: SimpleNamespace(id=10)
    try:
        client = TestClient(app)
        nouvelles = client.get("/api/v1/notifications", params={"apres_id": 5}).json()
        compteur = client.get("/api/v1/notifications/compteur").json()

        assert [n["id"] for n in nouvelles] == [7]
        assert compteur == {"non_lues": 1, "dernier_id": 7}
    finally:
        app.dependency_overrides.clear()
        db.close()
        moteur.dispose()
