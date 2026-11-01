"""Point d'entrée de l'API. Lancement : uvicorn app.main:app --reload"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.api.routers import (
    administration, applications, auth, collaboration, criteres, fiabilite, problemes, suivi, taches, tests_validation,
    verifications,
)
from app.config import settings
from app.core.db_errors import traduire_erreur_regle
from app.core.exceptions import ErreurMetier
from app.services.verifications import marquer_verifications_interrompues

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:  # les vérifications interrompues par un redémarrage passent à « échouée »
        n = marquer_verifications_interrompues()
        if n:
            log.warning("%s vérification(s) interrompue(s) marquée(s) comme échouée(s).", n)
    except Exception:  # noqa: BLE001 - base indisponible au démarrage
        log.exception("Impossible de vérifier les vérifications interrompues.")
    yield


app = FastAPI(title="Plateforme de maintenance des applications : API", version="0.1.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(ErreurMetier)
async def erreur_metier(_: Request, exc: ErreurMetier):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(DBAPIError)
async def erreur_base(_: Request, exc: DBAPIError):
    """Les règles d'enchaînement du script SQL (déclencheurs) deviennent des erreurs 409 lisibles."""
    conflit = traduire_erreur_regle(exc)
    if conflit is not None:
        return JSONResponse(status_code=conflit.status_code, content={"detail": conflit.message})
    log.exception("Erreur de base de données")
    return JSONResponse(status_code=500, content={"detail": "Erreur interne de base de données."})


for module in (auth, administration, applications, criteres, verifications, problemes, taches, tests_validation,
               collaboration, suivi, fiabilite):
    app.include_router(module.router, prefix="/api/v1")


@app.get("/sante", tags=["Technique"])
def sante():
    return {"statut": "ok"}
