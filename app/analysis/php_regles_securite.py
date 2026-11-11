"""Règles de sécurité PHP : XSS, secret en dur, fonction dangereuse, inclusion dynamique, hachage faible, upload non contrôlé.
Chaque règle repère un MOTIF ; elle ne peut pas savoir si la valeur est contrôlée ailleurs : un humain confirme ou écarte.
Deux couches : des fonctions `evaluer_*` PURES (texte -> décision, testables sans tree-sitter) et un parcours de l'arbre."""
import re

from app.analysis.base import Constat

REGLES_SECURITE = frozenset({
    "php.xss", "php.secret_en_dur", "php.fonction_dangereuse", "php.include_dynamique", "php.hash_faible",
    "php.upload_non_controle",
})
MAX_PAR_REGLE = 50

_ENTREES = re.compile(rb"\$_(?:GET|POST|REQUEST|COOKIE)\b")
_VARIABLE = re.compile(rb"\$[A-Za-z_]\w*")
_PROTECTION_XSS = re.compile(
    rb"(?i)\b(?:htmlspecialchars|htmlentities|strip_tags|esc_html|intval|floatval|number_format|urlencode|rawurlencode|json_encode)\s*\("
    rb"|\(\s*(?:int|float)\s*\)")
_CLE_SENSIBLE = re.compile(rb"(?i)(?<![a-z])(?:password|passwd|pwd|pass|secret|api_?key|token|auth_?key)(?![a-z])")
_DEFINE = re.compile(rb"""(?is)^define\s*\(\s*['"](?P<cle>[^'"]+)['"]\s*,\s*(?P<q>['"])(?P<val>[^'"\n$]{4,})(?P=q)""")
_AFFECTATION = re.compile(rb"""(?s)^(?P<cle>[^=,(]*?)\s*(?:=>|\.?=)\s*(?P<q>['"])(?P<val>[^'"\n$]{4,})(?P=q)""")
_FAUSSE_VALEUR = re.compile(rb"(?i)^(?:x+|\*+|\.+|changeme|change_me|your[_ -].*|<.*>|password|secret|token|null|none|todo)$")
_DANGEREUSES = {"eval", "assert", "exec", "shell_exec", "system", "passthru", "popen", "proc_open", "unserialize", "create_function"}
_MOT_DE_PASSE = re.compile(rb"(?i)pass|pwd|mdp|mot_?de_?passe")
_CONTROLE_UPLOAD = re.compile(rb"(?i)getimagesize|mime_content_type|finfo_|pathinfo|\bin_array\s*\(|\['type'\]|\[\"type\"\]|\bextension\b|image/")


def evaluer_xss(texte: bytes):
    """texte = instruction `echo ...;` ou `print ...;`. Retourne (gravité, message) ou None."""
    if not _VARIABLE.search(texte) or _PROTECTION_XSS.search(texte):
        return None
    if _ENTREES.search(texte):
        return "critique", "Valeur de la requête affichée sans échappement (risque de XSS)."
    return "moyenne", "Variable affichée sans échappement (risque de XSS si elle contient une saisie utilisateur)."


def evaluer_secret(texte: bytes):
    """texte = affectation, élément de tableau ou `define(...)`. Retourne la valeur littérale suspecte ou None."""
    t = texte.strip()
    m = _DEFINE.match(t) or _AFFECTATION.match(t)
    if not m or not _CLE_SENSIBLE.search(m.group("cle")):
        return None
    valeur = m.group("val")
    return None if _FAUSSE_VALEUR.match(valeur.strip()) else valeur


def evaluer_fonction_dangereuse(nom: str, args: bytes):
    if nom not in _DANGEREUSES:
        return None
    if _ENTREES.search(args):
        return "critique", f"Appel à {nom}() avec une valeur de la requête."
    if _VARIABLE.search(args):
        return "elevee", f"Appel à {nom}() avec une variable."
    return "moyenne", f"Appel à la fonction sensible {nom}()."


def evaluer_include(texte: bytes):
    if not _VARIABLE.search(texte):
        return None
    if _ENTREES.search(texte):
        return "critique", "Inclusion d'un fichier dont le nom vient de la requête (inclusion arbitraire)."
    return "moyenne", "Inclusion d'un fichier dont le nom est dans une variable."


def evaluer_hash(nom: str, args: bytes):
    if nom in ("md5", "sha1") and _MOT_DE_PASSE.search(args):
        return "elevee", f"Mot de passe haché avec {nom}() : algorithme inadapté (utiliser password_hash)."
    return None


def evaluer_upload(nom: str, contexte: bytes):
    if nom == "move_uploaded_file" and not _CONTROLE_UPLOAD.search(contexte):
        return "elevee", "Fichier envoyé déplacé sans contrôle visible du type ou de l'extension."
    return None


# ---------------------------------------------------------------- parcours de l'arbre
def _parcourir(noeud):
    pile = [noeud]
    while pile:
        n = pile.pop()
        yield n
        pile.extend(reversed(n.children))


def _englobante(noeud):
    p = noeud.parent
    while p is not None:
        if p.type in ("method_declaration", "function_definition"):
            return p
        p = p.parent
    return None


def _nom(n, src: bytes) -> str | None:
    if n is None:
        return None
    return src[n.start_byte:n.end_byte].decode(errors="replace")


def detecter_securite(root, src: bytes, lignes: list[bytes], rel: str, actives: set[str], outil: str, extrait) -> list[Constat]:
    """`extrait(lignes, debut, fin)` est la fonction de l'analyseur qui découpe l'extrait de code."""
    res: dict[str, list[Constat]] = {r: [] for r in actives}

    def ajouter(regle, gravite, message, preuve, n, masque=None):
        if len(res[regle]) >= MAX_PAR_REGLE:
            return
        ligne, fin = n.start_point[0] + 1, n.end_point[0] + 1
        texte = extrait(lignes, ligne, fin)
        if masque:
            texte = texte.replace(masque, "[MASQUE]")
        englobante = _englobante(n)
        res[regle].append(Constat(
            regle=regle, categorie="securite", gravite=gravite, fichier=rel, ligne_debut=ligne, ligne_fin=fin,
            fonction=_nom(englobante.child_by_field_name("name"), src) if englobante is not None else None,
            extrait_code=texte, outil=outil, message=message, elements_preuve=preuve))

    for n in _parcourir(root):
        t = n.type
        if t in ("echo_statement", "print_intrinsic") and "php.xss" in actives:
            r = evaluer_xss(src[n.start_byte:n.end_byte])
            if r:
                ajouter("php.xss", r[0], r[1], "La règle a repéré l'affichage d'une variable sans échappement visible. Elle ne peut "
                        "pas savoir si la valeur est déjà nettoyée ailleurs : un humain doit confirmer.", n)
        elif t in ("assignment_expression", "array_element_initializer", "const_element", "function_call_expression") \
                and "php.secret_en_dur" in actives:
            v = evaluer_secret(src[n.start_byte:n.end_byte])
            if v is not None:
                ajouter("php.secret_en_dur", "elevee", "Secret (mot de passe, clé ou jeton) écrit en clair dans le code.",
                        "Un nom de type mot de passe reçoit une valeur littérale. La valeur est masquée dans l'extrait. "
                        "Elle peut être un exemple ou un mot de passe de test : un humain doit confirmer.", n, v.decode(errors="replace"))
        if t == "function_call_expression":
            nom = (_nom(n.child_by_field_name("function"), src) or "").lstrip("\\").lower()
            args = src[n.child_by_field_name("arguments").start_byte:n.child_by_field_name("arguments").end_byte] \
                if n.child_by_field_name("arguments") is not None else b""
            if "php.fonction_dangereuse" in actives and (r := evaluer_fonction_dangereuse(nom, args)):
                ajouter("php.fonction_dangereuse", r[0], r[1], "La règle repère l'appel d'une fonction à risque. "
                        "Elle ne peut pas savoir si l'argument est maîtrisé : un humain doit confirmer.", n)
            if "php.hash_faible" in actives and (r := evaluer_hash(nom, args)):
                ajouter("php.hash_faible", r[0], r[1], "Le nom de la donnée évoque un mot de passe. "
                        "Un humain doit confirmer qu'il s'agit bien d'un mot de passe.", n)
            if "php.upload_non_controle" in actives and nom == "move_uploaded_file":
                e = _englobante(n)
                contexte = src[e.start_byte:e.end_byte] if e is not None else src
                if (r := evaluer_upload(nom, contexte)):
                    ajouter("php.upload_non_controle", r[0], r[1], "Aucun contrôle du type ou de l'extension n'a été repéré dans la "
                            "fonction. Il peut exister ailleurs (autre fichier) : un humain doit confirmer.", n)
        elif t in ("include_expression", "include_once_expression", "require_expression", "require_once_expression") \
                and "php.include_dynamique" in actives:
            r = evaluer_include(src[n.start_byte:n.end_byte])
            if r:
                ajouter("php.include_dynamique", r[0], r[1], "Le chemin du fichier inclus contient une variable. "
                        "La règle ne sait pas si elle est contrôlée : un humain doit confirmer.", n)
    return [c for liste in res.values() for c in liste]