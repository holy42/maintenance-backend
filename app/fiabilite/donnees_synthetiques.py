"""Données FICTIVES pour tester la chaîne d'entraînement et d'évaluation.
AUCUN résultat obtenu sur ces données ne doit figurer dans le mémoire : elles servent seulement à vérifier que le code fonctionne.
Les vraies données viennent de l'application de test (problèmes injectés) et des décisions humaines de la plateforme."""
import math
import random

from app.fiabilite.variables import NOMS


def generer(etape: int, n: int = 200, graine: int = 0) -> tuple[list[list[float]], list[int]]:
    rng = random.Random(graine)
    noms = NOMS[etape]
    X, y = [], []
    for _ in range(n):
        v: dict[str, float] = {}
        for nom in noms:
            if nom.startswith(("cat_", "regle_", "dossier_", "a_", "code_", "reference_", "touche_", "entree_", "protection_")):
                v[nom] = float(rng.random() < 0.4)
            elif nom == "gravite":
                v[nom] = float(rng.randint(0, 3))
            elif nom in ("taux_confirmation_regle", "confiance_declaree", "fiabilite_preuve"):
                v[nom] = rng.random()
            else:
                v[nom] = abs(rng.gauss(1.5, 1.0))
        if etape == 3:
            logit = -0.5 + 1.8 * v["entree_utilisateur"] - 1.6 * v["protection_proche"] + 1.5 * (v["taux_confirmation_regle"] - 0.5) - 1.0 * v["dossier_tiers"]
        else:
            logit = -1.0 + 1.5 * v["fiabilite_preuve"] + 1.2 * v["code_syntaxe_valide"] + 0.8 * v["reference_valide"] - 0.4 * v["nb_fichiers_touches"] * 0.3
        p = 1 / (1 + math.exp(-(logit + rng.gauss(0, 0.5))))
        X.append([v[nom] for nom in noms])
        y.append(int(rng.random() < p))
    return X, y
