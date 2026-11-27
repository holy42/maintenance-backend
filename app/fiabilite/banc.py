"""Banc de test automatique de l'étape 6 : produit des étiquettes (solution validée ou non) sur les applications de TEST.

Pour chaque problème confirmé issu de l'analyse (règle tree-sitter connue) :
  1. l'IA génère un diagnostic par le MÊME code que la plateforme (`generer_diagnostic`) : les variables de l'étape 6 sont donc
     calculées et enregistrées exactement comme en production ;
  2. chaque solution est appliquée TELLE QUELLE à une copie du fichier, au commit analysé (le dépôt n'est jamais modifié) ;
  3. l'oracle automatique la juge validée si : le correctif s'applique, `php -l` accepte chaque fichier modifié, l'anomalie visée
     a disparu à la nouvelle analyse (une occurrence de moins de la règle dans le fichier) et aucune erreur de syntaxe n'est apparue.

L'oracle remplace le testeur : c'est une approximation, à décrire comme telle dans le mémoire. Il ne vérifie pas que le
comportement de l'application est préservé (un correctif qui supprime la requête ferait disparaître l'anomalie).
Les solutions au format « extrait » (code d'illustration, pas un correctif) ne s'appliquent pas automatiquement : elles sont
écartées de l'étiquetage par défaut, pour ne pas apprendre au modèle un artefact du banc.

  python -m app.fiabilite.cli banc --utilisateur aina --max 20 --sortie var/banc_etape6.csv            # essai, sans étiqueter la base
  python -m app.fiabilite.cli banc --utilisateur aina --max 250 --sortie var/banc_etape6.csv --etiqueter
"""
import csv
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.php_regles_securite import REGLES_SECURITE
from app.analysis.php_treesitter import AnalyseurPHPTreeSitter
from app.config import settings
from app.fiabilite.variables import NOMS
from app.models import (
    Critere, Diagnostic, EvaluationFiabilite, Probleme, ResultatAnalyse, Solution, Utilisateur, Verification,
)
from app.services import git_service

# Règles que l'oracle sait re-vérifier. php.secret_en_dur est exclue : le secret est masqué dans le contexte envoyé à l'IA,
# son correctif ne peut donc pas s'appliquer tel quel. Les règles PHPStan sont exclues (une analyse PHPStan par solution est trop lente).
# php.fonction_dangereuse et php.include_dynamique sont exclues aussi : elles signalent la PRÉSENCE de l'appel (unserialize, include avec
# variable) même quand l'entrée est contrôlée ; un vrai correctif (liste blanche, allowed_classes) ne fait donc pas disparaître l'alerte
# et l'oracle le jugerait non validé à tort (constaté sur le premier lancement).
REGLES_BANC = frozenset({"php.sql_concat", "php.syntaxe"}) | (
    REGLES_SECURITE - {"php.secret_en_dur", "php.fonction_dangereuse", "php.include_dynamique"})
_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")


# ---------------------------------------------------------------- application d'un diff

@dataclass
class Bloc:
    fichier: str | None          # None : pas d'en-tête, on suppose le fichier du problème
    ligne: int | None            # ligne de départ annoncée par l'en-tête @@ (indice de proximité seulement)
    avant: list[str]
    apres: list[str]


def _nom(entete: str) -> str | None:
    n = entete.split(maxsplit=1)[1].split("\t")[0].strip() if len(entete.split(maxsplit=1)) > 1 else ""
    if n == "/dev/null" or not n:
        return None
    return n[2:] if n.startswith(("a/", "b/")) else n


def lire_diff(code: str) -> list[Bloc]:
    """Découpe un diff unifié (éventuellement sans en-têtes) en blocs « avant / après »."""
    blocs: list[Bloc] = []
    fichier: str | None = None
    courant: Bloc | None = None
    lignes = code.splitlines()
    for i, l in enumerate(lignes):
        if l.startswith("diff --git") or l.startswith("index "):
            continue
        if l.startswith("--- ") and i + 1 < len(lignes) and lignes[i + 1].startswith("+++ "):
            continue
        if l.startswith("+++ "):
            fichier, courant = _nom(l), None
            continue
        m = _HUNK.match(l)
        if m:
            courant = Bloc(fichier, int(m.group(1)), [], [])
            blocs.append(courant)
            continue
        if l.startswith("\\"):                 # « \ No newline at end of file »
            continue
        if courant is None:
            courant = Bloc(fichier, None, [], [])
            blocs.append(courant)
        if l.startswith("-"):
            courant.avant.append(l[1:])
        elif l.startswith("+"):
            courant.apres.append(l[1:])
        else:
            texte = l[1:] if l.startswith(" ") else l
            courant.avant.append(texte)
            courant.apres.append(texte)
    return [b for b in blocs if b.avant or b.apres]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def appliquer_bloc(lignes: list[str], bloc: Bloc) -> list[str] | None:
    """Remplace le passage « avant » par « après ». Comparaison sans tenir compte des espaces ; si le passage apparaît plusieurs
    fois, on prend le plus proche de la ligne annoncée. None si le passage est introuvable (le correctif ne s'applique pas)."""
    avant = [_norm(x) for x in bloc.avant]
    while avant and not avant[0]:                        # lignes vides en bordure : non significatives
        avant, bloc = avant[1:], Bloc(bloc.fichier, bloc.ligne, bloc.avant[1:], bloc.apres)
    if not avant:                                        # pur ajout sans contexte (@@ -N,0 ...) : inséré après la ligne N annoncée
        if bloc.ligne is None or not 0 <= bloc.ligne <= len(lignes):
            return None
        return lignes[:bloc.ligne] + bloc.apres + lignes[bloc.ligne:]
    norm = [_norm(x) for x in lignes]
    n = len(avant)
    positions = [i for i in range(len(norm) - n + 1) if norm[i:i + n] == avant]
    if not positions:
        return None
    cible = (bloc.ligne or 1) - 1
    i = min(positions, key=lambda p: abs(p - cible))
    return lignes[:i] + bloc.apres + lignes[i + n:]


def appliquer_diff(code: str, lire_fichier, fichier_defaut: str) -> tuple[dict[str, str] | None, str]:
    """Applique le diff. `lire_fichier(chemin)` retourne le contenu au commit analysé (None si absent).
    Retourne ({chemin: nouveau contenu}, motif) ou (None, motif d'échec)."""
    blocs = lire_diff(code)
    if not blocs:
        return None, "diff vide ou illisible"
    contenus: dict[str, list[str]] = {}
    for b in blocs:
        chemin = chemin_git(b.fichier or fichier_defaut)
        if chemin not in contenus:
            original = lire_fichier(chemin)
            if original is None:
                if any(_norm(x) for x in b.avant):
                    return None, f"fichier cité introuvable : {chemin}"
                contenus[chemin] = []                    # création de fichier
            else:
                contenus[chemin] = original.splitlines()
        if not contenus[chemin] and not any(_norm(x) for x in b.avant):
            contenus[chemin] = b.apres[:]
            continue
        nouveau = appliquer_bloc(contenus[chemin], b)
        if nouveau is None:
            return None, f"le passage à remplacer est introuvable dans {chemin}"
        contenus[chemin] = nouveau
    return {c: "\n".join(l) + "\n" for c, l in contenus.items()}, "appliqué"


# ---------------------------------------------------------------- oracle

def _php() -> str:
    return settings.phpstan_commande[0] if settings.phpstan_commande and settings.phpstan_commande[0].lower().endswith(("php", "php.exe")) else "php"


def php_lint(contenu: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".php", delete=False, encoding="utf-8") as f:
        f.write(contenu)
    try:
        r = subprocess.run([_php(), "-l", f.name], capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    finally:
        os.unlink(f.name)


def compter_regles(contenu: str, nom_fichier: str, regles: set[str]) -> dict[str, int]:
    """Nombre de constats de chaque règle dans ce fichier seul (même analyseur que la plateforme)."""
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / nom_fichier
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
        constats = AnalyseurPHPTreeSitter().analyser(Path(d), [], [], regles)
    return {r: sum(1 for c in constats if c.regle == r) for r in regles}


def juger(code: str | None, format_code: str, lire_fichier, fichier: str, regle: str) -> tuple[int | None, str]:
    """(1 validée / 0 non validée / None non jugeable, motif)."""
    if not code or not code.strip():
        return None, "pas de code proposé"
    est_diff = format_code == "diff" or any(l.startswith(("+++ ", "@@", "diff --git")) for l in code.splitlines())
    if not est_diff:
        return None, "extrait d'illustration, non applicable automatiquement"
    nouveaux, motif = appliquer_diff(code, lire_fichier, fichier)
    if nouveaux is None:
        return 0, f"ne s'applique pas : {motif}"
    nouveaux = {chemin_git(c): v for c, v in nouveaux.items()}
    for chemin, contenu in nouveaux.items():
        if chemin.endswith(".php") and not php_lint(contenu):
            return 0, f"php -l refuse {chemin}"
    if fichier not in nouveaux:
        return 0, "le correctif ne modifie pas le fichier du problème"
    regles = {regle, "php.syntaxe"}
    avant = compter_regles(lire_fichier(fichier) or "", fichier, regles)
    apres = compter_regles(nouveaux[fichier], fichier, regles)
    if apres[regle] >= avant[regle]:
        return 0, f"l'anomalie est toujours détectée ({regle} : {avant[regle]} -> {apres[regle]})"
    if regle != "php.syntaxe" and apres["php.syntaxe"] > avant["php.syntaxe"]:
        return 0, "le correctif introduit une erreur de syntaxe"
    return 1, f"anomalie disparue ({regle} : {avant[regle]} -> {apres[regle]}), php -l OK"


# ---------------------------------------------------------------- orchestration

def chemin_git(chemin: str) -> str:
    """Chemin relatif au dépôt, avec « / » (d'anciennes analyses sous Windows ont enregistré des barres obliques inverses)."""
    chemin = chemin.replace("\\", "/")
    while chemin.startswith(("./", "/")):
        chemin = chemin[1:] if chemin.startswith("/") else chemin[2:]
    return chemin


def _lecteur(depot: Path, commit: str):
    cache: dict[str, str | None] = {}

    def lire(chemin: str) -> str | None:
        chemin = chemin_git(chemin)
        if chemin not in cache:
            r = subprocess.run(["git", "-C", str(depot), "show", f"{commit}:{chemin}"], capture_output=True, timeout=30)
            cache[chemin] = r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None
        return cache[chemin]
    return lire


def problemes_eligibles(db: Session, applications: list[int] | None) -> list[tuple[Probleme, str, str, Path]]:
    """(problème, règle, commit, dépôt) : confirmé, issu de l'analyse, règle re-vérifiable, fichier lisible au commit analysé,
    et jamais diagnostiqué (pour ne pas payer deux fois l'IA)."""
    deja = select(Diagnostic.probleme_id)
    q = (select(Probleme, Critere.formulation_structuree["regle"].astext, Verification.commit_analyse)
         .join(ResultatAnalyse, ResultatAnalyse.id == Probleme.resultat_id).join(Critere, Critere.id == ResultatAnalyse.critere_id)
         .join(Verification, Verification.id == Probleme.verification_id)
         .where(Probleme.statut == "confirme", Probleme.fichier.is_not(None), Verification.commit_analyse.is_not(None),
                Probleme.id.not_in(deja)).order_by(Probleme.id))
    if applications:
        q = q.where(Probleme.application_id.in_(applications))
    res = []
    for p, regle, commit in db.execute(q).all():
        if regle not in REGLES_BANC:
            continue
        depot = git_service.dossier_depot(p.application_id)
        if depot.is_dir() and _lecteur(depot, commit)(p.fichier) is not None:
            res.append((p, regle, commit, depot))
    return res


def repartir(eligibles: list, maximum: int) -> list:
    """Tour de rôle entre (application, règle) : un échantillon varié plutôt que 250 fois la même règle du même projet."""
    groupes: dict[tuple, list] = {}
    for e in eligibles:
        groupes.setdefault((e[0].application_id, e[1]), []).append(e)
    choisis, files = [], list(groupes.values())
    while files and len(choisis) < maximum:
        for f in list(files):
            if f:
                choisis.append(f.pop(0))
            if not f:
                files.remove(f)
            if len(choisis) >= maximum:
                break
    return choisis


# Tarifs en dollars par million de tokens (entrée, sortie), pour afficher le coût du lancement. À mettre à jour si les tarifs changent.
TARIFS = {"claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0), "claude-haiku-5-5": (0.10, 0.50)}


def cout(ia) -> dict | None:
    """Tokens consommés et coût estimé depuis le début du lancement (None si le client ne mesure pas sa consommation)."""
    c = getattr(getattr(ia, "client", None), "consommation", None)
    if c is None:
        return None
    t_e, t_s = TARIFS.get(ia.modele, (None, None))
    res = dict(c)
    if t_e is not None:
        res["cout_dollars"] = round(c["entree"] / 1e6 * t_e + c["sortie"] / 1e6 * t_s, 4)
        res["cout_par_appel"] = round(res["cout_dollars"] / c["appels"], 4) if c["appels"] else None
    return res


COLONNES_INFO = ["probleme_id", "application_id", "regle", "solution_id", "evaluation_id", "format_code", "score_avant", "motif"]


def executer(db: Session, identifiant: str, maximum: int, sortie: str, etiqueter: bool, applications: list[int] | None,
             ia=None, journal=print) -> dict:
    from app.ai.service import ServiceIA
    from app.services.diagnostics import generer_diagnostic

    user = db.execute(select(Utilisateur).where(Utilisateur.identifiant == identifiant)).scalar_one_or_none()
    if user is None:
        raise ValueError(f"Utilisateur inconnu : {identifiant}")
    ia = ia or ServiceIA()
    eligibles = problemes_eligibles(db, applications)
    lot = repartir(eligibles, maximum)
    journal(f"{len(eligibles)} problème(s) éligible(s) ; {len(lot)} traité(s) dans ce lancement (IA : {ia.modele}).")
    noms = NOMS[6]
    nouveau = not os.path.exists(sortie)
    os.makedirs(os.path.dirname(sortie) or ".", exist_ok=True)
    bilan = {"problemes": 0, "erreurs_ia": 0, "validees": 0, "non_validees": 0, "non_jugees": 0}
    with open(sortie, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nouveau:
            w.writerow([*COLONNES_INFO, *noms, "etiquette"])
        for n, (p, regle, commit, depot) in enumerate(lot, 1):
            try:
                d = generer_diagnostic(db, p, user, ia)
                db.commit()                              # chaque diagnostic est conservé, même si la suite échoue
            except Exception as exc:                     # IA indisponible, réponse non conforme... : on passe au suivant
                db.rollback()
                bilan["erreurs_ia"] += 1
                journal(f"[{n}/{len(lot)}] problème {p.id} : diagnostic impossible ({type(exc).__name__}: {exc})")
                continue
            bilan["problemes"] += 1
            lire = _lecteur(depot, commit)
            for s in d.solutions:
                etiquette, motif = juger(s.extrait_code, s.format_code, lire, chemin_git(p.fichier), regle)
                ev = db.execute(select(EvaluationFiabilite).where(EvaluationFiabilite.cible_type == "solution",
                                                                  EvaluationFiabilite.cible_id == s.id)).scalars().first()
                cle = {1: "validees", 0: "non_validees", None: "non_jugees"}[etiquette]
                bilan[cle] += 1
                if etiquette is not None and etiqueter and ev is not None:
                    ev.etiquette = bool(etiquette)
                    from app.fiabilite.service import _maintenant
                    ev.etiquette_le = _maintenant()
                variables = ev.variables if ev else {}
                w.writerow([p.id, p.application_id, regle, s.id, ev.id if ev else "", s.format_code, float(ev.score) if ev else "", motif,
                            *[variables.get(x, "") for x in noms], "" if etiquette is None else etiquette])
            db.commit()
            f.flush()
            c = cout(ia)
            journal(f"[{n}/{len(lot)}] problème {p.id} ({regle}) : "
                    + ", ".join(f"sol {s.id}" for s in d.solutions) + f" — bilan {bilan['validees']} validées / {bilan['non_validees']} non validées"
                    + (f" — coût cumulé {c['cout_dollars']} $" if c and "cout_dollars" in c else ""))
    bilan["consommation"] = cout(ia)
    return bilan


def importer_csv(db: Session, chemin: str) -> int:
    """Écrit dans la base les étiquettes d'un CSV du banc (lancement fait sans --etiqueter). N'écrase jamais une étiquette existante."""
    from app.fiabilite.service import _maintenant
    n = 0
    with open(chemin, newline="", encoding="utf-8") as f:
        for ligne in csv.DictReader(f):
            if ligne.get("etiquette") in ("0", "1") and ligne.get("evaluation_id"):
                ev = db.get(EvaluationFiabilite, int(ligne["evaluation_id"]))
                if ev is not None and ev.etiquette is None:
                    ev.etiquette, ev.etiquette_le = ligne["etiquette"] == "1", _maintenant()
                    n += 1
    db.commit()
    return n
