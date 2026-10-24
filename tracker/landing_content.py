"""The words and pictures of the public landing page, apart from the headline and sub-headline (those are editable in the admin).

Every claim here describes something the app really does; tests/tests_public.py checks the ones that can be checked."""
from django.utils.safestring import mark_safe


def _icon(paths: str):
    return mark_safe(
        f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths}</svg>'
    )


ICONS = {
    "search": _icon('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>'),
    "pin": _icon('<path d="M12 22s7-6.2 7-12a7 7 0 10-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="10" r="2.5"/>'),
    "gauge": _icon('<path d="M4 18a8 8 0 1116 0"/><path d="M12 18l4-6"/>'),
    "file": _icon('<path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>'),
    "mail": _icon('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>'),
    "check": _icon('<path d="M20 6L9 17l-5-5"/>'),
    "calendar": _icon('<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>'),
    "bell": _icon('<path d="M18 8a6 6 0 10-12 0c0 7-3 8-3 8h18s-3-1-3-8"/><path d="M10 21a2 2 0 004 0"/>'),
    "shield": _icon('<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>'),
}

FEATURES = [
    (ICONS["search"], "One search, every source",
     "Company career pages and job boards are read together, so you stop checking site after site. Found one somewhere else? Paste the link and it joins the same list."),
    (ICONS["pin"], "Only jobs you can really take",
     "Tell us once where you could work: your country, remote, other countries. Jobs stated to be somewhere you cannot work are left out, and anything unclear is kept and flagged."),
    (ICONS["gauge"], "An honest fit score, no AI needed",
     "We count how many of your main skills a posting mentions, in a number and a sentence. Free, instant and explained. Bring your own AI key later if you want a deeper read."),
    (ICONS["file"], "A CV tailored to each job, truthfully",
     "Your own CV, reshaped toward the posting. Nothing is invented: claims your material does not support are flagged and locked until you approve them. Every version is kept."),
    (ICONS["mail"], "Cover letters in one click",
     "A short, specific letter built from your own words, fact-checked the same way. Edit it, download it as Word or text, and send it yourself."),
    (ICONS["check"], "A calm apply checklist",
     "Is the posting still open, which CV are you sending, a plain email draft. Then you apply on the employer's site and record it; we never apply or message anyone for you."),
    (ICONS["calendar"], "Interviews, referrals and offers",
     "Keep interview times and prep notes, who might refer you, and compare offers side by side in plain numbers, with currencies never silently converted."),
    (ICONS["bell"], "Reminders only when you want them",
     "Follow-up nudges, interview reminders and new-job alerts by email, each switched on by you and each off by default."),
    (ICONS["shield"], "Private and portable",
     "Your data is yours: no ads, no tracking, no third-party scripts. Export everything or delete your account and all of it, whenever you like."),
]

# (what, can you do it by hand, can a spreadsheet do it)
COMPARISON = [
    ("Searches many job sites and career pages for you", False, False),
    ("Shows only jobs you can actually take", False, False),
    ("Scores how well each job fits your skills", False, False),
    ("Tailors your CV and cover letter for each job", False, False),
    ("Remembers what you sent where", False, True),
    ("Reminds you to follow up", False, False),
    ("Tracks interviews, referrals and offers", False, True),
    ("Free, with your data exportable", True, True),
]

FAQ = [
    ("Is it really free?",
     "Yes. Creating an account, searching, scoring, tailoring a CV and writing cover letters cost nothing and need no card. If you choose to connect your own AI service, that provider bills you directly, and it is optional."),
    ("Do I need an AI key or any paid plan?",
     "No. Searching, filtering, the fit score, CV tailoring and cover letters all work without AI. Connect your own key later if you want a more careful read of how you fit."),
    ("Which sites does it search?",
     "Employers' own hiring pages (Greenhouse, Lever, Ashby, SmartRecruiters and Recruitee) and open remote-job boards, many sources at once. Sites that forbid automated reading are never scraped. You can paste a link from any site, including ones we cannot search, and it joins your list."),
    ("Does it apply to jobs for me?",
     "Never. It prepares everything and tracks what you did, but you press apply on the employer's site yourself, and nothing is ever sent to an employer or recruiter on your behalf."),
    ("How is the match percentage worked out?",
     "By counting how many of your main skills a posting mentions, ignoring filler words that nearly every posting repeats. It is a quick estimate, not a verdict. A posting with too little text to judge gets no score instead of a fake one."),
    ("Will it invent things on my CV?",
     "No. Tailoring only rearranges and rewords what your own CV and documents say. Anything it cannot find in your material is flagged, and a flagged CV cannot be downloaded until you review and approve it."),
    ("Which countries does it cover?",
     "Jobs come from sources around the world, and you choose where you would work, such as your own country, remote work, or places like Malaysia and the Gulf. Coverage is strongest for remote and international employers; local job sites that publish no open feed are not included."),
    ("What happens to my CV and data?",
     "Only you can see it. It is stored to run the service for you, never sold, and never used to advertise to you. You can download everything or delete your account and all of it from your profile at any time."),
    ("Is it open source? Can I run it myself?",
     "Yes to both. The code is public under the Apache-2.0 licence. You can use this site or run your own private copy with one Docker command, and your data then stays on your own machine. The self-hosting guide on GitHub walks through it."),
    ("What if a posting has closed?",
     "Jobs that have not been seen for a few days disappear from the public list, and in your own list the 'Are they still open?' check marks closed ones. Always confirm on the employer's page before applying."),
]


def country_rows(stats) -> list:
    """(label, count) rows for the 'where the jobs are' chart: the top countries, then the remote total."""
    rows = [(c["name"], c["n"]) for c in stats["by_country"]]
    if stats["remote"]:
        rows.append(("Remote (any place)", stats["remote"]))
    return sorted(rows, key=lambda r: -r[1])[:9]


def day_rows(stats) -> list:
    """(day of month, count) for the last 14 days, or nothing while there is too little history to chart."""
    return [(str(d["day"].day), d["n"]) for d in stats["by_day"]]
