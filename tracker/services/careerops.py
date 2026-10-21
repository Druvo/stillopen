"""Read the career-ops tracker, reports and generated PDFs, and import them."""
import posixpath
import re
from datetime import date
from pathlib import Path

from tracker.models import Application, Bucket, Document, DocumentKind, Insight, Status

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
LIST_KEYS = {"soft_gaps": "gap", "hard_stops": "gap", "top_strengths": "strength"}


class ImportErrorMessage(Exception):
    pass


def tracker_file(root: Path) -> Path:
    canonical = root / "data" / "applications.md"
    return canonical if canonical.exists() else root / "applications.md"


def parse_tracker_table(markdown: str) -> list[dict]:
    lines = [ln for ln in markdown.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        return []

    def split(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]

    header = [h.lower() for h in split(lines[0])]
    rows = []
    for line in lines[2:]:
        cells = split(line)
        if len(cells) != len(header):
            continue
        row = dict(zip(header, cells))
        m = re.search(r"\[([^\]]*)\]\(([^)]+)\)", row.get("report", ""))
        report_rel = ""
        if m:
            # Links are relative to data/applications.md's own folder.
            report_rel = posixpath.normpath(posixpath.join("data", m.group(2)))
        score_raw = row.get("score", "").replace("/5", "").strip()
        try:
            score = float(score_raw)
        except ValueError:
            score = None
        rows.append(
            {
                "num": row.get("#", ""),
                "date": row.get("date", ""),
                "company": row.get("company", ""),
                "role": row.get("role", ""),
                "score": score,
                "status": row.get("status", ""),
                "report": report_rel,
                "notes": row.get("notes", ""),
                "url": row.get("url", ""),
            }
        )
    return rows


def _unquote(v: str) -> str:
    s = v.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1]
    return s


def parse_machine_summary(md: str) -> dict:
    m = re.search(r"```yaml\s*\r?\n(.*?)\r?\n```", md, re.S)
    if not m:
        return {}
    out: dict = {}
    list_key = None
    for line in m.group(1).splitlines():
        top = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if top:
            key, val = top.groups()
            if val == "" and key in LIST_KEYS:
                out[key] = []
                list_key = key
            else:
                list_key = None
                if key not in ("requirement_importance", "risk_summary"):
                    u = _unquote(val)
                    out[key] = None if u == "null" else u
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and list_key:
            out[list_key].append(_unquote(item.group(1)))
    return out


def parse_tldr(md: str) -> str:
    m = re.search(r"\|\s*TL;DR\s*\|\s*(.+?)\s*\|\s*$", md, re.M)
    return m.group(1).replace("**", "").strip() if m else ""


def parse_deadline(text: str) -> date | None:
    m = re.search(r"deadline[^0-9]{0,12}(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4})", text or "", re.I)
    if not m:
        return None
    mon = MONTHS.get(m.group(2).lower())
    if not mon:
        return None
    try:
        return date(int(m.group(3)), mon, int(m.group(1)))
    except ValueError:
        return None


def slug_for(report_rel: str, company: str) -> str:
    if report_rel:
        base = Path(report_rel).stem
        base = re.sub(r"^\d+-", "", base)
        return re.sub(r"-\d{4}-\d{2}-\d{2}$", "", base)
    return re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")


def pdfs_for(slug: str, output_dir: Path) -> list[Path]:
    if not slug or not output_dir.is_dir():
        return []
    rx = re.compile(r"(^|-)" + re.escape(slug) + r"(-|\.)")
    return [p for p in output_dir.glob("*.pdf") if rx.search(p.name.lower())]


def _kind_for(name: str, kinds: list[DocumentKind]) -> DocumentKind | None:
    for k in kinds:
        if k.matches(name):
            return k
    return None


def _status(name: str) -> Status:
    existing = Status.objects.filter(name__iexact=name).first()
    if existing:
        return existing
    bucket = Bucket.objects.order_by("order").first()
    if bucket is None:
        raise ImportErrorMessage("No buckets configured. Run migrations to seed defaults.")
    return Status.objects.create(name=name, bucket=bucket, order=99)


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        return date.today()


def import_all(config, sync_status: bool = False) -> dict:
    """Idempotent import. New applications are created; existing ones refresh evaluation data only.

    Status, notes, URL, company and role of an existing application are never overwritten
    unless sync_status is set (status only)."""
    if not config.careerops_path:
        raise ImportErrorMessage("Set the career-ops folder in Site configuration first.")
    root = Path(config.careerops_path)
    tf = tracker_file(root)
    if not tf.exists():
        raise ImportErrorMessage(f"Tracker not found: {tf}")

    kinds = list(DocumentKind.objects.all())
    default_kind = _kind_for("cv", kinds) or (kinds[0] if kinds else None)
    report_kind = DocumentKind.objects.filter(name__iexact="report").first()
    counts = {"created": 0, "updated": 0, "documents": 0}

    for row in parse_tracker_table(tf.read_text(encoding="utf-8")):
        try:
            num = int(row["num"])
        except ValueError:
            continue

        report_md = ""
        summary, tldr = {}, ""
        report_file = root / row["report"] if row["report"] else None
        if report_file and report_file.is_file():
            report_md = report_file.read_text(encoding="utf-8")
            summary = parse_machine_summary(report_md)
            tldr = parse_tldr(report_md)

        app = Application.objects.filter(careerops_num=num).first()
        created = app is None
        if created:
            status = _status(row["status"] or "Evaluated")
            app = Application(
                careerops_num=num,
                company=row["company"],
                role=row["role"],
                url=row["url"] if row["url"].startswith("http") else "",
                status=status,
                found_date=_parse_date(row["date"]),
                notes=row["notes"],
            )
            if status.counts_as_applied:
                app.applied_date = _parse_date(row["date"])
        elif sync_status and row["status"]:
            app.status = _status(row["status"])

        score = row["score"]
        if score is not None:
            app.score = score
        app.decision = summary.get("final_decision") or app.decision
        app.legitimacy = summary.get("legitimacy_tier") or app.legitimacy
        risk = summary.get("risk_level") or ""
        app.risk = risk if risk in ("Low", "Medium", "High") else app.risk
        app.summary = tldr or app.summary
        app.next_action = summary.get("next_action") or app.next_action
        app.advertised_pay = summary.get("advertised_comp") or app.advertised_pay
        app.report_path = row["report"] or app.report_path
        app.deadline = parse_deadline(row["notes"]) or app.deadline
        app.save()

        app.insights.all().delete()
        order = 0
        for key, kind in LIST_KEYS.items():
            for text in summary.get(key) or []:
                Insight.objects.create(application=app, kind=kind, text=text[:500], order=order)
                order += 1

        slug = slug_for(row["report"], row["company"])
        best: dict[int, Path] = {}
        for p in pdfs_for(slug, root / "output"):
            kind = _kind_for(p.name, kinds) or default_kind
            if kind is None:
                continue
            cur = best.get(kind.id)
            if cur is None or p.stat().st_mtime > cur.stat().st_mtime:
                best[kind.id] = p
        kinds_by_id = {k.id: k for k in kinds}
        for kind_id, p in best.items():
            _, doc_created = Document.objects.get_or_create(
                application=app,
                source_path=str(p),
                defaults={"kind": kinds_by_id[kind_id], "title": p.name},
            )
            counts["documents"] += int(doc_created)
        if report_kind and report_file and report_file.is_file():
            _, doc_created = Document.objects.get_or_create(
                application=app,
                source_path=str(report_file),
                defaults={"kind": report_kind, "title": report_file.name},
            )
            counts["documents"] += int(doc_created)

        counts["created" if created else "updated"] += 1
    return counts
