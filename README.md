# Backend : plateforme de maintenance multi-applications

API REST (FastAPI + SQLAlchemy + PostgreSQL). **Squelette généré mais non exécuté** : aucune dépendance n'était
installable dans l'environnement de génération. Le code a seulement été vérifié statiquement (syntaxe et imports
internes). Les tests et la mise en route sont à faire dans votre environnement.

## À télécharger / installer vous-même

| Quoi | Pourquoi |
|---|---|
| Python 3.11 ou supérieur | le code utilise `StrEnum` et la syntaxe de types récente |
| PostgreSQL 12 ou supérieur | le script SQL utilise des colonnes générées et des déclencheurs |
| Git (en ligne de commande) | lecture des dépôts analysés (clone, fetch, lecture seule) |
| Les paquets de `requirements.txt` | `pip install -r requirements.txt` (versions à figer ensuite avec `pip freeze`) |
| Un compte et une clé API Gemini | uniquement si `AI_PROVIDER=gemini` ; sinon le mode `mock` suffit au développement |
| Un serveur SMTP de test (facultatif) | « mot de passe oublié » ; sans lui, le lien est écrit dans les journaux |
| Un client PostgreSQL (pgAdmin, DBeaver...) | consulter la base (facultatif) |

## Mise en route

```bash
python -m venv .venv && source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                      # puis renseigner SECRET_KEY, ENCRYPTION_KEY, DATABASE_URL

createdb maintenance                                      # ou via votre client PostgreSQL
alembic upgrade head                                      # exécute sql/schema_base_de_donnees.sql
python -m app.jobs.seed --admin aina --criteres-standard  # administrateur + critères standards (mot de passe demandé)

uvicorn app.main:app --reload                             # documentation interactive : http://localhost:8000/docs
pytest                                                    # tests sans base ; avec base : TEST_DATABASE_URL=... pytest
```

Ensuite, via l'API : créer une équipe, attribuer des rôles (`/api/v1/equipes/{id}/membres`), créer une application,
configurer son dépôt, ajouter ses technologies (`php`), puis lancer une vérification.

## Échéances (cron)

```
0 7 * * *  cd /chemin/backend && .venv/bin/python -m app.jobs.echeances
```
Sous Windows : Planificateur de tâches. Une notification au plus par destinataire, par élément et par jour.

## Organisation (n-tiers)

```
app/
  main.py               application FastAPI, gestion des erreurs, routes
  config.py database.py réglages (.env) et session SQLAlchemy
  api/                  PRÉSENTATION / RESTITUTION : routes, dépendances, chargement + contrôle d'accès
    routers/            auth, administration, applications, criteres, verifications, problemes, taches,
                        tests_validation, collaboration, suivi (notifications, historique, rapports)
  services/             logique métier : problèmes, tâches, tests, vérifications, critères, diagnostics, rapports...
  analysis/             COUCHE ANALYSE : interface d'adaptateurs, registre, tree-sitter PHP, masquage des secrets
  ai/                   MODULE IA : client Gemini/mock, prompts, schémas stricts, service
  models/               COUCHE DONNÉES : modèles SQLAlchemy (tables du script SQL)
  schemas/              contrats de l'API (Pydantic)
  core/                 sécurité, permissions, énumérations, exceptions, chiffrement
  jobs/                 échéances (cron), données initiales
sql/schema_base_de_donnees.sql   source de vérité de la base (tables, vues, déclencheurs)
alembic/                migration 0001 = exécution du script SQL
tests/
```

## Où sont appliquées les règles

| Règle | Où |
|---|---|
| Permissions par rôle d'équipe, cloisonnement par équipe | serveur (`core/permissions.py`, `api/helpers.py`) à chaque requête |
| Une tâche ne se termine que si ses sous-tâches le sont ; transitions des tâches | service **et** déclencheur SQL |
| Test seulement si toutes les tâches sont terminées (arrêtées ignorées) et une tâche terminée depuis la réouverture | service **et** déclencheur SQL |
| Un testeur ne teste pas sa propre correction ; un seul passage actif par test | déclencheur SQL / index unique |
| Historique en ajout seul | déclencheurs SQL |
| Notes et messages : modifiables/supprimables par leur seul auteur ; salons supprimés par le chef de projet | services (suppression logique, contenu conservé dans l'historique) |
| L'IA propose, ne modifie jamais le code ; réponses validées par schéma strict ; IA en panne = 503 sans bloquer le reste | `ai/`, `services/` |
| Secrets masqués avant envoi à l'IA ; clé API et jeton Git côté serveur uniquement | `analysis/secrets_filter.py`, `core/crypto.py` |

## Modèle de fiabilité (IA hybride)

Un modèle simple, développé et entraîné dans ce projet, qui **mesure seulement la fiabilité** des réponses des autres outils : il ne
détecte ni ne diagnostique rien. Un même code, entraîné séparément pour chaque étape :

| Étape | Question posée | Vérité terrain |
|---|---|---|
| 3 : preuves de l'analyse de code | l'anomalie détectée est-elle réelle ? | décision humaine (confirmer / écarter) |
| 6 : solutions de Gemini | la solution sera-t-elle validée au test ? | premier retour du testeur (solution retenue telle quelle) |

- Code : `app/fiabilite/` (variables, régression logistique, forêt aléatoire, calibration, métriques, entraînement, contrôles, service).
- Tant qu'aucune version n'est activée (page d'administration « Modèle de fiabilité »), un score de départ **par règles, non appris** est utilisé.
- Minimum pour entraîner : 150 exemples étiquetés, dont 30 de chaque classe (`app/fiabilite/entrainement.py`).
- Base : tables `modele_fiabilite` et `evaluation_fiabilite`, colonne `diagnostic.verifications_recommandees`. Base déjà créée : `alembic upgrade head`
  (la révision 0002 est idempotente).
- Les « vérifications recommandées » sont rédigées par Gemini puis contrôlées par des règles (`app/fiabilite/verifications.py`).

```bash
pytest tests/test_fiabilite.py tests/test_fiabilite_integration.py                     # sans base ni bibliothèque externe (sauf pydantic)
python -m app.fiabilite.cli synthetique --etape 3 --n 300 --sortie /tmp/e3.csv         # données FICTIVES : tester le code seulement
python -m app.fiabilite.cli comparer --etape 3 --csv donnees_etape3.csv [--sklearn]    # validation croisée de tous les modèles
python -m app.fiabilite.cli entrainer --etape 3 --csv donnees_etape3.csv --algo auto --sortie var/modeles/etape3.json --test 0.3
```
Aucun résultat obtenu sur les données fictives ne doit figurer dans le mémoire.

Limites connues : un contrôle de syntaxe PHP d'un extrait coupé en plein bloc peut échouer à tort ; seules les solutions retenues telles quelles sont
étiquetées (biais de sélection) ; les seuils de niveau (0,40 et 0,70) ne sont pas encore ajustés sur des données réelles.

## Limites connues et points à décider

- **Non exécuté** : à tester d'abord avec `pytest`, puis `alembic upgrade head` sur une base vide. Points à surveiller :
  colonne générée `probleme.code`, API de `tree-sitter-php` (noms de nœuds selon la version installée), format de
  requête Gemini et nom du modèle (à confirmer dans la documentation officielle).
- **Périmètre d'analyse par défaut** : les dossiers à analyser/exclure ne sont pas stockés dans la base (aucune colonne
  dans le schéma) ; ils sont fournis à chaque vérification. À ajouter au schéma si vous voulez un paramètre d'application.
- **Transitions des statuts d'un problème** : proposition dans `services/problemes.py` (`TRANSITIONS_MANUELLES`), non validée.
- **Exécution en arrière-plan** : `BackgroundTasks` de FastAPI, dans le même processus. Un redémarrage interrompt la
  vérification (marquée « échouée » au démarrage suivant). Une file de tâches serait nécessaire pour plus de robustesse.
- **Exécution des analyses** : directement sur le serveur, sans isolation (conteneur) : à décider avant d'analyser du
  code non maîtrisé.
- **Pas de limitation de débit** sur la connexion et « mot de passe oublié » : à ajouter avant toute exposition publique.
- **Rapports** : la période ne filtre que les comptages directs ; les indicateurs IA et tests sont cumulés.
- **Multi-technologies** : seul l'adaptateur PHP (tree-sitter) existe ; ajouter une technologie = un adaptateur dans
  `analysis/` + son enregistrement dans `analysis/registry.py`.
- **Critères standards** : liés à une règle d'analyse par `formulation_structuree = {"regle": "php.syntaxe"}`.
