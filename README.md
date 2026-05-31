# otf-class-cal

Subscribable iCalendar feed of the Orangetheory Fitness class schedule for North Hollywood, CA.

## How it works

1. A GitHub Actions workflow runs every 6 hours.
2. It logs in to the unofficial OTF DNA API via AWS Cognito (SRP).
3. Fetches the next 14 days of classes for the configured studio.
4. Generates `schedule.ics` and deploys it to GitHub Pages.
5. Google Calendar subscribes to that URL and shows the schedule alongside your other calendars.

The published feed URL is `https://<username>.github.io/otf-class-cal/schedule.ics` once Pages is enabled.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your OTF email/password
python fetch_schedule.py
```

Outputs `out/schedule.ics`.

## Secrets

In the GitHub repo settings → Secrets and variables → Actions, add:

- `OTF_EMAIL` — your OTF account email
- `OTF_PASSWORD` — your OTF account password
