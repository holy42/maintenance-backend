import pytest

from app.analysis.secrets_filter import masquer_secrets
from app.core.exceptions import DonneesInvalides
from app.core.security import creer_jeton_acces, hacher_mot_de_passe, lire_jeton_acces, verifier_mot_de_passe
from app.services import git_service


def test_secrets_masques_avant_envoi_a_l_ia():
    texte, n = masquer_secrets("$password = 'abc123'; $url = 'postgresql://u:p@h/db';")
    assert "abc123" not in texte and "u:p@h" not in texte and n >= 2


def test_mot_de_passe_et_jeton():
    assert verifier_mot_de_passe("MotDePasse-2026", hacher_mot_de_passe("MotDePasse-2026"))
    assert lire_jeton_acces(creer_jeton_acces(42)) == 42


@pytest.mark.parametrize("nom", ["--upload-pack=x", "a b", "../x", ""])
def test_branches_invalides(nom):
    with pytest.raises(DonneesInvalides):
        git_service.valider_branche(nom)


def test_branches_valides():
    for nom in ("develop", "PB-1029", "feature/ajout-filtre"):
        assert git_service.valider_branche(nom) == nom
