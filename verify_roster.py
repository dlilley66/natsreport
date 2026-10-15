#!/usr/bin/env python3
"""Check that every player named or linked in a page is still in the Nationals organization.

Usage: python3 verify_roster.py newsletter/issue-2.html [more files...]
- Player IDs come from links (mlb.com/player/<id>, prospect URLs ending in -<id>).
- Full names in the text are matched against every 2026 MLB player and the Nats' current
  40-man, affiliate rosters and Top 30 IDs.
- Each player's current team (people?hydrate=currentTeam) must be the Nats or a Nats affiliate.
Exit code 1 if anyone is flagged, so the workflow step fails before publishing.
Lines marked data-ok="departed" (where a departure is stated on purpose) are reported as OK.
"""
import json, re, sys, html, urllib.request
API = "https://statsapi.mlb.com/api/v1"
def get(p):
    with urllib.request.urlopen(API + p, timeout=30) as r: return json.load(r)

org = {120} | {t["id"] for t in get("/teams/affiliates?teamIds=120")["teams"]}
forty = {x["person"]["id"] for x in get("/teams/120/roster?rosterType=40Man")["roster"]}
mlb_names = {}
for sp in (1,):
    for p in get(f"/sports/{sp}/players?season=2026")["people"]:
        mlb_names.setdefault(p["fullName"], p["id"])

def strip(s): return html.unescape(re.sub(r"<[^>]+>", " ", s))
bad = 0
for f in sys.argv[1:]:
    src = open(f, encoding="utf-8").read()
    # Intentional non-Nats mentions: <span data-ok="departed|other" data-pid="ID">
    ok_departed = set(int(i) for i in re.findall(r'data-ok="(?:departed|other)"[^>]*data-pid="(\d+)"', src))
    ids = set(int(i) for i in re.findall(r"mlb\.com/player/(\d+)", src))
    ids |= set(int(i) for i in re.findall(r"/prospects/nationals/[a-z0-9-]+-(\d+)", src))
    text = strip(src)
    found = [n for n in mlb_names if re.search(r"(?<!\w)" + re.escape(n) + r"(?![\w.])", text)]
    # drop names that only appear inside a longer matched name (e.g. "Luis García" in "Luis García Jr.")
    for n in found:
        if not any(n != m and n in m and text.count(n) == text.count(m) for m in found): ids.add(mlb_names[n])
    if not ids: print(f"{f}: no players found"); continue
    people = []
    idl = sorted(ids)
    for i in range(0, len(idl), 50):
        people += get("/people?personIds=" + ",".join(map(str, idl[i:i+50])) + "&hydrate=currentTeam")["people"]
    print(f"== {f}: {len(people)} players")
    for p in sorted(people, key=lambda p: p["fullName"]):
        ct = p.get("currentTeam", {}); tid = ct.get("id")
        parent = ct.get("parentOrgId", tid)
        in_org = tid in org or parent == 120 or p["id"] in forty
        tag = "40-man" if p["id"] in forty else ("org" if in_org else "")
        if in_org: status = "OK  "
        elif p["id"] in ok_departed: status = "OK* "; tag = "non-Nats mention marked intentional"
        else: status = "FLAG"; bad += 1
        print(f"  {status} {p['fullName']:<24} {ct.get('name','(no team)'):<28} {tag}")
print("\nRESULT:", "all players in org" if not bad else f"{bad} player(s) not in the Nationals org")
sys.exit(1 if bad else 0)
