"""Tests du branchement du modèle de fiabilité : contrôles, vérifications recommandées, métriques sans NaN, contrats de l'API.
Python standard + pydantic ; aucune base de données (les tests du service utilisent des objets factices)."""
import math
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.fiabilite import controles, entrainement as en, metriques as m
from app.fiabilite.libelles import LIBELLES, libelle
from app.fiabilite.variables import NOMS
from app.fiabilite.verifications import MAX_VERIFICATIONS, controler_verifications


# ---------- vérifications recommandées ----------

def test_une_consigne_contenant_corrige_est_gardee_mais_pas_une_affirmation():
    res = controler_verifications(["Vérifier que le bug est bien corrigé.", "Le bug est résolu.", "Tout est réglé."], None, "securite")
    assert [r["texte"] for r in res] == ["Vérifier que le bug est bien corrigé."]


def test_fichier_cite_sans_contexte_connu_est_a_verifier():
    res = controler_verifications(["Lire app/Models/User.php"], None, "securite")
    assert res[0]["controle"] == "a_verifier" and "app/Models/User.php" in res[0]["motif"]
    ok = controler_verifications(["Lire app/Models/User.php"], {"app/Models/User.php"}, "securite")
    assert ok[0]["controle"] == "ok"


def test_verifications_generiques_selon_la_categorie_et_plafond():
    assert controler_verifications(None, None, "securite")[0]["origine"] == "regle"
    assert controler_verifications(["", "  "], None, "inconnue")[0]["origine"] == "regle"
    beaucoup = [f"Vérifier le point numéro {i}" for i in range(20)]
    assert len(controler_verifications(beaucoup, None, "securite")) == MAX_VERIFICATIONS


# ---------- contrôles d'une solution ----------

DIFF = "--- a/app/Controllers/Messages.php\n+++ b/app/Controllers/Messages.php\n@@ -1,2 +1,2 @@\n- $a = 1;\n+ $a = 2;\n"


def test_reference_valide(tmp_path: Path):
    (tmp_path / "app" / "Controllers").mkdir(parents=True)
    (tmp_path / "app" / "Controllers" / "Messages.php").write_text("<?php")
    assert controles.reference_valide(DIFF, tmp_path) is True
    assert controles.reference_valide(DIFF.replace("Messages", "Absent"), tmp_path) is False
    assert controles.reference_valide("- $a;\n+ $b;\n", tmp_path) is None            # aucun fichier cité : non vérifiable
    assert controles.reference_valide(DIFF, None) is None                              # dépôt absent
    assert controles.reference_valide(DIFF, tmp_path / "inexistant") is None


def test_reference_valide_refuse_de_sortir_de_la_racine(tmp_path: Path):
    depot = tmp_path / "depot"
    depot.mkdir()
    (tmp_path / "secret.txt").write_text("x")
    assert controles.reference_valide("--- a/../secret.txt\n+++ b/../secret.txt\n", depot) is False


def test_creation_de_fichier_et_ligne_retiree_qui_ressemble_a_un_en_tete():
    assert controles.fichiers_cites("--- /dev/null\n+++ b/app/Nouveau.php\n+<?php\n") == []
    assert controles.fichiers_cites("-- commentaire SQL retiré\n+ SELECT 1;\n") == []        # « --- commentaire » dans un diff = ligne retirée
    assert controles.fichiers_cites("diff --git a/x.php b/x.php\n--- a/x.php\n+++ b/x.php\n") == ["x.php"]


def test_syntaxe_php_non_verifiable_sans_tree_sitter_ou_sans_php():
    assert controles.syntaxe_php_valide("", "extrait") is None
    assert controles.syntaxe_php_valide("Ceci n'est pas du code", "extrait") is None
    pytest.importorskip("tree_sitter_php")
    assert controles.syntaxe_php_valide("$a = 1;", "extrait") is True
    assert controles.syntaxe_php_valide("$a = (1 + ;", "extrait") is False
    assert controles.syntaxe_php_valide("- $a = 1;\n+ $a = 2;", "diff") is True


# ---------- métriques sans NaN, minimums ----------

def test_les_metriques_ne_contiennent_jamais_nan():
    r = m.rapport([0, 0, 1, 1], [0.1, 0.2, 0.3, 0.4])        # aucun « vrai » prédit à 0,5 : précision indéfinie
    assert r["precision"] is None and r["f1"] is None
    assert all(not (isinstance(v, float) and math.isnan(v)) for v in r.values())
    assert m.sans_nan({"a": [float("nan"), 1.0], "b": {"c": float("inf")}}) == {"a": [None, 1.0], "b": {"c": None}}


def test_minimum_d_exemples_par_classe():
    X = [[float(i % 7)] for i in range(200)]
    y = [1] * 10 + [0] * 190
    with pytest.raises(ValueError, match="insuffisant"):
        en.comparer(X, y)
    assert en.MIN_EXEMPLES >= 100 and en.MIN_PAR_CLASSE >= 20


# ---------- libellés et contrats de l'API ----------

def test_toutes_les_variables_ont_un_libelle_lisible():
    for noms in NOMS.values():
        for n in noms:
            assert n in LIBELLES and "_" not in libelle(n)


def test_contrats_pydantic_et_valeurs_par_defaut():
    from app.schemas.fiabilite import FiabiliteOut
    from app.schemas.probleme import DiagnosticOut, ProblemeOut, SolutionOut
    f = FiabiliteOut(etape=3, score=0.7, pourcentage=70, niveau="eleve", libelle_niveau="Élevée", source="heuristique", appris=False)
    now = __import__("datetime").datetime.now()
    sol = SimpleNamespace(id=1, diagnostic_id=1, description="d", extrait_code=None, format_code="extrait", risques=None,
                          tests_suggeres=None, cree_le=now)                            # pas d'attribut `fiabilite`
    assert SolutionOut.model_validate(sol).fiabilite is None
    sol.fiabilite = f
    assert SolutionOut.model_validate(sol).fiabilite.pourcentage == 70
    diag = SimpleNamespace(id=1, probleme_id=1, explication="e", causes_probables=[], niveau_confiance=Decimal("0.7"), incertitudes=None,
                           verifications_recommandees=[{"texte": "t", "controle": "ok", "origine": "ia"}], branche_analysee=None,
                           commit_reference=None, modele_ia="mock", cree_le=now, solutions=[sol])
    assert DiagnosticOut.model_validate(diag).verifications_recommandees[0]["controle"] == "ok"


# ---------- service : présentation (objets factices, sans base) ----------

def _evaluation(**kw):
    base = dict(etape=3, score=Decimal("0.712"), niveau="eleve", source="heuristique", modele_id=None, etiquette=None,
                explication=[{"variable": "protection_proche", "valeur": 1.0, "effet": -0.2, "sens": "diminue"}])
    base.update(kw)
    return SimpleNamespace(**base)


def test_sortie_presente_un_score_lisible():
    pytest.importorskip("sqlalchemy")
    from app.fiabilite.service import ServiceFiabilite
    s = ServiceFiabilite.sortie(_evaluation())
    assert s.pourcentage == 71 and s.libelle_niveau == "Élevée" and s.appris is False
    assert s.facteurs[0].libelle.startswith("protection") and "_" not in s.facteurs[0].libelle
    assert ServiceFiabilite.sortie(_evaluation(source="modele", modele_id=4)).appris is True


def test_annotation_en_une_requete_pour_toute_la_liste():
    pytest.importorskip("sqlalchemy")
    from app.fiabilite.service import ServiceFiabilite
    svc = ServiceFiabilite(db=None)
    appels = []
    svc.evaluations = lambda type_, ids: appels.append((type_, list(ids))) or {1: _evaluation()}
    resultats = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    svc.annoter_resultats(resultats)
    assert len(appels) == 1 and resultats[0].fiabilite.pourcentage == 71 and resultats[1].fiabilite is None
    problemes = [SimpleNamespace(resultat_id=1), SimpleNamespace(resultat_id=None)]
    svc.annoter_problemes(problemes)
    assert problemes[0].fiabilite_preuve is not None and problemes[1].fiabilite_preuve is None
