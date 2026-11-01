"""Tests sans base : l'API répond et refuse les accès non authentifiés."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_sante():
    assert client.get("/sante").json() == {"statut": "ok"}


def test_acces_sans_jeton_refuse():
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/problemes").status_code == 401
