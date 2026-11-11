"""Règles de sécurité PHP. Partie 1 : décisions pures (sans tree-sitter). Partie 2 : analyseur complet (tree-sitter requis).
Les exemples dangereux sont assemblés à partir de morceaux : écrits en entier, ils ressemblent à du code malveillant
et certains antivirus (Windows Defender) bloquent le fichier à tort."""
import pytest

from app.analysis.php_regles_securite import (
    evaluer_fonction_dangereuse as danger, evaluer_hash, evaluer_include, evaluer_secret, evaluer_upload, evaluer_xss,
)

b = str.encode
GET = "$_" + "GET"                       # la requête de l'utilisateur
EVAL = "ev" + "al"                       # fonction d'exécution de code
UNSER = "un" + "serialize"
MOVE = "move_" + "uploaded_file"


def test_xss():
    assert evaluer_xss(b(f"echo {GET}['q'];"))[0] == "critique"
    assert evaluer_xss(b("echo $titre;"))[0] == "moyenne"
    assert evaluer_xss(b(f"echo htmlspecialchars({GET}['q']);")) is None
    assert evaluer_xss(b(f"echo (int){GET}['id'];")) is None
    assert evaluer_xss(b("echo 'bonjour';")) is None


def test_secret():
    assert evaluer_secret(b("$password = 'abc12345'")) == b"abc12345"
    assert evaluer_secret(b("'password' => 'abc12345'")) == b"abc12345"
    assert evaluer_secret(b("define('DB_PASS', 'abc12345')")) == b"abc12345"
    for faux in ("$password = ''", f"$password = {GET}['p']", "$password = 'changeme'", "$compass = 'abcdefgh'",
                 "$nom = 'abcdefgh'", "$token = \"abc$id\""):
        assert evaluer_secret(b(faux)) is None


def test_fonctions_dangereuses_include_hash_upload():
    assert danger(EVAL, b(f"({GET}['c'])"))[0] == "critique"
    assert danger(UNSER, b("($data)"))[0] == "elevee"
    assert danger("strlen", b("($x)")) is None
    assert evaluer_include(b(f"require {GET}['page'] . '.php';"))[0] == "critique"
    assert evaluer_include(b("require_once __DIR__ . '/a.php';")) is None
    assert evaluer_hash("md5", b("($password)"))[0] == "elevee"
    assert evaluer_hash("md5", b("($fichier)")) is None
    assert evaluer_upload(MOVE, b(f"{MOVE}($t, $d);"))[0] == "elevee"
    assert evaluer_upload(MOVE, b(f"$e = pathinfo($n); {MOVE}($t,$d);")) is None


# ---- Partie 2 : nécessite tree-sitter-php. Si ces tests échouent, les noms de nœuds de TA version de la grammaire diffèrent.
@pytest.fixture
def analyser(tmp_path):
    pytest.importorskip("tree_sitter_php")                       # ignoré (skip) seulement pour ces tests-là
    from app.analysis.php_treesitter import AnalyseurPHPTreeSitter

    def _analyser(code, regle):
        (tmp_path / "a.php").write_text(code, encoding="utf-8")
        return AnalyseurPHPTreeSitter().analyser(tmp_path, [], [], {regle})
    return _analyser


def test_analyseur_xss(analyser):
    r = analyser(f"<?php\necho {GET}['q'];\necho htmlspecialchars({GET}['q']);\n", "php.xss")
    assert [c.ligne_debut for c in r] == [2]


def test_analyseur_secret_masque(analyser):
    r = analyser("<?php\n$password = 'abc12345';\n$nom = 'abcdefgh';\n", "php.secret_en_dur")
    assert [c.ligne_debut for c in r] == [2] and "abc12345" not in r[0].extrait_code


def test_analyseur_fonction_dangereuse(analyser):
    r = analyser(f"<?php\n{EVAL}({GET}['c']);\nstrlen($x);\n", "php.fonction_dangereuse")
    assert [(c.ligne_debut, c.gravite) for c in r] == [(2, "critique")]


def test_analyseur_include_dynamique(analyser):
    r = analyser(f"<?php\nrequire {GET}['p'] . '.php';\nrequire_once __DIR__ . '/a.php';\n", "php.include_dynamique")
    assert [c.ligne_debut for c in r] == [2]


def test_analyseur_hash_faible(analyser): 
    r = analyser("<?php\n$h = md5($password);\n$k = md5($fichier);\n", "php.hash_faible")
    assert [c.ligne_debut for c in r] == [2]


def test_analyseur_upload(analyser):
    code = f"<?php\nfunction a() {{\n  {MOVE}($t, $d);\n}}\nfunction b() {{\n  $e = pathinfo($n);\n  {MOVE}($t, $d);\n}}\n"
    r = analyser(code, "php.upload_non_controle")
    assert [c.ligne_debut for c in r] == [3]