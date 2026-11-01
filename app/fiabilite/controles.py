"""Contrôles automatiques d'une solution de Gemini (variables `reference_valide` et `code_syntaxe_valide` de l'étape 6).

Chaque contrôle retourne True / False, ou None quand il n'est pas vérifiable (aucun fichier cité, dépôt absent, tree-sitter
non installé, code non PHP). Dans le modèle, None compte comme « non confirmé » (0), comme False.
Les chemins cités par l'IA sont une entrée non fiable : ils ne peuvent jamais sortir de la racine du dépôt."""
import re
from pathlib import Path

_DIFF_GIT = re.compile(r"^diff --git a/(\S+) b/\S+", re.M)


def fichiers_cites(code: str | None) -> list[str]:
    """Fichiers EXISTANTS que le diff dit modifier : en-têtes `diff --git a/x b/x` et `--- a/x` (suivi de `+++`).
    `/dev/null` (création de fichier) est ignoré."""
    if not code:
        return []
    avant = [m.group(1) for m in _DIFF_GIT.finditer(code)]
    # une ligne « --- x » n'est un en-tête que si elle est suivie de « +++ » (sinon c'est une ligne retirée, ex. un commentaire SQL)
    avant += [m.group(1) for m in re.finditer(r"^---\s+(?:a/)?(\S+)[^\n]*\n\+\+\+\s", code, re.M)]
    vus: list[str] = []
    for n in avant:
        if n != "/dev/null" and n not in vus:
            vus.append(n)
    return vus


def reference_valide(code: str | None, racine: Path | None) -> bool | None:
    """Tous les fichiers cités existent-ils dans le dépôt ? None si aucun fichier n'est cité ou si le dépôt est absent."""
    cites = fichiers_cites(code)
    if not cites or racine is None or not racine.is_dir():
        return None
    base = racine.resolve()
    for nom in cites:
        chemin = (base / nom).resolve()
        if base not in chemin.parents or not chemin.is_file():     # absent, ou tentative de sortie de la racine
            return False
    return True


def _version_apres(code: str) -> str:
    """Reconstitue le code « après » d'un diff : lignes ajoutées et lignes de contexte (le reste est ignoré)."""
    gardees = []
    for ligne in code.splitlines():
        if ligne.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if ligne.startswith("+") or ligne.startswith(" "):
            gardees.append(ligne[1:])
    return "\n".join(gardees)


def _ressemble_a_php(texte: str) -> bool:
    return "<?php" in texte or "$" in texte or "->" in texte or "::" in texte


def syntaxe_php_valide(code: str | None, format_code: str | None = None) -> bool | None:
    """Le code proposé est-il syntaxiquement valide en PHP ? Les extraits partiels sont acceptés tels quels, ou enveloppés dans une
    classe (corps de méthode). None si tree-sitter est absent, si le code est vide ou s'il ne ressemble pas à du PHP.
    Limite : un extrait coupé au milieu d'un bloc peut être jugé invalide à tort."""
    if not code or not code.strip():
        return None
    from app.analysis import php_treesitter as pt
    if getattr(pt, "_LANGUE", None) is None or getattr(pt, "Parser", None) is None:
        return None
    est_diff = format_code == "diff" or any(l.startswith(("+++", "@@", "diff ")) for l in code.splitlines())
    texte = _version_apres(code) if est_diff else code
    if not texte.strip() or not _ressemble_a_php(texte):
        return None
    parseur = pt.Parser(pt._LANGUE)
    base = texte if "<?php" in texte else "<?php\n" + texte
    candidats = [base, "<?php class _C {\n" + texte.replace("<?php", "") + "\n}"]
    for src in candidats:
        if not parseur.parse(src.encode("utf-8")).root_node.has_error:
            return True
    return False
