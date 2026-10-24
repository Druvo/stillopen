"""Job sources every new install starts with, so a candidate sees jobs on day one with no setup and no AI.

Every entry is a public, documented endpoint that needs no key (checked live when this list was written):
a company's own hiring-system board (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee) or a remote-jobs
feed that publishes an open API or RSS. Applied by a data migration (only when the install has no site-wide
sources yet) and by `manage.py seed_sources`, which adds anything missing and never touches what an admin
changed or removed on purpose. The admin can add, pause or delete any of them.

Not here, deliberately: LinkedIn, Indeed, Glassdoor, bdjobs (their terms forbid automated reading or they have no
public feed). Paste one of their links into "Add job" instead.
"""

# name, connector, board_token. Aggregators span many employers; the real employer comes back per posting.
FEEDS = [
    ("Remotive", "remotive", "all"),
    ("RemoteOK", "remoteok", "all"),
    ("We Work Remotely", "weworkremotely", "all"),
    ("Himalayas", "himalayas", "all"),
    ("Jobicy", "jobicy", "all"),
    ("Working Nomads", "workingnomads", "all"),
    ("Arbeitnow", "arbeitnow", "all"),
    ("The Muse", "themuse", "all"),
]

# Companies with a public hiring board. Single-company: the name is the employer.
COMPANIES = [
    ("Ashby", "ashby", "ashby"),
    ("ClickHouse", "ashby", "clickhouse"),
    ("Cohere", "ashby", "cohere"),
    ("Cursor", "ashby", "cursor"),
    ("ElevenLabs", "ashby", "elevenlabs"),
    ("Hightouch", "ashby", "hightouch"),
    ("Linear", "ashby", "linear"),
    ("Modal", "ashby", "modal"),
    ("Notion", "ashby", "notion"),
    ("OpenAI", "ashby", "openai"),
    ("Perplexity", "ashby", "perplexity"),
    ("PostHog", "ashby", "posthog"),
    ("Railway", "ashby", "railway"),
    ("Ramp", "ashby", "ramp"),
    ("Render", "ashby", "render"),
    ("Replit", "ashby", "replit"),
    ("Runway", "ashby", "runway"),
    ("Supabase", "ashby", "supabase"),
    ("Temporal", "ashby", "temporal"),
    ("Zapier", "ashby", "zapier"),
    ("Adyen", "greenhouse", "adyen"),
    ("Agoda", "greenhouse", "agoda"),
    ("Airbnb", "greenhouse", "airbnb"),
    ("Airtable", "greenhouse", "airtable"),
    ("Anduril Industries", "greenhouse", "andurilindustries"),
    ("Anthropic", "greenhouse", "anthropic"),
    ("Asana", "greenhouse", "asana"),
    ("Brex", "greenhouse", "brex"),
    ("Calendly", "greenhouse", "calendly"),
    ("Carta", "greenhouse", "carta"),
    ("Celonis", "greenhouse", "celonis"),
    ("Checkr", "greenhouse", "checkr"),
    ("Chime Financial", "greenhouse", "chime"),
    ("CircleCI", "greenhouse", "circleci"),
    ("Cloudflare", "greenhouse", "cloudflare"),
    ("Cockroach Labs", "greenhouse", "cockroachlabs"),
    ("Coinbase", "greenhouse", "coinbase"),
    ("Contentful", "greenhouse", "contentful"),
    ("Databricks", "greenhouse", "databricks"),
    ("Datadog", "greenhouse", "datadog"),
    ("Discord", "greenhouse", "discord"),
    ("Dropbox", "greenhouse", "dropbox"),
    ("Duolingo", "greenhouse", "duolingo"),
    ("Elastic", "greenhouse", "elastic"),
    ("Epic Games", "greenhouse", "epicgames"),
    ("Fastly", "greenhouse", "fastly"),
    ("Figma", "greenhouse", "figma"),
    ("Fin", "greenhouse", "intercom"),
    ("General Assembly Remote Jobs", "greenhouse", "remote"),
    ("GitLab", "greenhouse", "gitlab"),
    ("Grafana Labs", "greenhouse", "grafanalabs"),
    ("Gusto", "greenhouse", "gusto"),
    ("Instacart", "greenhouse", "instacart"),
    ("KAYAK", "greenhouse", "kayak"),
    ("Klaviyo", "greenhouse", "klaviyo"),
    ("LaunchDarkly", "greenhouse", "launchdarkly"),
    ("Lyft", "greenhouse", "lyft"),
    ("Mixpanel", "greenhouse", "mixpanel"),
    ("MongoDB", "greenhouse", "mongodb"),
    ("Monzo", "greenhouse", "monzo"),
    ("N26", "greenhouse", "n26"),
    ("New Relic", "greenhouse", "newrelic"),
    ("Okta", "greenhouse", "okta"),
    ("PagerDuty", "greenhouse", "pagerduty"),
    ("Pinterest", "greenhouse", "pinterest"),
    ("PlanetScale", "greenhouse", "planetscale"),
    ("Reddit", "greenhouse", "reddit"),
    ("Riot Games", "greenhouse", "riotgames"),
    ("Robinhood", "greenhouse", "robinhood"),
    ("Roblox", "greenhouse", "roblox"),
    ("Samsara", "greenhouse", "samsara"),
    ("Scale AI", "greenhouse", "scaleai"),
    ("SpaceX", "greenhouse", "spacex"),
    ("Squarespace", "greenhouse", "squarespace"),
    ("Stripe", "greenhouse", "stripe"),
    ("Sumo Logic", "greenhouse", "sumologic"),
    ("Toast", "greenhouse", "toast"),
    ("trivago", "greenhouse", "trivago"),
    ("Twilio", "greenhouse", "twilio"),
    ("Vercel", "greenhouse", "vercel"),
    ("Wise Worksite Field Sales", "greenhouse", "wise"),
    ("Wolt - English", "greenhouse", "wolt"),
    ("Zscaler", "greenhouse", "zscaler"),
    ("Outreach", "lever", "outreach"),
    ("Spotify", "lever", "spotify"),
    ("Bunq", "recruitee", "bunq"),
    ("Channable", "recruitee", "channable"),
    ("BoschGroup", "smartrecruiters", "BoschGroup"),
    ("Equinox", "smartrecruiters", "Equinox"),
    ("Experian", "smartrecruiters", "Experian"),
    ("LVMH", "smartrecruiters", "LVMH"),
]


# Boards verified live (2026-10) to have openings in Malaysia, the Gulf or Bangladesh. Added to existing installs once
# by migration 0033 and to new installs with everything else.
REGIONAL = [
    ("Bybit", "greenhouse", "bybit"),
    ("Binance", "greenhouse", "binance"),
    ("Binance (more roles)", "lever", "binance"),
    ("OKX", "greenhouse", "okx"),
    ("Tamara", "greenhouse", "tamara"),
    ("Careem", "greenhouse", "careem"),
    ("Xendit", "greenhouse", "xendit"),
    ("Thunes", "greenhouse", "thunes"),
    ("Coursera", "greenhouse", "coursera"),
    ("Ninja Van", "lever", "ninjavan"),
    ("Lalamove", "lever", "lalamove"),
    ("Airwallex", "ashby", "airwallex"),
    ("Ziina", "ashby", "ziina"),
    ("Snowflake", "ashby", "snowflake"),
    ("Grab", "smartrecruiters", "grab"),
    ("Delivery Hero (Talabat)", "smartrecruiters", "deliveryhero"),
    ("Namshi", "smartrecruiters", "namshi"),
    ("Wise", "smartrecruiters", "wise"),
    ("Unifonic", "recruitee", "unifonic"),
]

# Jooble searches (needs the site's free key; skipped silently without one): one per country, asked with each person's own roles.
JOOBLE = [
    ("Jooble Bangladesh", "jooble", "bd"),
    ("Jooble Malaysia", "jooble", "my"),
    ("Jooble United Arab Emirates", "jooble", "ae"),
    ("Jooble Saudi Arabia", "jooble", "sa"),
    ("Jooble Qatar", "jooble", "qa"),
    ("Jooble Kuwait", "jooble", "kw"),
    ("Jooble Bahrain", "jooble", "bh"),
    ("Jooble Oman", "jooble", "om"),
]

DEFAULT_SOURCES = FEEDS + COMPANIES + REGIONAL + JOOBLE

# Sources whose own published terms allow showing their jobs on a public site (with a visible credit link to the original):
# RemoteOK, Himalayas, Jobicy and Arbeitnow ask exactly that, and an employer's own hiring board exists to be seen.
# NOT here, on purpose: Remotive (forbids sending its jobs to third-party sites and showing them to collect signups),
# We Work Remotely, Working Nomads, The Muse (terms not verified) and Jooble (results belong to Jooble's partners).
# An admin can change any of it per source (Job sources > "Show publicly").
PUBLIC_OK_CONNECTORS = {"greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "remoteok", "himalayas", "jobicy", "arbeitnow"}
