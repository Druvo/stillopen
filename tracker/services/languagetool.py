"""Grammar/clarity check for CV and cover letter text, via LanguageTool -- self-hostable, open-source, no
invented metrics, just real linting. Off by default: nothing is sent anywhere unless an admin sets
`SiteConfig.languagetool_url` (Site configuration > Job search keys), same discipline as Paperless and
GlitchTip. Unlike those, this is a one-shot read of text the person themselves is editing, not a standing
server-to-server integration, so there is no "enabled" switch separate from the URL -- a URL is the opt-in."""
import requests

from tracker.models import SiteConfig

MAX_CHARS = 20000  # LanguageTool's own public instance caps a request there; keep self-hosted runs just as sane


class LanguageToolError(Exception):
    pass


def available(config: SiteConfig) -> bool:
    return bool(config.effective_languagetool_url)


def check(text: str, config: SiteConfig, language: str = "auto") -> list[dict]:
    """Issues LanguageTool finds in `text`: [{"message", "short_message", "context", "offset", "length",
    "category", "suggestions"}, ...]. Raises LanguageToolError if no server is configured or it cannot be reached."""
    base = config.effective_languagetool_url
    if not base:
        raise LanguageToolError("Writing check is not set up on this server (Site configuration > Job search keys).")
    if not text.strip():
        return []
    try:
        resp = requests.post(
            f"{base}/v2/check", data={"text": text[:MAX_CHARS], "language": language},
            timeout=20, headers={"User-Agent": "StillOpen/1.0"},
        )
    except requests.RequestException as exc:
        raise LanguageToolError(f"Could not reach the writing checker: {exc.__class__.__name__}") from exc
    if resp.status_code != 200:
        raise LanguageToolError(f"The writing checker returned HTTP {resp.status_code}.")
    try:
        matches = resp.json().get("matches", [])
    except ValueError as exc:
        raise LanguageToolError("The writing checker's reply was not valid JSON.") from exc
    out = []
    for m in matches:
        offset, length = m.get("offset", 0), m.get("length", 0)
        out.append({
            "message": m.get("message", ""),
            "short_message": m.get("shortMessage", ""),
            "context": text[offset:offset + length],
            "offset": offset,
            "length": length,
            "category": (m.get("rule") or {}).get("category", {}).get("name", ""),
            "suggestions": [r["value"] for r in m.get("replacements", [])[:5] if "value" in r],
        })
    return out
