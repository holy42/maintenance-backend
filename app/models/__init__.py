"""Importer tous les modèles pour que les relations soient résolues."""
from app.models.acces import (  # noqa: F401
    Equipe, MembreEquipe, Permission, ReinitialisationMotDePasse, Role, RolePermission, Utilisateur,
)
from app.models.application import Application, ApplicationTechnologie, DepotGit, Technologie  # noqa: F401
from app.models.base import Base  # noqa: F401
from app.models.collaboration import (  # noqa: F401
    ConversationIA, MessageDiscussion, MessageIA, Mention, Note, Notification, PreferenceCanalNotification, PreferenceNotification,
    Salon, SalonLecture,
)
from app.models.historique import EvenementHistorique, HistoriqueStatut, Rapport  # noqa: F401
from app.models.probleme import (  # noqa: F401
    DecisionCorrection, DecisionSolution, Diagnostic, Probleme, RetourSolution, Solution,
)
from app.models.tache import CritereAcceptation, SousTache, Tache, TacheSolution  # noqa: F401
from app.models.validation import ResultatCritereAcceptation, SessionTest, TestCorrection  # noqa: F401
from app.models.verification import Critere, ResultatAnalyse, Verification, VerificationCritere  # noqa: F401
from app.models.fiabilite import EvaluationFiabilite, ModeleFiabiliteVersion  # noqa: F401
