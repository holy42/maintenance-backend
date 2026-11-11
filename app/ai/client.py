"""Clients du service d'IA. Seul ce module effectue des appels réseau vers l'IA.
La clé d'API reste côté serveur et n'apparaît jamais dans un message d'erreur."""
from typing import Protocol

import httpx

from app.config import settings
from app.core.exceptions import IAIndisponible

import logging 
log = logging.getLogger(__name__)
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
        except httpx.HTTPStatusError as exc:
            log.warning("Gemini a répondu HTTP %s : %s", exc.response.status_code, exc.response.text[:300])
            raise IAIndisponible("Le service d'IA est indisponible.") from exc
        except httpx.HTTPError as exc:
            log.warning("Appel à Gemini impossible : %s", type(exc).__name__)
            raise IAIndisponible("Le service d'IA est indisponible.") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise IAIndisponible("Réponse du service d'IA inexploitable.") from exc


class ClaudeClient:
    """API Messages d'Anthropic. La clé reste côté serveur."""

    def __init__(self) -> None:
        self.nom_modele = settings.claude_model

    def generer_json(self, prompt: str) -> str:
        if not settings.claude_api_key:
            raise IAIndisponible("Service d'IA non configuré.")
        import anthropic                                        # import tardif : inutile en mode mock
        client = anthropic.Anthropic(api_key=settings.claude_api_key, timeout=settings.ai_timeout_seconds, max_retries=2)
        try:
            msg = client.messages.create(
                model=self.nom_modele, max_tokens=settings.claude_max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(b.text for b in msg.content if b.type == "text")      # ignore les blocs de réflexion
        except anthropic.APIStatusError as exc:
            log.warning("Claude a répondu HTTP %s : %s", exc.status_code, str(exc.message)[:300])
            raise IAIndisponible("Le service d'IA est indisponible.") from exc
        except anthropic.APIError as exc:
            log.warning("Appel à Claude impossible : %s", type(exc).__name__)
            raise IAIndisponible("Le service d'IA est indisponible.") from exc

def obtenir_client() -> ClientIA:
    if settings.ai_provider == "gemini":
        return GeminiClient()
    if settings.ai_provider == "claude":
        return ClaudeClient()
    from app.ai.mock import MockClient
    return MockClient()
