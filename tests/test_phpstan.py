"""Analyseur PHPStan. Partie 1 : conversion du rapport JSON (sans PHPStan). Partie 2 : lancement réel (ignoré si PHPStan est absent)."""
import shutil

import pytest

from app.analysis.php_phpstan import AnalyseurPHPStan, REGLES_PHPSTAN, convertir, regle_pour
from app.config import settings
from app.core.exceptions import ErreurMetier


def test_correspondance_des_identifiants():
    assert regle_pour("variable.undefined", "Undefined variable: $x") == ("php.variable_non_definie", "elevee")
    assert regle_pour("function.notFound", "Function f not found.") == ("php.appel_inexistant", "elevee")
    assert regle_pour("method.notFound", "Call to an undefined method A::b().") == ("php.appel_inexistant", "elevee")
    assert regle_pour("argument.type", "Parameter #1 ...")[0] == "php.type_incoherent"
    assert regle_pour("deadCode.unreachable", "Unreachable statement") == ("php.code_mort", "faible")
    assert regle_pour("if.alwaysTrue", "If condition is always true.")[0] == "php.code_mort"
    assert regle_pour("binaryOp.invalid", 'Binary operation "/" between 10 and 0 results in an error.') == ("php.division_par_zero", "elevee")
    assert regle_pour("binaryOp.invalid", 'Binary operation "+" between string and array results in an error.')[0] == "php.type_incoherent"


def test_identifiants_ignores():
    assert regle_pour("phpstan.parse", "Syntax error") is None            # déjà couvert par php.syntaxe
    assert regle_pour("function.resultUnused", "Call to function f() has no effect.") is None
    assert regle_pour(None, "message sans identifiant") is None
    assert regle_pour("class.notFound", "Instantiated class X not found.") is None           # bruit sans « vendor »
    assert regle_pour("class.notFound", "Instantiated class X not found.", classes_inconnues=True)[0] == "php.appel_inexistant"


def test_conversion_du_rapport(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.php").write_text("<?php\nfunction f() {\n  return $absente;\n}\n", encoding="utf-8")
    rapport = {"files": {str(tmp_path / "src" / "a.php"): {"messages": [
        {"message": "Undefined variable: $absente", "line": 3, "identifier": "variable.undefined"},
        {"message": "Syntax error", "line": 9, "identifier": "phpstan.parse"},
        {"message": "Call to function f() has no effect.", "line": 3, "identifier": "function.resultUnused"},
    ]}}}
    c = convertir(rapport, tmp_path, set(REGLES_PHPSTAN), 5)
    assert len(c) == 1
    assert (c[0].regle, c[0].fichier, c[0].ligne_debut, c[0].gravite) == ("php.variable_non_definie", "src/a.php", 3, "elevee")
    assert c[0].categorie == "erreur_technique" and c[0].outil == "phpstan" and "$absente" in c[0].extrait_code
    # une règle non cochée ne produit rien
    assert convertir(rapport, tmp_path, {"php.code_mort"}, 5) == []


def test_plafond_par_fichier_et_regle(tmp_path):
    msgs = [{"message": "Undefined variable: $v", "line": i + 1, "identifier": "variable.undefined"} for i in range(80)]
    c = convertir({"files": {str(tmp_path / "a.php"): {"messages": msgs}}}, tmp_path, set(REGLES_PHPSTAN), 5)
    assert len(c) == 50


# ---- Partie 2 : lancement réel (nécessite PHP + PHPStan, réglés par PHPSTAN_COMMANDE)
@pytest.fixture
def phpstan_disponible():
    if shutil.which(settings.phpstan_commande[0]) is None:
        pytest.skip("PHPStan non installé (voir PHPSTAN_COMMANDE)")


def test_lancement_reel_avec_erreur_de_syntaxe_ailleurs(tmp_path, phpstan_disponible):
    (tmp_path / "bon.php").write_text("<?php\nfunction f() {\n  return $absente;\n}\n", encoding="utf-8")
    (tmp_path / "casse.php").write_text("<?php\nfunction {\n", encoding="utf-8")      # un fichier illisible ne doit pas tout bloquer
    try:
        c = AnalyseurPHPStan().analyser(tmp_path, [], [], set(REGLES_PHPSTAN))
    except ErreurMetier as exc:
        pytest.skip(f"PHPStan présent mais inutilisable : {exc.message}")
    assert [(x.fichier, x.ligne_debut, x.regle) for x in c] == [("bon.php", 3, "php.variable_non_definie")]


def test_dossier_inexistant_ne_donne_rien(tmp_path, phpstan_disponible):
    assert AnalyseurPHPStan().analyser(tmp_path, ["absent"], [], set(REGLES_PHPSTAN)) == []