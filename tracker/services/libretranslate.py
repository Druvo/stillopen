"""Translate a job description, via LibreTranslate -- self-hostable, open-source machine translation. Off by
default: nothing is sent anywhere unless an admin sets `SiteConfig.libretranslate_url` (Site configuration >
Job search keys & writing check), same discipline as LanguageTool: a URL is the opt-in, there is no separate
enable switch, since this is a one-shot read of text the person is already looking at, not a standing
integration."""
import requests

from tracker.models import SiteConfig

MAX_CHARS = 5000  # a job description is never this long; keeps a single request reasonably sized regardless


class TranslateError(Exception):
    pass


def available(config: SiteConfig) -> bool:
    return bool(config.effective_libretranslate_url)


def translate(text: str, config: SiteConfig, target: str = "en", source: str = "auto") -> str:
    """The translated text, or TranslateError if no server is configured or it cannot be reached."""
    base = config.effective_libretranslate_url
    if not base:
        raise TranslateError("Translation is not set up on this server (Site configuration > Job search keys).")
    if not text.strip():
        return ""
    payload = {"q": text[:MAX_CHARS], "source": source, "target": target, "format": "text"}
    key = config.effective_libretranslate_api_key
    if key:
        payload["api_key"] = key
    try:
        resp = requests.post(f"{base}/translate", json=payload, timeout=20, headers={"User-Agent": "StillOpen/1.0"})
    except requests.RequestException as exc:
        raise TranslateError(f"Could not reach the translator: {exc.__class__.__name__}") from exc
    if resp.status_code != 200:
        raise TranslateError(f"The translator returned HTTP {resp.status_code}.")
    try:
        return resp.json()["translatedText"]
    except (ValueError, KeyError) as exc:
        raise TranslateError("The translator's reply was not in the expected shape.") from exc
