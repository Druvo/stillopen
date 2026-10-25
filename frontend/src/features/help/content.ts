/** The words of the Help page, as data so a test can check it is complete. Plain words, no jargon, nothing promised that the app does not do. */

export type HelpLink = { label: string; to: string };
export type HelpSection = { id: string; title: string; intro?: string; steps?: string[]; points?: string[]; links?: HelpLink[] };
export type Faq = { question: string; answer: string; link?: HelpLink };

export const SECTIONS: HelpSection[] = [
  {
    id: "start",
    title: "Get started in five steps",
    steps: [
      "Tell us the roles you want and where you would work, in your Profile. Rough is fine; you can change it any time.",
      "Add your CV (upload it, paste it, or build one step by step). Your matches are judged against it.",
      "Look at your dashboard. Jobs from the boards we search for you appear there by themselves, and you can add one you found yourself with Add job.",
      "Press Check my fit on a job to see how well it suits you, what you have that it asks for, and what is missing.",
      "When you apply, open the job's apply screen and record what you sent. We keep the date, your CV and a reminder to follow up.",
    ],
    links: [
      { label: "Your profile", to: "/profile" },
      { label: "Add a job", to: "/jobs/add" },
    ],
  },
  {
    id: "linkedin",
    title: "Get your LinkedIn jobs in",
    intro:
      "LinkedIn, Indeed and Glassdoor do not allow other programs to read their pages, so StillOpen never opens them or signs in for you. You can still bring in the jobs you see there, in three lawful ways. All of them are on Add job.",
    steps: [
      "Turn on a LinkedIn job alert: search for jobs on LinkedIn, then switch on Set alert (it is a toggle at the top of the results). LinkedIn emails you the matches. Open one of those emails, select everything, copy, and paste it into Import from an email on Add job (or save the email as an .eml file and choose it, which keeps the real links). Press Check, untick any job you do not want, then Add selected.",
      "Ask LinkedIn for your data: Settings, then Data privacy, then Get a copy of your data. Choose Jobs (or everything) and request it. LinkedIn emails a download link, which can take minutes or up to a day. On Add job, choose that zip (or its Saved Jobs and Job Applications files) under Import your LinkedIn jobs. Saved jobs come in as Saved and applications you sent come in as Applied with their date. We never read your contact details, phone number or application answers.",
      "Paste the text of any single job: open the job on LinkedIn, select the description, copy it, and paste it on Add job. Pasting a LinkedIn link keeps the link and asks you for the text. Press Fill the form from pasted text and check the result. You can also copy a whole results or notifications list by hand and paste it into Import from an email.",
    ],
    points: [
      "A job brought in from text with no link is saved with a Find it on LinkedIn search link in its notes. It is only a link you click yourself; StillOpen never fetches it.",
      "A company's own careers page is different: if it lists its openings in a standard way, add it under Job sources and we read it the way a search engine does, obeying its robots.txt.",
    ],
    links: [
      { label: "Add a job", to: "/jobs/add" },
      { label: "Job sources", to: "/sources" },
    ],
  },
  {
    id: "score",
    title: "How your match score works",
    intro: "Every job has a match percentage once its fit has been checked. It compares what the posting asks for with what your CV and documents show.",
    points: [
      "The bands are Strong (80% and up), Fair (70 to 79%) and A stretch (under 70%). The site owner can change these numbers.",
      "The free keyword check counts how many of the posting's skills and terms appear in your own material. It costs nothing, makes no network call and never leaves your account.",
      "The AI read goes further: it reads the posting and your CV the way a person would and explains each strength and gap. It needs your own AI key and is only used when you press Check my fit.",
      "Not checked yet means nobody has read this job against your CV so far. It is not a bad score, only no score.",
      "A score can be low because the posting asks for things your CV does not mention, because your CV is short, because the posting is vague, or because the job sits outside the places and pay you said you want. Adding detail to your CV and documents is the quickest way to a fairer score.",
      "A score is a guide to where to spend your time. It is never a prediction of whether you will be hired.",
    ],
    links: [{ label: "Documents", to: "/knowledge" }],
  },
  {
    id: "ai",
    title: "What the AI does and does not do",
    intro: "The AI is optional. Everything important works without it, using plain rules.",
    points: [
      "It uses your own key, which you add in AI settings (a free Google AI Studio key is the easiest). Nothing is billed through StillOpen.",
      "These buttons use it: Check my fit, tailoring a CV, interview questions and feedback on a practice answer, a draft answer to an application question, reading a posting, suggesting roles from your CV, polishing a message, the counter-offer note, prep plans.",
      "Only what a button needs is sent to your AI provider: the job text and the parts of your CV needed for that task. Nothing is sent when you do not press a button.",
      "Job postings, your CV and anything you type are treated as plain text to read, never as instructions. A posting that says 'ignore your rules' changes nothing.",
      "Anything the AI writes about you is checked against your own material. Figures and names it invented are flagged or dropped, but it can still be wrong, so read every word.",
      "The AI never applies, sends or saves anything as your words. It only suggests, and you copy what you want.",
    ],
    links: [{ label: "AI settings", to: "/profile/ai" }],
  },
  {
    id: "ats",
    title: "The ATS check",
    intro: "Many employers use an applicant tracking system (ATS) that reads a CV as plain text before a person does.",
    points: [
      "The ATS check looks at your CV the way a parser commonly does: contact details, clear section headings, dates, bullet points, a single column and plain text, and it says what could trip a parser.",
      "You can also compare it with one of your jobs. It then shows which of the posting's terms your own material really contains, and which it does not. It never suggests adding something you have not done.",
      "It is a checklist of what parsers commonly need. It is not a score from any real ATS, and no public ATS gives scores to compare with, so we do not pretend to give you one.",
      "It is free, uses no AI and sends nothing anywhere.",
    ],
    links: [{ label: "Your CVs", to: "/cv" }],
  },
  {
    id: "keys",
    title: "Keyboard shortcuts",
    points: [
      "Cmd+K (Mac) or Ctrl+K (Windows, Linux) jumps to the search box in the header.",
      "Moving a job card on the board with the keyboard: press Space or Enter on a card to pick it up, use the Left and Right arrow keys to choose a column, press Space to drop it, or Escape to put it back.",
      "Escape closes an open menu, the account menu and dialogs, and puts focus back where you were.",
      "The first Tab on any page offers 'Skip to the page', which jumps past the menu straight to the content.",
    ],
  },
  {
    id: "data",
    title: "Your data",
    points: [
      "Everything you add belongs to you alone. Nobody else can see your jobs, CVs, notes or contacts.",
      "Export a copy of all of it as a file from Profile, under Your data.",
      "You can delete your account from Profile. That removes your jobs, CVs, documents and settings for good. The button asks you to type your username first.",
      "Nothing is ever applied for, sent or posted on your behalf. StillOpen only records what you did and drafts words you can copy.",
    ],
    links: [{ label: "Profile and your data", to: "/profile" }],
  },
  {
    id: "emails",
    title: "About reminders and emails",
    points: [
      "In-app reminders (a follow-up that is due, an interview coming up, a deadline) show on your dashboard under Coming up, with nothing to switch on.",
      "Emails are optional and only go to an address you have confirmed: follow-up reminders, interview reminders, a weekly summary and new-job alerts. Choose them under Profile, in Emails.",
      "An email type also needs the site owner to have switched it on. The Emails card tells you plainly when they have not yet.",
      "Every email links back to the app and ends with a line saying where to change what you get.",
    ],
    links: [{ label: "Emails in your profile", to: "/profile" }],
  },
];

export const FAQ: Faq[] = [
  {
    question: "Why are there jobs from places I do not want?",
    answer:
      "Some boards list remote and on-site roles from everywhere, and a posting that does not say where it is stays unknown rather than guessed. Check the places you would work in your Profile and set Where you would work. A job outside them is flagged, never hidden, so you can still look.",
    link: { label: "Where you would work", to: "/profile" },
  },
  {
    question: "How do I stop a source?",
    answer: "Open Job sources. Boards you added yourself can be switched off or removed there. Boards the site owner runs for everyone can only be changed by the owner.",
    link: { label: "Job sources", to: "/sources" },
  },
  {
    question: "Can I use it without AI?",
    answer:
      "Yes. Searching, the free keyword fit check, the tracker, deadlines, follow-ups, interviews, offers, the ATS check, the CV builder and plain-text drafts all work without a key. The AI only adds deeper reading and polish.",
  },
  {
    question: "What does Check my fit cost?",
    answer:
      "The keyword check is free. The AI check uses your own key, so the cost is whatever your provider charges, usually a fraction of a cent for one job. AI settings shows what you have used this month, as an estimate.",
    link: { label: "AI settings", to: "/profile/ai" },
  },
  {
    question: "How do I delete a job?",
    answer: "Open the job's menu on the dashboard. Not for me sets it aside and can be undone. Remove for good deletes it with its notes and history, after asking you to confirm. You can also tick several jobs and remove them together.",
  },
  {
    question: "What is a prep plan?",
    answer:
      "A short study plan built from the skills a job asks for that your CV does not show. It has weekly lessons with links to official sources and quiz questions. It needs your own AI key and nothing starts until you have read it.",
    link: { label: "Prep plans", to: "/prep" },
  },
  {
    question: "How do I get my data out?",
    answer: "Profile, under Your data, has Export my data. You get one file with everything you added. Your jobs can also be downloaded as a spreadsheet file from the dashboard.",
    link: { label: "Your profile", to: "/profile" },
  },
  {
    question: "Why does a job say it may be closed?",
    answer: "We open each posting's page and look for the phrases sites use when a role is filled. It is a good hint, not a promise, so check the posting yourself before you give up on it.",
  },
  {
    question: "Does StillOpen apply for me?",
    answer: "No, never. It prepares things and records what you did. You send every application and message yourself.",
  },
  {
    question: "Can I add a job from LinkedIn?",
    answer: "LinkedIn does not let other sites read its pages, so we never open them. On Add job you can import your LinkedIn job-alert emails, import your own LinkedIn data (saved jobs and applications), or paste a job link and then the text of the posting; we fill the form from it. See Get your LinkedIn jobs in on this page.",
    link: { label: "Add a job", to: "/jobs/add" },
  },
  {
    question: "My CV did not upload. What now?",
    answer: "Use a PDF, .txt or .md file under 2 MB, or paste the text. We keep the text we read, not the file. If a PDF is a scan, paste the text instead.",
    link: { label: "Your CV", to: "/profile" },
  },
  {
    question: "Why did I not get an email?",
    answer:
      "Emails need three things: the site owner has switched that kind on, you have it ticked in Profile under Emails, and your email address is confirmed. The Emails card shows which of these is missing.",
    link: { label: "Emails", to: "/profile" },
  },
];

export const CONTACT_LINE = "Still stuck? Write to";
