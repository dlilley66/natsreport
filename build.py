#!/usr/bin/env python3
"""Fetch Nationals org data from MLB Stats API and write index.html."""
import json, urllib.request, datetime as dt, html
API="https://statsapi.mlb.com/api/v1"
def get(p):
    with urllib.request.urlopen(API+p, timeout=30) as r: return json.load(r)
E=html.escape
today=dt.date.today()
TEAMS=[(120,1,"Nationals"),(534,11,"Rochester (AAA)"),(547,12,"Harrisburg (AA)"),(426,13,"Wilmington (High-A)"),(436,14,"Fredericksburg (A)")]
try:
    aff=get("/teams/affiliates?teamIds=120")["teams"]
    m={t["sport"]["id"]:(t["id"],t["name"]) for t in aff if t["sport"]["id"] in (1,11,12,13,14)}
    TEAMS=[(m[s][0],s,lbl) for (_,s,lbl) in TEAMS if s in m]
except Exception as e: print("affiliates fallback",e)
YEAR=today.year
def games(tid,sid):
    s=get(f"/schedule?sportId={sid}&teamId={tid}&startDate={YEAR}-02-15&endDate={today+dt.timedelta(days=60)}&hydrate=linescore")
    gs=[g for d in s["dates"] for g in d["games"]]
    done=[g for g in gs if g["status"]["abstractGameState"]=="Final" and "score" in g["teams"]["home"]]
    up=[g for g in gs if g["status"]["abstractGameState"]!="Final"]
    return done[-5:][::-1],up[:3]
def gline(g,tid):
    a,h=g["teams"]["away"],g["teams"]["home"]
    st=g["status"]["detailedState"]; d=g.get("officialDate","")
    if g["status"]["abstractGameState"]=="Final":
        me,op=(h,a) if h["team"]["id"]==tid else (a,h)
        wl="W" if me.get("isWinner") else "L"
        txt=f"{wl} {me.get('score','?')}-{op.get('score','?')} {'vs' if me is h else '@'} {op['team']['name']} ({d})"
        if st!="Final": txt+=f" [{st}]"
    else:
        txt=f"{a['team']['name']} @ {h['team']['name']} — {d} {st}"
    return f'<a href="https://www.mlb.com/gameday/{g["gamePk"]}">{E(txt)}</a>'
sections={}; top=None; gaps=[]
for tid,sid,lbl in TEAMS:
    try:
        d,u=games(tid,sid)
        if tid==120 and d: top=(d[0],tid)
        items=[gline(g,tid) for g in d]+[ "<b>NEXT:</b> "+gline(g,tid) for g in u]
        sections.setdefault("scores",[]).append((lbl,items or ["No games found"]))
    except Exception as e: gaps.append(f"scores {lbl}: {e}")
def leaders(tid,sid,group,stat,n=5,asc=False):
    r=get(f"/teams/{tid}/roster?rosterType=fullSeason&season={YEAR}&hydrate=person(stats(type=season,season={YEAR},group={group},sportId={sid}))")
    rows=[]
    for p in r.get("roster",[]):
        pe=p["person"]
        for s in pe.get("stats",[]):
            for sp in s.get("splits",[]):
                st=sp["stat"]
                if group=="hitting" and st.get("plateAppearances",0)>=(150 if sid==1 else 100): rows.append((pe,st))
                if group=="pitching" and float(st.get("inningsPitched","0"))>=(40 if sid==1 else 30): rows.append((pe,st))
    key=(lambda x:float(x[1].get(stat) or 0))
    rows.sort(key=key,reverse=not asc)
    seen=set(); rows=[r for r in rows if not (r[0]["id"] in seen or seen.add(r[0]["id"]))]
    return rows[:n]
def plink(pe,txt): return f'<a href="https://www.mlb.com/player/{pe["id"]}">{E(txt)}</a>'
stats=[]
for tid,sid,lbl in TEAMS[:3]:
    try:
        h=leaders(tid,sid,"hitting","ops"); p=leaders(tid,sid,"pitching","era",asc=True)
        hr=leaders(tid,sid,"hitting","homeRuns",3)
        it=[plink(pe,f"{pe['fullName']}: {s['avg']}/{s['obp']}/{s['slg']}, {s['homeRuns']} HR, {s['rbi']} RBI") for pe,s in h]
        it+=[plink(pe,f"HR: {pe['fullName']} {s['homeRuns']}") for pe,s in hr[:1]]
        it+=[plink(pe,f"{pe['fullName']}: {s['era']} ERA, {s['inningsPitched']} IP, {s['strikeOuts']} K") for pe,s in p]
        stats.append((lbl+" — top OPS / ERA (min PA/IP)",it or ["No stats returned"]))
    except Exception as e: gaps.append(f"stats {lbl}: {e}")
import re as _re
PROSPECT_URL="https://www.mlb.com/milb/prospects/nationals"
prospects={}  # id -> (rank, name, pos)
try:
    req=urllib.request.Request(PROSPECT_URL,headers={"User-Agent":"Mozilla/5.0"})
    raw=html.unescape(urllib.request.urlopen(req,timeout=30).read().decode("utf-8","replace"))
    seg=raw[raw.find("getPlayerRankingsFromSelection"):]
    found=_re.findall(r'"RankedPlayerEntity","rank":(\d+),.*?"player":\{"__ref":"Person:(\d+)"\}(?:,"position":"([^"]*)")?',seg)[:30]
    ids=",".join(p for _,p,_ in found)
    names={p["id"]:p["fullName"] for p in get(f"/people?personIds={ids}")["people"]} if ids else {}
    for r,p,pos in found: prospects[int(p)]=(int(r),names.get(int(p),"?"),pos)
except Exception as e: gaps.append(f"prospects: {e}")
pname={v[1].lower():k for k,v in prospects.items()}
def prank(x):
    pid=x.get("person",{}).get("id")
    if pid in prospects: return pid
    return pname.get(x.get("person",{}).get("fullName","").lower())
def fmt(x,pid):
    desc=x.get("description") or x.get("typeDesc","")
    if pid:
        r,n,_=prospects[pid]
        desc=desc.replace(n,f"#{r} {n}",1) if n in desc else f"#{r} {n}: {desc}"
    d=dt.date.fromisoformat(x.get("date","")[:10]).strftime("%b %d") if x.get("date") else ""
    href=f'https://www.mlb.com/player/{x["person"]["id"]}' if x.get("person") else None
    t=f'{E(desc)}<span class="meta">{d}</span>'
    return (f'<a href="{href}">{E(desc)}</a><span class="meta">{d}</span>') if href else t
def noise(x):
    c=x.get("typeCode"); d=(x.get("description") or "").lower()
    if c in ("NUM",): return True
    if c=="SC" and "injured list" not in d: return True
    if c=="ASG": return True
    if "minor league contract" in d or "elected free agency" in d: return True
    return False
start=today-dt.timedelta(days=60)
nats_moves=[]; pros_moves={}
for tid,sid,lbl in TEAMS:
    try:
        t=get(f"/transactions?teamId={tid}&startDate={start}&endDate={today}")["transactions"]
        for x in t:
            pid=prank(x)
            if pid: pros_moves[x["id"]]=(x,pid)
            elif tid==120 and not noise(x): nats_moves.append(x)
    except Exception as e: gaps.append(f"moves {lbl}: {e}")
nats_moves.sort(key=lambda x:x.get("date",""),reverse=True)
from collections import OrderedDict
grp=OrderedDict()
for x in nats_moves: grp.setdefault((x.get("date","")[:10],x.get("typeDesc","")),[]).append(x)
nats_items=[]
for (d,typ),xs in grp.items():
    if len(xs)>=3 and typ in ("Recalled","Optioned","Selected","Designated for Assignment","Released","Outrighted"):
        dd=dt.date.fromisoformat(d).strftime("%b %d")
        names=", ".join(f'<a href="https://www.mlb.com/player/{x["person"]["id"]}">{E(x["person"]["fullName"])}</a>' for x in xs if x.get("person"))
        nats_items.append(f'<b>{len(xs)} players {E(typ.lower())}:</b> {names}<span class="meta">{dd}</span>')
    else: nats_items+= [fmt(x,None) for x in xs]
nats_items=nats_items[:15]
pm=sorted(pros_moves.values(),key=lambda v:v[0].get("date",""),reverse=True)
pros_items=[fmt(x,p) for x,p in pm]
top30=[f'<a href="https://www.mlb.com/player/{pid}">#{r} {E(n)}</a> <span class="meta" style="display:inline">{E(pos or "")}</span>' for pid,(r,n,pos) in sorted(prospects.items(),key=lambda kv:kv[1][0])]
headline="NATS REPORT"
if top: headline=gline(*top)

import xml.etree.ElementTree as ET, email.utils, os
def rss(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=20) as r: root=ET.fromstring(r.read())
    out=[]
    for it in root.iter("item"):
        t=(it.findtext("title") or "").strip(); l=(it.findtext("link") or "").strip()
        src=it.find("source"); src=src.text if src is not None else "MLB.com"
        if src!="MLB.com" and t.endswith(" - "+src): t=t[:-len(src)-3]
        try: d=email.utils.parsedate_to_datetime(it.findtext("pubDate"))
        except Exception: d=None
        out.append(dict(title=t,link=l,src=src,date=d))
    return out
news=[]
for u in ["https://www.mlb.com/nationals/feeds/news/rss.xml","https://news.google.com/rss/search?q=%22Washington+Nationals%22+when:14d&hl=en-US&gl=US&ceid=US:en"]:
    try: news+=rss(u)
    except Exception as e: gaps.append(f"rss {u}: {e}")
seen=set(); nd=[]
for n in sorted(news,key=lambda n:n["date"].timestamp() if n["date"] else 0,reverse=True):
    k="".join(c for c in n["title"].lower() if c.isalnum())[:60]
    if k in seen or not n["title"]: continue
    seen.add(k); nd.append(n)
news_items=[f'<a href="{E(n["link"])}">{E(n["title"])}</a><span class="meta">{E(n["src"])} · {n["date"].strftime("%b %d") if n["date"] else ""}</span>' for n in nd[:10]]
xp=[]
if os.path.exists("x_posts.json"):
    for p in json.load(open("x_posts.json")).get("posts",[])[:10]:
        txt=p["text"].replace("\n"," "); txt=txt[:220]+("…" if len(txt)>220 else "")
        xp.append(f'<a href="https://x.com/{E(p["username"])}/status/{p["id"]}">{E(txt)}</a><span class="meta">@{E(p["username"])} · {E(p["created_at"][:10])}</span>')
def tile(title,items,cls="",show=99):
    li=lambda xs:"".join(f"<li>{i}</li>" for i in xs)
    more=f'<details><summary>More ({len(items)-show})</summary><ul>{li(items[show:])}</ul></details>' if len(items)>show else ""
    return f'<section class="tile {cls}"><h3>{E(title)}</h3><ul>{li(items[:show])}</ul>{more}</section>'
tiles=[tile("Latest News",news_items or ["No headlines fetched"],"wide news",8)]
tiles.append(tile("Nats Roster Moves",nats_items or ["No significant moves in last 60 days"],"moves",7))
tiles.append(tile("Top-30 Prospect Moves",pros_items or ["No prospect moves in last 60 days"],"moves",6))
tiles.append(tile("On X",xp or ["X posts unavailable right now (feed busy). Will appear on next refresh."],"xtile",5))
tiles+=[tile(l,i,"score") for l,i in sections.get("scores",[])]
tiles+=[tile("Leaders · "+l.split(" —")[0],i,"stats",8) for l,i in stats]
tiles.append(tile("Top 30 Prospects (MLB Pipeline)",(top30 or ["Prospect list unavailable"])+[f'<a href="{PROSPECT_URL}">Full list on MLB.com »</a>'],"stats",10))
now=dt.datetime.now().strftime("%b %d, %Y %I:%M %p CT")
page=f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="Nats Report">
<meta name="theme-color" content="#14225A"><link rel="manifest" href="manifest.json"><link rel="apple-touch-icon" href="icon.png">
<title>Nats Report</title><style>
:root{{--navy:#14225A;--red:#AB0003}}
*{{box-sizing:border-box}}body{{margin:0;background:#f3f4f8;color:#1c1f2a;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Helvetica,Arial,sans-serif}}
header{{background:var(--navy);color:#fff;padding:18px 20px calc(18px);border-bottom:4px solid var(--red)}}
header h1{{margin:0;font-size:1.5em;letter-spacing:.5px}}header h1 span{{color:#ff5a5f}}header p{{margin:4px 0 0;opacity:.75;font-size:.85em}}
main{{max-width:1180px;margin:0 auto;padding:14px}}
.banner{{background:#fff;border-left:6px solid var(--red);border-radius:14px;padding:18px 22px;box-shadow:0 2px 10px rgba(20,34,90,.08);margin-bottom:14px}}
.banner small{{color:var(--red);font-weight:700;text-transform:uppercase;letter-spacing:1px;font-size:.75em}}
.banner a{{display:block;color:var(--navy);font-size:1.45em;font-weight:800;margin-top:4px;text-decoration:none}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;align-items:start}}.wide{{grid-column:span 2}}
.tile{{background:#fff;border-radius:14px;padding:12px 16px;box-shadow:0 2px 10px rgba(20,34,90,.08)}}
.tile h3{{margin:0 0 10px;font-size:.8em;text-transform:uppercase;letter-spacing:1px;color:var(--navy);border-bottom:2px solid var(--red);padding-bottom:8px}}
ul{{list-style:none;margin:0;padding:0}}li{{padding:5px 0;border-bottom:1px solid #eef0f5;font-size:.86em;line-height:1.3}}.meta{{display:block;color:#7a8099;font-size:.82em;font-weight:400;margin-top:2px}}details summary{{cursor:pointer;color:#AB0003;font-weight:700;font-size:.82em;padding-top:6px}}.score li{{font-size:.84em}}li:last-child{{border:0}}
li a{{color:#1c1f2a;text-decoration:none;font-weight:600}}li a:hover{{color:var(--red)}}
footer{{text-align:center;color:#888;font-size:.8em;padding:20px}}
@media(max-width:1000px){{.grid{{grid-template-columns:1fr 1fr}}}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}.wide{{grid-column:auto}}main{{padding:12px}}.banner a{{font-size:1.15em}}}}
</style></head><body><header><h1>NATS <span>REPORT</span></h1><p>Washington Nationals · MLB &amp; Minors · Updated {now}</p></header>
<main><div class="banner"><small>Latest</small>{headline}</div><div class="grid">{''.join(tiles)}</div></main>
<footer>Data: MLB Stats API</footer></body></html>"""
open("index.html","w").write(page)
json.dump({"name":"Nats Report","short_name":"Nats Report","start_url":"./","scope":"./","display":"standalone","background_color":"#ffffff","theme_color":"#14225A","icons":[{"src":"icon.png","sizes":"180x180","type":"image/png"}]},open("manifest.json","w"))
print("gaps:",gaps)
