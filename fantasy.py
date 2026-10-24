#!/usr/bin/env python3
"""Builds fantasy/index.html, a general (not league-specific) fantasy football page for the family.
Sources (all free, no keys): ESPN public scoreboard + injuries JSON, Sleeper trending players API
(player map cached in data/sleeper_players.json, refreshed at most weekly), Rotowire / FantasyPros / ESPN /
Google News RSS. Every source is optional: a failed fetch just shows a short note in its tile.
build.py imports season() for the main-page tile and runs this script at the end of each build.
Test offseason: FF_FORCE_OFFSEASON=1 python3 fantasy.py"""
import json, os, re, html, time, urllib.request, urllib.parse, datetime as dt, email.utils, unicodedata
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
CT=ZoneInfo("America/Chicago"); E=html.escape; UA={"User-Agent":"Mozilla/5.0"}
ESPN="https://site.api.espn.com/apis/site/v2/sports/football/nfl/"
CACHE="data/sleeper_players.json"; TITLE="Lilley Family Fantasy HQ"
gaps=[]
def fetch(url,timeout=30):
    return urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=timeout).read()
def getj(url,what):
    try: return json.loads(fetch(url))
    except Exception as e: gaps.append(f"{what}: {e}"); return None
_sb=None
def scoreboard():
    global _sb
    if _sb is None: _sb=getj(ESPN+"scoreboard","espn scoreboard") or {}
    return _sb
def season():
    """(in_season, week, season_type_label). ESPN season type 2=regular, 3=postseason. Falls back to Sep 1-Feb 15."""
    if os.environ.get("FF_FORCE_OFFSEASON"): return False,None,"Offseason"
    sb=scoreboard(); st=(sb.get("season") or {}).get("type"); wk=(sb.get("week") or {}).get("number")
    if st in (2,3): return True,wk,("Regular Season" if st==2 else "Playoffs")
    if st in (1,4): return False,None,("Preseason" if st==1 else "Offseason")
    d=dt.date.today(); ins=d.month>=9 or d.month==1 or (d.month==2 and d.day<=15)
    return ins,wk,("Season" if ins else "Offseason")
# ---------- helpers
def norm(n):
    n=unicodedata.normalize("NFKD",n or "").encode("ascii","ignore").decode().lower()
    n=re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?","",n); return re.sub(r"[^a-z]","",n)
def ct(iso): return dt.datetime.fromisoformat(iso.replace("Z","+00:00")).astimezone(CT)
def tile(title,items,cls="",show=99,count=None):
    li=lambda xs:"".join(f"<li>{i}</li>" for i in xs)
    more=f'<details><summary>Show {len(items)-show} more</summary><ul>{li(items[show:])}</ul></details>' if len(items)>show else ""
    cnt=len(items) if count is None else count
    return f'<section class="tile {cls}"><h3><span>{title}</span>{f"<em>{cnt}</em>" if cnt!="" else ""}</h3><ul>{li(items[:show])}</ul>{more}</section>'
def note(t): return f'<span class="muted">{E(t)}</span>'
def rss(url,default_src=""):
    out=[]
    try:
        root=ET.fromstring(fetch(url,20))
        for it in root.iter("item"):
            t=(it.findtext("title") or "").strip(); l=(it.findtext("link") or "").strip()
            s=it.find("source"); src=s.text if s is not None and s.text else default_src
            if s is not None and src and t.endswith(" - "+src): t=t[:-len(src)-3]
            pd=(it.findtext("pubDate") or "").strip(); d=None
            m=re.match(r"\w+, (\d+ \w+ \d{4} \d+:\d\d:\d\d [AP]M) ([PMCE])([SD])T$",pd)  # RotoWire: 12h clock + US zone
            if m:
                try: d=dt.datetime.strptime(m.group(1),"%d %b %Y %I:%M:%S %p").replace(tzinfo=dt.timezone(dt.timedelta(hours=-{"P":8,"M":7,"C":6,"E":5}[m.group(2)]+(m.group(3)=="D"))))
                except Exception: d=None
            if d is None:
                try: d=email.utils.parsedate_to_datetime(pd)
                except Exception: d=None
            if d and d.tzinfo is None: d=d.replace(tzinfo=dt.timezone.utc)
            if t: out.append(dict(title=t,link=l,src=src,date=d,desc=(it.findtext("description") or "").strip()))
    except Exception as e: gaps.append(f"rss {url[:60]}: {e}")
    return out
def dedupe(items,n):
    seen=set(); res=[]
    for x in sorted(items,key=lambda x:x["date"].timestamp() if x["date"] else 0,reverse=True):
        k=re.sub(r"[^a-z0-9]","",x["title"].lower())[:60]
        if k in seen: continue
        seen.add(k); res.append(x)
    return res[:n]
def nitem(x): return f'<a href="{E(x["link"])}">{E(x["title"])}</a><span class="meta">{E(x["src"])}{" · "+x["date"].astimezone(CT).strftime("%a %b %-d") if x["date"] else ""}</span>'
# ---------- Sleeper player map (slim, cached, weekly refresh at most)
def players():
    cache={}
    try: cache=json.load(open(CACHE))
    except Exception: pass
    age=time.time()-cache.get("fetched",0)
    if cache.get("players") and age<7*86400: return cache["players"]
    try:
        raw=json.loads(fetch("https://api.sleeper.app/v1/players/nfl",90)); slim={}
        for pid,p in raw.items():
            pos=p.get("position")
            if pos not in ("QB","RB","WR","TE","K") or not p.get("active"): continue
            slim[pid]=[p.get("full_name") or f'{p.get("first_name","")} {p.get("last_name","")}'.strip(),pos,p.get("team") or "FA",p.get("search_rank") or 9999,p.get("espn_id")]
        os.makedirs("data",exist_ok=True)
        json.dump({"fetched":int(time.time()),"source":"https://api.sleeper.app/v1/players/nfl","players":slim},open(CACHE,"w"),separators=(",",":"))
        print("fantasy: refreshed Sleeper player cache",len(slim)); return slim
    except Exception as e:
        gaps.append(f"sleeper players: {e}"); return cache.get("players",{})
TEAMFIX={"WAS":"WSH","JAC":"JAX","LA":"LAR"}
def main():
    ins,wk,lbl=season(); sb=scoreboard(); now=dt.datetime.now(CT)
    yr=(sb.get("season") or {}).get("year") or now.year
    tiles=[]; byes=[]; live=False
    if ins:
        P=players(); byid={str(v[4]):v for v in P.values() if v[4]}; byname={}
        for v in P.values(): byname.setdefault((norm(v[0]),v[2]),v)
        # ---- injuries (ESPN), key fantasy players only (Sleeper search rank <= 200)
        inj=getj(ESPN+"injuries","espn injuries"); injmap={}; rows=[]
        for t in (inj or {}).get("injuries",[]):
            for x in t.get("injuries",[]):
                a=x.get("athlete",{}); pos=(a.get("position") or {}).get("abbreviation"); team=(a.get("team") or {}).get("abbreviation","")
                if pos not in ("QB","RB","WR","TE","K"): continue
                m=re.search(r"/players/full/(\d+)\.png",(a.get("headshot") or {}).get("href",""))
                sp=byid.get(m.group(1)) if m else None
                sp=sp or byname.get((norm(a.get("displayName")),TEAMFIX.get(team,team))) or byname.get((norm(a.get("displayName")),team))
                rank=sp[3] if sp else 9999; st=x.get("status","")
                injmap[norm(a.get("displayName"))]=st
                d=x.get("details") or {}
                rows.append(dict(name=a.get("displayName",""),pos=pos,team=team,st=st,rank=rank,body=d.get("type",""),
                    ret=d.get("returnDate",""),cm=x.get("shortComment",""),date=x.get("date",""),
                    href=next((l["href"] for l in a.get("links",[]) if "playercard" in l.get("rel",[])),"")))
        ORDER={"Out":0,"Doubtful":1,"Questionable":2}
        key=[r for r in rows if r["st"] in ORDER and r["rank"]<=200]
        key.sort(key=lambda r:(ORDER[r["st"]],r["rank"]))
        cls={"Out":"o","Doubtful":"d","Questionable":"q","Injured Reserve":"ir"}
        def irow(r):
            body=f" ({E(r['body'])})" if r["body"] and r["body"]!="Not Specified" else ""
            nm=f'<a href="{E(r["href"])}">{E(r["name"])}</a>' if r["href"] else E(r["name"])
            when=ct(r["date"]).strftime("%b %-d") if r["date"] else ""
            return f'<div class="ij"><span class="tag {cls.get(r["st"],"")}">{E({"Injured Reserve":"IR"}.get(r["st"],r["st"][0]))}</span><span class="nm">{nm}<span class="pos">{E(r["pos"])}</span> <span class="tm2">{E(r["team"])}</span>{body}</span></div><span class="meta">{E(r["cm"][:200])}{" · "+when if when else ""}</span>'
        cut=(now-dt.timedelta(days=7)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        newir=sorted([r for r in rows if r["st"]=="Injured Reserve" and r["rank"]<=200 and r["date"]>=cut],key=lambda r:r["rank"])
        items=[irow(r) for r in key]+[irow(r) for r in newir]
        if inj is None: items=[note("Injury report unavailable right now. It'll be back on the next refresh.")]
        tiles.append(tile("🚑 Injury Report · Key Players",items or [note("No key fantasy players listed Out, Doubtful or Questionable.")],"inj",10,count=len(key)))
        # ---- trending adds / drops (Sleeper)
        def trend(kind):
            d=getj(f"https://api.sleeper.app/v1/players/nfl/trending/{kind}?lookback_hours=24&limit=20",f"sleeper trending {kind}")
            if d is None: return [note("Sleeper trending data unavailable right now.")]
            out=[]
            for i,x in enumerate(d,1):
                pid=str(x.get("player_id")); c=x.get("count",0); p=P.get(pid)
                if p: nm,pos,team=p[0],p[1],p[2]
                elif pid.isalpha(): nm,pos,team=f"{pid} D/ST","DEF",pid
                else: nm,pos,team=f"Player #{pid}","",""
                st=injmap.get(norm(nm)); stt=f' <span class="tag {cls.get(st,"")} sm">{E({"Injured Reserve":"IR"}.get(st,st[0]))}</span>' if st and st!="Active" else ""
                cs=f"{c/1000:.1f}K" if c>=1000 else str(c)
                out.append(f'<div class="pros"><span class="rk">{i}</span><span class="nm">{E(nm)}{stt}</span><span class="pos">{E(pos)}</span><span class="tm2">{E(team)}</span><b class="cnt">{"+" if kind=="add" else "−"}{cs}</b></div>')
            return out or [note("No trending data yet.")]
        tiles.append(tile("📈 Trending Adds · 24h",trend("add"),"",10,count="Sleeper"))
        tiles.append(tile("📉 Trending Drops · 24h",trend("drop"),"",10,count="Sleeper"))
        # ---- schedule (ESPN)
        evs=sb.get("events",[]); byes=[t.get("abbreviation","") for t in (sb.get("week") or {}).get("teamsOnBye",[])]
        days={}
        for e in sorted(evs,key=lambda e:e.get("date","")):
            try:
                c=e["competitions"][0]; t=ct(e["date"]); s=e["status"]["type"]; state=s.get("state")
                tm={x["homeAway"]:x for x in c["competitors"]}; a,h=tm["away"],tm["home"]
                lg=lambda x:f'<img class="lg" src="{E(x["team"].get("logo",""))}" alt="">'
                rec=lambda x:next((r["summary"] for r in x.get("records",[]) if r.get("type")=="total"),"")
                if state=="pre": right=t.strftime("%-I:%M %p")
                else:
                    live=live or state=="in"
                    right=f'{a.get("score","")}-{h.get("score","")}'
                tv=", ".join(n for b in c.get("broadcasts",[]) for n in b.get("names",[]))
                od=(c.get("odds") or [{}])[0] if state=="pre" else {}
                meta=[s.get("shortDetail","") if state=="in" else ("Final" if state=="post" else "")]
                meta+=[tv, f'Line {od["details"]}' if od.get("details") else "", f'O/U {od["overUnder"]}' if od.get("overUnder") else ""]
                link=next((l["href"] for l in e.get("links",[]) if "summary" in l.get("rel",[])),"")
                row=(f'<a class="game" href="{E(link)}"><span class="opp">{lg(a)}{E(a["team"]["abbreviation"])} <small>{E(rec(a))}</small> @ {lg(h)}{E(h["team"]["abbreviation"])} <small>{E(rec(h))}</small></span>'
                     f'<span class="sc{" live" if state=="in" else ""}">{E(right)}</span></a><span class="meta">{E(" · ".join(m for m in meta if m))}</span>')
                days.setdefault(t.strftime("%a %b %-d"),[]).append(row)
            except Exception as ex: gaps.append(f"game {e.get('id')}: {ex}")
        parts="".join(f'<div class="lvl">{E(d)} <span>· times CT</span></div><ul>'+"".join(f"<li>{r}</li>" for r in rs)+"</ul>" for d,rs in days.items())
        if byes: parts+=f'<div class="lvl">On bye</div><ul><li>{E(", ".join(byes))}</li></ul>'
        tiles.insert(0,f'<section class="tile wide sched"><h3><span>🗓️ Week {wk or "?"} Schedule</span><em>{len(evs)} games</em></h3>{parts or "<ul><li>"+note("Schedule unavailable right now.")+"</li></ul>"}</section>')
        # ---- player updates (Rotowire)
        rw=rss("https://www.rotowire.com/rss/news.php?sport=NFL","RotoWire")
        tiles.append(tile("⚡ Latest Player Updates",[nitem(x) for x in dedupe(rw,8)] or [note("Player updates unavailable right now.")],"",8))
        # ---- start/sit reads: expert articles via Google News (links only, no rankings of our own)
        q=urllib.parse.quote(f'"start sit" fantasy football week {wk}' if wk else '"start sit" fantasy football')
        ss=[x for x in rss(f"https://news.google.com/rss/search?q={q}+when:7d&hl=en-US&gl=US&ceid=US:en") if not wk or f"week {wk}" in x["title"].lower()]
        res=[f'<a href="https://www.fantasypros.com/nfl/start/">FantasyPros Who Should I Start? (expert consensus tool)</a><span class="meta">FantasyPros · free tool</span>',
             f'<a href="https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php">FantasyPros weekly PPR rankings</a><span class="meta">FantasyPros · consensus of experts</span>']
        tiles.append(tile(f"🤔 Start / Sit Reads{f' · Week {wk}' if wk else ''}",[nitem(x) for x in dedupe(ss,6)]+res,"",8,count=""))
        # ---- headlines
        # mix sources (cap each) so one busy feed can't crowd out the rest
        hd=dedupe(rss(f"https://news.google.com/rss/search?q=%22fantasy+football%22+when:3d&hl=en-US&gl=US&ceid=US:en"),7)
        hd+=dedupe([x for x in rss("https://www.fantasypros.com/feed/","FantasyPros") if "football" in x["title"].lower() or "nfl" in x["title"].lower()],4)
        hd+=dedupe(rss("https://www.espn.com/espn/rss/nfl/news","ESPN"),6)
        tiles.insert(4,tile("📰 Fantasy &amp; NFL Headlines",[nitem(x) for x in dedupe(hd,16)] or [note("Headlines unavailable right now.")],"wide news",8))
    else:
        tiles.append(f'<section class="tile wide"><h3><span>🏈 NFL {E(lbl)}</span></h3><ul><li>Fantasy football is on break. Injury reports, waiver-wire trends, headlines and the weekly schedule come back when the NFL season starts in September.</li></ul></section>')
    sub=f"Week {wk} · {yr} {lbl}" if ins and wk else f"{yr} · {lbl}"
    bmeta=("On bye: "+", ".join(byes)) if byes else "General fantasy info for every league"
    stamp=now.strftime("%b %-d, %-I:%M %p CT")
    page=f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#14225A"><link rel="apple-touch-icon" href="../icon.png"><title>{E(TITLE)}</title><style>
:root{{--navy:#14225A;--red:#AB0003;--ink:#151a2d;--mute:#6b7189;--line:#eceef4;--bg:#f2f3f7;color-scheme:light}}*{{box-sizing:border-box}}html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.4 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Inter,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}}
a{{color:var(--ink);text-decoration:none}}a:hover{{color:var(--red)}}
header{{position:sticky;top:0;z-index:10;background:var(--navy);color:#fff;border-bottom:3px solid var(--red);padding:calc(env(safe-area-inset-top) + 10px) calc(env(safe-area-inset-right) + 16px) 10px calc(env(safe-area-inset-left) + 16px)}}
.hd{{max-width:1180px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:12px}}.hd a{{color:#ff8a8e;font-weight:700;font-size:14px}}header p{{margin:0;font-size:12px;color:#c9cfe6;white-space:nowrap}}
main{{max-width:1180px;margin:0 auto;padding:16px calc(env(safe-area-inset-right) + 16px) 8px calc(env(safe-area-inset-left) + 16px)}}
.banner{{background:var(--navy);border-radius:14px;padding:16px 20px;margin-bottom:16px;box-shadow:0 4px 14px rgba(20,34,90,.18);border-left:6px solid var(--red)}}
.banner small{{display:block;color:#ff8a8e;font-weight:700;text-transform:uppercase;letter-spacing:.12em;font-size:11px}}.banner h1{{margin:4px 0 0;color:#fff;font-size:24px;font-weight:800;line-height:1.2}}.bmeta{{display:block;color:#c9cfe6;font-size:13px;margin-top:4px}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-items:start}}.wide{{grid-column:span 2}}.grid.mas{{grid-auto-rows:8px;row-gap:0;grid-auto-flow:row dense}}.grid.mas>.tile{{margin-bottom:16px}}
.tile{{background:#fff;border-radius:14px;padding:14px 16px 10px;box-shadow:0 1px 2px rgba(20,34,90,.06),0 4px 14px rgba(20,34,90,.06);min-width:0}}
.tile h3{{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:0 0 6px;padding-bottom:8px;border-bottom:2px solid var(--red);font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--navy)}}
.tile h3 em{{font-style:normal;font-weight:700;font-size:11px;color:var(--mute);background:var(--bg);border-radius:10px;padding:1px 8px;white-space:nowrap;text-transform:none;letter-spacing:0}}
ul{{list-style:none;margin:0;padding:0}}li{{padding:8px 0;border-bottom:1px solid var(--line);font-size:14px;line-height:1.35;overflow-wrap:anywhere}}li:last-child{{border:0}}li>a{{font-weight:600}}
.meta{{display:block;color:var(--mute);font-size:12px;font-weight:400;margin-top:2px}}.muted{{color:var(--mute)}}
.game{{display:flex;align-items:center;justify-content:space-between;gap:10px;font-weight:600}}.opp{{min-width:0}}.opp small{{color:var(--mute);font-weight:500;font-size:11px}}
.sc{{font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap;font-size:13px}}.sc.live{{color:var(--red)}}
.lg{{width:20px;height:20px;vertical-align:-5px;margin-right:4px;object-fit:contain}}
.lvl{{font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--navy);margin:12px 0 0;padding:4px 8px;background:#e8ebf5;border-radius:6px}}.lvl span{{color:var(--mute);font-weight:600;letter-spacing:0;text-transform:none}}.lvl:first-of-type{{margin-top:4px}}
.sched{{}}@media(min-width:701px){{.sched ul{{display:grid;grid-template-columns:1fr 1fr;column-gap:20px}}.sched li:last-child{{border-bottom:1px solid var(--line)}}}}
.pros{{display:flex;align-items:center;gap:8px}}.rk{{flex:none;width:24px;height:24px;border-radius:50%;background:var(--navy);color:#fff;display:grid;place-items:center;font-size:11px;font-weight:800}}
.pros .nm{{flex:1;font-weight:600;min-width:0}}.pos{{font-size:11px;font-weight:700;color:var(--navy);background:#e8ebf5;border-radius:6px;padding:2px 6px;margin-left:4px}}.tm2{{font-size:12px;color:var(--mute);font-weight:600;min-width:30px}}
.cnt{{font-size:12px;font-variant-numeric:tabular-nums;color:var(--navy);min-width:46px;text-align:right}}
.ij{{display:flex;align-items:flex-start;gap:8px}}.ij .nm{{font-weight:600}}.ij .nm a{{font-weight:700}}
.tag{{flex:none;display:inline-grid;place-items:center;min-width:24px;height:22px;padding:0 4px;border-radius:6px;font-size:11px;font-weight:800;color:#fff;background:var(--mute)}}.tag.o,.tag.ir{{background:var(--red)}}.tag.d{{background:#d9480f}}.tag.q{{background:#e0a800;color:#222}}.tag.sm{{min-width:18px;height:17px;font-size:10px;vertical-align:1px}}
.inj .meta{{padding-left:32px}}
details summary{{list-style:none;cursor:pointer;color:var(--red);font-weight:700;font-size:13px;padding:8px 0 4px}}details summary::-webkit-details-marker{{display:none}}details summary::after{{content:" ▾"}}details[open] summary::after{{content:" ▴"}}details[open] summary{{border-bottom:1px solid var(--line)}}
footer{{text-align:center;color:var(--mute);font-size:12px;padding:16px 16px calc(env(safe-area-inset-bottom) + 20px)}}footer a{{color:var(--red);font-weight:700}}
@media(max-width:1000px){{.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:700px){{body{{font-size:16px}}.grid{{grid-template-columns:1fr;gap:12px}}.wide{{grid-column:auto}}main{{padding-top:12px}}.banner h1{{font-size:21px}}header p{{font-size:11px}}li{{font-size:15px}}.tile{{padding:12px 14px 8px}}}}
</style></head><body><header><div class="hd"><a href="../">← Nats Report</a><p>Updated {stamp}</p></div></header>
<main><div class="banner"><small>🏈 {E(sub)}</small><h1>{E(TITLE)}</h1><span class="bmeta">{E(bmeta)}</span></div><div class="grid">{''.join(tiles)}</div></main>
<script>
(function(){{var g=document.querySelector('.grid');function lay(){{if(getComputedStyle(g).gridTemplateColumns.split(' ').length<2){{g.classList.remove('mas');[].forEach.call(g.children,function(t){{t.style.gridRowEnd=''}});return}}g.classList.add('mas');[].forEach.call(g.children,function(t){{t.style.gridRowEnd='span '+Math.ceil((t.getBoundingClientRect().height+16)/8)}})}}
window.addEventListener('load',lay);window.addEventListener('resize',lay);document.querySelectorAll('details').forEach(function(d){{d.addEventListener('toggle',lay)}});lay()}})();
</script>
<footer><a href="../">← Back to the Nats Report</a><br>General fantasy info, not tied to any league. Injury statuses can change right up to kickoff.<br>Data: ESPN · Sleeper · RotoWire · FantasyPros · Google News</footer></body></html>"""
    os.makedirs("fantasy",exist_ok=True); open("fantasy/index.html","w").write(page)
    print("fantasy: wrote",len(tiles),"tiles; in_season",ins,"week",wk,"gaps:",gaps)
if __name__=="__main__": main()
