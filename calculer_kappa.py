#!/usr/bin/env python3
"""Calcule l'accord entre deux étiqueteurs (coefficient kappa de Cohen). Python standard, rien à installer.

  python calculer_kappa.py --cle cle_decisions_a.csv --feuille feuille_etiqueteur2_remplie.csv

  --cle     le fichier cle_decisions_a.csv (décisions du premier étiqueteur : REEL / FAUX / NON_DECIDE)
  --feuille la feuille renvoyée par le second étiqueteur (colonne « decision » remplie : REEL ou FAUX ; HORS accepté)
Les lignes où l'un des deux n'a pas répondu REEL ou FAUX sont exclues du calcul et comptées à part.
Écrit aussi desaccords.csv : les cas où vous n'êtes pas d'accord (à relire ensemble, très utile pour le mémoire)."""
import argparse
import csv
import math
import sys
import unicodedata
from collections import Counter


def norm(texte: str) -> str:
    t = unicodedata.normalize("NFKD", (texte or "").strip().upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {"REEL": "REEL", "R": "REEL", "VRAI": "REEL", "OUI": "REEL", "1": "REEL",
            "FAUX": "FAUX", "F": "FAUX", "NON": "FAUX", "0": "FAUX", "ECARTE": "FAUX",
            "HORS": "HORS", "HORS PERIMETRE": "HORS"}.get(t, t or "VIDE")


def lire(chemin: str) -> list[dict]:
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        contenu = f.read()
    separateur = ";" if contenu.splitlines()[0].count(";") > contenu.splitlines()[0].count(",") else ","
    return list(csv.DictReader(contenu.splitlines(), delimiter=separateur))


def interpretation(k: float) -> str:
    return ("accord très faible" if k < 0.2 else "accord faible" if k < 0.4 else "accord moyen" if k < 0.6
            else "bon accord" if k < 0.8 else "excellent accord")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cle", required=True)
    ap.add_argument("--feuille", required=True)
    ap.add_argument("--sortie", default="desaccords.csv")
    a = ap.parse_args()

    cle = {r["id_resultat"].strip(): norm(r.get("decision_a")) for r in lire(a.cle)}
    feuille = lire(a.feuille)
    if feuille and "decision" not in feuille[0]:
        raise SystemExit("La feuille n'a pas de colonne « decision » (vérifier le séparateur ou le nom de la colonne).")
    paires, exclues, inconnus = [], Counter(), 0
    for r in feuille:
        i = r["id_resultat"].strip()
        if i not in cle:
            inconnus += 1
            continue
        a_, b_ = cle[i], norm(r["decision"])
        if a_ in ("REEL", "FAUX") and b_ in ("REEL", "FAUX"):
            paires.append((i, a_, b_, r))
        else:
            exclues[f"A={a_} / B={b_}"] += 1

    n = len(paires)
    if n < 2:
        raise SystemExit(f"Pas assez de cas comparables ({n}). Le second étiqueteur a-t-il rempli la colonne « decision » ?")
    c = Counter((x, y) for _, x, y, _ in paires)
    A_R, A_F = c[("REEL", "REEL")], c[("REEL", "FAUX")]
    B_R, B_F = c[("FAUX", "REEL")], c[("FAUX", "FAUX")]
    po = (A_R + B_F) / n
    pe = ((A_R + A_F) * (A_R + B_R) + (B_R + B_F) * (A_F + B_F)) / n ** 2
    kappa = 1.0 if pe == 1 else (po - pe) / (1 - pe)
    se = math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2)) if pe < 1 else 0.0          # erreur-type approchée
    print(f"\nCas comparés : {n}   (exclus : {sum(exclues.values())}, identifiants inconnus : {inconnus})")
    for k, v in exclues.items():
        print(f"   exclu : {k} -> {v}")
    print("\n                  Étiqueteur 2 : REEL   FAUX")
    print(f"Étiqueteur 1 : REEL          {A_R:>8}{A_F:>7}")
    print(f"Étiqueteur 1 : FAUX          {B_R:>8}{B_F:>7}")
    print(f"\nAccord observé   po = {po:.3f}   ({A_R + B_F}/{n})")
    print(f"Accord au hasard pe = {pe:.3f}")
    print(f"KAPPA = {kappa:.3f}   ({interpretation(kappa)} ; intervalle approx. à 95 % : {kappa - 1.96 * se:.2f} à {kappa + 1.96 * se:.2f})")
    if n < 30:
        print("Attention : moins de 30 cas, le kappa est peu fiable.")
    if pe > 0.8:
        print("Attention : presque tous les cas sont de la même classe, le kappa est instable (peu de REEL ou peu de FAUX dans l'échantillon).")
    with open(a.sortie, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id_resultat", "fichier", "ligne", "categorie", "etiqueteur_1", "etiqueteur_2", "motif_etiqueteur_2"])
        for i, x, y, r in paires:
            if x != y:
                w.writerow([i, r.get("fichier"), r.get("ligne"), r.get("categorie"), x, y, r.get("motif", "")])
    print(f"\nDésaccords : {A_F + B_R} cas, écrits dans {a.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
