"""Les règles d'enchaînement du script SQL (déclencheurs) lèvent des RAISE EXCEPTION (SQLSTATE P0001).
On les traduit en erreur 409 lisible."""
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import Conflit


def traduire_erreur_regle(exc: DBAPIError) -> Conflit | None:
    orig = getattr(exc, "orig", None)
    if getattr(orig, "pgcode", None) == "P0001":
        diag = getattr(orig, "diag", None)
        message = getattr(diag, "message_primary", None) or str(orig).splitlines()[0]
        return Conflit(message)
    return None
