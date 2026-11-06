"""Comparaison des modèles, entraînement final, évaluation sur un jeu de test, lecture et écriture de jeux de données CSV."""
import csv
import random
from collections.abc import Callable, Sequence

from app.fiabilite import metriques as m
from app.fiabilite.modeles import CalibrateurPlatt, ForetAleatoire, ModeleConstant, ModeleFiabilite, RegressionLogistique
from app.fiabilite.niveaux import SEUILS_PAR_DEFAUT

CANDIDATS: dict[str, Callable[[], object]] = {
    "logistique": lambda: RegressionLogistique(l2=1.0),
    "foret": lambda: ForetAleatoire(n_arbres=100, profondeur_max=4, min_feuille=5),
    "constant": lambda: ModeleConstant(),          # référence : ne tient compte d'aucune variable
}
MIN_EXEMPLES = 150          # avec une quinzaine de variables, moins d'exemples donne des estimations trop instables
MIN_PAR_CLASSE = 30
GAIN_MIN_FORET = 0.01      # la forêt n'est préférée que si elle améliore nettement le score de Brier (modèle plus simple privilégié)
DEGRADATION_MAX_ECE = 0.02  # ... sans dégrader la calibration de plus de 0,02 par rapport à la régression logistique


def _resume(y: Sequence[int], p: Sequence[float], graine: int) -> dict:
    r = m.rapport(y, p)
    r["auc_ic95"] = m.sans_nan(list(m.intervalle_bootstrap(y, p, m.auc, graine=graine)))
    return r


def comparer(X: Sequence[Sequence[float]], y: Sequence[int], k: int = 5, repetitions: int = 3, graine: int = 0,
             confiance_declaree: Sequence[float] | None = None, avec_sklearn: bool = False) -> dict:
    """Validation croisée répétée de chaque modèle. Les prédictions sont « hors échantillon ». Avec peu de données, lire les intervalles
    de confiance : de petits écarts entre modèles ne sont pas significatifs."""
    if len(y) < MIN_EXEMPLES or sum(y) < MIN_PAR_CLASSE or len(y) - sum(y) < MIN_PAR_CLASSE:
        raise ValueError(f"Jeu de données insuffisant : au moins {MIN_EXEMPLES} exemples étiquetés et {MIN_PAR_CLASSE} de chaque classe "
                         f"(reçu : {len(y)} exemples, {sum(y)} vrais, {len(y) - sum(y)} faux).")
    res: dict = {"n": len(y), "prevalence": sum(y) / len(y), "k": k, "repetitions": repetitions, "modeles": {}}
    for nom, fabrique in CANDIDATS.items():
        oof = m.validation_croisee(X, y, fabrique, k=k, graine=graine, repetitions=repetitions)
        res["modeles"][nom] = _resume(y, oof, graine)
    if confiance_declaree is not None:     # étape 6 : la confiance déclarée par Gemini est-elle déjà informative ?
        res["modeles"]["confiance_declaree_par_gemini"] = _resume(y, list(confiance_declaree), graine)
    if avec_sklearn:
        res["modeles"].update(_reference_sklearn(X, y, k, graine))
    res["recommande"] = choisir(res)
    return res


def _valide(x) -> bool:
    return isinstance(x, (int, float)) and x == x


def choisir(resultat: dict) -> str:
    """Règle explicite, par ordre : (1) jamais pire que la référence constante ; (2) la régression logistique (modèle simple, explicable)
    est conservée, SAUF si la forêt remplit les TROIS conditions : Brier meilleur d'au moins GAIN_MIN_FORET, AUC au-dessus de la borne haute
    de l'intervalle de confiance à 95 % de la logistique (amélioration hors du bruit statistique), et calibration (ECE) dégradée de
    DEGRADATION_MAX_ECE au plus. Une valeur manquante ou non calculable fait préférer la logistique."""
    mod = resultat["modeles"]
    lo, fo = mod["logistique"], mod["foret"]
    if lo["brier"] >= mod["constant"]["brier"]:
        return "constant"
    ic = lo.get("auc_ic95")
    if not (_valide(fo.get("brier")) and _valide(fo.get("auc")) and _valide(fo.get("ece")) and _valide(lo.get("ece"))
            and ic and _valide(ic[1])):
        return "logistique"
    if (fo["brier"] <= lo["brier"] - GAIN_MIN_FORET and fo["auc"] > ic[1] and fo["ece"] <= lo["ece"] + DEGRADATION_MAX_ECE):
        return "foret"
    return "logistique"


def _reference_sklearn(X, y, k, graine) -> dict:
    """Contrôle externe facultatif : compare nos modèles à ceux de scikit-learn (si installé)."""
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import StratifiedKFold, cross_val_predict
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return {}
    Xn, yn = np.array(X), np.array(y)
    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=graine)
    sorties = {
        "sklearn_logistique": make_pipeline(StandardScaler(), LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000)),
        "sklearn_foret": RandomForestClassifier(n_estimators=100, max_depth=4, min_samples_leaf=5, class_weight="balanced", random_state=graine),
    }
    return {nom: _resume(y, list(cross_val_predict(est, Xn, yn, cv=cv, method="predict_proba")[:, 1]), graine) for nom, est in sorties.items()}


def entrainer_final(etape: int, noms: list[str], X: Sequence[Sequence[float]], y: Sequence[int], algorithme: str = "logistique",
                    k: int = 5, repetitions: int = 3, graine: int = 0, seuils: tuple[float, float] = SEUILS_PAR_DEFAUT) -> ModeleFiabilite:
    """Entraîne le modèle choisi sur TOUTES les données fournies ; la calibration est apprise sur les prédictions hors échantillon."""
    fabrique = CANDIDATS[algorithme]
    oof = m.validation_croisee(X, y, fabrique, k=k, graine=graine, repetitions=repetitions)
    calibrateur = CalibrateurPlatt().fit(oof, y)
    coeur = fabrique().fit(X, y)
    n = len(X)
    moyennes = [sum(x[j] for x in X) / n for j in range(len(noms))]
    avant = m.rapport(y, oof)
    apres = m.rapport(y, [calibrateur.appliquer(p) for p in oof])
    return ModeleFiabilite(etape, noms, coeur, calibrateur, moyennes, seuils,
                           {"validation_croisee_avant_calibration": avant, "validation_croisee_apres_calibration": apres, "n": n,
                            "remarque_calibration": "calibreur ajusté sur ces mêmes prédictions hors échantillon : « après » est légèrement "
                                                    "optimiste ; l'évaluation finale doit se faire sur un jeu de test mis de côté"},
                           appris=True)


def separer_test(X, y, part: float = 0.3, graine: int = 0) -> tuple[list, list, list, list]:
    """Jeu de test mis de côté, utilisé UNE seule fois pour l'évaluation finale (jamais pour choisir le modèle)."""
    rng = random.Random(graine)
    test: set[int] = set()
    for classe in (0, 1):
        idx = [i for i, yi in enumerate(y) if yi == classe]
        rng.shuffle(idx)
        test.update(idx[: max(1, round(len(idx) * part))])
    app = [i for i in range(len(y)) if i not in test]
    tst = sorted(test)
    return [X[i] for i in app], [y[i] for i in app], [X[i] for i in tst], [y[i] for i in tst]


def evaluer_sur_test(modele: ModeleFiabilite, noms: list[str], X, y, graine: int = 0) -> dict:
    p = [modele.predire(dict(zip(noms, x))) for x in X]
    return _resume(y, p, graine)


def retirer_lignes(Xt, yt, Xa, ya) -> tuple[list, list]:
    """Différence de multi-ensembles : retire de (Xt, yt) UNE occurrence de chaque ligne de (Xa, ya). Sert quand l'export de la plateforme
    contient à la fois le jeu d'apprentissage et le jeu indépendant."""
    a_retirer: dict = {}
    for x, yi in zip(Xa, ya):
        cle = (tuple(x), yi)
        a_retirer[cle] = a_retirer.get(cle, 0) + 1
    X, y = [], []
    for x, yi in zip(Xt, yt):
        cle = (tuple(x), yi)
        if a_retirer.get(cle, 0) > 0:
            a_retirer[cle] -= 1
            continue
        X.append(x)
        y.append(yi)
    if sum(a_retirer.values()):
        raise ValueError(f"{sum(a_retirer.values())} ligne(s) d'apprentissage introuvables dans le CSV de test : "
                         "le CSV de test doit être un export complet fait APRÈS celui d'apprentissage.")
    return X, y


def evaluer_independant(etape: int, noms: list[str], Xa, ya, Xt, yt, graine: int = 0) -> dict:
    """Entraîne la logistique et la forêt sur (Xa, ya) PUIS les évalue une seule fois sur le jeu indépendant (Xt, yt), à côté des deux
    références : règles fixées à la main (non apprises) et prédiction constante (prévalence de l'apprentissage)."""
    from app.fiabilite.heuristique import modele_heuristique
    if len(yt) < 30 or sum(yt) < 10 or len(yt) - sum(yt) < 10:
        raise ValueError(f"Jeu indépendant trop petit pour conclure (reçu : {len(yt)} exemples, {sum(yt)} vrais, {len(yt) - sum(yt)} faux).")
    res: dict = {"apprentissage": {"n": len(ya), "vrais": sum(ya), "faux": len(ya) - sum(ya)},
                 "test": {"n": len(yt), "vrais": sum(yt), "faux": len(yt) - sum(yt)}, "modeles": {}}
    for algo in ("logistique", "foret"):
        modele = entrainer_final(etape, noms, Xa, ya, algo, graine=graine)
        res["modeles"][algo] = evaluer_sur_test(modele, noms, Xt, yt, graine)
    res["modeles"]["regles_fixees_a_la_main"] = evaluer_sur_test(modele_heuristique(etape), noms, Xt, yt, graine)
    prevalence = sum(ya) / len(ya)
    res["modeles"]["constant"] = _resume(yt, [prevalence] * len(yt), graine)
    res["modeles"] = m.sans_nan(res["modeles"])
    return res


def ecrire_csv(chemin: str, noms: list[str], lignes: Sequence[tuple[Sequence[float], int]]) -> None:
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([*noms, "etiquette"])
        for x, y in lignes:
            w.writerow([*x, y])


def lire_csv(chemin: str, noms: list[str]) -> tuple[list[list[float]], list[int]]:
    X, y = [], []
    with open(chemin, newline="", encoding="utf-8") as f:
        for ligne in csv.DictReader(f):
            X.append([float(ligne[n]) for n in noms])
            y.append(int(float(ligne["etiquette"])))
    return X, y
