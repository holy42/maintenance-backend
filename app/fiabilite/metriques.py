"""Métriques d'évaluation d'un modèle de probabilité, validation croisée stratifiée, intervalles par bootstrap."""
import math
import random
from collections.abc import Callable, Sequence


def auc(y: Sequence[int], p: Sequence[float]) -> float:
    """Aire sous la courbe ROC (rang moyen en cas d'égalité). NaN si une seule classe est présente."""
    n_pos = sum(y)
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    paires = sorted(zip(p, y))
    somme, i, n = 0.0, 0, len(paires)
    while i < n:
        j = i
        while j + 1 < n and paires[j + 1][0] == paires[i][0]:
            j += 1
        rang = (i + j) / 2 + 1
        somme += rang * sum(1 for k in range(i, j + 1) if paires[k][1] == 1)
        i = j + 1
    return (somme - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def brier(y: Sequence[int], p: Sequence[float]) -> float:
    return sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / len(y)


def log_loss(y: Sequence[int], p: Sequence[float], eps: float = 1e-12) -> float:
    return -sum(yi * math.log(min(max(pi, eps), 1 - eps)) + (1 - yi) * math.log(1 - min(max(pi, eps), 1 - eps))
                for pi, yi in zip(p, y)) / len(y)


def confusion(y: Sequence[int], p: Sequence[float], seuil: float = 0.5) -> tuple[int, int, int, int]:
    """(vrais positifs, faux positifs, vrais négatifs, faux négatifs)."""
    tp = fp = tn = fn = 0
    for yi, pi in zip(y, p):
        pred = pi >= seuil
        tp += pred and yi == 1
        fp += pred and yi == 0
        tn += (not pred) and yi == 0
        fn += (not pred) and yi == 1
    return tp, fp, tn, fn


def precision_rappel_f1(y: Sequence[int], p: Sequence[float], seuil: float = 0.5) -> tuple[float, float, float]:
    tp, fp, _, fn = confusion(y, p, seuil)
    precision = tp / (tp + fp) if tp + fp else float("nan")
    rappel = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * precision * rappel / (precision + rappel) if precision == precision and rappel == rappel and precision + rappel else float("nan")
    return precision, rappel, f1


def courbe_calibration(y: Sequence[int], p: Sequence[float], tranches: int = 10) -> list[dict]:
    """Pour chaque tranche de probabilité prédite : probabilité moyenne annoncée et fréquence réellement observée."""
    res = []
    for t in range(tranches):
        bas, haut = t / tranches, (t + 1) / tranches
        idx = [i for i, pi in enumerate(p) if (bas <= pi < haut) or (t == tranches - 1 and pi == 1.0)]
        if idx:
            res.append({"de": bas, "a": haut, "n": len(idx), "proba_moyenne": sum(p[i] for i in idx) / len(idx),
                        "frequence_observee": sum(y[i] for i in idx) / len(idx)})
    return res


def ece(y: Sequence[int], p: Sequence[float], tranches: int = 10) -> float:
    """Erreur de calibration attendue : écart moyen pondéré entre probabilité annoncée et fréquence observée."""
    n = len(y)
    return sum(t["n"] / n * abs(t["proba_moyenne"] - t["frequence_observee"]) for t in courbe_calibration(y, p, tranches))


def sans_nan(valeur):
    """Remplace NaN et l'infini par None (récursivement). Indispensable avant d'écrire des métriques en JSON : PostgreSQL (JSONB) et
    les réponses de l'API refusent NaN, qui apparaît par exemple pour la précision d'un modèle qui ne prédit jamais « vrai »."""
    if isinstance(valeur, float):
        return valeur if math.isfinite(valeur) else None
    if isinstance(valeur, dict):
        return {k: sans_nan(v) for k, v in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [sans_nan(v) for v in valeur]
    return valeur


def rapport(y: Sequence[int], p: Sequence[float], seuil: float = 0.5) -> dict:
    """Métriques d'un modèle de probabilité. Les valeurs non définies (NaN) sont retournées à None."""
    precision, rappel, f1 = precision_rappel_f1(y, p, seuil)
    return sans_nan({"n": len(y), "prevalence": sum(y) / len(y), "auc": auc(y, p), "brier": brier(y, p), "log_loss": log_loss(y, p),
                     "ece": ece(y, p), "seuil": seuil, "precision": precision, "rappel": rappel, "f1": f1})


def decouper_stratifie(y: Sequence[int], k: int, graine: int = 0) -> list[list[int]]:
    """k plis dont chacun garde environ la proportion de chaque classe."""
    rng = random.Random(graine)
    plis: list[list[int]] = [[] for _ in range(k)]
    for classe in (0, 1):
        idx = [i for i, yi in enumerate(y) if yi == classe]
        rng.shuffle(idx)
        for rang, i in enumerate(idx):
            plis[rang % k].append(i)
    return plis


def validation_croisee(X: Sequence[Sequence[float]], y: Sequence[int], fabrique: Callable[[], object], k: int = 5,
                       graine: int = 0, repetitions: int = 1) -> list[float]:
    """Prédictions « hors échantillon » : chaque exemple est prédit par un modèle qui ne l'a jamais vu.
    `fabrique()` retourne un modèle neuf (méthodes fit(X, y) et predict_proba(x))."""
    totaux = [0.0] * len(y)
    for r in range(repetitions):
        for pli in decouper_stratifie(y, k, graine + r):
            test = set(pli)
            apprentissage = [i for i in range(len(y)) if i not in test]
            modele = fabrique()
            modele.fit([X[i] for i in apprentissage], [y[i] for i in apprentissage])
            for i in pli:
                totaux[i] += modele.predict_proba(X[i])
    return [t / repetitions for t in totaux]


def intervalle_bootstrap(y: Sequence[int], p: Sequence[float], fonction: Callable[[Sequence[int], Sequence[float]], float],
                         n: int = 500, graine: int = 0, alpha: float = 0.05) -> tuple[float, float]:
    """Intervalle de confiance d'une métrique par rééchantillonnage : indispensable avec peu de données."""
    rng = random.Random(graine)
    m = len(y)
    valeurs = []
    for _ in range(n):
        idx = [rng.randrange(m) for _ in range(m)]
        v = fonction([y[i] for i in idx], [p[i] for i in idx])
        if v == v:
            valeurs.append(v)
    if not valeurs:
        return float("nan"), float("nan")
    valeurs.sort()
    return valeurs[int(alpha / 2 * len(valeurs))], valeurs[min(len(valeurs) - 1, int((1 - alpha / 2) * len(valeurs)))]
