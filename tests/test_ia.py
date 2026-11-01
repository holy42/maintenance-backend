import pytest

from app.ai.mock import MockClient
from app.ai.service import ServiceIA
from app.core.exceptions import IAIndisponible


class ClientInvalide:
    nom_modele = "faux"

    def generer_json(self, prompt):
        return '{"pas": "conforme"}'


def test_reponses_simulees_conformes_au_schema():
    ia = ServiceIA(MockClient())
    assert ia.diagnostiquer({"titre": "x"}).solutions
    assert ia.proposer_taches({}).taches
    assert ia.formuler_critere("Un utilisateur ne doit pas lire les messages d'un autre").categorie


def test_reponse_non_conforme_est_rejetee():
    with pytest.raises(IAIndisponible):
        ServiceIA(ClientInvalide()).diagnostiquer({})
