-- =====================================================================
-- SCHÉMA COMPLET DE LA BASE DE DONNÉES (PostgreSQL 12 ou supérieur)
-- PROPOSITION DE CONCEPTION : script non exécuté ni testé sur un serveur.
--
-- Chaîne métier :
--   Vérification -> Résultat d'analyse -> Problème -> Diagnostic -> Solution
--   -> Décision de correction -> Tâche(s) -> Sous-tâche(s)
--   -> Test (un seul par problème) -> Passages de test (validé / non validé)
--
-- Principes appliqués dans ce script :
--   * le code source n'est jamais modifié : les solutions ne sont que des extraits ;
--   * un problème peut avoir une ou plusieurs tâches ;
--   * le test n'est possible que si les tâches du problème sont terminées ;
--   * un test non validé fait passer le problème à « rouvert » ;
--   * l'historique est en ajout seul ;
--   * l'accès se règle par équipe (une application appartient à une équipe).
--
-- Ordre d'exécution : sections 1 à 13, dans l'ordre.
-- =====================================================================


-- ---------- 1. Accès, équipes, rôles, permissions --------------------

CREATE TABLE utilisateur (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    identifiant       VARCHAR(100) NOT NULL UNIQUE,
    email             VARCHAR(255) UNIQUE,
    mot_de_passe_hash VARCHAR(255) NOT NULL,
    est_admin         BOOLEAN NOT NULL DEFAULT FALSE,   -- administrateur de la plateforme
    actif             BOOLEAN NOT NULL DEFAULT TRUE,    -- on désactive, on ne supprime pas
    cree_le           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- « Mot de passe oublié » : seul cas d'envoi d'e-mail du prototype.
-- Seul le hachage du jeton est conservé.
CREATE TABLE reinitialisation_mot_de_passe (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    utilisateur_id BIGINT NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    jeton_hash     VARCHAR(255) NOT NULL UNIQUE,
    expire_le      TIMESTAMPTZ NOT NULL,
    utilise_le     TIMESTAMPTZ,
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE equipe (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom         VARCHAR(150) NOT NULL UNIQUE,
    description TEXT,
    cree_le     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE permission (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        VARCHAR(80) NOT NULL UNIQUE,   -- ex. probleme.modifier
    description TEXT
);

CREATE TABLE role (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom         VARCHAR(80) NOT NULL UNIQUE,   -- developpeur, testeur, chef_projet
    description TEXT
);

CREATE TABLE role_permission (
    role_id       BIGINT NOT NULL REFERENCES role(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES permission(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- Rôle d'un utilisateur DANS une équipe. Un utilisateur peut appartenir à plusieurs
-- équipes, donc avoir accès aux applications de toutes ces équipes.
CREATE TABLE membre_equipe (
    equipe_id      BIGINT NOT NULL REFERENCES equipe(id) ON DELETE CASCADE,
    utilisateur_id BIGINT NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    role_id        BIGINT NOT NULL REFERENCES role(id),
    attribue_par   BIGINT REFERENCES utilisateur(id),   -- l'administrateur
    attribue_le    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (equipe_id, utilisateur_id)
);


-- ---------- 2. Applications et dépôt ---------------------------------

CREATE TABLE application (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    equipe_id   BIGINT NOT NULL REFERENCES equipe(id),
    nom         VARCHAR(150) NOT NULL,
    description TEXT,
    statut      VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (statut IN ('active','en_maintenance','archivee')),
    responsable_id BIGINT REFERENCES utilisateur(id),
    cree_le     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (equipe_id, nom)
);

CREATE TABLE technologie (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom       VARCHAR(80) NOT NULL,           -- ex. PHP, JavaScript, SQL
    framework VARCHAR(80),                    -- ex. CodeIgniter 4
    UNIQUE (nom, framework)
);

CREATE TABLE application_technologie (
    application_id BIGINT NOT NULL REFERENCES application(id) ON DELETE CASCADE,
    technologie_id BIGINT NOT NULL REFERENCES technologie(id),
    PRIMARY KEY (application_id, technologie_id)
);

-- Un seul dépôt par application. Accès en lecture seule : la plateforme n'écrit jamais
-- dans le dépôt. Le jeton est chiffré et n'est jamais réaffiché.
CREATE TABLE depot_git (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id      BIGINT NOT NULL UNIQUE REFERENCES application(id) ON DELETE CASCADE,
    url                 VARCHAR(500) NOT NULL,
    branche_defaut      VARCHAR(100) NOT NULL DEFAULT 'develop',
    jeton_acces_chiffre TEXT,
    derniere_synchro_le TIMESTAMPTZ
);


-- ---------- 3. Critères et vérifications -----------------------------

CREATE TABLE critere (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT REFERENCES application(id) ON DELETE CASCADE, -- NULL = critère standard
    createur_id    BIGINT REFERENCES utilisateur(id),
    nom            VARCHAR(150) NOT NULL,
    description    TEXT NOT NULL,                 -- texte en langage naturel
    formulation_structuree JSONB,                 -- proposée par l'IA, validée par l'humain
    origine        VARCHAR(20) NOT NULL CHECK (origine IN ('standard','personnalisee')),
    categorie      VARCHAR(30) NOT NULL
                   CHECK (categorie IN ('erreur_technique','fonctionnel','nouvelle_fonctionnalite',
                                        'regression','securite','propre_application')),
    automatisabilite VARCHAR(20) NOT NULL DEFAULT 'a_determiner'
                   CHECK (automatisabilite IN ('automatisable','partielle','humaine','a_determiner')),
    mode_verification VARCHAR(30)
                   CHECK (mode_verification IN ('test_auto','regle_statique','assistee_ia','manuelle')),
    statut         VARCHAR(20) NOT NULL DEFAULT 'brouillon'
                   CHECK (statut IN ('brouillon','valide','actif','inactif','obsolete')),
    valide_par     BIGINT REFERENCES utilisateur(id),
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Un critère personnalisé doit être validé avant d'être actif.
    CHECK (statut NOT IN ('valide','actif') OR origine = 'standard' OR valide_par IS NOT NULL)
);

-- Version analysée = dernier commit de la branche choisie : develop par défaut, ou la
-- branche d'un problème rouvert (nommée d'après son code, ex. PB-1029).
-- Pas de comparaison entre versions dans le prototype.
CREATE TABLE verification (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES application(id),
    depot_id       BIGINT REFERENCES depot_git(id),
    branche        VARCHAR(100) NOT NULL DEFAULT 'develop',
    commit_analyse VARCHAR(64),
    perimetre      TEXT,
    declenchee_par BIGINT NOT NULL REFERENCES utilisateur(id),
    type           VARCHAR(20) NOT NULL DEFAULT 'a_la_demande' CHECK (type = 'a_la_demande'),
    statut         VARCHAR(20) NOT NULL DEFAULT 'en_attente'
                   CHECK (statut IN ('en_attente','en_cours','terminee','echouee')),
    motif_echec    TEXT,
    avec_interpretation_ia BOOLEAN NOT NULL DEFAULT TRUE,
    resultat_global VARCHAR(30),
    debut_le       TIMESTAMPTZ NOT NULL DEFAULT now(),
    fin_le         TIMESTAMPTZ,
    UNIQUE (id, application_id)
);

CREATE TABLE verification_critere (
    verification_id BIGINT NOT NULL REFERENCES verification(id) ON DELETE CASCADE,
    critere_id      BIGINT NOT NULL REFERENCES critere(id),
    PRIMARY KEY (verification_id, critere_id)
);


-- ---------- 4. Résultats, problèmes, diagnostics, solutions ----------

-- Trace brute : distingue outil, IA et humain.
CREATE TABLE resultat_analyse (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    verification_id BIGINT NOT NULL REFERENCES verification(id) ON DELETE CASCADE,
    critere_id      BIGINT REFERENCES critere(id),
    source          VARCHAR(10) NOT NULL CHECK (source IN ('outil','ia','humain')),
    outil           VARCHAR(80),
    categorie       VARCHAR(30) NOT NULL
                    CHECK (categorie IN ('erreur_technique','fonctionnel','nouvelle_fonctionnalite',
                                         'regression','securite','propre_application')),
    gravite         VARCHAR(10) CHECK (gravite IN ('critique','elevee','moyenne','faible')),
    fichier         VARCHAR(500),
    ligne_debut     INT,
    ligne_fin       INT,
    fonction        VARCHAR(200),
    extrait_code    TEXT,
    message         TEXT NOT NULL,
    elements_preuve TEXT,
    donnees_brutes  JSONB,
    statut_validation VARCHAR(20) NOT NULL DEFAULT 'non_valide'
                    CHECK (statut_validation IN ('non_valide','confirme','ecarte')),
    decide_par      BIGINT REFERENCES utilisateur(id),
    motif_decision  TEXT,
    decide_le       TIMESTAMPTZ,
    cree_le         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Statuts : nouveau, a_analyser, confirme, faux_positif, en_cours, a_tester, teste,
-- termine, rouvert. Les transitions entre statuts du problème sont contrôlées côté serveur.
-- Après « rouvert », la branche de correction porte le code du problème comme nom (ex. PB-1029).
CREATE TABLE probleme (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code             VARCHAR(20) GENERATED ALWAYS AS ('PB-' || id::text) STORED UNIQUE,
    application_id   BIGINT NOT NULL REFERENCES application(id),
    resultat_id      BIGINT REFERENCES resultat_analyse(id),   -- NULL si créé manuellement
    verification_id  BIGINT,
    critere_id       BIGINT REFERENCES critere(id),
    source           VARCHAR(10) NOT NULL CHECK (source IN ('outil','ia','humain')),
    titre            VARCHAR(255) NOT NULL,
    description      TEXT,
    comportement_attendu TEXT,
    comportement_observe TEXT,
    categorie        VARCHAR(30) NOT NULL
                     CHECK (categorie IN ('erreur_technique','fonctionnel','nouvelle_fonctionnalite',
                                          'regression','securite','propre_application')),
    gravite          VARCHAR(10) CHECK (gravite IN ('critique','elevee','moyenne','faible')),
    priorite         VARCHAR(10) CHECK (priorite IN ('urgente','haute','normale','basse')),
    statut           VARCHAR(20) NOT NULL DEFAULT 'nouveau'
                     CHECK (statut IN ('nouveau','a_analyser','confirme','faux_positif',
                                       'en_cours','a_tester','teste','termine','rouvert')),
    fichier          VARCHAR(500),
    ligne_debut      INT,
    ligne_fin        INT,
    fonction         VARCHAR(200),
    extrait_code     TEXT,
    niveau_confiance NUMERIC(3,2) CHECK (niveau_confiance BETWEEN 0 AND 1),
    responsable_id   BIGINT REFERENCES utilisateur(id),
    cree_par         BIGINT REFERENCES utilisateur(id),
    echeance         DATE,
    cree_le          TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, application_id),
    -- La vérification d'origine doit appartenir à la même application :
    FOREIGN KEY (verification_id, application_id) REFERENCES verification(id, application_id)
);

-- Un nouveau diagnostic n'écrase jamais l'ancien.
CREATE TABLE diagnostic (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    probleme_id      BIGINT NOT NULL REFERENCES probleme(id) ON DELETE CASCADE,
    explication      TEXT NOT NULL,
    causes_probables JSONB,
    niveau_confiance NUMERIC(3,2) CHECK (niveau_confiance BETWEEN 0 AND 1),
    incertitudes     TEXT,                        -- « ce que l'IA ne sait pas »
    verifications_recommandees JSONB,             -- rédigées par l'IA puis CONTRÔLÉES (voir fiabilite/verifications.py)
    branche_analysee VARCHAR(100),                -- develop, ou branche du problème rouvert
    commit_reference VARCHAR(64),                 -- version du code analysée
    modele_ia        VARCHAR(80),
    version_prompt   VARCHAR(40),
    cree_le          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Proposition avec extrait de code séparé : jamais appliqué au dépôt.
CREATE TABLE solution (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    diagnostic_id    BIGINT NOT NULL REFERENCES diagnostic(id) ON DELETE CASCADE,
    description      TEXT NOT NULL,
    extrait_code     TEXT,
    format_code      VARCHAR(20) DEFAULT 'extrait' CHECK (format_code IN ('extrait','diff')),
    risques          TEXT,
    tests_suggeres   TEXT,
    commit_reference VARCHAR(64),
    cree_le          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Évalue UNE solution de l'IA (utilité perçue par le développeur).
-- La réussite de la correction vient du testeur (session_test), jamais d'ici.
CREATE TABLE retour_solution (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    solution_id      BIGINT NOT NULL REFERENCES solution(id) ON DELETE CASCADE,
    utilisateur_id   BIGINT NOT NULL REFERENCES utilisateur(id),
    utilite_percue   VARCHAR(20) NOT NULL
                     CHECK (utilite_percue IN ('utile','partiellement_utile','ignoree',
                                               'autre_appliquee','incorrecte','non_traitee')),
    commentaire      TEXT,
    commit_associe   VARCHAR(64),
    cree_le          TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ---------- 5. Tâches, sous-tâches, critères d'acceptation -----------

-- Un problème peut avoir une ou plusieurs tâches (l'IA peut en proposer plusieurs ;
-- après « rouvert », de nouvelles tâches sont créées). Création à l'initiative de
-- l'utilisateur. Transitions contrôlées par le déclencheur de la section 10.
CREATE TABLE tache (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    probleme_id      BIGINT NOT NULL,
    application_id   BIGINT NOT NULL REFERENCES application(id),
    titre            VARCHAR(255) NOT NULL,
    description      TEXT,
    origine          VARCHAR(15) NOT NULL DEFAULT 'utilisateur'
                     CHECK (origine IN ('ia','utilisateur')),   -- proposée par l'IA puis retenue, ou saisie
    duree_estimee_h  NUMERIC(6,1),          -- indication de l'IA, modifiable
    statut           VARCHAR(20) NOT NULL DEFAULT 'a_faire'
                     CHECK (statut IN ('a_faire','en_cours','en_pause','arretee','terminee')),
    responsable_id   BIGINT REFERENCES utilisateur(id),
    cree_par         BIGINT NOT NULL REFERENCES utilisateur(id),
    echeance         DATE,
    cree_le          TIMESTAMPTZ NOT NULL DEFAULT now(),
    debut_le         TIMESTAMPTZ,
    fin_le           TIMESTAMPTZ,
    UNIQUE (id, application_id),
    FOREIGN KEY (probleme_id, application_id) REFERENCES probleme(id, application_id)
);

CREATE TABLE sous_tache (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tache_id    BIGINT NOT NULL REFERENCES tache(id) ON DELETE CASCADE,
    titre       VARCHAR(255) NOT NULL,
    description TEXT,
    statut      VARCHAR(20) NOT NULL DEFAULT 'a_faire'
                CHECK (statut IN ('a_faire','en_cours','en_pause','arretee','terminee')),
    ordre       INT NOT NULL,
    origine     VARCHAR(15) NOT NULL CHECK (origine IN ('ia','utilisateur')),
    UNIQUE (tache_id, ordre)
);

CREATE TABLE critere_acceptation (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tache_id  BIGINT NOT NULL REFERENCES tache(id) ON DELETE CASCADE,
    texte     TEXT NOT NULL,
    ordre     INT NOT NULL,
    origine   VARCHAR(15) NOT NULL CHECK (origine IN ('ia','utilisateur')),
    UNIQUE (tache_id, ordre)
);

-- Une tâche peut s'appuyer sur plusieurs solutions de l'IA. Aucune ligne = tâche issue
-- de la solution propre du développeur.
-- Règle serveur : les solutions liées doivent appartenir au même problème que la tâche.
CREATE TABLE tache_solution (
    tache_id    BIGINT NOT NULL REFERENCES tache(id) ON DELETE CASCADE,
    solution_id BIGINT NOT NULL REFERENCES solution(id),
    ajoute_par  BIGINT REFERENCES utilisateur(id),
    ajoute_le   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tache_id, solution_id)
);


-- ---------- 6. Décision de correction, test, passages de test --------

-- Le développeur retient, adapte ou non les solutions de l'IA, ou prend sa propre voie.
-- Plusieurs décisions successives possibles : la plus récente fait foi.
CREATE TABLE decision_correction (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    probleme_id     BIGINT NOT NULL REFERENCES probleme(id) ON DELETE CASCADE,
    developpeur_id  BIGINT NOT NULL REFERENCES utilisateur(id),
    type_decision   VARCHAR(20) NOT NULL
                    CHECK (type_decision IN ('ia_retenue','ia_adaptee','autre_solution','sans_ia')),
    description_alternative TEXT,
    extrait_code_alternatif TEXT,
    justification   TEXT,                       -- facultative
    motif_non_utilisation VARCHAR(20)           -- facultatif, prédéfini
                    CHECK (motif_non_utilisation IN ('pas_utile','fausse','autre_trouvee')),
    commit_associe  VARCHAR(64),
    pull_request    VARCHAR(255),
    cree_le         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (type_decision NOT IN ('autre_solution','sans_ia') OR description_alternative IS NOT NULL),
    CHECK (motif_non_utilisation IS NULL OR type_decision IN ('autre_solution','sans_ia'))
);

-- Solutions de l'IA retenues (une ou plusieurs).
-- Règle serveur : 'ia_retenue' et 'ia_adaptee' exigent au moins une ligne ici.
CREATE TABLE decision_solution (
    decision_id BIGINT NOT NULL REFERENCES decision_correction(id) ON DELETE CASCADE,
    solution_id BIGINT NOT NULL REFERENCES solution(id),
    PRIMARY KEY (decision_id, solution_id)
);

-- UN SEUL test par problème, avec sa description. Les passages successifs
-- (après chaque réouverture) sont enregistrés dans session_test.
CREATE TABLE test_correction (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES application(id),
    probleme_id    BIGINT NOT NULL UNIQUE,
    description    TEXT NOT NULL,
    origine        VARCHAR(15) NOT NULL DEFAULT 'utilisateur' CHECK (origine IN ('ia','utilisateur')),
    redige_par     BIGINT NOT NULL REFERENCES utilisateur(id),
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le     TIMESTAMPTZ,
    UNIQUE (id, application_id),
    FOREIGN KEY (probleme_id, application_id) REFERENCES probleme(id, application_id) ON DELETE CASCADE
);

-- Un passage de test. File ouverte à tous les testeurs ; le testeur qui prend le test
-- est toujours enregistré. Statuts : a_tester, en_cours, valide, non_valide.
CREATE TABLE session_test (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES application(id),
    test_id        BIGINT NOT NULL,
    numero         INT NOT NULL,                 -- numéro du passage (attribué par déclencheur)
    decision_id    BIGINT REFERENCES decision_correction(id),   -- correction testée
    demande_par    BIGINT NOT NULL REFERENCES utilisateur(id),
    testeur_id     BIGINT REFERENCES utilisateur(id),
    branche_testee VARCHAR(100) NOT NULL DEFAULT 'develop',     -- develop, ou branche du problème rouvert
    commit_teste   VARCHAR(64),
    environnement  VARCHAR(100),
    statut         VARCHAR(15) NOT NULL DEFAULT 'a_tester'
                   CHECK (statut IN ('a_tester','en_cours','valide','non_valide')),
    commentaire    TEXT,
    preuve         TEXT,
    demande_le     TIMESTAMPTZ NOT NULL DEFAULT now(),
    pris_le        TIMESTAMPTZ,
    decide_le      TIMESTAMPTZ,
    UNIQUE (test_id, numero),
    FOREIGN KEY (test_id, application_id) REFERENCES test_correction(id, application_id),
    CHECK (statut = 'a_tester' OR testeur_id IS NOT NULL),            -- on sait toujours qui teste
    CHECK (statut NOT IN ('valide','non_valide') OR decide_le IS NOT NULL),
    CHECK (statut <> 'non_valide' OR commentaire IS NOT NULL)          -- refus : commentaire obligatoire
);

-- Un seul passage actif à la fois pour un même test.
CREATE UNIQUE INDEX uq_session_test_active
    ON session_test(test_id) WHERE statut IN ('a_tester','en_cours');

-- Retour du testeur sur chaque critère d'acceptation des tâches.
CREATE TABLE resultat_critere_acceptation (
    session_id            BIGINT NOT NULL REFERENCES session_test(id) ON DELETE CASCADE,
    critere_acceptation_id BIGINT NOT NULL REFERENCES critere_acceptation(id),
    satisfait             BOOLEAN NOT NULL,
    commentaire           TEXT,
    PRIMARY KEY (session_id, critere_acceptation_id)
);


-- ---------- 7. Notes, discussions, assistant IA, notifications -------

-- Notes : l'auteur seul les modifie ou les supprime (règle serveur).
-- Suppression logique : le contenu reste conservé et visible dans l'historique.
CREATE TABLE note (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES application(id),
    probleme_id    BIGINT,
    tache_id       BIGINT,
    auteur_id      BIGINT NOT NULL REFERENCES utilisateur(id),
    type           VARCHAR(25) NOT NULL DEFAULT 'note_interne'
                   CHECK (type IN ('note_interne','commentaire_correction')),
    contenu        TEXT NOT NULL,
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le     TIMESTAMPTZ,
    supprime_le    TIMESTAMPTZ,
    CHECK ((probleme_id IS NOT NULL)::int + (tache_id IS NOT NULL)::int = 1),
    FOREIGN KEY (probleme_id, application_id) REFERENCES probleme(id, application_id) ON DELETE CASCADE,
    FOREIGN KEY (tache_id, application_id)    REFERENCES tache(id, application_id)    ON DELETE CASCADE
);

-- Discussions : un espace par application, organisé en salons.
-- Un salon est créé automatiquement pour chaque problème ; des salons généraux existent.
-- Tous ceux qui ont accès à l'application peuvent lire et écrire.
-- Un salon n'est jamais supprimé, sauf (suppression logique) par le chef de projet.
-- Un salon archivé (problème terminé) est rouvert si le problème est rouvert.
CREATE TABLE salon (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES application(id),
    type           VARCHAR(10) NOT NULL CHECK (type IN ('general','probleme')),
    probleme_id    BIGINT UNIQUE,
    titre          VARCHAR(255) NOT NULL,
    cree_par       BIGINT REFERENCES utilisateur(id),     -- NULL = créé automatiquement
    archive        BOOLEAN NOT NULL DEFAULT FALSE,
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now(),
    supprime_le    TIMESTAMPTZ,
    supprime_par   BIGINT REFERENCES utilisateur(id),
    CHECK ((type = 'probleme' AND probleme_id IS NOT NULL)
        OR (type = 'general'  AND probleme_id IS NULL)),
    CHECK ((supprime_le IS NULL) = (supprime_par IS NULL)),
    FOREIGN KEY (probleme_id, application_id) REFERENCES probleme(id, application_id) ON DELETE CASCADE
);

-- Messages : modifiables et supprimables par leur seul auteur (règle serveur).
-- Les événements automatiques (type 'systeme') sont distincts des messages d'utilisateurs.
CREATE TABLE message_discussion (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    salon_id    BIGINT NOT NULL REFERENCES salon(id) ON DELETE CASCADE,
    parent_id   BIGINT REFERENCES message_discussion(id),
    tache_id    BIGINT REFERENCES tache(id),             -- référence facultative à une tâche
    auteur_id   BIGINT REFERENCES utilisateur(id),
    type        VARCHAR(12) NOT NULL DEFAULT 'utilisateur'
                CHECK (type IN ('utilisateur','systeme')),
    contenu     TEXT NOT NULL,
    cree_le     TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le  TIMESTAMPTZ,
    supprime_le TIMESTAMPTZ,
    CHECK ((type = 'utilisateur' AND auteur_id IS NOT NULL) OR type = 'systeme')
);

CREATE TABLE salon_lecture (
    salon_id            BIGINT NOT NULL REFERENCES salon(id) ON DELETE CASCADE,
    utilisateur_id      BIGINT NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    derniere_lecture_le TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (salon_id, utilisateur_id)
);

CREATE TABLE mention (
    message_id     BIGINT NOT NULL REFERENCES message_discussion(id) ON DELETE CASCADE,
    utilisateur_id BIGINT NOT NULL REFERENCES utilisateur(id),
    PRIMARY KEY (message_id, utilisateur_id)
);

-- Assistant IA : UNE conversation COMMUNE par problème, visible par tous ceux qui ont
-- accès à l'application (développeurs, testeurs, chef de projet). Chaque question garde
-- son auteur. Le contexte reste celui du problème. Peut être alimentée par le bouton
-- « Demander de l'aide » d'une tâche ou d'une sous-tâche. L'IA propose, elle ne modifie
-- jamais le code.
CREATE TABLE conversation_ia (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    probleme_id    BIGINT NOT NULL UNIQUE,
    application_id BIGINT NOT NULL REFERENCES application(id),
    cree_par       BIGINT REFERENCES utilisateur(id),
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (probleme_id, application_id) REFERENCES probleme(id, application_id) ON DELETE CASCADE
);

CREATE TABLE message_ia (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id   BIGINT NOT NULL REFERENCES conversation_ia(id) ON DELETE CASCADE,
    emetteur          VARCHAR(12) NOT NULL CHECK (emetteur IN ('utilisateur','assistant')),
    auteur_id         BIGINT REFERENCES utilisateur(id),   -- NULL pour l'assistant
    contenu           TEXT NOT NULL,
    contexte_utilise  JSONB,                -- références du contexte fourni (jamais de secrets)
    informations_manquantes TEXT,           -- ce que l'IA signale ne pas savoir
    niveau_confiance  NUMERIC(3,2) CHECK (niveau_confiance BETWEEN 0 AND 1),
    solution_id       BIGINT REFERENCES solution(id),     -- si la réponse devient une solution
    tache_id          BIGINT REFERENCES tache(id),         -- question issue de « Demander de l'aide »
    sous_tache_id     BIGINT REFERENCES sous_tache(id),
    modele_ia         VARCHAR(80),
    version_prompt    VARCHAR(40),
    cree_le           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (emetteur = 'assistant' OR auteur_id IS NOT NULL)
);

-- Notifications internes. Un événement crée une notification par destinataire autorisé.
-- Chef de projet : seulement celles qui le concernent, plus les problèmes critiques
-- (règle de distribution côté serveur).
CREATE TABLE notification (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    destinataire_id BIGINT NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    application_id  BIGINT REFERENCES application(id) ON DELETE CASCADE,
    type_evenement  VARCHAR(40) NOT NULL
                    CHECK (type_evenement IN ('probleme_cree','probleme_critique','probleme_assigne',
                                              'probleme_rouvert','statut_modifie','tache_assignee',
                                              'commentaire_ajoute','mention','reponse_discussion',
                                              'verification_terminee','echeance_proche',
                                              'nouvelle_recommandation_ia','decision_enregistree',
                                              'test_demande','test_valide','test_non_valide')),
    message         VARCHAR(500) NOT NULL,
    type_element    VARCHAR(30),             -- lien direct vers l'élément concerné
    element_id      BIGINT,
    declencheur_id  BIGINT REFERENCES utilisateur(id),   -- NULL = événement système
    lu              BOOLEAN NOT NULL DEFAULT FALSE,
    lu_le           TIMESTAMPTZ,
    cree_le         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (destinataire_id, type_evenement, type_element, element_id, cree_le)
);

CREATE TABLE preference_notification (
    utilisateur_id BIGINT NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    type_evenement VARCHAR(40) NOT NULL,
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (utilisateur_id, type_evenement)
);


-- ---------- 8. Historique de toutes les activités (ajout seul) -------

-- Journal de TOUTES les actions dans l'application, quel que soit l'auteur
-- (NULL = système). Le contenu des notes et messages supprimés y reste conservé.
CREATE TABLE evenement_historique (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id  BIGINT REFERENCES application(id),
    type_element    VARCHAR(30) NOT NULL,
    element_id      BIGINT NOT NULL,
    auteur_id       BIGINT REFERENCES utilisateur(id),
    action          VARCHAR(50) NOT NULL,
    ancienne_valeur JSONB,
    nouvelle_valeur JSONB,
    commentaire     TEXT,
    cree_le         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Transitions de statut : historique ET base du calcul des temps de résolution.
CREATE TABLE historique_statut (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES application(id),
    type_element   VARCHAR(20) NOT NULL
                   CHECK (type_element IN ('probleme','tache','sous_tache','critere',
                                           'verification','session_test')),
    element_id     BIGINT NOT NULL,
    ancien_statut  VARCHAR(20),
    nouveau_statut VARCHAR(20) NOT NULL,
    auteur_id      BIGINT REFERENCES utilisateur(id),
    motif          TEXT,
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE FUNCTION interdire_modification_historique() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Historique en ajout seul : % interdit sur %', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_historique_statut_immuable
    BEFORE UPDATE OR DELETE ON historique_statut
    FOR EACH ROW EXECUTE FUNCTION interdire_modification_historique();

CREATE TRIGGER trg_evenement_historique_immuable
    BEFORE UPDATE OR DELETE ON evenement_historique
    FOR EACH ROW EXECUTE FUNCTION interdire_modification_historique();


-- ---------- 9. Rapports ----------------------------------------------

-- Rapports enregistrés (instantané daté, pour comparer et exporter).
CREATE TABLE rapport (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT REFERENCES application(id),   -- NULL = rapport global
    equipe_id      BIGINT REFERENCES equipe(id),
    type           VARCHAR(40) NOT NULL,                -- problemes_taches, ia_tests
    parametres     JSONB,
    contenu        JSONB NOT NULL,
    genere_par     BIGINT NOT NULL REFERENCES utilisateur(id),
    genere_le      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Vues d'indicateurs (accès filtrés côté serveur selon les permissions).
CREATE VIEW v_problemes_par_gravite AS
SELECT application_id, categorie, gravite, statut, count(*) AS nb
FROM probleme
GROUP BY application_id, categorie, gravite, statut;

CREATE VIEW v_evolution_problemes AS
SELECT application_id, date_trunc('month', cree_le) AS mois, count(*) AS nb_crees
FROM probleme
GROUP BY application_id, date_trunc('month', cree_le);

-- Temps de résolution : jusqu'à la dernière clôture (« termine »).
CREATE VIEW v_temps_resolution AS
SELECT p.id AS probleme_id, p.application_id, p.categorie, p.gravite,
       p.cree_le, h.termine_le, (h.termine_le - p.cree_le) AS duree
FROM probleme p
JOIN LATERAL (
    SELECT max(cree_le) AS termine_le
    FROM historique_statut
    WHERE type_element = 'probleme' AND element_id = p.id AND nouveau_statut = 'termine'
) h ON h.termine_le IS NOT NULL;

CREATE VIEW v_temps_moyen_resolution AS
SELECT application_id, categorie, gravite,
       count(*) AS nb_resolus, avg(duree) AS duree_moyenne
FROM v_temps_resolution
GROUP BY application_id, categorie, gravite;

CREATE VIEW v_taches_stats AS
SELECT application_id, statut, count(*) AS nb,
       count(*) FILTER (WHERE echeance < current_date
                          AND statut NOT IN ('terminee','arretee')) AS nb_en_retard
FROM tache
GROUP BY application_id, statut;

-- Faux positifs : décisions humaines, sans vérité de référence (à présenter séparément
-- du jeu de référence dans le mémoire).
CREATE VIEW v_faux_positifs AS
SELECT application_id, categorie, count(*) AS nb_total,
       count(*) FILTER (WHERE statut = 'faux_positif') AS nb_faux_positifs,
       round(100.0 * count(*) FILTER (WHERE statut = 'faux_positif') / count(*), 1) AS taux_pct
FROM probleme
GROUP BY application_id, categorie;

CREATE VIEW v_utilite_solutions_ia AS
SELECT p.application_id, r.utilite_percue, count(*) AS nb
FROM retour_solution r
JOIN solution s    ON s.id = r.solution_id
JOIN diagnostic dg ON dg.id = s.diagnostic_id
JOIN probleme p    ON p.id = dg.probleme_id
GROUP BY p.application_id, r.utilite_percue;

CREATE VIEW v_decisions_correction AS
SELECT p.application_id, d.type_decision, count(*) AS nb
FROM decision_correction d
JOIN probleme p ON p.id = d.probleme_id
GROUP BY p.application_id, d.type_decision;

CREATE VIEW v_validation_tests AS
SELECT application_id,
       count(*) FILTER (WHERE statut = 'valide')                 AS nb_valides,
       count(*) FILTER (WHERE statut = 'non_valide')             AS nb_non_valides,
       count(*) FILTER (WHERE statut IN ('a_tester','en_cours')) AS nb_en_attente,
       round(100.0 * count(*) FILTER (WHERE statut = 'valide')
             / NULLIF(count(*) FILTER (WHERE statut IN ('valide','non_valide')), 0), 1) AS taux_validation_pct
FROM session_test
GROUP BY application_id;

-- Problèmes rouverts (corrections qui ont échoué au test).
CREATE VIEW v_problemes_rouverts AS
SELECT p.application_id,
       count(*)             AS nb_reouvertures,
       count(DISTINCT p.id) AS nb_problemes_concernes
FROM historique_statut h
JOIN probleme p ON p.id = h.element_id
WHERE h.type_element = 'probleme' AND h.nouveau_statut = 'rouvert'
GROUP BY p.application_id;

-- Résultat du test selon le type de décision (utilité perçue != réussite).
CREATE VIEW v_validation_par_decision AS
SELECT s.application_id, d.type_decision,
       count(*) FILTER (WHERE s.statut = 'valide')                 AS nb_valides,
       count(*) FILTER (WHERE s.statut = 'non_valide')             AS nb_non_valides,
       count(*) FILTER (WHERE s.statut IN ('a_tester','en_cours')) AS nb_en_attente
FROM session_test s
JOIN decision_correction d ON d.id = s.decision_id
GROUP BY s.application_id, d.type_decision;


-- ---------- 10. Règles d'enchaînement (déclencheurs) -----------------

-- 10.1 Tâche : transitions autorisées, et fin conditionnée par les sous-tâches.
--      Éléments « arrêtés » ne bloquent pas. Dates de début et de fin posées automatiquement.
CREATE FUNCTION controle_transition_tache() RETURNS trigger AS $$
BEGIN
    IF NEW.statut = OLD.statut THEN
        RETURN NEW;
    END IF;

    IF NOT (
        (OLD.statut = 'a_faire'  AND NEW.statut = 'en_cours') OR
        (OLD.statut = 'en_pause' AND NEW.statut IN ('en_cours','arretee')) OR
        (OLD.statut = 'en_cours' AND NEW.statut IN ('en_pause','arretee','terminee'))
    ) THEN
        RAISE EXCEPTION 'Transition de statut de tâche interdite : % -> %', OLD.statut, NEW.statut;
    END IF;

    IF NEW.statut = 'terminee' AND EXISTS (
        SELECT 1 FROM sous_tache st
        WHERE st.tache_id = NEW.id AND st.statut NOT IN ('terminee','arretee')
    ) THEN
        RAISE EXCEPTION 'Une tâche ne peut être terminée que si toutes ses sous-tâches sont terminées';
    END IF;

    IF NEW.statut = 'en_cours' AND NEW.debut_le IS NULL THEN
        NEW.debut_le := now();
    END IF;
    IF NEW.statut IN ('terminee','arretee') AND NEW.fin_le IS NULL THEN
        NEW.fin_le := now();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tache_transition
    BEFORE UPDATE OF statut ON tache
    FOR EACH ROW EXECUTE FUNCTION controle_transition_tache();

-- 10.2 Demande de test : seulement si toutes les tâches du problème sont terminées
--      (les arrêtées ne bloquent pas) et si au moins une tâche a été terminée
--      depuis la dernière réouverture du problème. Numérote aussi le passage.
CREATE FUNCTION controle_demande_test() RETURNS trigger AS $$
DECLARE
    v_probleme    BIGINT;
    v_reouverture TIMESTAMPTZ;
BEGIN
    SELECT probleme_id INTO v_probleme FROM test_correction WHERE id = NEW.test_id;

    IF EXISTS (
        SELECT 1 FROM tache
        WHERE probleme_id = v_probleme AND statut NOT IN ('terminee','arretee')
    ) THEN
        RAISE EXCEPTION 'Test impossible : toutes les tâches du problème doivent être terminées';
    END IF;

    SELECT max(cree_le) INTO v_reouverture
    FROM historique_statut
    WHERE type_element = 'probleme' AND element_id = v_probleme AND nouveau_statut = 'rouvert';

    IF NOT EXISTS (
        SELECT 1 FROM tache
        WHERE probleme_id = v_probleme AND statut = 'terminee'
          AND (v_reouverture IS NULL OR fin_le > v_reouverture)
    ) THEN
        RAISE EXCEPTION 'Test impossible : aucune tâche terminée (depuis la dernière réouverture)';
    END IF;

    IF NEW.numero IS NULL THEN
        SELECT COALESCE(max(numero), 0) + 1 INTO NEW.numero
        FROM session_test WHERE test_id = NEW.test_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_session_test_demande
    BEFORE INSERT ON session_test
    FOR EACH ROW EXECUTE FUNCTION controle_demande_test();

-- 10.3 Un testeur ne teste pas une correction dont il est l'auteur.
CREATE FUNCTION controle_testeur() RETURNS trigger AS $$
BEGIN
    IF NEW.testeur_id IS NOT NULL AND NEW.decision_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM decision_correction d
        WHERE d.id = NEW.decision_id AND d.developpeur_id = NEW.testeur_id
    ) THEN
        RAISE EXCEPTION 'Un testeur ne peut pas tester une correction dont il est l''auteur';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_session_test_testeur
    BEFORE INSERT OR UPDATE ON session_test
    FOR EACH ROW EXECUTE FUNCTION controle_testeur();

-- 10.4 Date de dernière modification d'un problème.
CREATE FUNCTION maj_modifie_le() RETURNS trigger AS $$
BEGIN
    NEW.modifie_le := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_probleme_modifie
    BEFORE UPDATE ON probleme
    FOR EACH ROW EXECUTE FUNCTION maj_modifie_le();


-- ---------- 11. Données initiales : rôles et permissions -------------

INSERT INTO role (nom, description) VALUES
    ('developpeur', 'Étudie les problèmes, décide des corrections, gère ses tâches'),
    ('testeur',     'Teste les corrections et rend un retour validé ou non validé'),
    ('chef_projet', 'Pilote la maintenance de l''équipe, répartit les tâches, configure les applications');

INSERT INTO permission (code, description) VALUES
    ('probleme.consulter',    'Consulter les problèmes'),
    ('probleme.modifier',     'Créer et modifier les problèmes'),
    ('verification.lancer',   'Lancer une vérification'),
    ('solution.decider',      'Enregistrer la décision de correction'),
    ('test.valider',          'Valider ou non une correction'),
    ('historique.consulter',  'Consulter l''historique'),
    ('rapport.consulter',     'Consulter les rapports'),
    ('discussion.participer', 'Lire et écrire dans les salons de l''application'),
    ('assistant.utiliser',    'Utiliser l''assistant IA d''un problème'),
    ('critere.gerer',         'Créer, valider et activer les critères de vérification'),
    ('tache.gerer',           'Créer, assigner et suivre les tâches'),
    ('application.configurer','Configurer l''application, ses paramètres et son dépôt Git'),
    ('salon.supprimer',       'Supprimer un salon (suppression logique)');

-- L'administrateur de la plateforme (utilisateur.est_admin) a tous les droits.
INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id FROM role r, permission p
WHERE r.nom = 'developpeur'
  AND p.code NOT IN ('test.valider','application.configurer','salon.supprimer');

INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id FROM role r, permission p
WHERE r.nom = 'testeur'
  AND p.code IN ('probleme.consulter','test.valider','historique.consulter','rapport.consulter',
                 'discussion.participer','assistant.utiliser');

-- Le chef de projet a tous les droits d'équipe, sauf valider un test (séparation des rôles).
INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id FROM role r, permission p
WHERE r.nom = 'chef_projet' AND p.code <> 'test.valider';


-- ---------- 12. Index principaux -------------------------------------

CREATE INDEX idx_application_equipe    ON application(equipe_id);
CREATE INDEX idx_verification_app      ON verification(application_id, debut_le DESC);
CREATE INDEX idx_resultat_verif        ON resultat_analyse(verification_id);
CREATE INDEX idx_probleme_app_statut   ON probleme(application_id, statut);
CREATE INDEX idx_probleme_responsable  ON probleme(responsable_id);
CREATE INDEX idx_diagnostic_probleme   ON diagnostic(probleme_id, cree_le DESC);
CREATE INDEX idx_tache_probleme        ON tache(probleme_id);
CREATE INDEX idx_tache_app_statut      ON tache(application_id, statut);
CREATE INDEX idx_tache_solution_sol    ON tache_solution(solution_id);
CREATE INDEX idx_decision_probleme     ON decision_correction(probleme_id, cree_le DESC);
CREATE INDEX idx_decision_solution_sol ON decision_solution(solution_id);
CREATE INDEX idx_session_app_statut    ON session_test(application_id, statut);
CREATE INDEX idx_session_testeur       ON session_test(testeur_id, statut);
CREATE INDEX idx_note_probleme         ON note(probleme_id, cree_le);
CREATE INDEX idx_note_tache            ON note(tache_id, cree_le);
CREATE INDEX idx_salon_app             ON salon(application_id, type);
CREATE INDEX idx_message_salon         ON message_discussion(salon_id, cree_le);
CREATE INDEX idx_message_ia_conv       ON message_ia(conversation_id, cree_le);
CREATE INDEX idx_message_ia_soustache  ON message_ia(sous_tache_id) WHERE sous_tache_id IS NOT NULL;
CREATE INDEX idx_notif_destinataire    ON notification(destinataire_id, lu, cree_le DESC);
CREATE INDEX idx_histo_element         ON evenement_historique(type_element, element_id);
CREATE INDEX idx_histo_app_date        ON evenement_historique(application_id, cree_le DESC);
CREATE INDEX idx_hstatut_element       ON historique_statut(type_element, element_id, cree_le);
CREATE INDEX idx_hstatut_app           ON historique_statut(application_id, cree_le DESC);
CREATE INDEX idx_rapport_app           ON rapport(application_id, genere_le DESC);


-- ---------- 13. Modèle de fiabilité (étapes 3 et 6 du pipeline) ------

-- Versions du modèle de fiabilité (développé et entraîné dans ce projet). Un modèle entraîné reste INACTIF
-- tant qu'un administrateur ne l'a pas activé après lecture de ses métriques.
CREATE TABLE modele_fiabilite (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    etape        SMALLINT NOT NULL CHECK (etape IN (3, 6)),   -- 3 : preuves de l'analyse ; 6 : solutions de Gemini
    version      INT NOT NULL,
    algorithme   VARCHAR(20) NOT NULL CHECK (algorithme IN ('logistique','foret')),
    nb_exemples  INT,
    metriques    JSONB,
    parametres   JSONB NOT NULL,        -- modèle sérialisé : variables, coefficients ou arbres, calibration, seuils
    actif        BOOLEAN NOT NULL DEFAULT FALSE,
    entraine_par BIGINT REFERENCES utilisateur(id),
    entraine_le  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (etape, version)
);
CREATE UNIQUE INDEX uq_modele_fiabilite_actif ON modele_fiabilite(etape) WHERE actif;

-- Un score de fiabilité calculé pour un résultat d'analyse (étape 3) ou pour une solution de l'IA (étape 6),
-- avec ses variables, son explication et, plus tard, la vérité terrain (décision humaine, retour du testeur).
CREATE TABLE evaluation_fiabilite (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    etape          SMALLINT NOT NULL CHECK (etape IN (3, 6)),
    cible_type     VARCHAR(15) NOT NULL CHECK (cible_type IN ('resultat','solution')),
    cible_id       BIGINT NOT NULL,
    application_id BIGINT NOT NULL REFERENCES application(id),
    modele_id      BIGINT REFERENCES modele_fiabilite(id),      -- NULL = score de départ par règles (non appris)
    source         VARCHAR(12) NOT NULL CHECK (source IN ('modele','heuristique')),
    score          NUMERIC(4,3) NOT NULL CHECK (score BETWEEN 0 AND 1),
    niveau         VARCHAR(8) NOT NULL CHECK (niveau IN ('faible','moyen','eleve')),
    variables      JSONB NOT NULL,
    explication    JSONB,
    etiquette      BOOLEAN,             -- vérité terrain : résultat réel (confirmé) / solution validée au test
    etiquette_le   TIMESTAMPTZ,
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((etape = 3 AND cible_type = 'resultat') OR (etape = 6 AND cible_type = 'solution'))
);
CREATE INDEX idx_eval_fiab_cible ON evaluation_fiabilite(cible_type, cible_id, cree_le DESC);
CREATE INDEX idx_eval_fiab_etiquetee ON evaluation_fiabilite(etape) WHERE etiquette IS NOT NULL;

-- =====================================================================
-- RÈGLES CONTRÔLÉES CÔTÉ SERVEUR (non exprimables, ou non souhaitables, en SQL)
--  * Permissions : contrôlées à chaque requête, par rôle dans l'équipe de l'application.
--  * Transitions des statuts d'un PROBLÈME (nouveau, a_analyser, confirme, faux_positif,
--    en_cours, a_tester, teste, termine, rouvert) : à définir précisément. Proposé :
--    test non validé : a_tester -> rouvert ; nouvelle tâche démarrée : rouvert -> en_cours ;
--    demande de test acceptée : en_cours -> a_tester ; test validé : a_tester -> teste.
--  * Chaque action (de n'importe quel auteur) écrit une ligne dans evenement_historique ;
--    chaque changement de statut écrit une ligne dans historique_statut.
--  * Notes et messages : modifiables ou supprimables par leur seul auteur (suppression logique,
--    contenu conservé dans l'historique). Salons : suppression logique par le chef de projet.
--  * Une tâche liée à des solutions : celles-ci doivent appartenir au même problème.
--  * 'ia_retenue' / 'ia_adaptee' : au moins une solution dans decision_solution.
--  * Critère d'une vérification : standard, ou de la même application.
--  * Notifications : le chef de projet ne reçoit que celles qui le concernent, plus les
--    problèmes critiques.
--  * Données envoyées à l'IA : limitées au nécessaire, sans secrets ; clé API côté serveur.
--  * Salon archivé à la fin du problème, rouvert si le problème est rouvert.
-- =====================================================================
