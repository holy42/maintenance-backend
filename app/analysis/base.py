"""Interface des analyseurs de code. Un adaptateur par technologie ou par outil : c'est ce qui
permet d'étendre à d'autres technologies que PHP sans toucher au reste de l'application."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Constat:
    regle: str                    # code de règle, ex. "php.syntaxe" (lié à un critère standard)
    message: str
    categorie: str                # erreur_technique, securite, ...
    gravite: str | None = None
    fichier: str | None = None    # chemin relatif à la racine du dépôt
    ligne_debut: int | None = None
    ligne_fin: int | None = None
    fonction: str | None = None
    extrait_code: str | None = None
    elements_preuve: str | None = None   # ce que l'outil a vu ET ce qu'il ne peut pas savoir
    outil: str = ""
    donnees_brutes: dict = field(default_factory=dict)


class AnalyseurCode(ABC):
    nom: str = ""
    technologies: frozenset[str] = frozenset()      # ex. {"php"}
    regles: frozenset[str] = frozenset()            # règles gérées

    @abstractmethod
    def analyser(self, racine: Path, dossiers: list[str], exclusions: list[str], regles_actives: set[str]) -> list[Constat]:
        """Analyse le code en LECTURE SEULE et retourne les constats."""
