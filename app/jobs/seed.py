"""Données initiales :  python -m app.jobs.seed --admin aina --criteres-standard
Le script SQL crée déjà les rôles et les permissions."""
import argparse
import getpass

from sqlalchemy import select

from app.core.security import hacher_mot_de_passe
from app.database import SessionLocal
from app.models import Critere, Utilisateur

CRITERES_STANDARD = [
    dict(nom="Erreurs de syntaxe PHP", categorie="erreur_technique", automatisabilite="automatisable",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.syntaxe"},
         description="Le code PHP ne doit pas contenir d'erreur de syntaxe."),
    dict(nom="Requêtes SQL non protégées", categorie="securite", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.sql_concat"},
         description="Une valeur issue de l'utilisateur ne doit pas être concaténée dans une requête SQL."),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin", help="identifiant de l'administrateur de la plateforme à créer")
    parser.add_argument("--criteres-standard", action="store_true", help="insère les critères standards")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.admin:
            if db.execute(select(Utilisateur.id).where(Utilisateur.identifiant == args.admin)).first():
                print("Cet identifiant existe déjà.")
            else:
                mdp = getpass.getpass("Mot de passe (10 caractères minimum) : ")
                if len(mdp) < 10:
                    raise SystemExit("Mot de passe trop court.")
                db.add(Utilisateur(identifiant=args.admin, mot_de_passe_hash=hacher_mot_de_passe(mdp), est_admin=True))
                print("Administrateur créé.")
        if args.criteres_standard:
            for c in CRITERES_STANDARD:
                if not db.execute(select(Critere.id).where(Critere.nom == c["nom"], Critere.origine == "standard")).first():
                    db.add(Critere(application_id=None, origine="standard", statut="actif", **c))
                    print(f"Critère standard ajouté : {c['nom']}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
