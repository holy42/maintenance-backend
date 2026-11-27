"""Banc de test de l'étape 6 : application des diffs (sans base, sans IA, sans php)."""
from app.fiabilite.banc import appliquer_diff, chemin_git, lire_diff

SOURCE = "<?php\nclass A {\n    function f($id) {\n        $r = $db->query(\"SELECT \" . $id);\n        return $r;\n    }\n}\n"


def _lire(fichiers):
    return lambda c: fichiers.get(c)


def test_diff_avec_entetes_et_espaces_differents():
    diff = "--- a/x.php\n+++ b/x.php\n@@ -4,1 +4,2 @@\n-  $r = $db->query(\"SELECT \" . $id);\n+  $r = $db->prepare(\"SELECT ?\");\n+  $r->execute([$id]);\n"
    res, motif = appliquer_diff(diff, _lire({"x.php": SOURCE}), "x.php")
    assert motif == "appliqué" and "prepare" in res["x.php"] and "query" not in res["x.php"] and "return $r;" in res["x.php"]


def test_diff_sans_entete_vise_le_fichier_du_probleme():
    res, _ = appliquer_diff("-        return $r;\n+        return $r ?: null;", _lire({"x.php": SOURCE}), "x.php")
    assert "return $r ?: null;" in res["x.php"]


def test_passage_introuvable_ou_fichier_absent():
    assert appliquer_diff("-inexistant();\n+autre();", _lire({"x.php": SOURCE}), "x.php")[0] is None
    assert appliquer_diff("--- a/y.php\n+++ b/y.php\n-a\n+b", _lire({"x.php": SOURCE}), "x.php")[1].startswith("fichier cité introuvable")


def test_creation_de_fichier_et_chemins():
    res, _ = appliquer_diff("--- /dev/null\n+++ b/n.php\n@@ -0,0 +1,1 @@\n+<?php echo 1;", _lire({}), "x.php")
    assert res == {"n.php": "<?php echo 1;\n"}
    assert [b.fichier for b in lire_diff("diff --git a/p.php b/p.php\n--- a/p.php\n+++ b/p.php\n@@ -1 +1 @@\n-a\n+b")] == ["p.php"]
    assert chemin_git("app\\Controllers\\A.php") == "app/Controllers/A.php" and chemin_git("./.env") == ".env"


def test_pur_ajout_insere_apres_la_ligne_annoncee():
    diff = "--- a/x.php\n+++ b/x.php\n@@ -3,0 +4,1 @@\n+        $id = (int) $id;"
    res, _ = appliquer_diff(diff, _lire({"x.php": SOURCE}), "x.php")
    lignes = res["x.php"].splitlines()
    assert lignes[3] == "        $id = (int) $id;" and lignes[4].strip().startswith("$r = $db->query")
