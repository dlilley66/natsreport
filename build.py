#!/usr/bin/env python3
"""Fetch Nationals org data from MLB Stats API and write index.html."""
import json, urllib.request, datetime as dt, html
API="https://statsapi.mlb.com/api/v1"
def get(p):
    with urllib.request.urlopen(API+p, timeout=30) as r: return json.load(r)
E=html.escape
import os
DEBUG=os.environ.get('DEBUG_DATE')
today=dt.date.fromisoformat(DEBUG) if DEBUG else dt.date.today()
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
    done=[g for g in gs if g["status"]["abstractGameState"]=="Final" and "score" in g["teams"]["home"] and g["officialDate"]<str(today)]
    up=[g for g in gs if g["officialDate"]>=str(today) and (g["status"]["abstractGameState"]!="Final" or DEBUG)]
    return done[-5:][::-1],up[:3]
LOGO=lambda i:f'<img class="lg" src="https://www.mlbstatic.com/team-logos/{i}.svg" alt="" width="18" height="18">'
def gline(g,tid,plain=False):
    a,h=g["teams"]["away"],g["teams"]["home"]
    st=g["status"]["detailedState"]; d=g.get("officialDate","")
    dd=dt.date.fromisoformat(d).strftime("%b %-d") if d else ""
    url=f'https://www.mlb.com/gameday/{g["gamePk"]}'
    if g["status"]["abstractGameState"]=="Final":
        me,op=(h,a) if h["team"]["id"]==tid else (a,h)
        wl="W" if me.get("isWinner") else "L"
        opp=f"{'vs' if me is h else '@'} {op['team']['name']}"
        sc=f"{me.get('score','?')}–{op.get('score','?')}"
        if plain: return f'<a href="{url}">Nats {"beat" if wl=="W" else "fall to"} {E(op["team"]["name"])} {sc}</a><span class="bmeta">{dd} · Final</span>'
        note=f' <span class="note">{E(st)}</span>' if st!="Final" else ""
        return f'<a class="game" href="{url}"><span class="wl {wl.lower()}">{wl}</span><span class="opp">{'vs' if me is h else '@'} {LOGO(op['team']['id'])}{E(op['team']['name'])}{note}</span><span class="sc">{sc}</span><span class="dt">{dd}</span></a>'
    return f'<a class="game" href="{url}"><span class="wl n">•</span><span class="opp">{E(a["team"]["name"])} @ {E(h["team"]["name"])}</span><span class="sc"></span><span class="dt">{dd}</span></a>'
sections={}; top=None; gaps=[]; nats_upcoming=0
for tid,sid,lbl in TEAMS:
    try:
        d,u=games(tid,sid)
        if tid==120 and d: top=(d[0],tid); nats_upcoming=len(u)
        items=[gline(g,tid) for g in d]+[gline(g,tid) for g in u]
        sections.setdefault("scores",[]).append((lbl,items or ["No games found"],tid))
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
def plink(pe,txt):
    n,_,rest=txt.partition(": ")
    if n.startswith("HR"): n,rest=("HR leader · "+txt[4:].rsplit(" ",1)[0]),txt.rsplit(" ",1)[1]+" HR"
    return f'<a class="pl" href="https://www.mlb.com/player/{pe["id"]}"><span class="nm">{E(n)}</span><span class="st">{E(rest)}</span></a>'
stats=[]
try: FORTY={x["person"]["id"] for x in get("/teams/120/roster?rosterType=40Man")["roster"]}
except Exception: FORTY=set()
for tid,sid,lbl in TEAMS[:3]:
    try:
        h=leaders(tid,sid,"hitting","ops"); p=leaders(tid,sid,"pitching","era",asc=True)
        hr=leaders(tid,sid,"hitting","homeRuns",3)
        ids=",".join(str(pe["id"]) for pe,_ in h+p+hr)
        cur={x["id"]:x.get("currentTeam",{}) for x in get(f"/people?personIds={ids}&hydrate=currentTeam")["people"]} if ids else {}
        def gone(pe):
            if pe["id"] in FORTY: return ""
            c=cur.get(pe["id"],{})
            return "" if (c.get("id") in {t for t,_,_ in TEAMS} or c.get("parentOrgId")==120 or not c) else f" · now with {c.get('name')}"
        it=[plink(pe,f"{pe['fullName']}: {s['avg']}/{s['obp']}/{s['slg']}, {s['homeRuns']} HR, {s['rbi']} RBI{gone(pe)}") for pe,s in h]
        it+=[plink(pe,f"HR: {pe['fullName']} {s['homeRuns']}") for pe,s in hr[:1]]
        it+=[plink(pe,f"{pe['fullName']}: {s['era']} ERA, {s['inningsPitched']} IP, {s['strikeOuts']} K{gone(pe)}") for pe,s in p]
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
import unicodedata
slugs={int(b):a for a,b in _re.findall(r'stories/([a-z0-9-]+-(\d+))"',raw)} if 'raw' in dir() else {}
def pslug(pid):
    if pid in slugs: return slugs[pid]
    n=unicodedata.normalize("NFKD",prospects[pid][1]).encode("ascii","ignore").decode().lower()
    n=_re.sub(r"[^a-z0-9\s-]","",n); n=_re.sub(r"[\s-]+","-",n).strip("-")
    return f"{n}-{pid}"
def purl(pid): return f"https://www.mlb.com/app/atbat/milb/prospects/nationals/{pslug(pid)}"
pname={v[1].lower():k for k,v in prospects.items()}
def prank(x):
    pid=x.get("person",{}).get("id")
    if pid in prospects: return pid
    return pname.get(x.get("person",{}).get("fullName","").lower())
def fmt(x,pid):
    desc=x.get("description") or x.get("typeDesc","")
    if pid:
        r,n,_=prospects[pid]
        desc=desc if n in desc else f"{n}: {desc}"
    d=dt.date.fromisoformat(x.get("date","")[:10]).strftime("%b %d") if x.get("date") else ""
    href=purl(pid) if pid else (f'https://www.mlb.com/player/{x["person"]["id"]}' if x.get("person") else None)
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
top30=[f'<a class="pros" href="{purl(pid)}"><span class="rk">{r}</span><img class="hs" src="https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_60,q_auto:best/v1/people/{pid}/headshot/milb/current" alt="" loading="lazy" width="30" height="30"><span class="nm">{E(n)}</span><span class="pos">{E(pos or "")}</span></a>' for pid,(r,n,pos) in sorted(prospects.items(),key=lambda kv:kv[1][0])]
headline="NATS REPORT"
if top:
    headline=gline(*top,plain=True)
    if not nats_upcoming: headline=headline.replace('· Final</span>','· Final · <b>Offseason</b> — season finale</span>')

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
news_items=[f'<a href="{E(n["link"])}">{E(n["title"])}</a><span class="meta">{E(n["src"])} · {n["date"].strftime("%b %-d") if n["date"] else ""}</span>' for n in nd[:10]]
xp=[]
if os.path.exists("x_posts.json"):
    for p in json.load(open("x_posts.json")).get("posts",[])[:10]:
        txt=p["text"].replace("\n"," "); txt=txt[:220]+("…" if len(txt)>220 else "")
        xp.append(f'<a href="https://x.com/{E(p["username"])}/status/{p["id"]}">{E(txt)}</a><span class="meta">@{E(p["username"])} · {dt.date.fromisoformat(p["created_at"][:10]).strftime("%b %-d")}</span>')
def tile(title,items,cls="",show=99,count=None):
    li=lambda xs:"".join(f"<li>{i}</li>" for i in xs)
    more=f'<details><summary>Show {len(items)-show} more</summary><ul>{li(items[show:])}</ul></details>' if len(items)>show else ""
    return f'<section class="tile {cls}"><h3><span>{E(title)}</span><em>{len(items) if count is None else count}</em></h3><ul>{li(items[:show])}</ul>{more}</section>'
sc=sections.get("scores",[])
nats_sc=[x for x in sc if x[2]==120]; farm=[x for x in sc if x[2]!=120]
def farm_tile():
    parts="".join(f'<div class="lvl">{LOGO(t)}<span>{E(l)}</span></div><ul>'+"".join(f"<li>{i}</li>" for i in items[:3])+"</ul>" for l,items,t in farm)
    return f'<section class="tile score farm"><h3><span>Farm System Scores</span><em>{len(farm)}</em></h3>{parts}</section>'
def htile(title,items,cls,show,logo):
    return tile(title,items,cls,show).replace("<h3><span>",f"<h3><span>{LOGO(logo)}",1)

from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
# ---- prospect season lines (aggregated across levels)
PIT=("RHP","LHP","P")
plines={}
try:
    ids=",".join(map(str,prospects))
    agg={}
    for sp in (1,11,12,13,14):
        for pe in get(f"/people?personIds={ids}&hydrate=stats(group=[hitting,pitching],type=[season],season={YEAR},sportId={sp})")["people"]:
            for st in pe.get("stats",[]):
                g=st["group"]["displayName"]
                spl=st["splits"]
                if any("team" not in x for x in spl): spl=[x for x in spl if "team" not in x]
                for x in spl:
                    a=agg.setdefault((pe["id"],g),{"lv":[]}); a["lv"].append(sp)
                    for k,v in x["stat"].items():
                        if isinstance(v,(int,float)): a[k]=a.get(k,0)+v
    LV={1:"MLB",11:"AAA",12:"AA",13:"A+",14:"A"}
    for pid,(r,n,pos) in prospects.items():
        isp=any(p in (pos or "") for p in PIT)
        a=agg.get((pid,"pitching" if isp else "hitting"))
        if not a: continue
        lv="/".join(LV[x] for x in sorted(set(a["lv"]),key=lambda q:[1,11,12,13,14].index(q)))
        if isp:
            o=a.get("outs",0); ip=o/3 or 0
            if not o: continue
            era=9*a.get("earnedRuns",0)/ip; whip=(a.get("baseOnBalls",0)+a.get("hits",0))/ip
            plines[pid]=f"{lv} · {era:.2f} ERA · {o//3}.{o%3} IP · {a.get('strikeOuts',0)} K · {whip:.2f} WHIP"
        else:
            ab=a.get("atBats",0)
            if not ab: continue
            h,bb,hbp,sf=a.get("hits",0),a.get("baseOnBalls",0),a.get("hitByPitch",0),a.get("sacFlies",0)
            tb=a.get("totalBases",0); f=lambda v:f"{v:.3f}".lstrip("0")
            obp=(h+bb+hbp)/max(1,ab+bb+hbp+sf)
            plines[pid]=f"{lv} · {f(h/ab)}/{f(obp)}/{f(tb/ab)} · {a.get('homeRuns',0)} HR · {a.get('stolenBases',0)} SB"
except Exception as e: gaps.append(f"prospect stats: {e}")
top30=[t.replace('<span class="pos">',f'<span class="pline">{E(plines.get(pid,"No 2026 stats"))}</span><span class="pos">',1) for t,pid in zip(top30,[k for k,_ in sorted(prospects.items(),key=lambda kv:kv[1][0])])]
# ---- Today / next game
CT=ZoneInfo("America/Chicago")
def ct(iso): return dt.datetime.fromisoformat(iso.replace("Z","+00:00")).astimezone(CT)
today_html=""; gameday=False
try:
    sch=get(f"/schedule?sportId=1&teamId=120&startDate={today}&endDate={today+dt.timedelta(days=7)}&hydrate=probablePitcher,linescore,venue")
    gl=[g for d in sch["dates"] for g in d["games"]]
    if gl:
        g=gl[0]; a,h=g["teams"]["away"],g["teams"]["home"]
        state=g["status"]["abstractGameState"]; t=ct(g["gameDate"])
        when=("Today" if g["officialDate"]==str(today) else t.strftime("%a %b %-d"))+" · "+t.strftime("%-I:%M %p CT")
        def side(x):
            pp=x.get("probablePitcher",{}).get("fullName","TBD")
            sc=f'<b class="tsc">{x.get("score","")}</b>' if state!="Preview" else ""
            return f'<div class="tm">{LOGO(x["team"]["id"]).replace("width=\"18\" height=\"18\"","width=\"34\" height=\"34\"")}<div><div class="tn">{E(x["team"]["name"])}</div><div class="pp">{E(pp)}</div></div>{sc}</div>'
        ls=g.get("linescore",{})
        stxt={"Preview":"Scheduled","Live":f'LIVE · {ls.get("inningHalf","")} {ls.get("currentInningOrdinal","")}',"Final":"Final"}.get(state,g["status"]["detailedState"])
        gameday=g["officialDate"]==str(today)
        today_html=f'<section class="tile today wide"><h3><span>{"Today" if g["officialDate"]==str(today) else "Next Game"}</span><em>{E(stxt)}</em></h3>{side(a)}{side(h)}<div class="tmeta">{E(when)} · {E(g.get("venue",{}).get("name",""))} · <a href="https://www.mlb.com/gameday/{g["gamePk"]}">Gameday →</a></div></section>'
    else:
        nx=get(f"/schedule?sportId=1&teamId=120&startDate={today}&endDate={today+dt.timedelta(days=200)}&gameType=R")
        ng=[g for d in nx["dates"] for g in d["games"]]
        if ng: today_html=f'<section class="tile today"><h3><span>Next Game</span></h3><div class="tmeta">Opening Day {ct(ng[0]["gameDate"]).strftime("%a %b %-d, %Y")}</div></section>'
except Exception as e: gaps.append(f"today: {e}")
# ---- standings
stand_html=""; strip=[]
try:
    st=get(f"/standings?leagueId=104&season={YEAR}&date={today}&standingsTypes=regularSeason")
    if not st["records"]: st=get(f"/standings?leagueId=104&season={YEAR}&standingsTypes=regularSeason")
    rec=[r for r in st["records"] if r["division"]["id"]==204]
    rows="".join(f'<tr class="{"us" if t["team"]["id"]==120 else ""}"><td>{LOGO(t["team"]["id"])}{E(t["team"]["name"].split()[-1])}</td><td>{t["wins"]}</td><td>{t["losses"]}</td><td>{t["winningPercentage"]}</td><td>{t["gamesBack"]}</td></tr>' for t in (rec[0]["teamRecords"] if rec else []))
    if rows: stand_html=f'<section class="tile stand"><h3><span>NL East {"Final " if not nats_upcoming else ""}Standings</span><em>{YEAR}</em></h3><table><tr><th></th><th>W</th><th>L</th><th>PCT</th><th>GB</th></tr>{rows}</table>'
    for tid,sid,lbl in TEAMS[1:]:
        lg=get(f"/teams/{tid}")["teams"][0]["league"]["id"]
        s2=get(f"/standings?leagueId={lg}&season={YEAR}&date={today}")
        if not s2["records"]: s2=get(f"/standings?leagueId={lg}&season={YEAR}")
        for r in s2["records"]:
            for t in r["teamRecords"]:
                if t["team"]["id"]==tid: strip.append(f'<div class="aff">{LOGO(tid)}<span>{E(lbl)}</span><b>{t["wins"]}-{t["losses"]}</b><em>{"—" if t["gamesBack"]=="-" else t["gamesBack"]+" GB"}</em></div>')
    if stand_html: stand_html+=(f'<div class="lvl">Affiliates</div>{"".join(strip)}' if strip else "")+"</section>"
except Exception as e: gaps.append(f"standings: {e}")
# ---- rank badges in text
import re as _r2
def badge_html(h):
    if not prospects: return h
    pat=_r2.compile(r"(?<![\w#])("+"|".join(_r2.escape(E(n)) for _,n,_ in prospects.values())+r")(?![\w])")
    rk={E(n):r for r,n,_ in prospects.values()}
    parts=_r2.split(r"(<[^>]+>)",h)
    return "".join(p if p.startswith("<") else pat.sub(lambda m:f'<span class="prk">#{rk[m.group(1)]}</span>{m.group(1)}',p) for p in parts)
tiles=[tile("Latest News",news_items or ["No headlines fetched"],"wide news",6)]
tiles+=[htile("Nationals Scores",i,"score",5,120) for l,i,t in nats_sc]
tiles.append(tile("Nats Roster Moves",nats_items or ["No significant moves in last 60 days"],"moves",6))
tiles.append(tile("Top-30 Prospect Moves",pros_items or ["No prospect moves in last 60 days"],"moves",6))
tiles.append(tile("On X",xp or ["X posts unavailable right now. Will appear on next refresh."],"xtile",5))
tiles.append(farm_tile())
tiles+=[tile("Leaders · "+l.split(" —")[0],i,"stats",8) for l,i in stats]
tiles=[badge_html(t) for t in tiles]
if stand_html: tiles.insert(3,stand_html)
# ---- newsletter tile: latest issue = first entry in newsletter/index.html (newest first), so adding an issue there is all it takes
def latest_issue():
    href,title,when="issue-1.html","Issue #1 · How the Nats can retake the NL East","Week of Oct 15, 2026"
    try:
        m=_r2.search(r'<a class="issue" href="([^"]+)"><b>([^<]+)</b><span>([^<]+)</span>',open("newsletter/index.html",encoding="utf-8").read())
        if m: href,title,when=m.group(1),m.group(2).replace(": "," · ",1),m.group(3)
    except Exception as e: gaps.append(f"newsletter archive: {e}")
    return href,title,when
_nh,_nt,_nw=latest_issue()
tiles.insert(1,f'<section class="tile nl"><h3><span>🪷 The Nats Lilleypad Weekly Report</span></h3><ul><li><a href="newsletter/{_nh}">Latest: {_nt}</a><span class="meta">{_nw}</span></li><li><a href="newsletter/">All issues →</a></li></ul></section>')
if today_html: tiles.insert(0,today_html)
tiles.append(tile("Top 30 Prospects",(top30 or ["Prospect list unavailable"])+[f'<a class="all" href="{PROSPECT_URL}">Full list on MLB.com →</a>'],"stats",10,count=len(top30)))
now=dt.datetime.now().strftime("%b %-d, %-I:%M %p CT")+(f" · SIMULATED {today}" if DEBUG else "")
page=f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="Nats Report">
<meta name="theme-color" content="#14225A"><link rel="manifest" href="manifest.json"><link rel="apple-touch-icon" href="icon.png">
<title>Nats Report</title><style>
:root{{--navy:#14225A;--red:#AB0003;--ink:#151a2d;--mute:#6b7189;--line:#eceef4;--bg:#f2f3f7;color-scheme:light}}
*{{box-sizing:border-box}}html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.4 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Inter,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}}
a{{color:var(--ink);text-decoration:none}}a:hover{{color:var(--red)}}
header{{position:sticky;top:0;z-index:10;background:var(--navy);color:#fff;border-bottom:3px solid var(--red);padding:calc(env(safe-area-inset-top) + 10px) calc(env(safe-area-inset-right) + 16px) 10px calc(env(safe-area-inset-left) + 16px)}}
.hd{{max-width:1180px;margin:0 auto;display:flex;align-items:baseline;justify-content:space-between;gap:12px}}
header h1{{margin:0;font-size:19px;font-weight:800;letter-spacing:.06em}}header h1 span{{color:#ff6b70}}
header p{{margin:0;font-size:12px;color:#c9cfe6;white-space:nowrap}}
main{{max-width:1180px;margin:0 auto;padding:16px calc(env(safe-area-inset-right) + 16px) 8px calc(env(safe-area-inset-left) + 16px)}}
.banner{{background:var(--navy);border-radius:14px;padding:16px 20px;margin-bottom:16px;box-shadow:0 4px 14px rgba(20,34,90,.18);border-left:6px solid var(--red)}}
.banner small{{display:block;color:#ff8a8e;font-weight:700;text-transform:uppercase;letter-spacing:.12em;font-size:11px}}
.banner a{{display:block;color:#fff;font-size:24px;font-weight:800;line-height:1.2;margin-top:4px}}.bmeta{{display:block;color:#c9cfe6;font-size:13px;margin-top:4px}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-items:start}}.wide{{grid-column:span 2}}.grid.mas{{grid-auto-rows:8px;row-gap:0;grid-auto-flow:row dense}}.grid.mas>.tile{{margin-bottom:16px}}
.tile{{background:#fff;border-radius:14px;padding:14px 16px 10px;box-shadow:0 1px 2px rgba(20,34,90,.06),0 4px 14px rgba(20,34,90,.06);min-width:0}}
.tile h3{{display:flex;justify-content:space-between;align-items:center;margin:0 0 6px;padding-bottom:8px;border-bottom:2px solid var(--red);font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--navy)}}
.tile h3 em{{font-style:normal;font-weight:700;font-size:11px;color:var(--mute);background:var(--bg);border-radius:10px;padding:1px 8px}}
ul{{list-style:none;margin:0;padding:0}}li{{padding:8px 0;border-bottom:1px solid var(--line);font-size:14px;line-height:1.35;overflow-wrap:anywhere}}li:last-child{{border:0}}
li>a{{font-weight:600}}.meta{{display:block;color:var(--mute);font-size:12px;font-weight:400;margin-top:2px}}
.game{{display:grid;grid-template-columns:24px minmax(0,1fr) auto 46px;align-items:center;gap:10px;font-weight:500}}
.wl{{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:6px;font-size:12px;font-weight:800;color:#fff}}.wl.w{{background:#1f7a3d}}.wl.l{{background:var(--red)}}.wl.n{{background:var(--mute)}}
.opp{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.sc{{font-weight:800;font-variant-numeric:tabular-nums}}.dt{{color:var(--mute);font-size:12px;text-align:right}}.note{{color:var(--red);font-size:11px}}
.pl{{display:flex;flex-direction:column}}.pl .nm{{font-weight:700}}.pl .st{{color:var(--mute);font-size:12.5px;font-variant-numeric:tabular-nums}}
.pros{{display:flex;align-items:center;gap:10px}}.rk{{flex:none;width:26px;height:26px;border-radius:50%;background:var(--navy);color:#fff;display:grid;place-items:center;font-size:12px;font-weight:800}}
.pros .nm{{font-weight:600;flex:1}}.pos{{font-size:11px;font-weight:700;color:var(--navy);background:#e8ebf5;border-radius:6px;padding:2px 6px}}
.lg{{width:18px;height:18px;vertical-align:-4px;margin-right:6px;object-fit:contain}}.tile h3 .lg{{width:20px;height:20px;vertical-align:-5px}}
.hs{{width:30px;height:30px;border-radius:50%;object-fit:cover;background:#e8ebf5;flex:none}}
.lvl{{display:flex;align-items:center;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);margin:10px 0 0}}.lvl:first-of-type{{margin-top:4px}}
.prk{{display:inline-block;background:var(--red);color:#fff;font-size:10px;font-weight:800;border-radius:5px;padding:1px 4px;margin-right:4px;vertical-align:1px}}
.pros{{flex-wrap:wrap}}.pros .nm{{flex:1 1 auto}}.pline{{flex:1 0 100%;order:9;padding-left:76px;margin-top:-4px;color:var(--mute);font-size:12px;font-variant-numeric:tabular-nums}}
.today .tm{{display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--line)}}.today .tm>div{{flex:1}}.tn{{font-weight:800;font-size:17px}}.pp{{color:var(--mute);font-size:12.5px}}.tsc{{font-size:26px;font-weight:800;font-variant-numeric:tabular-nums}}
.tmeta{{color:var(--mute);font-size:13px;padding-top:8px}}.tmeta a{{color:var(--red);font-weight:700}}
.stand table{{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}}.stand th{{font-size:11px;color:var(--mute);text-align:right;font-weight:700;padding:4px}}.stand td{{padding:6px 4px;border-bottom:1px solid var(--line);text-align:right}}.stand td:first-child{{text-align:left;font-weight:600}}.stand tr.us td{{background:#fff4f4;font-weight:800}}
.aff{{display:grid;grid-template-columns:24px 1fr auto 56px;align-items:center;gap:6px;font-size:13px;padding:5px 0;border-bottom:1px solid var(--line)}}.aff em{{font-style:normal;color:var(--mute);text-align:right;font-size:12px}}
.bmeta b{{color:#ff8a8e;font-weight:700}}
.all{{color:var(--red)!important;font-weight:700;font-size:13px}}
details summary{{list-style:none;cursor:pointer;color:var(--red);font-weight:700;font-size:13px;padding:8px 0 4px}}details summary::-webkit-details-marker{{display:none}}details summary::after{{content:" ▾"}}details[open] summary::after{{content:" ▴"}}details[open] summary{{border-bottom:1px solid var(--line)}}
footer{{text-align:center;color:var(--mute);font-size:12px;padding:16px 16px calc(env(safe-area-inset-bottom) + 20px)}}
@media(max-width:1000px){{.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:700px){{body{{font-size:16px}}.grid{{grid-template-columns:1fr;gap:12px}}.wide{{grid-column:auto}}main{{padding-top:12px}}.banner a{{font-size:20px}}header p{{font-size:11px}}li{{font-size:15px}}.tile{{padding:12px 14px 8px}}}}
</style></head><body><header><div class="hd"><h1>NATS <span>REPORT</span></h1><p>Updated {now}</p></div></header>
<main><div class="banner"><small>Latest</small>{headline}</div><div class="grid">{''.join(tiles)}</div></main>
<script>
(function(){{var g=document.querySelector('.grid');function lay(){{if(getComputedStyle(g).gridTemplateColumns.split(' ').length<2){{g.classList.remove('mas');[].forEach.call(g.children,function(t){{t.style.gridRowEnd=''}});return}}g.classList.add('mas');[].forEach.call(g.children,function(t){{t.style.gridRowEnd='span '+Math.ceil((t.getBoundingClientRect().height+16)/8)}})}}
window.addEventListener('load',lay);window.addEventListener('resize',lay);document.querySelectorAll('details').forEach(function(d){{d.addEventListener('toggle',lay)}});lay()}})();
</script>{'<script>setTimeout(function(){{location.reload()}},300000)</script>' if gameday else ''}<footer>Data: MLB Stats API · MLB Pipeline · MLB.com &amp; Google News · X</footer></body></html>"""
open("index.html","w").write(page)
json.dump({"name":"Nats Report","short_name":"Nats Report","start_url":"./","scope":"./","display":"standalone","background_color":"#ffffff","theme_color":"#14225A","icons":[{"src":"icon.png","sizes":"180x180","type":"image/png"}]},open("manifest.json","w"))
print("gaps:",gaps)
