"""Reading an employer's email the person pasted, to suggest where the job now stands. Free: fixed phrase lists, no AI, English only.

The text is untrusted: it is never stored, never run, never given to a model, and only its own sentences are quoted back as the reason. Nothing
changes by itself; the person confirms the suggestion (the app never moves a job on its own reading of an email).

The reading works sentence by sentence. A phrase counts only on word boundaries, and a good-news phrase that follows a negation ("we are not able
to offer", "will not be inviting you to interview") counts as a rejection instead. Priority when several appear: an offer, then a rejection,
then an interview, then a plain acknowledgement. An email that carries good news and bad news at once is reported as unsure."""
import re

MAX_CHARS = 12000
MAX_QUOTES = 2
QUOTE_CHARS = 300

STATUS_NAMES = {"offer": "Offer", "rejected": "Rejected", "interview": "Interview", "responded": "Responded"}

NEGATION = re.compile(r"\b(?:not|no longer|unable|cannot|can't|cant|won't|wont|never|without|isn't|aren't|don't|do not|did not|didn't)\b|n't\b", re.I)


def _any(*patterns: str) -> list[re.Pattern]:
    return [re.compile(p, re.I) for p in patterns]


# (pattern list, strong): a strong phrase on its own is a "clear" reading
OFFER = _any(
    r"\bpleased to offer\b", r"\bhappy to offer\b", r"\bexcited to offer\b", r"\bdelighted to offer\b", r"\bwould like to offer you\b",
    r"\boffer you (?:the|a) (?:position|role|job|post)\b", r"\bextend(?:ing)? (?:you )?an offer\b", r"\boffer of employment\b", r"\bjob offer\b",
    r"\boffer letter\b", r"\bwe(?:'re| are) offering you\b",
)
REJECT = _any(
    r"\bregret to inform\b", r"\bnot (?:be )?(?:moving|proceeding|going|taking (?:your application )?|progressing) forward\b",
    r"\b(?:will|would|do|can|could) not (?:be )?(?:moving|proceeding|progressing|continuing|taking)\b", r"\b(?:won't|wont) be (?:moving|proceeding|progressing|continuing|taking)\b",
    r"\bnot (?:been )?(?:selected|successful|shortlisted|chosen)\b", r"\bnot (?:to|be) (?:proceed|moving|progress)\b",
    r"\bdecided (?:not )?to (?:pursue|move forward with|proceed with|go with|continue with) (?:other|another|different)\b",
    r"\bother (?:candidates|applicants)\b", r"\b(?:position|role|vacancy|job) (?:has been|was|is) (?:filled|closed|cancelled|canceled|put on hold)\b",
    r"\bno longer (?:considering|being considered|moving)\b", r"\bnot (?:a|the) (?:right |good |strong )?(?:fit|match)\b", r"\bwe (?:have )?decided not to\b",
    r"\bunable to (?:offer|proceed|move forward|invite|progress|take)\b", r"\b(?:decline|declined|reject|rejected|rejection)\b",
    r"\bon this occasion\b", r"\bwill not be (?:able|inviting|offering)\b", r"\bkeep your (?:cv|resume|details) on file\b",
)
REJECT_STRONG = _any(
    r"\bregret to inform\b", r"\bnot (?:be )?(?:moving|proceeding|going|progressing) forward\b", r"\b(?:will|would|do|can|could) not (?:be )?(?:moving|proceeding|progressing|continuing)\b",
    r"\b(?:won't|wont) be (?:moving|proceeding|progressing|continuing)\b", r"\bnot been (?:selected|successful|shortlisted)\b", r"\bother (?:candidates|applicants)\b",
    r"\bno longer (?:considering|being considered)\b", r"\bunable to (?:offer|proceed|move forward)\b", r"\bwe (?:have )?decided not to\b",
)
INTERVIEW = _any(
    r"\binvit(?:e|ing) you to (?:an? |a )?(?:\w+ )?(?:interview|call|chat|conversation|meeting|screen)\b", r"\b(?:schedule|arrange|book|set up) (?:an? |a )?(?:\w+ )?(?:interview|call|chat|conversation|meeting|time|slot)\b",
    r"\bwould like to (?:speak|talk|chat|meet) (?:with|to) you\b", r"\binterview (?:is |has been )?(?:scheduled|confirmed|booked)\b",
    r"\bavailable for (?:an? |a )?(?:\w+ )?(?:call|interview|chat|conversation)\b", r"\b(?:phone|video|technical|first|second|final|next) (?:screen|interview|round|stage)\b",
    r"\bnext (?:step|steps|round|stage)\b", r"\b(?:take-home|coding) (?:test|challenge|assessment|task)\b", r"\bcalendly\b", r"\bpick a (?:time|slot)\b",
)
INTERVIEW_STRONG = _any(
    r"\binvit(?:e|ing) you to (?:an? |a )?(?:\w+ )?(?:interview|call|chat|conversation|meeting|screen)\b", r"\binterview (?:is |has been )?(?:scheduled|confirmed|booked)\b",
    r"\b(?:schedule|arrange|book|set up) (?:an? |a )?(?:\w+ )?interview\b", r"\bwould like to (?:speak|talk|chat|meet) (?:with|to) you\b",
)
RESPOND = _any(
    r"\bthank you for (?:your )?(?:application|applying|interest)\b", r"\bthanks for (?:your )?(?:application|applying|interest)\b", r"\b(?:have )?received your application\b",
    r"\b(?:reviewing|review) your (?:application|cv|resume|profile)\b", r"\bapplication is (?:being )?(?:reviewed|under review)\b", r"\bwill be in touch\b", r"\bget back to you\b",
    r"\bunder review\b",
)

SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def sentences(text: str) -> list[str]:
    parts = [p.strip() for p in SENTENCE_END.split(text) if p and p.strip()]
    return parts


def _hits(sentence: str, patterns: list[re.Pattern]):
    return [m for p in patterns if (m := p.search(sentence))]


def _negated(sentence: str, match: re.Match) -> bool:
    """True when a negation sits shortly before the phrase ("not able to offer you", "won't be inviting you to interview")."""
    before = sentence[max(0, match.start() - 40):match.start()]
    return bool(NEGATION.search(before))


def _quote(sentence: str) -> str:
    text = re.sub(r"\s+", " ", sentence).strip()
    return text if len(text) <= QUOTE_CHARS else text[: QUOTE_CHARS - 1].rstrip() + "…"


def read(text: str) -> dict:
    """What the email seems to say: {"kind": offer|rejected|interview|responded|None, "confidence": clear|probably|unsure, "quotes": [exact sentences], "mixed": bool}."""
    text = (text or "")[:MAX_CHARS]
    found: dict[str, list[tuple[str, bool]]] = {"offer": [], "rejected": [], "interview": [], "responded": []}  # kind -> [(sentence, strong)]
    for sentence in sentences(text):
        for match in _hits(sentence, OFFER):
            (found["rejected"] if _negated(sentence, match) else found["offer"]).append((sentence, True))
        for match in _hits(sentence, INTERVIEW):
            if _negated(sentence, match):
                found["rejected"].append((sentence, False))
            else:
                found["interview"].append((sentence, any(p.search(sentence) for p in INTERVIEW_STRONG)))
        for match in _hits(sentence, REJECT):
            found["rejected"].append((sentence, any(p.search(sentence) for p in REJECT_STRONG)))
        if _hits(sentence, RESPOND):
            found["responded"].append((sentence, False))

    def unique(items):
        seen, out = set(), []
        for sentence, strong in items:
            if sentence not in seen:
                seen.add(sentence)
                out.append((sentence, strong))
        return out

    found = {k: unique(v) for k, v in found.items()}
    strong_reject = any(strong for _, strong in found["rejected"])
    strong_interview = any(strong for _, strong in found["interview"])

    def result(kind: str, confidence: str, mixed: bool = False) -> dict:
        return {"kind": kind, "confidence": confidence, "quotes": [_quote(s) for s, _ in found[kind][:MAX_QUOTES]], "mixed": mixed}

    if found["offer"]:
        return result("offer", "unsure" if strong_reject else "clear", mixed=strong_reject)
    if found["rejected"] and (strong_reject or not found["interview"]):
        if strong_reject and strong_interview:
            return result("rejected", "unsure", mixed=True)
        return result("rejected", "clear" if strong_reject or len(found["rejected"]) >= 2 else "probably")
    if found["interview"]:
        return result("interview", "clear" if strong_interview or len(found["interview"]) >= 2 else "probably")
    if found["responded"]:
        return result("responded", "probably" if len(found["responded"]) > 1 else "unsure")
    return {"kind": None, "confidence": "unsure", "quotes": [], "mixed": False}
