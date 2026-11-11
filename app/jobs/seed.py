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
    dict(nom="Affichage sans échappement (XSS)", categorie="securite", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.xss"},
         description="Une valeur affichée dans une page doit être échappée (htmlspecialchars)."),
    dict(nom="Secrets écrits en clair", categorie="securite", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.secret_en_dur"},
         description="Un mot de passe, une clé ou un jeton ne doit pas être écrit en clair dans le code."),
    dict(nom="Fonctions dangereuses", categorie="securite", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.fonction_dangereuse"},
         description="eval, exec, system, unserialize et équivalents ne doivent pas recevoir de valeur non contrôlée."),
    dict(nom="Inclusion de fichier dynamique", categorie="securite", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.include_dynamique"},
         description="Le nom d'un fichier inclus (include, require) ne doit pas venir d'une variable non contrôlée."),
    dict(nom="Hachage de mot de passe faible", categorie="securite", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.hash_faible"},
         description="Un mot de passe doit être haché avec password_hash, pas avec md5 ou sha1."),
    dict(nom="Upload de fichier non contrôlé", categorie="securite", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.upload_non_controle"},
         description="Un fichier envoyé par l'utilisateur doit être contrôlé (type, extension) avant d'être enregistré."),
        dict(nom="Variables non définies", categorie="erreur_technique", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.variable_non_definie"},
         description="Toute variable utilisée doit avoir été définie avant."),
    dict(nom="Appels de fonctions ou méthodes inexistantes", categorie="erreur_technique", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.appel_inexistant"},
         description="Le code ne doit pas appeler une fonction, une méthode ou une classe qui n'existe pas."),
    dict(nom="Types incohérents", categorie="erreur_technique", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.type_incoherent"},
         description="Les types des valeurs passées, retournées et calculées doivent être cohérents."),
    dict(nom="Divisions par zéro", categorie="erreur_technique", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.division_par_zero"},
         description="Le code ne doit pas diviser par zéro."),
    dict(nom="Code mort", categorie="erreur_technique", automatisabilite="partielle",
         mode_verification="regle_statique", formulation_structuree={"regle": "php.code_mort"},
         description="Le code ne doit pas contenir d'instruction inatteignable ni de condition toujours vraie ou fausse."),
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
