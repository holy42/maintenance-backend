"""Modèles de fiabilité écrits ici, sans bibliothèque externe : régression logistique (IRLS, régularisée), arbre de décision
(CART), forêt aléatoire, calibration de Platt, et le conteneur ModeleFiabilite (variables, calibration, explication)."""
import math
import random
from collections.abc import Sequence


def _sigmoide(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _logit(p: float, eps: float = 1e-6) -> float:
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def _resoudre(A: list[list[float]], b: list[float]) -> list[float]:
    """Résout A x = b (élimination de Gauss, pivot partiel)."""
    n = len(b)
    M = [A[i][:] + [b[i]] for i in range(n)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            raise ValueError("Matrice singulière.")
        M[c], M[piv] = M[piv], M[c]
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            if f:
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


def poids_equilibres(y: Sequence[int]) -> list[float]:
    """Même poids total pour les deux classes (utile quand les cas vrais et faux sont déséquilibrés)."""
    n, pos = len(y), sum(y)
    neg = n - pos
    if pos == 0 or neg == 0:
        return [1.0] * n
    return [n / (2 * pos) if yi else n / (2 * neg) for yi in y]


class RegressionLogistique:
    """Modèle de base, interprétable : un coefficient par variable. Entraînement par IRLS (Newton), régularisation L2."""
    type = "logistique"

    def __init__(self, l2: float = 1.0, equilibrer: bool = True, iterations: int = 50, tol: float = 1e-8):
        self.l2, self.equilibrer, self.iterations, self.tol = l2, equilibrer, iterations, tol
        self.moy: list[float] = []
        self.ecart: list[float] = []
        self.theta: list[float] = []          # theta[0] = biais, puis un coefficient par variable standardisée

    def _z(self, x: Sequence[float]) -> list[float]:
        return [(x[j] - self.moy[j]) / self.ecart[j] for j in range(len(self.moy))]

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> "RegressionLogistique":
        n, d = len(X), len(X[0])
        self.moy = [sum(x[j] for x in X) / n for j in range(d)]
        self.ecart = [math.sqrt(sum((x[j] - self.moy[j]) ** 2 for x in X) / n) or 1.0 for j in range(d)]
        Z = [[1.0] + self._z(x) for x in X]
        sw = poids_equilibres(y) if self.equilibrer else [1.0] * n
        theta = [0.0] * (d + 1)

        def perte(t: list[float]) -> float:
            s = 0.0
            for z, yi, w in zip(Z, y, sw):
                p = min(max(_sigmoide(sum(a * b for a, b in zip(t, z))), 1e-12), 1 - 1e-12)
                s -= w * (yi * math.log(p) + (1 - yi) * math.log(1 - p))
            return s + 0.5 * self.l2 * sum(v * v for v in t[1:])

        courante = perte(theta)
        for _ in range(self.iterations):
            g = [0.0] * (d + 1)
            H = [[0.0] * (d + 1) for _ in range(d + 1)]
            for z, yi, w in zip(Z, y, sw):
                p = _sigmoide(sum(a * b for a, b in zip(theta, z)))
                r, h = w * (p - yi), w * p * (1 - p)
                for a in range(d + 1):
                    g[a] += r * z[a]
                    for b in range(a, d + 1):
                        H[a][b] += h * z[a] * z[b]
            for a in range(d + 1):
                for b in range(a):
                    H[a][b] = H[b][a]
            for j in range(1, d + 1):
                g[j] += self.l2 * theta[j]
                H[j][j] += self.l2
            H[0][0] += 1e-9
            delta = _resoudre(H, g)
            pas, accepte = 1.0, False
            while pas > 1e-4:
                cand = [t - pas * dl for t, dl in zip(theta, delta)]
                nouvelle = perte(cand)
                if nouvelle <= courante + 1e-12:
                    theta, accepte = cand, True
                    break
                pas /= 2
            if not accepte or max(abs(pas * dl) for dl in delta) < self.tol:
                break
            courante = nouvelle
        self.theta = theta
        return self

    def predict_proba(self, x: Sequence[float]) -> float:
        z = self._z(x)
        return _sigmoide(self.theta[0] + sum(self.theta[j + 1] * z[j] for j in range(len(z))))

    def coefficients(self) -> list[float]:
        """Coefficients sur variables standardisées (comparables entre eux)."""
        return self.theta[1:]

    def to_dict(self) -> dict:
        return {"type": self.type, "l2": self.l2, "equilibrer": self.equilibrer, "moy": self.moy, "ecart": self.ecart, "theta": self.theta}

    @classmethod
    def from_dict(cls, d: dict) -> "RegressionLogistique":
        m = cls(l2=d["l2"], equilibrer=d["equilibrer"])
        m.moy, m.ecart, m.theta = d["moy"], d["ecart"], d["theta"]
        return m


class ArbreDecision:
    """Arbre CART (impureté de Gini). Les feuilles donnent une probabilité lissée (Laplace)."""
    type = "arbre"

    def __init__(self, profondeur_max: int = 4, min_feuille: int = 5, max_variables: int | None = None, graine: int = 0):
        self.profondeur_max, self.min_feuille, self.max_variables, self.graine = profondeur_max, min_feuille, max_variables, graine
        self.racine: dict = {"p": 0.5, "n": 0}

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int], poids: Sequence[float] | None = None,
            indices: Sequence[int] | None = None, rng: random.Random | None = None) -> "ArbreDecision":
        w = list(poids) if poids is not None else [1.0] * len(y)
        self.racine = self._construire(X, y, w, list(indices) if indices is not None else list(range(len(y))), 0, rng or random.Random(self.graine))
        return self

    def _construire(self, X, y, w, idx, prof, rng) -> dict:
        tot = sum(w[i] for i in idx)
        pos = sum(w[i] for i in idx if y[i] == 1)
        feuille = {"p": (pos + 0.5) / (tot + 1.0), "n": len(idx)}
        if prof >= self.profondeur_max or len(idx) < 2 * self.min_feuille or pos <= 0 or pos >= tot:
            return feuille
        d = len(X[0])
        cand = list(range(d))
        if self.max_variables and self.max_variables < d:
            rng.shuffle(cand)
            cand = cand[: self.max_variables]
        gini_parent = 2 * (pos / tot) * (1 - pos / tot)
        meilleur = None
        for j in cand:
            ordre = sorted(idx, key=lambda i: X[i][j])
            g_tot = g_pos = 0.0
            for rang in range(len(ordre) - 1):
                i = ordre[rang]
                g_tot += w[i]
                g_pos += w[i] if y[i] == 1 else 0.0
                suivant = ordre[rang + 1]
                if X[i][j] == X[suivant][j]:
                    continue
                if rang + 1 < self.min_feuille or len(ordre) - rang - 1 < self.min_feuille:
                    continue
                d_tot, d_pos = tot - g_tot, pos - g_pos
                if g_tot <= 0 or d_tot <= 0:
                    continue
                impurete = (g_tot * 2 * (g_pos / g_tot) * (1 - g_pos / g_tot) + d_tot * 2 * (d_pos / d_tot) * (1 - d_pos / d_tot)) / tot
                gain = gini_parent - impurete
                if meilleur is None or gain > meilleur[0] + 1e-12:
                    meilleur = (gain, j, (X[i][j] + X[suivant][j]) / 2)
        if meilleur is None or meilleur[0] <= 1e-9:
            return feuille
        _, j, seuil = meilleur
        gauche = [i for i in idx if X[i][j] <= seuil]
        droite = [i for i in idx if X[i][j] > seuil]
        return {"var": j, "seuil": seuil, "g": self._construire(X, y, w, gauche, prof + 1, rng),
                "d": self._construire(X, y, w, droite, prof + 1, rng)}

    def predict_proba(self, x: Sequence[float]) -> float:
        n = self.racine
        while "var" in n:
            n = n["g"] if x[n["var"]] <= n["seuil"] else n["d"]
        return n["p"]

    def to_dict(self) -> dict:
        return {"type": self.type, "profondeur_max": self.profondeur_max, "min_feuille": self.min_feuille, "racine": self.racine}

    @classmethod
    def from_dict(cls, d: dict) -> "ArbreDecision":
        a = cls(profondeur_max=d["profondeur_max"], min_feuille=d["min_feuille"])
        a.racine = d["racine"]
        return a


class ForetAleatoire:
    """Moyenne de nombreux arbres entraînés sur des échantillons tirés avec remise, avec un sous-ensemble de variables par séparation."""
    type = "foret"

    def __init__(self, n_arbres: int = 100, profondeur_max: int = 4, min_feuille: int = 5, equilibrer: bool = True, graine: int = 0):
        self.n_arbres, self.profondeur_max, self.min_feuille, self.equilibrer, self.graine = n_arbres, profondeur_max, min_feuille, equilibrer, graine
        self.arbres: list[ArbreDecision] = []

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> "ForetAleatoire":
        rng = random.Random(self.graine)
        n, d = len(X), len(X[0])
        w = poids_equilibres(y) if self.equilibrer else [1.0] * n
        mv = max(1, round(math.sqrt(d)))
        self.arbres = []
        for _ in range(self.n_arbres):
            echantillon = [rng.randrange(n) for _ in range(n)]
            self.arbres.append(ArbreDecision(self.profondeur_max, self.min_feuille, mv).fit(X, y, w, echantillon, rng))
        return self

    def predict_proba(self, x: Sequence[float]) -> float:
        return sum(a.predict_proba(x) for a in self.arbres) / len(self.arbres)

    def to_dict(self) -> dict:
        return {"type": self.type, "arbres": [a.to_dict() for a in self.arbres]}

    @classmethod
    def from_dict(cls, d: dict) -> "ForetAleatoire":
        f = cls(n_arbres=len(d["arbres"]))
        f.arbres = [ArbreDecision.from_dict(a) for a in d["arbres"]]
        return f


class ModeleConstant:
    """Référence de comparaison : prédit toujours la fréquence des cas vrais observée à l'entraînement."""
    type = "constant"

    def __init__(self) -> None:
        self.p = 0.5

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> "ModeleConstant":
        self.p = (sum(y) + 0.5) / (len(y) + 1.0)
        return self

    def predict_proba(self, x: Sequence[float]) -> float:
        return self.p

    def to_dict(self) -> dict:
        return {"type": self.type, "p": self.p}

    @classmethod
    def from_dict(cls, d: dict) -> "ModeleConstant":
        m = cls()
        m.p = d["p"]
        return m


class ModeleHeuristique:
    """Score par règles pondérées FIXÉES À LA MAIN (NON APPRIS). Sert de point de départ tant qu'aucun modèle n'est entraîné."""
    type = "heuristique"

    def __init__(self, poids: list[float] | None = None, biais: float = 0.0):
        self.poids, self.biais = poids or [], biais

    def fit(self, X, y):  # pas d'apprentissage
        return self

    def predict_proba(self, x: Sequence[float]) -> float:
        return _sigmoide(self.biais + sum(w * v for w, v in zip(self.poids, x)))

    def to_dict(self) -> dict:
        return {"type": self.type, "poids": self.poids, "biais": self.biais}

    @classmethod
    def from_dict(cls, d: dict) -> "ModeleHeuristique":
        return cls(d["poids"], d["biais"])


class CalibrateurPlatt:
    """Recale les probabilités pour qu'un score de 70 % corresponde à environ 70 % de cas vrais (régression logistique à 1 variable)."""

    def __init__(self) -> None:
        self.reg = RegressionLogistique(l2=1e-3, equilibrer=False)

    def fit(self, scores: Sequence[float], y: Sequence[int]) -> "CalibrateurPlatt":
        self.reg.fit([[_logit(s)] for s in scores], y)
        return self

    def appliquer(self, p: float) -> float:
        return self.reg.predict_proba([_logit(p)])

    def to_dict(self) -> dict:
        return self.reg.to_dict()

    @classmethod
    def from_dict(cls, d: dict) -> "CalibrateurPlatt":
        c = cls()
        c.reg = RegressionLogistique.from_dict(d)
        return c


_TYPES = {c.type: c for c in (RegressionLogistique, ArbreDecision, ForetAleatoire, ModeleConstant, ModeleHeuristique)}


class ModeleFiabilite:
    """Un modèle de fiabilité pour UNE étape (3 : preuves de l'analyse ; 6 : solutions de Gemini) : même code, entraîné séparément."""

    def __init__(self, etape: int, noms: list[str], coeur, calibrateur: CalibrateurPlatt | None = None,
                 moyennes: list[float] | None = None, seuils: tuple[float, float] = (0.40, 0.70),
                 metriques: dict | None = None, appris: bool = True):
        self.etape, self.noms, self.coeur, self.calibrateur = etape, noms, coeur, calibrateur
        self.moyennes = moyennes or [0.0] * len(noms)
        self.seuils, self.metriques, self.appris = seuils, metriques or {}, appris

    @property
    def algorithme(self) -> str:
        return self.coeur.type

    def _x(self, variables: dict[str, float]) -> list[float]:
        return [float(variables.get(n, self.moyennes[i])) for i, n in enumerate(self.noms)]

    def _proba(self, x: list[float]) -> float:
        p = self.coeur.predict_proba(x)
        return self.calibrateur.appliquer(p) if self.calibrateur else p

    def predire(self, variables: dict[str, float]) -> float:
        return self._proba(self._x(variables))

    def expliquer(self, variables: dict[str, float], top: int = 4) -> list[dict]:
        """Contribution de chaque variable : écart de score quand elle est remplacée par sa valeur moyenne d'entraînement."""
        x = self._x(variables)
        base = self._proba(x)
        res = []
        for j, nom in enumerate(self.noms):
            y = list(x)
            y[j] = self.moyennes[j]
            delta = base - self._proba(y)
            if abs(delta) > 1e-6:
                res.append({"variable": nom, "valeur": x[j], "effet": round(delta, 4), "sens": "augmente" if delta > 0 else "diminue"})
        return sorted(res, key=lambda r: abs(r["effet"]), reverse=True)[:top]

    def to_dict(self) -> dict:
        return {"etape": self.etape, "noms": self.noms, "coeur": self.coeur.to_dict(), "moyennes": self.moyennes,
                "calibrateur": self.calibrateur.to_dict() if self.calibrateur else None, "seuils": list(self.seuils),
                "metriques": self.metriques, "appris": self.appris}

    @classmethod
    def from_dict(cls, d: dict) -> "ModeleFiabilite":
        coeur = _TYPES[d["coeur"]["type"]].from_dict(d["coeur"])
        cal = CalibrateurPlatt.from_dict(d["calibrateur"]) if d.get("calibrateur") else None
        return cls(d["etape"], d["noms"], coeur, cal, d["moyennes"], tuple(d["seuils"]), d.get("metriques"), d.get("appris", True))
