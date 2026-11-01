"""Outils en ligne de commande (à lancer depuis backend/) :

  python -m app.fiabilite.cli synthetique --etape 3 --n 200 --sortie /tmp/etape3.csv      # données FICTIVES (test du code seulement)
  python -m app.fiabilite.cli comparer    --etape 3 --csv donnees_etape3.csv [--sklearn]  # validation croisée de tous les modèles
  python -m app.fiabilite.cli entrainer   --etape 3 --csv donnees_etape3.csv --algo auto --sortie var/modeles/etape3.json [--test 0.3]

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
    a = p.parse_args(argv)
    noms = NOMS[a.etape]

    if a.cmd == "synthetique":
        X, y = generer(a.etape, a.n, a.graine)
        en.ecrire_csv(a.sortie, noms, list(zip(X, y)))
        print(f"{a.n} exemples FICTIFS écrits dans {a.sortie} : à n'utiliser que pour tester le code.", file=sys.stderr)
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
