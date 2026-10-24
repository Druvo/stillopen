"""Starting texts for /privacy/ and /terms/. They describe what StillOpen really does, in plain words.

They are templates, not legal advice: the [bracketed parts] are things only the site owner can say (who runs the site, how to
reach them, which laws apply), and the admin dashboard warns while any bracket is left. Have the final text reviewed for your
country before real people sign up."""
import re

PRIVACY = """Who runs this site: [name of the person or organisation], reachable at [contact email].

What we store: your account (email, username and a one-way hash of your password); the CV text and documents you add (the files themselves are read for their text and then discarded); your job preferences and the places you would work; the jobs you track with your notes and scores; and the interviews, contacts, referrals, offers and cover letters you save. We also keep a short log of your job searches. API keys you add are stored encrypted and are never shown again.

What the job search reads: job lists that employers and job sites publish openly. Reading them sends nothing about you. If the site owner has switched on Jooble, the job titles you are looking for and a country name are sent to Jooble so it can search for you, never your name, email or CV.

Who sees your data: only you. Job postings the search finds are shared facts about the job market, so a posting can show up in other people's searches too, but nobody can see that you tracked it. Site administrators can reach the database for maintenance, so the number of administrators is kept small.

AI features (optional): only when you press a button that needs an AI, the job description, your preferences and the relevant parts of your CV are sent to the AI provider you chose, using your own key. The free keyword checks never leave this server.

Email: we email you to confirm your address (where email is set up) and, only if you turn them on, interview reminders, follow-up reminders and job alerts.

Cookies: one to keep you signed in and one to protect forms. There are no advertising or tracking cookies, and pages load no third-party scripts, fonts or images.

Keeping and deleting: your data stays until you delete it. On your Profile page you can export everything as a file, or delete your account and everything attached to it, straight away. Backups are cleared as they rotate out, within [how long backups are kept].

Your rights: [say how people can ask for access, correction or deletion, and which data-protection law applies where you operate].

Changes: [say how people are told when this page changes].

(Site owner: replace every [bracketed part], and have this reviewed for your country. This is a starting template, not legal advice.)"""

TERMS = """By using [site name] you agree to these terms.

What this is: a personal job-search organiser. It finds job postings that are published openly, helps you track them and prepare applications, and estimates how well a job fits you.

Estimates, not advice: match percentages, fit labels, summaries and anything an AI writes are automated and can be wrong. Check every posting yourself and make your own decisions.

Your content: you own what you add. You allow us to store and process it only to run the service for you. Do not add anything you have no right to share, or anything unlawful.

Your applications: tailored CVs and cover letters are drafts built from what you told us. Read and correct them; you are responsible for anything you send to an employer. We never apply for you and never send anything to an employer or recruiter.

Job postings: postings belong to the employers and sites that published them. We link to them and do not promise that a posting is real, still open or accurate.

Fair use: do not try to break, overload or scrape the service or other people's data, and do not use it to harass anyone. We may limit or close accounts that do.

No warranty: the service is provided as it is, without promises about availability or results, as far as the law allows. [Add your own liability terms.]

Contact: [contact email]. [Which law applies and where disputes are handled.]

(Site owner: replace every [bracketed part], and have this reviewed for your country. This is a starting template, not legal advice.)"""

# What earlier versions shipped, so `manage.py update_legal_text` can tell "never edited" from "the owner's own words".
OLD_PRIVACY = """What we store: your account (email, username), the CV text and documents you add, your job preferences, and the jobs you track with their notes and evaluations. API keys you add are stored encrypted.

Who sees it: only you. Site administrators can access the database for maintenance.

AI features: only when you press Evaluate, the job description, your preferences and the relevant parts of your CV are sent to the AI provider you configured, using your own key. We do not send your data to any AI provider you have not chosen.

Your control: you can export all of your data and delete your account, with everything attached to it, from the Profile page at any time.

(Site owner: replace this text in the admin under Site configuration > Legal with your own policy, including who operates the service and how to contact you.)"""

OLD_TERMS = """This service is provided as is. You are responsible for the content you add and for checking any job posting yourself before applying. The match percentages and summaries are automated estimates, not advice, and can be wrong.

(Site owner: replace this text in the admin under Site configuration > Legal.)"""

_PLACEHOLDER = re.compile(r"\[[^\]\n]{3,}\]|\(Site owner:")


def has_placeholders(text: str) -> bool:
    """True while a [bracketed part] or the old "(Site owner: ...)" note is still in the text."""
    return bool(_PLACEHOLDER.search(text or ""))
