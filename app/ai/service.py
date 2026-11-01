"""Service d'IA : prompts + appel + validation stricte. Point d'entrée unique pour le reste du code.
Si l'IA est indisponible, IAIndisponible (503) est levée : le reste de l'application continue de fonctionner."""
import json
import re

from pydantic import BaseModel, ValidationError

from app.ai import prompts
from app.ai.client import ClientIA, obtenir_client
from app.ai.schemas import (
    DescriptionTestIA, HypothesesIA, PropositionCritere, PropositionTaches, ReponseAssistant, ReponseDiagnostic,
)
from app.core.exceptions import IAIndisponible


class ServiceIA:
    def __init__(self, client: ClientIA | None = None):
        self.client = client or obtenir_client()

    @property
    def modele(self) -> str:
        return self.client.nom_modele

    @property
    def version_prompt(self) -> str:
        return prompts.VERSION_PROMPT

    def _appeler(self, prompt: str, schema: type[BaseModel]):
        for tentative in range(2):                       # une nouvelle tentative si la forme est invalide
            brut = self.client.generer_json(prompt)
            brut = re.sub(r"^```(?:json)?|```$", "", brut.strip(), flags=re.MULTILINE).strip()
            try:
                return schema.model_validate_json(brut)
            except (ValidationError, json.JSONDecodeError):
                if tentative == 1:
                    raise IAIndisponible("Réponse du service d'IA non conforme au schéma attendu.")
        raise IAIndisponible("Réponse du service d'IA non conforme.")

    def diagnostiquer(self, contexte: dict) -> ReponseDiagnostic:
        return self._appeler(prompts.prompt_diagnostic(contexte, ReponseDiagnostic), ReponseDiagnostic)

    def proposer_taches(self, contexte: dict) -> PropositionTaches:
        return self._appeler(prompts.prompt_taches(contexte, PropositionTaches), PropositionTaches)

    def formuler_critere(self, description: str) -> PropositionCritere:
        return self._appeler(prompts.prompt_critere(description, PropositionCritere), PropositionCritere)

    def repondre(self, contexte: dict, historique: list[dict], question: str) -> ReponseAssistant:
        return self._appeler(prompts.prompt_assistant(contexte, historique, question, ReponseAssistant), ReponseAssistant)

    def proposer_description_test(self, contexte: dict) -> DescriptionTestIA:
        return self._appeler(prompts.prompt_description_test(contexte, DescriptionTestIA), DescriptionTestIA)

    def interpreter(self, contexte: dict) -> HypothesesIA:
        return self._appeler(prompts.prompt_interpretation(contexte, HypothesesIA), HypothesesIA)


def get_service_ia() -> ServiceIA:
    """Dépendance FastAPI (surchargeable dans les tests)."""
    return ServiceIA()
