"""Variables du modèle de fiabilité. Toutes sont calculables AUTOMATIQUEMENT à partir des données de la plateforme.
Étape 3 : la preuve fournie par l'outil d'analyse est-elle solide ?   Étape 6 : la solution proposée par Gemini est-elle fiable ?"""
import math
import re
from dataclasses import dataclass, field

NOMS_ETAPE3 = [
    "cat_securite", "cat_erreur_technique", "gravite", "regle_syntaxe", "regle_sql_concat", "entree_utilisateur",
    "protection_proche", "taille_extrait", "nb_meme_regle_fichier", "nb_meme_regle_verification", "dossier_tiers",
    "dossier_test", "taux_confirmation_regle",
]
NOMS_ETAPE6 = [
    "confiance_declaree", "a_incertitudes", "nb_causes", "code_present", "lignes_ajoutees", "lignes_retirees",
    "nb_fichiers_touches", "code_syntaxe_valide", "reference_valide", "fiabilite_preuve", "cat_securite", "gravite",
    "a_tests_suggeres", "a_risques", "touche_authentification", "longueur_explication",
]
NOMS = {3: NOMS_ETAPE3, 6: NOMS_ETAPE6}

_GRAVITE = {"faible": 0.0, "moyenne": 1.0, "elevee": 2.0, "critique": 3.0}
_ENTREE = re.compile(r"\$_(?:GET|POST|REQUEST|COOKIE)\b|\$this->input->(?:get|post|cookie|get_post)\s*\(|\$this->request->(?:getGet|getPost|getVar|getCookie|getJSON)\s*\(")
_PROTECTION = re.compile(r"\b(?:prepare|bind_?param|bind_?value|escape\w*|real_escape_string|intval|filter_var|htmlspecialchars|esc|addslashes)\b|\(int\)|->query\([^,]+,\s*\[")
_AUTH = re.compile(r"(?i)\b(?:auth\w*|login|logout|session|password|mot de passe|token|jwt|permission|csrf)\b")
_TIERS = {"vendor", "node_modules", "third_party", "thirdparty", "libs"}
_TESTS = {"tests", "test", "spec"}


def _log(n: float) -> float:
    return math.log1p(max(n, 0.0))


def _gravite(g: str | None) -> float:
    return _GRAVITE.get(g or "", 1.0)


def _parties(chemin: str | None) -> set[str]:
    return {p.lower() for p in re.split(r"[\\/]", chemin or "") if p}


@dataclass
class EntreeEtape3:
    """Un résultat de l'outil d'analyse + son contexte."""
    categorie: str
    gravite: str | None = None
    regle: str | None = None
    fichier: str | None = None
    extrait: str | None = None
    nb_meme_regle_fichier: int = 1
    nb_meme_regle_verification: int = 1
    taux_confirmation_regle: float = 0.5      # historique des décisions humaines, SANS l'exemple évalué


def variables_etape3(e: EntreeEtape3) -> dict[str, float]:
    texte = e.extrait or ""
    parties = _parties(e.fichier)
    return {
        "cat_securite": float(e.categorie == "securite"), "cat_erreur_technique": float(e.categorie == "erreur_technique"),
        "gravite": _gravite(e.gravite), "regle_syntaxe": float(e.regle == "php.syntaxe"),
        "regle_sql_concat": float(e.regle == "php.sql_concat"), "entree_utilisateur": float(bool(_ENTREE.search(texte))),
        "protection_proche": float(bool(_PROTECTION.search(texte))), "taille_extrait": _log(len(texte)),
        "nb_meme_regle_fichier": _log(e.nb_meme_regle_fichier), "nb_meme_regle_verification": _log(e.nb_meme_regle_verification),
        "dossier_tiers": float(bool(parties & _TIERS)), "dossier_test": float(bool(parties & _TESTS)),
        "taux_confirmation_regle": float(e.taux_confirmation_regle),
    }


@dataclass
class EntreeEtape6:
    """Une solution proposée par Gemini (dans son diagnostic) + le contexte de la preuve."""
    explication: str = ""
    causes: list[str] = field(default_factory=list)
    confiance_declaree: float | None = None
    incertitudes: str | None = None
    description: str = ""
    extrait_code: str | None = None
    risques: str | None = None
    tests_suggeres: str | None = None
    fiabilite_preuve: float | None = None      # score de l'étape 3
    categorie: str = ""
    gravite: str | None = None
    reference_valide: bool | None = None       # le fichier cité existe-t-il ? (None = non vérifiable)
    syntaxe_valide: bool | None = None         # le code proposé est-il syntaxiquement valide ? (None = non vérifiable)


def _compter_diff(code: str) -> tuple[int, int, int]:
    ajoutees = retirees = fichiers = 0
    for ligne in code.splitlines():
        if ligne.startswith("+++ ") or ligne.startswith("diff --git"):
            fichiers += 1
        elif ligne.startswith("+") and not ligne.startswith("+++"):
            ajoutees += 1
        elif ligne.startswith("-") and not ligne.startswith("---"):
            retirees += 1
    return ajoutees, retirees, max(fichiers, 1 if code.strip() else 0)


def variables_etape6(e: EntreeEtape6) -> dict[str, float]:
    code = e.extrait_code or ""
    ajoutees, retirees, fichiers = _compter_diff(code)
    return {
        "confiance_declaree": 0.5 if e.confiance_declaree is None else float(e.confiance_declaree),
        "a_incertitudes": float(bool((e.incertitudes or "").strip())), "nb_causes": float(len(e.causes)),
        "code_present": float(bool(code.strip())), "lignes_ajoutees": _log(ajoutees), "lignes_retirees": _log(retirees),
        "nb_fichiers_touches": float(fichiers), "code_syntaxe_valide": float(e.syntaxe_valide is True),
        "reference_valide": float(e.reference_valide is True),
        "fiabilite_preuve": 0.5 if e.fiabilite_preuve is None else float(e.fiabilite_preuve),
        "cat_securite": float(e.categorie == "securite"), "gravite": _gravite(e.gravite),
        "a_tests_suggeres": float(bool((e.tests_suggeres or "").strip())), "a_risques": float(bool((e.risques or "").strip())),
        "touche_authentification": float(bool(_AUTH.search(code + " " + e.description))), "longueur_explication": _log(len(e.explication)),
    }
