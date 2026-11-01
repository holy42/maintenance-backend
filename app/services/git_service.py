"""Accès Git en LECTURE SEULE (clone, fetch, checkout dans un répertoire de travail propre à la plateforme).
Aucune écriture dans le dépôt distant : jamais de push. Le jeton est transmis par variables
d'environnement (pas dans la ligne de commande). L'en-tête d'authentification dépend de l'hébergeur
(GitHub, GitLab...) : à adapter à celui que vous choisirez."""
import base64
import os
import re
import subprocess
from pathlib import Path

from app.config import settings
from app.core.exceptions import DonneesInvalides, ErreurMetier

_BRANCHE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,99}$")
_URL = re.compile(r"^(https://|ssh://|git@)[^\s]+$")


def valider_branche(branche: str) -> str:
    if not _BRANCHE.match(branche) or ".." in branche:
        raise DonneesInvalides("Nom de branche invalide.")
    return branche


def valider_url(url: str) -> str:
    if not _URL.match(url):
        raise DonneesInvalides("URL de dépôt invalide (https, ssh ou git@ attendus).")
    return url


def _env(jeton: str | None) -> dict:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if jeton:
        basique = base64.b64encode(f"oauth2:{jeton}".encode()).decode()
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.extraHeader",
                   GIT_CONFIG_VALUE_0=f"Authorization: Basic {basique}")
    return env


def _git(args: list[str], cwd: Path | None, jeton: str | None = None) -> str:
    try:
        r = subprocess.run(
            ["git", *args], cwd=cwd, env=_env(jeton), capture_output=True, text=True,
            timeout=settings.git_timeout_seconds, check=True,
        )
        return r.stdout.strip()
    except subprocess.CalledProcessError as exc:
        # on ne renvoie jamais la sortie brute (elle pourrait contenir l'URL ou des indices sur le jeton)
        raise ErreurMetier("Opération Git impossible (accès refusé, branche ou dépôt introuvable).") from exc
    except subprocess.TimeoutExpired as exc:
        raise ErreurMetier("Délai dépassé lors de l'accès au dépôt Git.") from exc


def dossier_depot(application_id: int) -> Path:
    d = Path(settings.git_workdir).resolve() / f"app_{application_id}"
    d.parent.mkdir(parents=True, exist_ok=True)
    return d


def tester_connexion(url: str, jeton: str | None) -> list[str]:
    """Liste les branches distantes (sans cloner)."""
    sortie = _git(["ls-remote", "--heads", valider_url(url)], None, jeton)
    return [ligne.split("refs/heads/")[-1] for ligne in sortie.splitlines() if "refs/heads/" in ligne]


def synchroniser(application_id: int, url: str, jeton: str | None, branche: str) -> tuple[Path, str]:
    """Clone ou met à jour le dépôt local, se place sur la branche et retourne (racine, dernier commit)."""
    branche = valider_branche(branche)
    dest = dossier_depot(application_id)
    if not (dest / ".git").exists():
        _git(["clone", "--no-checkout", valider_url(url), str(dest)], None, jeton)
    _git(["fetch", "--prune", "origin"], dest, jeton)
    _git(["checkout", "--force", "--detach", f"origin/{branche}"], dest, jeton)
    return dest, _git(["rev-parse", "HEAD"], dest)


def commits_recents(application_id: int, branche: str, limite: int = 10) -> list[dict]:
    dest = dossier_depot(application_id)
    sortie = _git(["log", f"origin/{valider_branche(branche)}", f"-{limite}", "--format=%H|%an|%aI|%s"], dest)
    out = []
    for ligne in sortie.splitlines():
        h, auteur, date, sujet = (ligne.split("|", 3) + ["", "", ""])[:4]
        out.append({"commit": h, "auteur": auteur, "date": date, "sujet": sujet})
    return out
