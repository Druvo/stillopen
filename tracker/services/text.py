"""Small shared text helpers."""
import re

STOPWORDS = set(
    "the and for with you your our are will have has from that this who what who all any can able well work team "
    "experience years year role job position company candidate ability skills strong good great including such "
    "etc requirements responsibilities preferred plus must should about their they them more other new using use "
    "based across within into over also not but out per via one two three high level working knowledge understanding".split()
)
# Short tokens that are real skills; everything else under three characters is noise.
SHORT_KEEP = {"c#", "c++", "go", "qa", "ui", "ux", "ml", "ai", "bi", "r", "js", "ts", "db", "ci", "cd"}
_TOKEN = re.compile(r"\.net|[a-z][a-z0-9+#.]*")


def terms(text: str) -> list[str]:
    """Lower-case skill-ish tokens: keeps c#, c++, .net, node.js; drops trailing full stops and stop words."""
    out = []
    for raw in _TOKEN.findall(text.lower()):
        word = raw.rstrip(".")
        if word in STOPWORDS or not word:
            continue
        if len(word) > 2 or word in SHORT_KEEP:
            out.append(word)
    return out
