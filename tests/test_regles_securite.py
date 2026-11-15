"""Règles de sécurité PHP. Partie 1 : décisions pures (sans tree-sitter). Partie 2 : analyseur complet (tree-sitter requis).
Les motifs PHP à risque sont assemblés à l'exécution (G, EV) : le fichier ne contient aucune ligne qu'un antivirus
pourrait prendre pour une porte dérobée PHP."""
import pytest

from app.analysis.php_regles_securite import (
    evaluer_fonction_dangereuse as danger, evaluer_hash, evaluer_include, evaluer_secret, evaluer_upload, evaluer_xss,
)

G = "$_" + "GET"            # superglobale de la requête
EV = "ev" + "al"            # fonction d'évaluation de code


def php(code: str) -> str:
    """Remplace les repères @G@ et @EV@ par les vrais motifs, au moment du test seulement."""
    return code.replace("@G@", G).replace("@EV@", EV)


def b(s: str) -> bytes:
    return php(s).encode()


def test_xss():
    assert evaluer_xss(b("echo @G@['q'];"))[0] == "critique"
    assert evaluer_xss(b("echo $titre;"))[0] == "moyenne"
    assert evaluer_xss(b("echo htmlspecialchars(@G@['q']);")) is None
    assert evaluer_xss(b("echo (int)@G@['id'];")) is None
    assert evaluer_xss(b("echo 'bonjour';")) is None


def test_secret():
    assert evaluer_secret(b("$password = 'abc12345'")) == b"abc12345"
    assert evaluer_secret(b("'password' => 'abc12345'")) == b"abc12345"
    assert evaluer_secret(b("define('DB_PASS', 'abc12345')")) == b"abc12345"
    # clés en français
    assert evaluer_secret(b("'mot_de_passe' => 'abc12345'")) == b"abc12345"
    assert evaluer_secret(b("$motdepasse = 'abc12345'")) == b"abc12345"
    assert evaluer_secret(b("'cle_api' => 'abc12345'")) == b"abc12345"
    assert evaluer_secret(b("$jeton = 'abc12345'")) == b"abc12345"
    assert evaluer_secret(b("'mot_de_passe' => ''")) is None
    for faux in ("$password = ''", "$password = $_POST['p']", "$password = 'changeme'", "$compass = 'abcdefgh'",
                 "$nom = 'abcdefgh'", "$token = \"abc$id\""):
        assert evaluer_secret(b(faux)) is None


def test_fonctions_dangereuses_include_hash_upload():
    assert danger(EV, b("(@G@['c'])"))[0] == "critique"
    assert danger("unserialize", b("($data)"))[0] == "elevee"
    assert danger("strlen", b("($x)")) is None
    assert evaluer_include(b("require @G@['page'] . '.php';"))[0] == "critique"
    assert evaluer_include(b("require_once __DIR__ . '/a.php';")) is None
    assert evaluer_hash("md5", b("($password)"))[0] == "elevee"
    assert evaluer_hash("md5", b("($fichier)")) is None
    assert evaluer_upload("move_uploaded_file", b("move_uploaded_file($t, $d);"))[0] == "elevee"
    assert evaluer_upload("move_uploaded_file", b("$e = pathinfo($n); move_uploaded_file($t,$d);")) is None


# ---- Partie 2 : nécessite tree-sitter-php. Si ces tests échouent, les noms de nœuds de TA version de la grammaire diffèrent.
def analyser(tmp_path, code, regle):
    pytest.importorskip("tree_sitter_php")            # saute seulement ces tests-ci si tree-sitter est absent
    from app.analysis.php_treesitter import AnalyseurPHPTreeSitter
    (tmp_path / "a.php").write_text(php(code), encoding="utf-8")
    return AnalyseurPHPTreeSitter().analyser(tmp_path, [], [], {regle})


def test_analyseur_xss(tmp_path):
    r = analyser(tmp_path, "<?php\necho @G@['q'];\necho htmlspecialchars(@G@['q']);\n", "php.xss")
    assert [c.ligne_debut for c in r] == [2]


def test_analyseur_secret_masque(tmp_path):
    r = analyser(tmp_path, "<?php\n$password = 'abc12345';\n$nom = 'abcdefgh';\n", "php.secret_en_dur")
    assert [c.ligne_debut for c in r] == [2] and "abc12345" not in r[0].extrait_code


def test_analyseur_fonction_dangereuse(tmp_path):
    r = analyser(tmp_path, "<?php\n@EV@($code);\nstrlen($x);\n", "php.fonction_dangereuse")
    assert [(c.ligne_debut, c.gravite) for c in r] == [(2, "elevee")]


def test_analyseur_include_dynamique(tmp_path):
    r = analyser(tmp_path, "<?php\nrequire @G@['p'] . '.php';\nrequire_once __DIR__ . '/a.php';\n", "php.include_dynamique")
    assert [c.ligne_debut for c in r] == [2]


def test_analyseur_hash_faible(tmp_path):
    r = analyser(tmp_path, "<?php\n$h = md5($password);\n$k = md5($fichier);\n", "php.hash_faible")
    assert [c.ligne_debut for c in r] == [2]


def test_analyseur_upload(tmp_path):
    code = "<?php\nfunction a() {\n  move_uploaded_file($t, $d);\n}\nfunction b() {\n  $e = pathinfo($n);\n  move_uploaded_file($t, $d);\n}\n"
    r = analyser(tmp_path, code, "php.upload_non_controle")
    assert [c.ligne_debut for c in r] == [3]
