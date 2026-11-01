"""Clients du service d'IA. Seul ce module effectue des appels réseau vers l'IA.
La clé d'API reste côté serveur et n'apparaît jamais dans un message d'erreur."""
from typing import Protocol

import httpx

from app.config import settings
from app.core.exceptions import IAIndisponible


class ClientIA(Protocol):
    nom_modele: str

    def generer_json(self, prompt: str) -> str: ...


class GeminiClient:
    """Format de requête « generateContent » de l'API Gemini (à confirmer dans la documentation
    officielle de Google : endpoint, modèle disponible et quotas changent dans le temps)."""

    def __init__(self) -> None:
        self.nom_modele = settings.gemini_model

    def generer_json(self, prompt: str) -> str:
        if not settings.gemini_api_key:
            raise IAIndisponible("Service d'IA non configuré.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.nom_modele}:generateContent"
        corps = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
        }
        try:
            r = httpx.post(
                url, json=corps, headers={"x-goog-api-key": settings.gemini_api_key},
                timeout=settings.ai_timeout_seconds,          # jamais d'attente infinie
            )
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except httpx.HTTPError as exc:
            raise IAIndisponible("Le service d'IA est indisponible.") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise IAIndisponible("Réponse du service d'IA inexploitable.") from exc


def obtenir_client() -> ClientIA:
    if settings.ai_provider == "gemini":
        return GeminiClient()
    from app.ai.mock import MockClient
    return MockClient()
