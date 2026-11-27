"""Outils en ligne de commande (à lancer depuis backend/) :

  python -m app.fiabilite.cli synthetique --etape 3 --n 200 --sortie /tmp/etape3.csv      # données FICTIVES (test du code seulement)
  python -m app.fiabilite.cli comparer    --etape 3 --csv donnees_etape3.csv [--sklearn]  # validation croisée de tous les modèles
  python -m app.fiabilite.cli entrainer   --etape 3 --csv donnees_etape3.csv --algo auto --sortie var/modeles/etape3.json [--test 0.3]
  python -m app.fiabilite.cli evaluer     --etape 3 --apprentissage jeu1.csv --test export_complet.csv --retirer-apprentissage
      # entraîne sur jeu1.csv puis évalue UNE fois sur un jeu indépendant ; compare aux règles fixées à la main et à la référence constante
  python -m app.fiabilite.cli banc        --utilisateur aina --max 20 --sortie var/banc_etape6.csv [--etiqueter] [--applications 1,2]
      # étape 6 : banc de test automatique sur les applications de TEST (appelle l'IA ; voir app/fiabilite/banc.py)

Le CSV contient une colonne par variable (voir app/fiabilite/variables.py) et une colonne `etiquette` (1 = vrai, 0 = faux)."""
import argparse
import json
import os
import sys

from app.fiabilite import entrainement as en
from app.fiabilite.donnees_synthetiques import generer
from app.fiabilite.variables import NOMS


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("synthetique"); s.add_argument("--etape", type=int, choices=(3, 6), required=True)
    s.add_argument("--n", type=int, default=200); s.add_argument("--sortie", required=True); s.add_argument("--graine", type=int, default=0)
    c = sp.add_parser("comparer"); c.add_argument("--etape", type=int, choices=(3, 6), required=True); c.add_argument("--csv", required=True)
    c.add_argument("--k", type=int, default=5); c.add_argument("--repetitions", type=int, default=3); c.add_argument("--graine", type=int, default=0)
    c.add_argument("--sklearn", action="store_true", help="ajoute une comparaison avec scikit-learn s'il est installé")
    e = sp.add_parser("entrainer"); e.add_argument("--etape", type=int, choices=(3, 6), required=True); e.add_argument("--csv", required=True)
    e.add_argument("--algo", choices=("logistique", "foret", "auto"), default="auto"); e.add_argument("--sortie", required=True)
    e.add_argument("--test", type=float, default=0.0, help="part mise de côté pour l'évaluation finale (ex. 0.3)"); e.add_argument("--graine", type=int, default=0)
    v = sp.add_parser("evaluer"); v.add_argument("--etape", type=int, choices=(3, 6), required=True)
    v.add_argument("--apprentissage", required=True, help="CSV d'entraînement (ex. export de la plateforme avant d'étiqueter le jeu indépendant)")
    v.add_argument("--test", required=True, help="CSV du jeu indépendant, jamais utilisé pour entraîner")
    v.add_argument("--retirer-apprentissage", action="store_true",
                   help="le CSV de test est un export COMPLET : on en retire d'abord les lignes présentes dans le CSV d'apprentissage")
    v.add_argument("--graine", type=int, default=0)
    b = sp.add_parser("banc", help="étape 6 : étiquettes produites par un banc de test automatique (appelle l'IA)")
    b.add_argument("--utilisateur", required=True, help="identifiant du compte au nom duquel les diagnostics sont créés")
    b.add_argument("--max", type=int, default=20, help="nombre de problèmes à diagnostiquer (un appel à l'IA chacun)")
    b.add_argument("--sortie", default="var/banc_etape6.csv", help="CSV complété à chaque lancement")
    b.add_argument("--etiqueter", action="store_true", help="écrit aussi les étiquettes dans la base (sinon : CSV seulement)")
    b.add_argument("--applications", default="", help="identifiants d'applications séparés par des virgules (défaut : toutes)")
    b.add_argument("--importer", nargs="*", default=[], metavar="CSV",
                   help="écrit d'abord dans la base les étiquettes de ces CSV (lancements précédents faits sans --etiqueter)")
    a = p.parse_args(argv)

    if a.cmd == "banc":
        from app.database import SessionLocal
        from app.fiabilite.banc import executer
        apps = [int(x) for x in a.applications.split(",") if x.strip()] or None
        from app.fiabilite.banc import importer_csv
        with SessionLocal() as db:
            for chemin in a.importer:
                print(f"{importer_csv(db, chemin)} étiquette(s) importée(s) depuis {chemin}", file=sys.stderr)
            if a.max <= 0:
                return 0
            bilan = executer(db, a.utilisateur, a.max, a.sortie, a.etiqueter, apps, journal=lambda m: print(m, file=sys.stderr, flush=True))
        print(json.dumps(bilan, indent=2, ensure_ascii=False))
        return 0

    noms = NOMS[a.etape]

    if a.cmd == "synthetique":
        X, y = generer(a.etape, a.n, a.graine)
        en.ecrire_csv(a.sortie, noms, list(zip(X, y)))
        print(f"{a.n} exemples FICTIFS écrits dans {a.sortie} : à n'utiliser que pour tester le code.", file=sys.stderr)
        return 0

    if a.cmd == "evaluer":
        Xa, ya = en.lire_csv(a.apprentissage, noms)
        Xt, yt = en.lire_csv(a.test, noms)
        if a.retirer_apprentissage:
            Xt, yt = en.retirer_lignes(Xt, yt, Xa, ya)
        print(json.dumps(en.evaluer_independant(a.etape, noms, Xa, ya, Xt, yt, a.graine), indent=2, ensure_ascii=False))
        return 0

    X, y = en.lire_csv(a.csv, noms)
    if a.cmd == "comparer":
        conf = [x[noms.index("confiance_declaree")] for x in X] if a.etape == 6 else None
        print(json.dumps(en.comparer(X, y, a.k, a.repetitions, a.graine, conf, a.sklearn), indent=2, ensure_ascii=False))
        return 0

    # entraîner : sélection sur la partie apprentissage, évaluation finale sur la partie test (une seule fois)
    Xa, ya, Xt, yt = en.separer_test(X, y, a.test, a.graine) if a.test > 0 else (X, y, [], [])
    algo = a.algo
    if algo == "auto":
        algo = en.comparer(Xa, ya, graine=a.graine)["recommande"]
        if algo == "constant":
            print("Les variables n'apportent rien par rapport à une prédiction constante : entraînement refusé.", file=sys.stderr)
            return 2
    modele = en.entrainer_final(a.etape, noms, Xa, ya, algo, graine=a.graine)
    if Xt:
        modele.metriques["jeu_de_test"] = en.evaluer_sur_test(modele, noms, Xt, yt, a.graine)
    os.makedirs(os.path.dirname(a.sortie) or ".", exist_ok=True)
    with open(a.sortie, "w", encoding="utf-8") as f:
        json.dump(modele.to_dict(), f, ensure_ascii=False)
    print(json.dumps({"algorithme": algo, "metriques": modele.metriques}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
