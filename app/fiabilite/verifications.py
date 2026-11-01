"""« Vérifications recommandées » : rédigées par Gemini, puis CONTRÔLÉES par des règles avant d'être affichées.

Ce que le contrôle fait (déterministe, sans IA) :
  - supprime les lignes vides et les doublons (sans tenir compte de la casse ni de la ponctuation finale) ;
  - rejette toute AFFIRMATION de correction (« Le problème est corrigé ») : seule une validation humaine peut l'établir ;
  - marque « a_verifier » une vérification qui cite un fichier absent du contexte fourni à l'IA (risque d'invention) ;
  - si rien d'exploitable ne reste, propose des vérifications génériques par règles (origine « regle »).
Chaque élément retourné : {"texte", "controle": "ok" | "a_verifier", "origine": "ia" | "regle", "motif"?}.
"""
import re

MAX_VERIFICATIONS = 8

# Un texte qui commence par un verbe d'action est une consigne de vérification : on la garde même s'il contient « corrigé ».
_VERBES = (
    "vérifier", "verifier", "contrôler", "controler", "tester", "lire", "relire", "confirmer", "s'assurer", "examiner",
    "écrire", "ecrire", "reproduire", "valider", "comparer", "rechercher", "regarder", "consulter", "ajouter", "exécuter",
    "executer", "lancer", "inspecter", "analyser", "identifier", "chercher", "contrôle", "vérification", "test", "check",
)
_AFFIRMATION = re.compile(r"(?i)\b(?:corrig|résolu|resolu|réglé|regle|répar|repar|fix)\w*\b")
_FICHIER = re.compile(r"(?i)(?<![\w/])([\w.\-]+(?:[/\\][\w.\-]+)*\.(?:php|js|ts|tsx|jsx|py|html|twig|sql|json|ya?ml|xml|env|ini))\b")

GENERIQUES = {
    "securite": [
        "Vérifier que la valeur concernée est contrôlée ou échappée en amont de l'endroit signalé.",
        "Vérifier les droits d'accès de l'utilisateur sur la ressource concernée.",
        "Écrire un test qui reproduit l'anomalie avec une entrée malveillante.",
    ],
    "erreur_technique": [
        "Reproduire l'erreur dans un environnement de test avant toute modification.",
        "Vérifier si le même motif apparaît dans d'autres fichiers.",
        "Relancer la vérification après correction pour confirmer que le constat a disparu.",
    ],
}
GENERIQUES_DEFAUT = [
    "Reproduire le problème avant toute modification.",
    "Vérifier l'impact de la correction sur les fonctions voisines.",
    "Faire valider la correction par un testeur.",
]


def _cle(texte: str) -> str:
    return re.sub(r"[\s.;:!]+$", "", re.sub(r"\s+", " ", texte.strip())).casefold()


def _normaliser_chemin(c: str) -> str:
    return c.replace("\\", "/").lstrip("./").casefold()


def _est_affirmation(texte: str) -> bool:
    debut = texte.strip().casefold()
    if debut.startswith(_VERBES):
        return False
    return bool(_AFFIRMATION.search(texte))


def _fichier_connu(chemin: str, connus: set[str]) -> bool:
    c = _normaliser_chemin(chemin)
    return any(c == k or k.endswith("/" + c) or c.endswith("/" + k) for k in (_normaliser_chemin(x) for x in connus))


def _generiques(categorie: str | None) -> list[dict]:
    return [{"texte": t, "controle": "ok", "origine": "regle"} for t in GENERIQUES.get(categorie or "", GENERIQUES_DEFAUT)]


def controler_verifications(brutes: list[str] | None, fichiers_connus: set[str] | None, categorie: str | None) -> list[dict]:
    """`fichiers_connus` : fichiers présents dans le contexte envoyé à l'IA (None = inconnus : toute citation est à vérifier)."""
    vus: set[str] = set()
    res: list[dict] = []
    for brut in brutes or []:
        texte = (brut or "").strip()
        if not texte:
            continue
        cle = _cle(texte)
        if cle in vus or _est_affirmation(texte):
            continue
        vus.add(cle)
        item = {"texte": texte, "controle": "ok", "origine": "ia"}
        cites = [m.group(1) for m in _FICHIER.finditer(texte)]
        inconnus = [c for c in cites if not _fichier_connu(c, fichiers_connus or set())]
        if inconnus:
            item["controle"] = "a_verifier"
            item["motif"] = "Fichier cité absent du contexte fourni à l'IA : " + ", ".join(inconnus)
        res.append(item)
        if len(res) >= MAX_VERIFICATIONS:
            break
    return res or _generiques(categorie)
