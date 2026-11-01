"""Adaptateur PHP fondé sur tree-sitter (analyse syntaxique).
ATTENTION : écrit pour l'API récente de py-tree-sitter (Language(tsphp.language_php()), Parser(langage)).
Les noms de nœuds de la grammaire PHP sont à valider avec votre version installée (voir tests/)."""
import re
from pathlib import Path

from app.analysis.base import AnalyseurCode, Constat

try:  # dépendances à installer (voir requirements.txt)
    import tree_sitter_php as _tsphp
    from tree_sitter import Language, Parser
    _LANGUE = Language(_tsphp.language_php())
except Exception:  # pragma: no cover - dépendance absente
    _LANGUE = None
    Parser = None  # type: ignore

_SQL = re.compile(rb"(?i)\b(select|insert|update|delete)\b")
_ENTREES = (b"$_GET", b"$_POST", b"$_REQUEST")
TAILLE_MAX = 1_000_000


def _parcourir(noeud):
    pile = [noeud]
    while pile:
        n = pile.pop()
        yield n
        pile.extend(reversed(n.children))


def _fonction_englobante(noeud, src: bytes) -> str | None:
    p = noeud.parent
    while p is not None:
        if p.type in ("method_declaration", "function_definition"):
            nom = p.child_by_field_name("name")
            return src[nom.start_byte:nom.end_byte].decode(errors="replace") if nom else None
        p = p.parent
    return None


class AnalyseurPHPTreeSitter(AnalyseurCode):
    nom = "tree-sitter"
    technologies = frozenset({"php"})
    regles = frozenset({"php.syntaxe", "php.sql_concat"})

    def analyser(self, racine: Path, dossiers: list[str], exclusions: list[str], regles_actives: set[str]) -> list[Constat]:
        if _LANGUE is None:
            raise RuntimeError("tree-sitter / tree-sitter-php ne sont pas installés.")
        parseur = Parser(_LANGUE)
        constats: list[Constat] = []
        for fichier in self._fichiers(racine, dossiers, exclusions):
            try:
                if fichier.stat().st_size > TAILLE_MAX:
                    continue
                src = fichier.read_bytes()
            except OSError:
                continue
            rel = str(fichier.relative_to(racine))
            arbre = parseur.parse(src)
            lignes = src.splitlines()
            if "php.syntaxe" in regles_actives and arbre.root_node.has_error:
                constats += self._erreurs_syntaxe(arbre.root_node, src, lignes, rel)
            if "php.sql_concat" in regles_actives:
                constats += self._sql_concatene(arbre.root_node, src, lignes, rel)
        return constats

    @staticmethod
    def _fichiers(racine: Path, dossiers: list[str], exclusions: list[str]):
        bases = [racine / d for d in dossiers] if dossiers else [racine]
        exclus = {e.strip("/") for e in exclusions}
        for base in bases:
            if not base.exists():
                continue
            for f in base.rglob("*.php"):
                parties = f.relative_to(racine).parts
                if any(p in exclus for p in parties[:-1]) or ".git" in parties:
                    continue
                yield f

    @staticmethod
    def _extrait(lignes: list[bytes], debut: int, fin: int) -> str:
        return b"\n".join(lignes[max(debut - 1, 0):fin]).decode(errors="replace")[:1500]

    def _erreurs_syntaxe(self, root, src, lignes, rel) -> list[Constat]:
        res = []
        for n in _parcourir(root):
            if n.type == "ERROR" or n.is_missing:
                ligne = n.start_point[0] + 1
                res.append(Constat(
                    regle="php.syntaxe", categorie="erreur_technique", gravite="elevee", fichier=rel,
                    ligne_debut=ligne, ligne_fin=n.end_point[0] + 1, fonction=_fonction_englobante(n, src),
                    extrait_code=self._extrait(lignes, ligne, ligne + 1), outil=self.nom,
                    message="Erreur de syntaxe PHP détectée par l'analyseur.",
                    elements_preuve="L'analyseur syntaxique n'a pas pu interpréter ce passage. "
                                    "Il peut s'agir d'une syntaxe valide mais non gérée par la grammaire utilisée.",
                ))
        return res[:50]

    def _sql_concatene(self, root, src, lignes, rel) -> list[Constat]:
        res = []
        for n in _parcourir(root):
            if n.type != "member_call_expression":
                continue
            nom = n.child_by_field_name("name")
            args = n.child_by_field_name("arguments")
            if nom is None or args is None or src[nom.start_byte:nom.end_byte] != b"query":
                continue
            texte = src[args.start_byte:args.end_byte]
            if not _SQL.search(texte):
                continue
            concat = any(
                b.type == "binary_expression"
                and (op := b.child_by_field_name("operator")) is not None and op.type == "."
                and any(v.type == "variable_name" for v in _parcourir(b))
                for b in _parcourir(args)
            )
            if not concat:
                continue
            ligne = n.start_point[0] + 1
            entree = any(e in texte for e in _ENTREES)
            res.append(Constat(
                regle="php.sql_concat", categorie="securite", gravite="critique" if entree else "elevee",
                fichier=rel, ligne_debut=ligne, ligne_fin=n.end_point[0] + 1, fonction=_fonction_englobante(n, src),
                extrait_code=self._extrait(lignes, ligne, n.end_point[0] + 1), outil=self.nom,
                message="Requête SQL construite par concaténation avec une variable.",
                elements_preuve="La règle a repéré une variable concaténée dans une requête. Elle ne peut pas "
                                "savoir si la valeur est contrôlée ailleurs : un humain doit confirmer.",
            ))
        return res[:50]
