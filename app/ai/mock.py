"""Client simulé : réponses fixes, sans réseau. Sert au développement et aux tests."""
import json


class MockClient:
    nom_modele = "mock"

    def generer_json(self, prompt: str) -> str:
        type_ = prompt.split("\n", 1)[0].replace("# TYPE:", "").strip()
        return json.dumps(REPONSES.get(type_, {}), ensure_ascii=False)


SOLUTION = {
    "description": "Contrôler que l'utilisateur est concerné avant d'afficher la ressource.",
    "extrait_code": "- $x = $this->model->find($id);\n+ $x = $this->model->findPourUtilisateur($id, $userId);",
    "format_code": "diff",
    "risques": "Peut refuser l'accès à tort dans des cas non décrits (ex. messages de groupe).",
    "tests_suggeres": "Accès refusé à un tiers ; accès autorisé au propriétaire.",
}

REPONSES = {
    "diagnostic": {
        "diagnostic": {
            "explication": "La ressource est lue sans contrôle d'appartenance (hypothèse).",
            "causes_probables": ["Absence de contrôle dans le contrôleur", "Absence de filtre dans le modèle"],
            "niveau_confiance": 0.7,
            "incertitudes": "Je n'ai pas vu si un filtre existe ailleurs (route, middleware).",
            "verifications_recommandees": ["Vérifier que la valeur est contrôlée en amont dans le contrôleur.", "Écrire un test d'accès refusé pour un tiers."],
        },
        "solutions": [SOLUTION],
    },
    "taches": {"taches": [{
        "titre": "Ajouter le contrôle d'appartenance",
        "description": "Refuser l'accès si l'utilisateur n'est pas concerné.",
        "duree_estimee_h": 4,
        "sous_taches": [{"titre": "Écrire la méthode de contrôle"}, {"titre": "Appeler le contrôle dans le contrôleur"},
                        {"titre": "Écrire les tests"}],
        "criteres_acceptation": ["Un tiers reçoit un refus", "Le propriétaire garde l'accès"],
    }]},
    "critere": {
        "nom": "Critère proposé",
        "formulation": {"condition": "Condition (simulée)", "attendu": "Résultat attendu (simulé)", "portee": None},
        "categorie": "propre_application", "automatisabilite": "humaine", "mode_verification": "manuelle",
        "incertitudes": ["Réponse simulée : à remplacer par le vrai service."],
    },
    "assistant": {
        "contenu": "Réponse simulée à partir du contexte du problème.",
        "informations_manquantes": "Contexte limité (mode simulé).",
        "niveau_confiance": 0.5, "solution": None,
    },
    "description_test": {"description": "1. Reproduire le scénario. 2. Vérifier le résultat attendu."},
    "interpretation": {"hypotheses": []},
}
