"""Score de départ par règles pondérées FIXÉES À LA MAIN. Il n'est PAS appris : il est utilisé tant qu'aucun modèle n'est entraîné
et il sert de référence de comparaison. Les poids sont des valeurs de départ arbitraires, à remplacer par l'apprentissage."""
from app.fiabilite.modeles import ModeleFiabilite, ModeleHeuristique
from app.fiabilite.variables import NOMS

_POIDS = {
    3: ({"cat_securite": 0.2, "gravite": 0.15, "regle_syntaxe": 0.8, "entree_utilisateur": 1.2, "protection_proche": -1.5,
         "taille_extrait": -0.1, "nb_meme_regle_fichier": -0.2, "nb_meme_regle_verification": -0.1, "dossier_tiers": -1.0,
         "dossier_test": -0.8, "taux_confirmation_regle": 2.0}, -1.0),
    6: ({"confiance_declaree": 0.8, "a_incertitudes": -0.4, "code_present": 0.3, "lignes_ajoutees": -0.2, "lignes_retirees": -0.1,
         "nb_fichiers_touches": -0.3, "code_syntaxe_valide": 1.0, "reference_valide": 0.8, "fiabilite_preuve": 1.2, "cat_securite": -0.2,
         "gravite": -0.1, "a_tests_suggeres": 0.3, "touche_authentification": -0.5, "longueur_explication": 0.05}, -0.9),
}


def modele_heuristique(etape: int) -> ModeleFiabilite:
    poids, biais = _POIDS[etape]
    noms = NOMS[etape]
    return ModeleFiabilite(etape, noms, ModeleHeuristique([poids.get(n, 0.0) for n in noms], biais), appris=False)
