"""Masquage des secrets avant tout envoi à l'IA, et limitation de la quantité de code transmise."""
import re

_MOTIFS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[CLE_PRIVEE_MASQUEE]"),
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|token|auth[_-]?key)\b(\s*[=:]>?\s*)(['\"])(.+?)\3"),
     r"\1\2\3[MASQUE]\3"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{16,}"), "Bearer [MASQUE]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[CLE_AWS_MASQUEE]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"), "[CLE_API_MASQUEE]"),
    (re.compile(r"(?i)\b(postgres(?:ql)?|mysql|mongodb)(\+\w+)?://[^\s'\"]+"), "[URL_BASE_MASQUEE]"),
]


def masquer_secrets(texte: str | None) -> tuple[str, int]:
    """Retourne (texte masqué, nombre de masquages)."""
    if not texte:
        return "", 0
    total = 0
    for motif, remplacement in _MOTIFS:
        texte, n = motif.subn(remplacement, texte)
        total += n
    return texte, total


def preparer_extrait(texte: str | None, max_chars: int) -> str:
    """Masque les secrets puis tronque : seul le nécessaire part vers le service externe."""
    masque, _ = masquer_secrets(texte)
    return masque if len(masque) <= max_chars else masque[:max_chars] + "\n[... tronqué ...]"
