"""Valeurs autorisées (alignées sur les contraintes CHECK du script SQL)."""
from enum import StrEnum


class StatutProbleme(StrEnum):
    NOUVEAU = "nouveau"
    A_ANALYSER = "a_analyser"
    CONFIRME = "confirme"
    FAUX_POSITIF = "faux_positif"
    EN_COURS = "en_cours"
    A_TESTER = "a_tester"
    TESTE = "teste"
    TERMINE = "termine"
    ROUVERT = "rouvert"


class StatutTache(StrEnum):
    A_FAIRE = "a_faire"
    EN_COURS = "en_cours"
    EN_PAUSE = "en_pause"
    ARRETEE = "arretee"
    TERMINEE = "terminee"


class StatutSession(StrEnum):
    A_TESTER = "a_tester"
    EN_COURS = "en_cours"
    VALIDE = "valide"
    NON_VALIDE = "non_valide"


class Categorie(StrEnum):
    ERREUR_TECHNIQUE = "erreur_technique"
    FONCTIONNEL = "fonctionnel"
    NOUVELLE_FONCTIONNALITE = "nouvelle_fonctionnalite"
    REGRESSION = "regression"
    SECURITE = "securite"
    PROPRE_APPLICATION = "propre_application"


class Gravite(StrEnum):
    CRITIQUE = "critique"
    ELEVEE = "elevee"
    MOYENNE = "moyenne"
    FAIBLE = "faible"


class Priorite(StrEnum):
    URGENTE = "urgente"
    HAUTE = "haute"
    NORMALE = "normale"
    BASSE = "basse"


class Source(StrEnum):
    OUTIL = "outil"
    IA = "ia"
    HUMAIN = "humain"


class TypeDecision(StrEnum):
    IA_RETENUE = "ia_retenue"
    IA_ADAPTEE = "ia_adaptee"
    AUTRE_SOLUTION = "autre_solution"
    SANS_IA = "sans_ia"


class StatutCritere(StrEnum):
    BROUILLON = "brouillon"
    VALIDE = "valide"
    ACTIF = "actif"
    INACTIF = "inactif"
    OBSOLETE = "obsolete"


class StatutVerification(StrEnum):
    EN_ATTENTE = "en_attente"
    EN_COURS = "en_cours"
    TERMINEE = "terminee"
    ECHOUEE = "echouee"


class Perm(StrEnum):
    PROBLEME_CONSULTER = "probleme.consulter"
    PROBLEME_MODIFIER = "probleme.modifier"
    VERIFICATION_LANCER = "verification.lancer"
    SOLUTION_DECIDER = "solution.decider"
    TEST_VALIDER = "test.valider"
    HISTORIQUE_CONSULTER = "historique.consulter"
    RAPPORT_CONSULTER = "rapport.consulter"
    DISCUSSION_PARTICIPER = "discussion.participer"
    ASSISTANT_UTILISER = "assistant.utiliser"
    CRITERE_GERER = "critere.gerer"
    TACHE_GERER = "tache.gerer"
    APPLICATION_CONFIGURER = "application.configurer"
    SALON_SUPPRIMER = "salon.supprimer"
