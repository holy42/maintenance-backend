"""Règles d'enchaînement testables SANS base de données."""
from types import SimpleNamespace

import pytest

from app.core.exceptions import Conflit
from app.services import problemes, taches


def tache(statut, sous=()):
    return SimpleNamespace(statut=statut, sous_taches=[SimpleNamespace(statut=s) for s in sous])


def test_tache_ne_demarre_que_depuis_a_faire_ou_en_pause():
    taches._controler_transition(tache("a_faire"), "en_cours")
    taches._controler_transition(tache("en_pause"), "en_cours")
    with pytest.raises(Conflit):
        taches._controler_transition(tache("terminee"), "en_cours")


def test_tache_non_terminable_si_sous_tache_ouverte():
    with pytest.raises(Conflit):
        taches._controler_transition(tache("en_cours", ["terminee", "a_faire"]), "terminee")


def test_sous_taches_arretees_ne_bloquent_pas():
    taches._controler_transition(tache("en_cours", ["terminee", "arretee"]), "terminee")


def test_transitions_reservees_au_systeme():
    # « à tester », « testé » et « rouvert » (après test) ne peuvent pas être posés à la main
    for ancien, nouveau in (("en_cours", "a_tester"), ("a_tester", "teste"), ("a_tester", "rouvert")):
        assert nouveau not in problemes.TRANSITIONS_MANUELLES.get(ancien, set())
