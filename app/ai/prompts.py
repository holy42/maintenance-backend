"""Construction des prompts. Pas d'entraînement de modèle : prompts + schéma de sortie strict."""
import json

from pydantic import BaseModel

VERSION_PROMPT = "v2"

REGLES = """Tu es un assistant d'aide à la maintenance d'applications.
Règles impératives :
- Tu PROPOSES, tu ne décides jamais et tu ne modifies jamais le code source.
- Tu distingues les faits (présents dans le contexte) des hypothèses.
- Si une information manque, tu le dis explicitement au lieu d'inventer une cause.
- Tu n'affirmes jamais qu'un problème est corrigé : seule une validation humaine peut l'établir.
- Tu réponds uniquement en JSON conforme au schéma fourni, en français, sans texte autour.
- Ne reproduis aucun secret (mot de passe, clé) qui apparaîtrait dans le contexte."""


def _prompt(type_: str, consigne: str, contexte: dict, schema: type[BaseModel], extra: str = "") -> str:
    return (
        f"# TYPE: {type_}\n{REGLES}\n\n## Tâche\n{consigne}\n{extra}\n\n"
        f"## Contexte (JSON)\n{json.dumps(contexte, ensure_ascii=False, default=str)}\n\n"
        f"## Schéma JSON de la réponse\n{json.dumps(schema.model_json_schema(), ensure_ascii=False)}\n"
    )


def prompt_diagnostic(contexte: dict, schema: type[BaseModel]) -> str:
    return _prompt(
        "diagnostic",
        "Explique les causes probables du problème et propose 1 à 4 solutions, chacune avec un extrait de code "
        "séparé (de préférence en diff unifié avec les en-têtes `--- a/chemin` et `+++ b/chemin`, en n'utilisant que des fichiers "
        "présents dans le contexte), ses risques et des tests de validation. Indique ce que tu ne sais pas. "
        "Le contexte contient `fiabilite_preuve` (fiabilité estimée de la preuve fournie par l'outil d'analyse) et "
        "`incertitudes_identifiees` : si la fiabilité est faible ou moyenne, dis-le explicitement et recommande d'abord de "
        "confirmer la preuve. Remplis `verifications_recommandees` avec 3 à 5 vérifications concrètes qu'un humain doit effectuer ; "
        "n'affirme jamais qu'un problème est corrigé.",
        contexte, schema,
    )


def prompt_taches(contexte: dict, schema: type[BaseModel]) -> str:
    return _prompt(
        "taches",
        "Propose 1 à 5 tâches pour résoudre le problème, chacune avec une durée estimée (simple indication), "
        "des sous-tâches ordonnées et des critères d'acceptation vérifiables. L'utilisateur choisira.",
        contexte, schema,
    )


def prompt_critere(description: str, schema: type[BaseModel]) -> str:
    return _prompt(
        "critere",
        "Reformule ce critère de vérification en une formulation structurée (condition, attendu, portée), "
        "classe-le (catégorie, vérifiabilité, mode) et liste les points incertains. Ne prétends pas qu'un "
        "critère est automatisable s'il exige un jugement humain.",
        {"critere_utilisateur": description}, schema,
    )


def prompt_assistant(contexte: dict, historique: list[dict], question: str, schema: type[BaseModel]) -> str:
    return _prompt(
        "assistant",
        "Réponds à la question de l'utilisateur en t'appuyant UNIQUEMENT sur le contexte du problème. "
        "Remplis informations_manquantes si tu ne peux pas conclure. Ne mets `solution` que si une "
        "proposition de code est demandée.",
        {**contexte, "conversation": historique, "question": question}, schema,
    )


def prompt_description_test(contexte: dict, schema: type[BaseModel]) -> str:
    return _prompt(
        "description_test",
        "Rédige la description d'un test manuel permettant de vérifier la correction : étapes, résultat attendu.",
        contexte, schema,
    )


def prompt_interpretation(contexte: dict, schema: type[BaseModel]) -> str:
    return _prompt(
        "interpretation",
        "À partir des extraits, formule des HYPOTHÈSES d'anomalies (jamais des certitudes) qui ne figurent pas "
        "déjà dans `constats_outils`. Chaque hypothèse sera examinée par un humain.",
        contexte, schema,
    )
