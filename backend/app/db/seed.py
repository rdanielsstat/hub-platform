"""Seed data so the API has something to log in to and look at.

Two callers, both of which seed only when the demo account doesn't
exist yet, so existing data is never re-seeded, duplicated, or
overwritten:

  - Local: app/db/init_local.py, only with SEED_DEMO_DATA on and never
    with USE_SSM on, into a database with no users. Uses the default,
    publicly-known SEED_USER_PASSWORD.
  - Deployed: app/bootstrap_db.py, only when the environment sets
    DEMO_PASSWORD_PARAM_NAME, always passing the password it read from
    SSM. It never falls back to SEED_USER_PASSWORD.
"""

from datetime import date, datetime, timedelta, timezone

from app.auth.security import hash_password
from app.db.store import Store
from app.models.project import Status

SEED_USER_EMAIL = "demo@hub.dev"
SEED_USER_PASSWORD = "demo1234"


def _days_ago(n: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


def _hours_ago(n: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=n)


def _days_from_now(n: int) -> date:
    return (datetime.now(timezone.utc) + timedelta(days=n)).date()


def _end_of_this_year() -> date:
    return date(datetime.now(timezone.utc).year, 12, 31)


def seed(store: Store, password: str = SEED_USER_PASSWORD) -> None:
    user = store.create_user(
        email=SEED_USER_EMAIL,
        password_hash=hash_password(password),
        display_name="Demo User",
    )

    # 1. Parked, genuinely stale — untouched for months.
    p1 = store.create_project(
        owner_id=user.id,
        name="Dial in a sourdough starter",
        pitch="Keep a starter alive long enough to bake one good loaf.",
        description=(
            "Every attempt so far has died within two weeks. Want to "
            "actually understand hydration and feeding schedules instead "
            "of following recipes blindly."
        ),
        status=Status.PARKED,
        tags=["cooking", "hobby"],
        excitement=2,
        effort=2,
        potential=2,
        next_action="Buy a kitchen scale and try the no-discard method.",
        target_date=None,
        links=[],
        created_at=_days_ago(150),
        updated_at=_days_ago(130),
    )
    store.create_note(
        project_id=p1.id,
        body="Third attempt died. Maybe the kitchen's too cold. Revisit in winter.",
        created_at=_days_ago(130),
    )

    # 2. Exploring, quick win + stale — high excitement/low effort, but
    # hasn't been touched in over a month.
    p2 = store.create_project(
        owner_id=user.id,
        name="Etsy shop for my prints",
        pitch="Turn the illustrations I already make into a tiny income stream.",
        description=(
            "I've got a backlog of prints sitting in a folder. Test "
            "whether anyone would actually pay for them before investing "
            "in inventory."
        ),
        status=Status.EXPLORING,
        tags=["creative", "side-hustle", "art"],
        excitement=4,
        effort=2,
        potential=3,
        next_action="List the first three prints and see if anything sells in a month.",
        target_date=None,
        links=[
            {"label": "Seller guide", "url": "https://www.etsy.com/seller-handbook"},
            {"label": None, "url": "https://www.pinterest.com"},
        ],
        created_at=_days_ago(70),
        updated_at=_days_ago(40),
    )
    store.create_note(
        project_id=p2.id,
        body="Ordered sample prints to check quality",
        created_at=_days_ago(61),
    )
    store.create_note(
        project_id=p2.id,
        body="Shipping costs are brutal for large sizes, maybe stick to A4/A5",
        created_at=_days_ago(49),
    )
    store.create_note(
        project_id=p2.id,
        body="Name idea: 'Second Sun Studio'?",
        created_at=_days_ago(40),
    )

    # 3. Active, stale — deadline still coming, but no progress in weeks.
    p3 = store.create_project(
        owner_id=user.id,
        name="Automate my budgeting spreadsheet",
        pitch="Stop manually typing every transaction into a sheet I abandon by March.",
        description=(
            "The tracking always dies because entry is tedious. If "
            "categorization were automatic I might actually stick with it."
        ),
        status=Status.ACTIVE,
        tags=["finance", "productivity"],
        excitement=3,
        effort=4,
        potential=4,
        next_action="Figure out how to import the bank CSV and auto-categorize.",
        target_date=_days_from_now(21),
        links=[{"label": "Template", "url": "https://docs.google.com/spreadsheets"}],
        created_at=_days_ago(55),
        updated_at=_days_ago(40),
    )
    store.create_note(
        project_id=p3.id,
        body="Categorize transactions automatically, look into bank CSV export",
        created_at=_days_ago(48),
    )
    store.create_note(
        project_id=p3.id,
        body="Manual entry is the thing I always give up on, fix that first",
        created_at=_days_ago(40),
    )

    # 4. Active, recent — target date ~10 weeks out.
    p4 = store.create_project(
        owner_id=user.id,
        name="Train for a half-marathon",
        pitch="Go from couch-ish to 21k without wrecking my knees.",
        description=(
            "Signed up already so there's no backing out. Need a "
            "structured plan rather than just running randomly until "
            "something hurts."
        ),
        status=Status.ACTIVE,
        tags=["health", "running", "fitness"],
        excitement=5,
        effort=4,
        potential=3,
        next_action="Do the week 4 long run this weekend.",
        target_date=_days_from_now(70),
        links=[
            {"label": "Race day", "url": "https://www.runsignup.com"},
            {"label": "12-week plan", "url": "https://www.halhigdon.com"},
        ],
        created_at=_days_ago(21),
        updated_at=_hours_ago(20),
    )
    store.create_note(
        project_id=p4.id,
        body="Week 3 done, knee held up fine",
        created_at=_days_ago(4),
    )
    store.create_note(
        project_id=p4.id,
        body="Need better shoes before mileage ramps",
        created_at=_hours_ago(20),
    )

    # 5. Exploring, the most-noted / most heavily-worked idea.
    p5 = store.create_project(
        owner_id=user.id,
        name="Pivot into UX design",
        pitch="Move from my current role into UX within a year.",
        description=(
            "I keep gravitating toward the design side of every project. "
            "Want to test whether it's a real career move or just a "
            "grass-is-greener thing, before committing money to it."
        ),
        status=Status.EXPLORING,
        tags=["career", "learning", "design"],
        excitement=5,
        effort=5,
        potential=4,
        next_action=(
            "Finish the first module of the UX cert and redesign one "
            "app as a case study."
        ),
        target_date=_days_from_now(182),
        links=[
            {"label": "Course", "url": "https://www.coursera.org"},
            {"label": None, "url": "https://www.behance.net"},
        ],
        created_at=_days_ago(60),
        updated_at=_days_ago(3),
    )
    store.create_note(
        project_id=p5.id,
        body="Talked to Priya who made the switch, coffee notes: portfolio > credentials",
        created_at=_days_ago(50),
    )
    store.create_note(
        project_id=p5.id,
        body="Started the Google UX cert",
        created_at=_days_ago(35),
    )
    store.create_note(
        project_id=p5.id,
        body="Redesign a real app as a case study, pick something I use daily",
        created_at=_days_ago(15),
    )
    store.create_note(
        project_id=p5.id,
        body="Imposter feelings are loud but the work is genuinely fun",
        created_at=_days_ago(3),
    )

    # 6. Inbox, brand new, blank pitch/next action — a raw capture.
    store.create_project(
        owner_id=user.id,
        name="Build my portfolio site",
        pitch="",
        description="Need a personal site. Nothing more than that yet.",
        status=Status.INBOX,
        tags=["web", "career"],
        excitement=3,
        effort=3,
        potential=3,
        next_action="",
        target_date=None,
        links=[],
        created_at=_hours_ago(3),
        updated_at=_hours_ago(3),
    )

    # 7. Active, target date end of this year.
    p7 = store.create_project(
        owner_id=user.id,
        name="Read 24 books this year",
        pitch="Two books a month, actually finished, not just started.",
        description=(
            "I buy books faster than I read them. A visible count might "
            "keep me honest."
        ),
        status=Status.ACTIVE,
        tags=["reading", "habit"],
        excitement=4,
        effort=2,
        potential=3,
        next_action="Pick the next book tonight instead of doom-scrolling.",
        target_date=_end_of_this_year(),
        links=[{"label": "Reading list", "url": "https://www.thestorygraph.com"}],
        created_at=_days_ago(240),
        updated_at=_days_ago(5),
    )
    store.create_note(
        project_id=p7.id,
        body="9 down, ahead of pace. Next: that sci-fi everyone won't shut up about.",
        created_at=_days_ago(5),
    )

    # 8. Parked, somewhat stale (weeks, not months).
    p8 = store.create_project(
        owner_id=user.id,
        name="Learn enough Spanish for the trip",
        pitch="Order food and ask directions without switching to English.",
        description=(
            "Not aiming for fluency, just enough to be polite and get "
            "around. Keeps stalling because app streaks aren't the same "
            "as talking."
        ),
        status=Status.PARKED,
        tags=["language", "learning", "travel"],
        excitement=4,
        effort=3,
        potential=2,
        next_action="Book a few italki conversation sessions.",
        target_date=_days_from_now(120),
        links=[
            {"label": None, "url": "https://www.duolingo.com"},
            {"label": "Podcast", "url": "https://www.duolingo.com/podcast"},
        ],
        created_at=_days_ago(70),
        updated_at=_days_ago(42),
    )
    store.create_note(
        project_id=p8.id,
        body="Duolingo streak died at 12 days lol",
        created_at=_days_ago(49),
    )
    store.create_note(
        project_id=p8.id,
        body="Actually need conversation practice, not more app streaks",
        created_at=_days_ago(42),
    )

    # 9. Killed, old.
    p9 = store.create_project(
        owner_id=user.id,
        name="Start a podcast with the group chat",
        pitch="A casual weekly podcast with the friends.",
        description=(
            "Fun in theory. In practice nobody can commit to a schedule "
            "and I'd end up doing all the editing."
        ),
        status=Status.KILLED,
        tags=["creative", "audio"],
        excitement=2,
        effort=4,
        potential=2,
        next_action="",
        target_date=None,
        links=[],
        created_at=_days_ago(120),
        updated_at=_days_ago(90),
    )
    store.create_note(
        project_id=p9.id,
        body="Everyone's excited for exactly one weekend then vanishes",
        created_at=_days_ago(100),
    )
    store.create_note(
        project_id=p9.id,
        body="Killing this. Fun idea, zero follow-through from anyone including me.",
        created_at=_days_ago(90),
    )

    # 10. Graduated.
    p10 = store.create_project(
        owner_id=user.id,
        name="Declutter and sell old furniture",
        pitch="Clear out the stuff I don't use and make a little cash doing it.",
        description=(
            "Moving soon-ish and half this furniture isn't coming with "
            "me. Sell what's worth selling, donate the rest."
        ),
        status=Status.GRADUATED,
        tags=["home", "minimalism"],
        excitement=3,
        effort=3,
        potential=3,
        next_action="",
        target_date=None,
        links=[{"label": "Listings", "url": "https://www.facebook.com/marketplace"}],
        created_at=_days_ago(60),
        updated_at=_days_ago(21),
    )
    store.create_note(
        project_id=p10.id,
        body="Sold the desk and the bookshelf, $180 total",
        created_at=_days_ago(28),
    )
    store.create_note(
        project_id=p10.id,
        body="Done. Apartment feels twice as big. Worth it.",
        created_at=_days_ago(21),
    )
