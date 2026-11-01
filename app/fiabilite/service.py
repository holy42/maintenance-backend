"""Orchestration du modèle de fiabilité dans la plateforme : calcul des scores (étapes 3 et 6), enregistrement, étiquetage
(vérité terrain), constitution du jeu de données et entraînement depuis la base."""
from collections import Counter
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.analysis.base import Constat
from app.fiabilite import entrainement as en
from app.fiabilite.libelles import libelle
from app.fiabilite.metriques import sans_nan
from app.fiabilite.heuristique import modele_heuristique
from app.fiabilite.modeles import ModeleFiabilite
from app.fiabilite.niveaux import LIBELLES as LIBELLES_NIVEAU
from app.fiabilite.niveaux import niveau as calculer_niveau
from app.fiabilite.variables import NOMS, EntreeEtape3, EntreeEtape6, variables_etape3, variables_etape6
from app.models import (
    Critere, DecisionCorrection, DecisionSolution, Diagnostic, EvaluationFiabilite, ModeleFiabiliteVersion, Probleme, ResultatAnalyse,
    Solution, Verification,
)
from app.ai.schemas import DiagnosticIA
from app.schemas.fiabilite import FacteurOut, FiabiliteOut


def _maintenant():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


class ServiceFiabilite:
    def __init__(self, db: Session):
        self.db = db
        self._cache: dict[int, tuple[ModeleFiabilite, int | None, str]] = {}

    # ---------- modèle actif ----------

    def modele(self, etape: int) -> tuple[ModeleFiabilite, int | None, str]:
        """(modèle, id de version, source). Sans modèle entraîné et activé : score de départ par règles (NON appris)."""
        if etape not in self._cache:
            v = self.db.execute(select(ModeleFiabiliteVersion).where(ModeleFiabiliteVersion.etape == etape, ModeleFiabiliteVersion.actif.is_(True))).scalar_one_or_none()
            self._cache[etape] = (ModeleFiabilite.from_dict(v.parametres), v.id, "modele") if v else (modele_heuristique(etape), None, "heuristique")
        return self._cache[etape]

    def _enregistrer(self, etape: int, cible_type: str, cible_id: int, application_id: int, variables: dict[str, float]) -> EvaluationFiabilite:
        modele, modele_id, source = self.modele(etape)
        score = modele.predire(variables)
        ev = EvaluationFiabilite(
            etape=etape, cible_type=cible_type, cible_id=cible_id, application_id=application_id, modele_id=modele_id, source=source,
            score=round(score, 3), niveau=calculer_niveau(score, modele.seuils), variables=variables, explication=modele.expliquer(variables),
        )
        self.db.add(ev)
        return ev

    # ---------- étape 3 : preuves de l'analyse de code ----------

    def taux_confirmation_regle(self, regle: str | None, exclure_resultat_id: int | None = None) -> float:
        """Part des résultats de cette règle confirmés par un humain (lissée). Calculé SANS l'exemple évalué."""
        if not regle:
            return 0.5
        q = (select(ResultatAnalyse.statut_validation, func.count()).join(Critere, Critere.id == ResultatAnalyse.critere_id)
             .where(Critere.formulation_structuree["regle"].astext == regle, ResultatAnalyse.statut_validation.in_(("confirme", "ecarte"))))
        if exclure_resultat_id:
            q = q.where(ResultatAnalyse.id != exclure_resultat_id)
        compte = dict(self.db.execute(q.group_by(ResultatAnalyse.statut_validation)).all())
        c, e = compte.get("confirme", 0), compte.get("ecarte", 0)
        return (c + 1) / (c + e + 2)

    def evaluer_resultats(self, verification: Verification, paires: Sequence[tuple[ResultatAnalyse, Constat]]) -> None:
        """Étape 3 : un score de fiabilité pour chaque résultat de l'outil d'analyse d'une vérification."""
        par_fichier = Counter((c.fichier, c.regle) for _, c in paires)
        par_verif = Counter(c.regle for _, c in paires)
        taux: dict[str | None, float] = {}
        for r, c in paires:
            if c.regle not in taux:
                taux[c.regle] = self.taux_confirmation_regle(c.regle)
            entree = EntreeEtape3(categorie=c.categorie, gravite=c.gravite, regle=c.regle, fichier=c.fichier, extrait=c.extrait_code,
                                  nb_meme_regle_fichier=par_fichier[(c.fichier, c.regle)], nb_meme_regle_verification=par_verif[c.regle],
                                  taux_confirmation_regle=taux[c.regle])
            self._enregistrer(3, "resultat", r.id, verification.application_id, variables_etape3(entree))

    # ---------- présentation (API) ----------

    @staticmethod
    def sortie(ev: EvaluationFiabilite) -> FiabiliteOut:
        """Évaluation -> contrat de l'API, avec des facteurs lisibles. `appris` est faux pour le score de départ par règles."""
        return FiabiliteOut(
            etape=ev.etape, score=float(ev.score), pourcentage=round(float(ev.score) * 100), niveau=ev.niveau,
            libelle_niveau=LIBELLES_NIVEAU.get(ev.niveau, ev.niveau), source=ev.source, appris=ev.source == "modele", modele_id=ev.modele_id,
            facteurs=[FacteurOut(variable=f["variable"], libelle=libelle(f["variable"]), effet=float(f["effet"]), sens=f["sens"])
                      for f in (ev.explication or [])],
            etiquette=ev.etiquette,
        )

    def annoter_resultats(self, resultats: Sequence[ResultatAnalyse]) -> None:
        """Ajoute `fiabilite` (étape 3) à chaque résultat avant sa sérialisation. Un seul accès à la base pour toute la liste."""
        evs = self.evaluations("resultat", [r.id for r in resultats])
        for r in resultats:
            r.fiabilite = self.sortie(evs[r.id]) if r.id in evs else None

    def annoter_problemes(self, problemes: Sequence[Probleme]) -> None:
        """Ajoute `fiabilite_preuve` : fiabilité de la preuve (étape 3) du résultat d'origine du problème."""
        evs = self.evaluations("resultat", [p.resultat_id for p in problemes if p.resultat_id])
        for p in problemes:
            p.fiabilite_preuve = self.sortie(evs[p.resultat_id]) if p.resultat_id in evs else None

    def annoter_diagnostics(self, diagnostics: Sequence[Diagnostic]) -> None:
        """Ajoute `fiabilite` (étape 6) à chaque solution de Gemini."""
        solutions = [s for d in diagnostics for s in d.solutions]
        evs = self.evaluations("solution", [s.id for s in solutions])
        for s in solutions:
            s.fiabilite = self.sortie(evs[s.id]) if s.id in evs else None

    def derniere_evaluation(self, cible_type: str, cible_id: int) -> EvaluationFiabilite | None:
        return self.db.execute(select(EvaluationFiabilite).where(EvaluationFiabilite.cible_type == cible_type, EvaluationFiabilite.cible_id == cible_id)
                               .order_by(EvaluationFiabilite.cree_le.desc(), EvaluationFiabilite.id.desc())).scalars().first()

    def evaluations(self, cible_type: str, ids: Sequence[int]) -> dict[int, EvaluationFiabilite]:
        """Dernière évaluation de chaque cible (pour l'affichage de listes)."""
        if not ids:
            return {}
        lignes = self.db.execute(select(EvaluationFiabilite).where(EvaluationFiabilite.cible_type == cible_type, EvaluationFiabilite.cible_id.in_(ids))
                                 .order_by(EvaluationFiabilite.id)).scalars()
        return {e.cible_id: e for e in lignes}      # l'ordre croissant fait gagner la plus récente

    def preuve_du_probleme(self, p: Probleme) -> EvaluationFiabilite | None:
        return self.derniere_evaluation("resultat", p.resultat_id) if p.resultat_id else None

    # ---------- étape 6 : solutions de Gemini ----------

    def evaluer_solution(self, solution: Solution, diagnostic: Diagnostic, probleme: Probleme, reponse: DiagnosticIA,
                         preuve: EvaluationFiabilite | None, reference_valide: bool | None = None, syntaxe_valide: bool | None = None) -> EvaluationFiabilite:
        entree = EntreeEtape6(
            explication=diagnostic.explication, causes=reponse.causes_probables, confiance_declaree=reponse.niveau_confiance,
            incertitudes=reponse.incertitudes, description=solution.description, extrait_code=solution.extrait_code, risques=solution.risques,
            tests_suggeres=solution.tests_suggeres, fiabilite_preuve=float(preuve.score) if preuve else None, categorie=probleme.categorie,
            gravite=probleme.gravite, reference_valide=reference_valide, syntaxe_valide=syntaxe_valide,
        )
        return self._enregistrer(6, "solution", solution.id, probleme.application_id, variables_etape6(entree))

    # ---------- vérité terrain ----------

    def etiqueter_resultat(self, resultat_id: int, reel: bool) -> None:
        """Décision humaine : résultat confirmé (réel) ou écarté (faux positif)."""
        self.db.execute(update(EvaluationFiabilite).where(EvaluationFiabilite.cible_type == "resultat", EvaluationFiabilite.cible_id == resultat_id)
                        .values(etiquette=reel, etiquette_le=_maintenant()))

    def etiqueter_solutions(self, decision: DecisionCorrection, valide: bool) -> None:
        """Retour du testeur sur une solution de l'IA retenue TELLE QUELLE (les solutions adaptées ne sont pas étiquetées : la correction
        testée n'est plus celle qui a été évaluée). Seul le PREMIER passage compte, pour ne pas biaiser les étiquettes."""
        if decision.type_decision != "ia_retenue":
            return
        ids = list(self.db.execute(select(DecisionSolution.solution_id).where(DecisionSolution.decision_id == decision.id)).scalars())
        if ids:
            self.db.execute(update(EvaluationFiabilite).where(EvaluationFiabilite.cible_type == "solution", EvaluationFiabilite.cible_id.in_(ids),
                                                              EvaluationFiabilite.etiquette.is_(None)).values(etiquette=valide, etiquette_le=_maintenant()))

    # ---------- jeu de données et entraînement ----------

    def jeu_de_donnees(self, etape: int) -> tuple[list[str], list[list[float]], list[int]]:
        """Exemples étiquetés (variables telles qu'elles étaient au moment du calcul du score)."""
        noms = NOMS[etape]
        lignes = self.db.execute(select(EvaluationFiabilite).where(EvaluationFiabilite.etape == etape, EvaluationFiabilite.etiquette.is_not(None))
                                 .order_by(EvaluationFiabilite.id)).scalars().all()
        dernier: dict[int, EvaluationFiabilite] = {l.cible_id: l for l in lignes}          # une ligne par cible (la plus récente)
        X = [[float(l.variables.get(n, 0.0)) for n in noms] for l in dernier.values()]
        return noms, X, [int(l.etiquette) for l in dernier.values()]

    def apercu(self, etape: int) -> dict:
        _, X, y = self.jeu_de_donnees(etape)
        return {"etape": etape, "exemples_etiquetes": len(y), "reels": sum(y), "faux": len(y) - sum(y), "minimum_requis": en.MIN_EXEMPLES,
                "minimum_par_classe": en.MIN_PAR_CLASSE}

    def entrainer(self, etape: int, utilisateur_id: int, algorithme: str = "auto") -> ModeleFiabiliteVersion:
        """Entraîne une NOUVELLE version à partir des exemples étiquetés. Elle reste inactive jusqu'à activation par un administrateur."""
        noms, X, y = self.jeu_de_donnees(etape)
        comparaison = en.comparer(X, y)                  # ValueError si jeu insuffisant
        choisi = comparaison["recommande"] if algorithme == "auto" else algorithme
        if choisi == "constant":
            raise ValueError("Les variables n'apportent rien par rapport à une prédiction constante : entraînement refusé.")
        modele = en.entrainer_final(etape, noms, X, y, choisi)
        modele.metriques["comparaison"] = comparaison
        modele.metriques = sans_nan(modele.metriques)        # JSONB et JSON de l'API refusent NaN
        version = (self.db.scalar(select(func.max(ModeleFiabiliteVersion.version)).where(ModeleFiabiliteVersion.etape == etape)) or 0) + 1
        v = ModeleFiabiliteVersion(etape=etape, version=version, algorithme=choisi, nb_exemples=len(y), metriques=modele.metriques,
                                   parametres=sans_nan(modele.to_dict()), actif=False, entraine_par=utilisateur_id)
        self.db.add(v)
        self.db.flush()
        return v

    def activer(self, version_id: int) -> ModeleFiabiliteVersion:
        v = self.db.get(ModeleFiabiliteVersion, version_id)
        if v is None:
            raise LookupError("Version introuvable.")
        self.db.execute(update(ModeleFiabiliteVersion).where(ModeleFiabiliteVersion.etape == v.etape, ModeleFiabiliteVersion.actif.is_(True)).values(actif=False))
        v.actif = True
        self.db.flush()
        return v
