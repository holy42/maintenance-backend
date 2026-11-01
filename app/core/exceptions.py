"""Exceptions métier, traduites en réponses HTTP dans main.py."""


class ErreurMetier(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NonTrouve(ErreurMetier):
    status_code = 404


class AccesRefuse(ErreurMetier):
    status_code = 403


class NonAuthentifie(ErreurMetier):
    status_code = 401


class Conflit(ErreurMetier):
    """Règle d'enchaînement non respectée (transition interdite, test impossible...)."""
    status_code = 409


class DonneesInvalides(ErreurMetier):
    status_code = 422


class IAIndisponible(ErreurMetier):
    """Le service d'IA est indisponible ou a renvoyé une réponse non conforme."""
    status_code = 503
