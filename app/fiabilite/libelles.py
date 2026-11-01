"""Libellés lisibles des variables du modèle : pour l'interface, et pour le contexte envoyé à Gemini
(qui ne doit pas recevoir des noms techniques comme « protection_proche »)."""

LIBELLES: dict[str, str] = {
    # étape 3 : preuves de l'analyse
    "cat_securite": "anomalie de catégorie sécurité",
    "cat_erreur_technique": "anomalie de catégorie erreur technique",
    "gravite": "gravité de l'anomalie",
    "regle_syntaxe": "règle de syntaxe PHP",
    "regle_sql_concat": "règle de requête SQL concaténée",
    "entree_utilisateur": "donnée venant de l'utilisateur présente dans l'extrait",
    "protection_proche": "protection (requête préparée, échappement, conversion) visible dans l'extrait",
    "taille_extrait": "taille de l'extrait de code",
    "nb_meme_regle_fichier": "nombre de constats de la même règle dans ce fichier",
    "nb_meme_regle_verification": "nombre de constats de la même règle dans cette vérification",
    "dossier_tiers": "fichier situé dans un dossier de code tiers",
    "dossier_test": "fichier situé dans un dossier de tests",
    "taux_confirmation_regle": "taux de confirmation historique de cette règle",
    # étape 6 : solutions de Gemini
    "confiance_declaree": "confiance déclarée par Gemini",
    "a_incertitudes": "incertitudes exprimées par Gemini",
    "nb_causes": "nombre de causes proposées",
    "code_present": "code proposé",
    "lignes_ajoutees": "nombre de lignes ajoutées par le correctif",
    "lignes_retirees": "nombre de lignes retirées par le correctif",
    "nb_fichiers_touches": "nombre de fichiers touchés par le correctif",
    "code_syntaxe_valide": "syntaxe du code proposé valide",
    "reference_valide": "fichiers cités par la solution existant dans le dépôt",
    "fiabilite_preuve": "fiabilité de la preuve de départ",
    "a_tests_suggeres": "tests suggérés avec la solution",
    "a_risques": "risques indiqués avec la solution",
    "touche_authentification": "correctif touchant l'authentification ou la session",
    "longueur_explication": "longueur de l'explication",
}


def libelle(variable: str) -> str:
    return LIBELLES.get(variable, variable.replace("_", " "))
