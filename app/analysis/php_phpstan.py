"""Second analyseur PHP : PHPStan, un outil d'analyse statique qui suit les types et les valeurs dans le programme.
Il détecte ce qu'un simple arbre syntaxique ne voit pas : variable non définie, appel d'une fonction ou méthode inexistante,
types incohérents, division par zéro, code mort. PHPStan est lancé en LECTURE SEULE sur la copie clonée (jamais sur le dépôt distant),
avec un fichier de configuration temporaire créé hors du dépôt. Son rapport JSON est converti en `Constat`.
Les erreurs de syntaxe (identifiant « phpstan.parse ») sont ignorées : la règle php.syntaxe s'en charge."""
import json
import re
import subprocess
import tempfile
from fnmatch import fnmatchcase
from pathlib import Path

from app.analysis.base import AnalyseurCode, Constat
from app.config import settings
from app.core.exceptions import ErreurMetier

REGLES_PHPSTAN = frozenset({
    "php.variable_non_definie", "php.appel_inexistant", "php.type_incoherent", "php.division_par_zero", "php.code_mort",
})

# identifiant PHPStan (motifs fnmatch) -> (règle, gravité). Pour couvrir un nouveau cas, ajouter une ligne ici.
CORRESPONDANCE = [
    ("variable.undefined", "php.variable_non_definie", "elevee"),
    ("function.notFound", "php.appel_inexistant", "elevee"),
    ("method.notFound", "php.appel_inexistant", "elevee"),
    ("staticMethod.notFound", "php.appel_inexistant", "elevee"),
    ("class.notFound", "php.appel_inexistant", "elevee"),          # ignoré par défaut (voir `classes_inconnues`)
    ("return.type", "php.type_incoherent", "moyenne"),
    ("argument.type", "php.type_incoherent", "moyenne"),
    ("arguments.count", "php.type_incoherent", "moyenne"),
    ("binaryOp.invalid", "php.type_incoherent", "moyenne"),
    ("deadCode.*", "php.code_mort", "faible"),
    ("*.alwaysTrue", "php.code_mort", "faible"),
    ("*.alwaysFalse", "php.code_mort", "faible"),
    ("*.alreadyNarrowedType", "php.code_mort", "faible"),
]
LIBELLES = {
    "php.variable_non_definie": "Variable non définie",
    "php.appel_inexistant": "Appel d'une fonction, méthode ou classe inexistante",
    "php.type_incoherent": "Types incohérents",
    "php.division_par_zero": "Division par zéro",
    "php.code_mort": "Code mort ou condition toujours identique",
}
_DIVISION_ZERO = re.compile(r'"[/%]" between .+ and 0 results')
MAX_PAR_FICHIER_ET_REGLE = 50
TAILLE_MAX = 1_000_000


def regle_pour(identifiant: str | None, message: str, classes_inconnues: bool = False):
    """(règle, gravité) pour une erreur PHPStan, ou None si elle ne nous intéresse pas."""
    if not identifiant or identifiant == "phpstan.parse":
        return None
    if identifiant == "binaryOp.invalid" and _DIVISION_ZERO.search(message):
        return "php.division_par_zero", "elevee"
    if identifiant == "class.notFound" and not classes_inconnues:
        return None          # sans « vendor », toute classe de bibliothèque serait « inconnue » : trop de bruit
    for motif, regle, gravite in CORRESPONDANCE:
        if fnmatchcase(identifiant, motif):
            return regle, gravite
    return None


def convertir(rapport: dict, racine: Path, regles_actives: set[str], niveau: int, classes_inconnues: bool = False) -> list[Constat]:
    """Rapport JSON de PHPStan -> constats. Fonction pure (hors lecture des fichiers pour l'extrait)."""
    base = racine.resolve()
    constats: list[Constat] = []
    for chemin, contenu in (rapport.get("files") or {}).items():
        try:
            rel = Path(chemin).resolve().relative_to(base).as_posix()
        except (ValueError, OSError):
            rel = Path(chemin).as_posix()
        lignes: list[bytes] | None = None
        compte: dict[str, int] = {}
        for m in contenu.get("messages", []):
            choix = regle_pour(m.get("identifier"), m.get("message", ""), classes_inconnues)
            if choix is None or choix[0] not in regles_actives:
                continue
            regle, gravite = choix
            if compte.get(regle, 0) >= MAX_PAR_FICHIER_ET_REGLE:
                continue
            compte[regle] = compte.get(regle, 0) + 1
            ligne = int(m.get("line") or 1)
            if lignes is None:
                try:
                    f = base / rel
                    lignes = f.read_bytes().splitlines() if f.stat().st_size <= TAILLE_MAX else []
                except OSError:
                    lignes = []
            extrait = b"\n".join(lignes[max(ligne - 2, 0):ligne + 1]).decode(errors="replace")[:1500] if lignes else None
            constats.append(Constat(
                regle=regle, categorie="erreur_technique", gravite=gravite, fichier=rel, ligne_debut=ligne, ligne_fin=ligne,
                extrait_code=extrait, outil="phpstan",
                message=f"{LIBELLES[regle]} : {m.get('message', '')}",
                elements_preuve=f"PHPStan (niveau {niveau}) déduit les types à partir du code. Il peut se tromper si une bibliothèque, "
                                f"un fichier inclus ou une annotation lui manque : un humain doit confirmer.",
                donnees_brutes={"identifiant": m.get("identifier"), "message_phpstan": m.get("message"), "astuce": m.get("tip")},
            ))
    return constats


def _neon(cibles: list[Path], exclus: list[Path], niveau: int, cache: Path) -> str:
    q = lambda p: "'" + p.resolve().as_posix().replace("'", "''") + "'"            # noqa: E731  (chaîne NEON)
    texte = f"parameters:\n    level: {niveau}\n    tmpDir: {q(cache)}\n    paths:\n" + "".join(f"        - {q(p)}\n" for p in cibles)
    if exclus:
        texte += "    excludePaths:\n        analyse:\n" + "".join(f"            - {q(p)} (?)\n" for p in exclus)
    return texte


def _lancer(racine: Path, cibles: list[Path], exclus: list[Path], niveau: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="phpstan_") as tmp:
        tmp = Path(tmp)
        (tmp / "phpstan.neon").write_text(_neon(cibles, exclus, niveau, tmp / "cache"), encoding="utf-8")
        cmd = [*settings.phpstan_commande, "analyse", f"--configuration={tmp / 'phpstan.neon'}", "--error-format=json",
               "--no-progress", "--no-interaction", "--memory-limit=1G"]
        try:
            r = subprocess.run(cmd, cwd=racine, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=settings.phpstan_timeout_secondes)
        except FileNotFoundError as exc:
            raise ErreurMetier("PHPStan est introuvable sur le serveur : vérifier PHPSTAN_COMMANDE dans le fichier .env.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ErreurMetier("PHPStan a dépassé le délai autorisé (PHPSTAN_TIMEOUT_SECONDES).") from exc
    try:
        rapport = json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        raise ErreurMetier(f"Sortie de PHPStan illisible (code {r.returncode}) : {(r.stderr or r.stdout)[:200].strip()}") from exc
    if rapport.get("errors"):
        raise ErreurMetier(f"PHPStan signale une erreur de configuration : {str(rapport['errors'][0])[:200]}")
    return rapport


def _fichiers_illisibles(rapport: dict) -> list[Path]:
    return [Path(f) for f, c in (rapport.get("files") or {}).items()
            if any(m.get("identifier") == "phpstan.parse" for m in c.get("messages", []))]


class AnalyseurPHPStan(AnalyseurCode):
    nom = "phpstan"
    technologies = frozenset({"php"})
    regles = REGLES_PHPSTAN

    def analyser(self, racine: Path, dossiers: list[str], exclusions: list[str], regles_actives: set[str]) -> list[Constat]:
        niveau = settings.phpstan_niveau
        cibles = [racine / d for d in dossiers if (racine / d).exists()] if dossiers else [racine]
        if not cibles:
            return []                                    # aucun des dossiers demandés n'existe : rien à analyser
        exclus = [racine / e.strip("/") for e in exclusions if e.strip("/")]
        rapport = _lancer(racine, cibles, exclus, niveau)
        illisibles = _fichiers_illisibles(rapport)
        if illisibles:
            # Avec une erreur de syntaxe, PHPStan n'analyse plus rien d'autre : on exclut ces fichiers et on relance UNE fois
            # (les erreurs de syntaxe elles-mêmes sont déjà signalées par la règle php.syntaxe).
            rapport = _lancer(racine, cibles, exclus + illisibles, niveau)
        return convertir(rapport, racine, regles_actives, niveau, getattr(settings, "phpstan_signaler_classes_inconnues", False))