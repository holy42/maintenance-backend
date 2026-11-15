"""Export d'un échantillon ALÉATOIRE de résultats pour un second étiqueteur (lecture seule, ne modifie PAS la base).

À placer dans le dossier backend/ puis lancer (environnement virtuel activé, base accessible) :

    python exporter_feuille_etiquetage.py --verification 5 --n 40 --graine 1

Produit deux fichiers dans le dossier courant (UTF-8 avec BOM, ouvrables dans Excel) :
  feuille_etiqueteur2.csv  -> à donner au second étiqueteur. Colonnes : id_resultat, fichier, ligne, categorie, extrait_code,
                              decision (vide), motif (vide). Ne contient NI la fiabilité du modèle, NI la décision du premier
                              étiqueteur, NI la vérité du générateur.
  cle_decisions_a.csv     -> pour VOUS seulement. Colonnes : id_resultat, decision_a (décision du premier étiqueteur
                              dans la plateforme : REEL / FAUX / NON_DECIDE). Sert à calculer le kappa après coup.

Règles :
  - tirage reproductible (même --graine = même échantillon) ;
  - seuls les résultats DÉJÀ décidés (confirmé / écarté) dans la plateforme sont tirés, sinon le kappa n'a rien à comparer
    (utilisez --inclure-non-decides pour les tirer quand même) ;
  - les résultats de code tiers (vendor, third_party, libs) restent dans le tirage : c'est aux étiqueteurs de répondre HORS.
"""
import argparse
import csv
import random
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models.verification import ResultatAnalyse

CORRESP = {"confirme": "REEL", "ecarte": "FAUX"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--verification", type=int, required=True, help="identifiant de la vérification à échantillonner")
    p.add_argument("--n", type=int, default=40, help="taille de l'échantillon commun (20 à 30 %% du total ; 30 minimum conseillé)")
    p.add_argument("--graine", type=int, default=1)
    p.add_argument("--inclure-non-decides", action="store_true")
    p.add_argument("--sortie-feuille", default="feuille_etiqueteur2.csv")
    p.add_argument("--sortie-cle", default="cle_decisions_a.csv")
    a = p.parse_args()

    with SessionLocal() as db:
        lignes = db.execute(select(ResultatAnalyse).where(ResultatAnalyse.verification_id == a.verification)
                            .order_by(ResultatAnalyse.id)).scalars().all()
        if not lignes:
            print(f"Aucun résultat pour la vérification {a.verification}.", file=sys.stderr)
            return 1
        if not a.inclure_non_decides:
            lignes = [r for r in lignes if r.statut_validation in CORRESP]
        if len(lignes) < a.n:
            print(f"Seulement {len(lignes)} résultats disponibles pour {a.n} demandés : échantillon réduit.", file=sys.stderr)
        tirage = random.Random(a.graine).sample(lignes, min(a.n, len(lignes)))
        random.Random(a.graine + 1).shuffle(tirage)          # ordre mélangé : pas de regroupement par fichier

        with open(a.sortie_feuille, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["id_resultat", "fichier", "ligne", "categorie", "extrait_code", "decision", "motif"])
            for r in tirage:
                w.writerow([r.id, r.fichier or "", r.ligne_debut or "", r.categorie, (r.extrait_code or "").strip(), "", ""])
        with open(a.sortie_cle, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["id_resultat", "decision_a"])
            for r in tirage:
                w.writerow([r.id, CORRESP.get(r.statut_validation, "NON_DECIDE")])

    print(f"{len(tirage)} résultats tirés.\n  À donner au second étiqueteur : {a.sortie_feuille}\n  À garder pour vous : {a.sortie_cle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
