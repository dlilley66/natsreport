#!/usr/bin/env python3
"""Decide whether a game-hours refresh should build. Prints run=true/false (and writes to $GITHUB_OUTPUT).
Builds only if a Nats game (teamId 120) is live, or 'now' is within 1h before to 4h after first pitch.
Test: DEBUG_NOW=2026-07-12T13:30:00-05:00 python3 gate.py"""
import json, os, sys, urllib.request, datetime as dt
from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago")
now = dt.datetime.fromisoformat(os.environ["DEBUG_NOW"]) if os.environ.get("DEBUG_NOW") else dt.datetime.now(dt.timezone.utc)
d = now.astimezone(CT).date()
url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=120&startDate={d - dt.timedelta(days=1)}&endDate={d}"
run, why = False, f"no Nats game window at {now.astimezone(CT):%Y-%m-%d %H:%M} CT"
try:
    games = [g for x in json.load(urllib.request.urlopen(url, timeout=20))["dates"] for g in x["games"]]
    for g in games:
        start = dt.datetime.fromisoformat(g["gameDate"].replace("Z", "+00:00"))
        live = g["status"]["abstractGameState"] == "Live" and not os.environ.get("DEBUG_NOW")
        if live or start - dt.timedelta(hours=1) <= now <= start + dt.timedelta(hours=4):
            run, why = True, f"game {g['gamePk']} ({g['status']['detailedState']}) starts {start.astimezone(CT):%m-%d %H:%M} CT"
            break
except Exception as e:
    why = f"schedule check failed: {e}"
print(f"run={'true' if run else 'false'}  # {why}")
if os.environ.get("GITHUB_OUTPUT"):
    open(os.environ["GITHUB_OUTPUT"], "a").write(f"run={'true' if run else 'false'}\n")
