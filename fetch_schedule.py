"""Fetch OTF class schedule and emit an iCalendar feed."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from botocore import UNSIGNED
from botocore.config import Config
from dotenv import load_dotenv
from icalendar import Calendar, Event
from pycognito import Cognito

STUDIO_UUID = "72e59921-7aa6-4be5-9e0a-2ae469a05342"  # North Hollywood, CA
STUDIO_LABEL = "OTF North Hollywood"

COGNITO_USER_POOL_ID = "us-east-1_dYDxUeyL1"
COGNITO_CLIENT_ID = "3dt9jpd58ej69f4183rqjrsu7c"
COGNITO_REGION = "us-east-1"

API_BASE = "https://api.orangetheory.io"
CLASSES_PATH = "/v1/classes"

HORIZON_DAYS = 14
OUTPUT_PATH = Path("out/schedule.ics")

DEEP_LINK_BASE = "https://mobile.orangetheory.com/app?screen=booking"


def login(email: str, password: str) -> str:
    # Cognito User Pool InitiateAuth is unauthenticated; force unsigned
    # requests so boto3 doesn't try to load AWS creds from the environment.
    u = Cognito(
        user_pool_id=COGNITO_USER_POOL_ID,
        client_id=COGNITO_CLIENT_ID,
        user_pool_region=COGNITO_REGION,
        username=email,
        boto3_client_kwargs={"config": Config(signature_version=UNSIGNED)},
    )
    u.authenticate(password=password)
    return u.id_token


def fetch_classes(id_token: str) -> list[dict]:
    r = httpx.get(
        f"{API_BASE}{CLASSES_PATH}",
        params={"studio_ids": STUDIO_UUID},
        headers={"Authorization": f"Bearer {id_token}"},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()["items"]


def filter_classes(classes: list[dict], now: datetime) -> list[dict]:
    horizon = now + timedelta(days=HORIZON_DAYS)
    out = []
    for c in classes:
        if c.get("canceled"):
            continue
        starts = datetime.fromisoformat(c["starts_at"].replace("Z", "+00:00"))
        if starts < now or starts > horizon:
            continue
        out.append(c)
    return sorted(out, key=lambda c: c["starts_at"])


def event_title(c: dict) -> str:
    name = c["name"]
    coach_first = (c.get("coach") or {}).get("first_name", "")
    base = f"{name} — {coach_first}" if coach_first else name
    if c.get("full"):
        if c.get("waitlist_available"):
            return f"{base} [Waitlist {c.get('waitlist_size', 0)}]"
        return f"{base} [FULL]"
    return base


def event_location(c: dict) -> str:
    s = c.get("studio") or {}
    addr = s.get("address") or {}
    parts = [addr.get("line1"), addr.get("city"), addr.get("state"), addr.get("postal_code")]
    return ", ".join(p for p in parts if p)


def event_description(c: dict, refreshed_at: datetime) -> str:
    cap = c.get("max_capacity", 0)
    waitlist = c.get("waitlist_size", 0)
    if c.get("full"):
        status = f"FULL · {waitlist} on waitlist" if waitlist else "FULL"
    else:
        status = f"Open · {waitlist} on waitlist" if waitlist else "Open"

    coach = (c.get("coach") or {}).get("first_name", "—")
    studio_name = (c.get("studio") or {}).get("name", "—")

    lines = [
        f"{status} ({cap}-seat class)",
        f"Coach: {coach}",
        f"Studio: {studio_name}",
        f"Last refreshed: {refreshed_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Class ID: {c['id']}",
        "",
        f"Open in OTF app: {DEEP_LINK_BASE}",
    ]
    return "\n".join(lines)


def build_calendar(classes: list[dict], refreshed_at: datetime) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//otf-class-cal//EN")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", STUDIO_LABEL)
    cal.add("X-WR-CALDESC", f"Class schedule for {STUDIO_LABEL}. Refreshes every 6 hours.")
    cal.add("X-PUBLISHED-TTL", "PT6H")
    cal.add("REFRESH-INTERVAL;VALUE=DURATION", "PT6H")

    for c in classes:
        ev = Event()
        ev.add("uid", f"{c['id']}@otf-class-cal")
        ev.add("summary", event_title(c))
        ev.add("dtstart", datetime.fromisoformat(c["starts_at"].replace("Z", "+00:00")))
        ev.add("dtend", datetime.fromisoformat(c["ends_at"].replace("Z", "+00:00")))
        ev.add("dtstamp", refreshed_at)
        ev.add("last-modified", refreshed_at)
        ev.add("location", event_location(c))
        ev.add("description", event_description(c, refreshed_at))
        cal.add_component(ev)

    return cal


def main() -> int:
    load_dotenv()
    email = os.environ.get("OTF_EMAIL")
    password = os.environ.get("OTF_PASSWORD")
    if not email or not password:
        print("Missing OTF_EMAIL or OTF_PASSWORD", file=sys.stderr)
        return 1

    refreshed_at = datetime.now(timezone.utc).replace(microsecond=0)

    print("Logging in to Cognito…", file=sys.stderr)
    token = login(email, password)

    print("Fetching classes…", file=sys.stderr)
    raw = fetch_classes(token)
    print(f"  got {len(raw)} classes from API", file=sys.stderr)

    classes = filter_classes(raw, refreshed_at)
    print(f"  {len(classes)} within next {HORIZON_DAYS} days, non-canceled", file=sys.stderr)

    cal = build_calendar(classes, refreshed_at)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(cal.to_ical())
    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
