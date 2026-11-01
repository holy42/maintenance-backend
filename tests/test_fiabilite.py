"""Tests du modèle de fiabilité (Python standard : aucune base de données ni bibliothèque externe)."""
import json
import math
import random

from app.fiabilite import entrainement as en
from app.fiabilite import metriques as m
from app.fiabilite.donnees_synthetiques import generer
from app.fiabilite.heuristique import modele_heuristique
from app.fiabilite.modeles import CalibrateurPlatt, ForetAleatoire, ModeleFiabilite, RegressionLogistique
from app.fiabilite.niveaux import niveau
from app.fiabilite.variables import NOMS, EntreeEtape3, EntreeEtape6, variables_etape3, variables_etape6
from app.fiabilite.verifications import controler_verifications


def _donnees(n=240, graine=3):
    rng = random.Random(graine)
    X = [[rng.gauss(0, 1) for _ in range(5)] for _ in range(n)]
    y = [int(rng.random() < 1 / (1 + math.exp(-(1.6 * x[0] - 1.2 * x[1])))) for x in X]
    return X, y


def test_auc_et_brier_valeurs_connues():
    assert m.auc([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]) == 0.75
    assert m.auc([0, 1], [0.5, 0.5]) == 0.5                      # égalité : rang moyen
    assert m.brier([1, 0], [1.0, 0.0]) == 0.0
    assert math.isnan(m.auc([1, 1], [0.2, 0.9]))


def test_plis_stratifies_couvrent_tout_une_seule_fois():
    y = [0] * 40 + [1] * 20
    plis = m.decouper_stratifie(y, 5)
    tous = sorted(i for p in plis for i in p)
    assert tous == list(range(60))
    assert all(sum(y[i] for i in p) == 4 for p in plis)            # 4 positifs par pli


def test_regression_logistique_apprend_et_se_serialise():
    X, y = _donnees()
    mod = RegressionLogistique().fit(X, y)
    assert m.auc(y, [mod.predict_proba(x) for x in X]) > 0.8
    copie = RegressionLogistique.from_dict(json.loads(json.dumps(mod.to_dict())))
    assert abs(copie.predict_proba(X[0]) - mod.predict_proba(X[0])) < 1e-12


def test_foret_apprend_et_se_serialise():
    X, y = _donnees()
    f = ForetAleatoire(n_arbres=25).fit(X, y)
    assert m.auc(y, [f.predict_proba(x) for x in X]) > 0.8
    copie = ForetAleatoire.from_dict(json.loads(json.dumps(f.to_dict())))
    assert abs(copie.predict_proba(X[1]) - f.predict_proba(X[1])) < 1e-12


def test_calibration_reduit_l_ecart_de_calibration():
    X, y = _donnees(400)
    oof = m.validation_croisee(X, y, lambda: ForetAleatoire(n_arbres=20), k=5)
    cal = CalibrateurPlatt().fit(oof, y)
    assert m.ece(y, [cal.appliquer(p) for p in oof]) <= m.ece(y, oof) + 1e-9


def test_modele_expliquable_et_complet():
    X, y = _donnees()
    noms = [f"v{i}" for i in range(5)]
    mod = en.entrainer_final(3, noms, X, y, "logistique", repetitions=1)
    v = dict(zip(noms, X[0]))
    assert 0 <= mod.predire(v) <= 1
    assert mod.expliquer(v, top=2)[0]["variable"] in ("v0", "v1")        # les deux variables réellement utiles
    assert ModeleFiabilite.from_dict(json.loads(json.dumps(mod.to_dict()))).predire(v) == mod.predire(v)


def test_comparaison_refuse_un_jeu_trop_petit():
    X, y = _donnees(20)
    try:
        en.comparer(X, y)
        assert False, "aurait dû refuser"
    except ValueError:
        pass


def test_choix_prefere_le_modele_simple_et_jamais_pire_que_la_constante():
    base = {"auc": .7, "brier": .2}
    assert en.choisir({"modeles": {"logistique": base, "foret": {"brier": .195}, "constant": {"brier": .25}}}) == "logistique"
    assert en.choisir({"modeles": {"logistique": base, "foret": {"brier": .15}, "constant": {"brier": .25}}}) == "foret"
    assert en.choisir({"modeles": {"logistique": {"brier": .26}, "foret": {"brier": .27}, "constant": {"brier": .25}}}) == "constant"


def test_variables_etape3_sql_concatene_avec_entree_utilisateur():
    e = EntreeEtape3(categorie="securite", gravite="critique", regle="php.sql_concat", fichier="app/Models/M.php",
                     extrait='$this->db->query("SELECT * FROM t WHERE a=\'" . $_GET["q"] . "\'");')
    v = variables_etape3(e)
    assert v["entree_utilisateur"] == 1.0 and v["protection_proche"] == 0.0 and v["gravite"] == 3.0 and set(v) == set(NOMS[3])
    protege = variables_etape3(EntreeEtape3(categorie="securite", regle="php.sql_concat", extrait="$q = intval($_GET['id']); $db->query($sql . $q);"))
    assert protege["protection_proche"] == 1.0
    assert variables_etape3(EntreeEtape3(categorie="securite", fichier="vendor/lib/x.php"))["dossier_tiers"] == 1.0


def test_variables_etape6_diff_et_authentification():
    diff = "--- a/x.php\n+++ b/x.php\n- $a = 1;\n+ $a = 2;\n+ if (! $session->has('user')) { return; }"
    v = variables_etape6(EntreeEtape6(extrait_code=diff, description="contrôle de session", confiance_declaree=0.8, incertitudes="x"))
    assert v["lignes_ajoutees"] == math.log1p(2) and v["lignes_retirees"] == math.log1p(1) and v["nb_fichiers_touches"] == 1.0
    assert v["touche_authentification"] == 1.0 and v["a_incertitudes"] == 1.0 and set(v) == set(NOMS[6])


def test_heuristique_non_apprise_et_niveaux():
    h = modele_heuristique(3)
    assert h.appris is False
    haut = h.predire(variables_etape3(EntreeEtape3(categorie="securite", gravite="critique", regle="php.sql_concat", extrait="$_GET['a']", taux_confirmation_regle=0.9)))
    bas = h.predire(variables_etape3(EntreeEtape3(categorie="securite", regle="php.sql_concat", fichier="vendor/x.php", extrait="intval($x)", taux_confirmation_regle=0.1)))
    assert haut > bas
    assert niveau(0.2) == "faible" and niveau(0.5) == "moyen" and niveau(0.9) == "eleve"


def test_verifications_recommandees_controlees():
    res = controler_verifications(
        ["Vérifier la validation dans app/Controllers/Messages.php", "vérifier la validation dans app/Controllers/Messages.php",
         "Le problème est corrigé.", "Lire autre/Fichier.php", ""], fichiers_connus={"app/Controllers/Messages.php"}, categorie="securite")
    textes = [r["texte"] for r in res]
    assert len(res) == 2 and "Le problème est corrigé." not in textes                  # doublon supprimé, affirmation rejetée
    assert res[0]["controle"] == "ok" and res[1]["controle"] == "a_verifier"           # fichier absent du contexte
    assert controler_verifications([], None, "securite")[0]["origine"] == "regle"      # vérification générique de secours


def test_chaine_complete_sur_donnees_fictives():
    X, y = generer(3, 200, graine=1)
    res = en.comparer(X, y, repetitions=1)
    assert res["recommande"] in ("logistique", "foret") and res["modeles"]["logistique"]["auc"] > 0.65
    Xa, ya, Xt, yt = en.separer_test(X, y, 0.3)
    assert len(Xt) + len(Xa) == len(X) and abs(sum(yt) / len(yt) - sum(y) / len(y)) < 0.1
