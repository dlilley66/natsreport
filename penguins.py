#!/usr/bin/env python3
"""Builds penguins/index.html — Justin's Penguins Paradise (NHL API api-web.nhle.com + Google News)."""
import json, os, urllib.request, html, datetime as dt, xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
CT=ZoneInfo("America/Chicago"); E=html.escape; B="https://api-web.nhle.com/v1/"; TITLE="Justin's Penguins Paradise"
def get(p):
    try: return json.load(urllib.request.urlopen(urllib.request.Request(B+p,headers={"User-Agent":"Mozilla/5.0"}),timeout=25))
    except Exception as e: print("pens fetch fail",p,e); return {}
def ct(s): return dt.datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(CT)
def nm(x): return x.get("default","") if isinstance(x,dict) else str(x or "")
def LG(ab): return f'<img class="lg" src="https://assets.nhle.com/logos/nhl/svg/{ab}_light.svg" alt="">'
def tile(t,body,cls="",cnt=""): return f'<section class="tile {cls}"><h3><span>{t}</span>{f"<em>{cnt}</em>" if cnt!="" else ""}</h3>{body}</section>'
def ul(items): return "<ul>"+"".join(f"<li>{i}</li>" for i in items)+"</ul>" if items else "<ul><li>Nothing to show yet</li></ul>"
sched=get("club-schedule-season/PIT/now").get("games",[])
done=[g for g in sched if g.get("gameState") in("FINAL","OFF")]; live=[g for g in sched if g.get("gameState") in("LIVE","CRIT")]
fut=[g for g in sched if g.get("gameState") in("FUT","PRE")]
def side(g):
    home=g["homeTeam"]["abbrev"]=="PIT"; us,op=(g["homeTeam"],g["awayTeam"]) if home else (g["awayTeam"],g["homeTeam"]); return us,op,home
def res(g):
    us,op,home=side(g); w=us.get("score",0)>op.get("score",0); pt=g.get("gameOutcome",{}).get("lastPeriodType","REG")
    tag="" if pt=="REG" else f' <span class="note">{pt}</span>'; pre=" (pre)" if g.get("gameType")==1 else ""
    return f'<div class="game"><span class="wl {"w" if w else "l"}">{"W" if w else "L"}</span><span class="opp">{"vs" if home else "@"} {LG(op["abbrev"])}{E(op["abbrev"])}{pre}{tag}</span><span class="sc">{us.get("score",0)}-{op.get("score",0)}</span><span class="dt">{ct(g["startTimeUTC"]):%b %-d}</span></div>'
def nxt(g):
    us,op,home=side(g); tv=", ".join(b["network"] for b in g.get("tvBroadcasts",[]))
    return f'{"vs" if home else "@"} {LG(op["abbrev"])}<b>{E(nm(op.get("placeName")))} {E(nm(op.get("commonName")))}</b><span class="meta">{ct(g["startTimeUTC"]):%a %b %-d · %-I:%M %p} CT{" · "+E(tv) if tv else ""}</span>'
tiles=[]
if live or fut:
    g=(live or fut)[0]; us,op,home=side(g); a,h=g["awayTeam"],g["homeTeam"]
    st="LIVE" if live else ("Today" if ct(g["startTimeUTC"]).date()==dt.datetime.now(CT).date() else "Next Game")
    sc=lambda t:f'<span class="tsc">{t.get("score","")}</span>' if live else ""
    row=lambda t:f'<div class="tm">{LG(t["abbrev"]).replace("lg","lgb")}<div class="tn">{E(nm(t.get("placeName")))} {E(nm(t.get("commonName")))}</div>{sc(t)}</div>'
    tiles.append(tile(st,row(a)+row(h)+f'<div class="tmeta">{ct(g["startTimeUTC"]):%a %b %-d · %-I:%M %p} CT · {E(nm(g.get("venue")))} · <a href="https://www.nhl.com/gamecenter/{g["id"]}">GameCenter →</a></div>',"today wide"))
tiles.append(tile("Recent Scores","".join(res(g) for g in done[-8:][::-1]) or "<ul><li>No games yet</li></ul>","score",len(done)))
# news
news=[]
try:
    r=ET.fromstring(urllib.request.urlopen(urllib.request.Request("https://news.google.com/rss/search?q=%22Pittsburgh+Penguins%22+when:7d&hl=en-US&gl=US&ceid=US:en",headers={"User-Agent":"Mozilla/5.0"}),timeout=25).read())
    for it in r.iter("item"):
        t=it.findtext("title",""); src=it.findtext("source","")
        if src and t.endswith(" - "+src): t=t[:-len(src)-3]
        try: when=dt.datetime.strptime(it.findtext("pubDate",""),"%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc).astimezone(CT).strftime("%b %-d")
        except Exception: when=""
        news.append(f'<a href="{E(it.findtext("link",""))}">{E(t)}</a><span class="meta">{E(src)} · {when}</span>')
        if len(news)>=8: break
except Exception as e: print("pens news fail",e)
tiles.append(tile("Penguins News",ul(news),"wide news",len(news)))
tiles.append(tile("Upcoming",ul([nxt(g) for g in fut[1 if not live else 0:6]]),"",len(fut)))
# standings
rows=[s for s in get("standings/now").get("standings",[]) if s.get("divisionAbbrev")=="M"]
rows.sort(key=lambda s:s.get("divisionSequence",99))
tr="".join(f'<tr class="{"us" if nm(s["teamAbbrev"])=="PIT" else ""}"><td>{LG(nm(s["teamAbbrev"]))}{E(nm(s["teamAbbrev"]))}</td><td>{s["gamesPlayed"]}</td><td>{s["wins"]}</td><td>{s["losses"]}</td><td>{s["otLosses"]}</td><td><b>{s["points"]}</b></td></tr>' for s in rows)
tiles.append(tile("Metropolitan Division",f'<table><tr><th></th><th>GP</th><th>W</th><th>L</th><th>OT</th><th>PTS</th></tr>{tr}</table>' if tr else "<ul><li>Standings unavailable</li></ul>","stand"))
# leaders
cs=get("club-stats/PIT/now"); sk=cs.get("skaters",[]); gl=cs.get("goalies",[])
pn=lambda p:E(nm(p["firstName"])+" "+nm(p["lastName"]))
def lead(key,lbl):
    return ul([f'<div class="pros"><img class="hs" src="{E(p.get("headshot",""))}" alt=""><span class="nm">{pn(p)}</span><b>{p[key]}</b></div>' for p in sorted(sk,key=lambda p:-p.get(key,0))[:5]])
for k,l in(("points","Points"),("goals","Goals"),("assists","Assists")): tiles.append(tile("Leaders · "+l,lead(k,l),"stats"))
gg=sorted([g for g in gl if g.get("gamesPlayed")],key=lambda g:-g["gamesPlayed"])
tiles.append(tile("Goalies",ul([f'<div class="pl"><span class="nm">{pn(g)}</span><span class="st">{g["wins"]}-{g["losses"]}-{g["overtimeLosses"]} · SV% {g["savePercentage"]:.3f} · GAA {g["goalsAgainstAverage"]:.2f} · SO {g["shutouts"]}</span></div>' for g in gg]),"stats"))
# roster
ro=get("roster/PIT/current"); parts=""; n=0
for k,l in(("forwards","Forwards"),("defensemen","Defense"),("goalies","Goalies")):
    ps=sorted(ro.get(k,[]),key=lambda p:p.get("sweaterNumber",99)); n+=len(ps)
    parts+=f'<div class="lvl">{l}</div>'+ul([f'<div class="pros"><span class="rk">{p.get("sweaterNumber","")}</span><span class="nm">{pn(p)}</span><span class="pos">{p.get("positionCode","")}</span></div>' for p in ps])
tiles.append(tile("Roster",f'<details><summary>Show full roster</summary>{parts}</details>',"",n))
rec=[g for g in done if g.get("gameType")==2]; w=sum(1 for g in rec if side(g)[0].get("score",0)>side(g)[1].get("score",0))
me=[s for s in rows if nm(s["teamAbbrev"])=="PIT"]
sub=f'{me[0]["wins"]}-{me[0]["losses"]}-{me[0]["otLosses"]} · {me[0]["points"]} pts · {me[0].get("divisionSequence","?")} in Metro' if me else "Let's go Pens!"
now=dt.datetime.now(CT).strftime("%b %-d, %-I:%M %p CT")
os.makedirs("penguins",exist_ok=True)
page=f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#000000"><title>{E(TITLE)}</title><style>
:root{{--blk:#111;--gold:#FCB514;--ink:#151515;--mute:#6b6b6b;--line:#eee;--bg:#f4f2ec}}*{{box-sizing:border-box}}html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Helvetica,Arial,sans-serif}}a{{color:var(--ink);text-decoration:none}}a:hover{{color:#b8860b}}
header{{position:sticky;top:0;z-index:10;background:var(--blk);color:#fff;border-bottom:3px solid var(--gold);padding:calc(env(safe-area-inset-top) + 10px) 16px 10px}}
.hd{{max-width:1180px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:12px}}.hd a{{color:var(--gold);font-weight:700;font-size:13px}}header p{{margin:0;font-size:12px;color:#bbb}}
main{{max-width:1180px;margin:0 auto;padding:16px 16px 8px}}
.banner{{display:flex;align-items:center;gap:16px;background:linear-gradient(135deg,#000,#2a2a2a);border-radius:14px;padding:18px 20px;margin-bottom:16px;border-left:6px solid var(--gold);box-shadow:0 4px 14px rgba(0,0,0,.25)}}
.banner img{{width:64px;height:64px}}.banner h1{{margin:0;color:var(--gold);font-size:26px;font-weight:900;line-height:1.1}}.banner small{{display:block;color:#ddd;font-size:13px;margin-top:4px}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-items:start}}.wide{{grid-column:span 2}}
.tile{{background:#fff;border-radius:14px;padding:14px 16px 10px;box-shadow:0 1px 2px rgba(0,0,0,.06),0 4px 14px rgba(0,0,0,.06);min-width:0}}
.tile h3{{display:flex;justify-content:space-between;align-items:center;margin:0 0 6px;padding-bottom:8px;border-bottom:2px solid var(--gold);font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}}
.tile h3 em{{font-style:normal;font-size:11px;color:var(--mute);background:var(--bg);border-radius:10px;padding:1px 8px}}
ul{{list-style:none;margin:0;padding:0}}li{{padding:8px 0;border-bottom:1px solid var(--line);font-size:14px;overflow-wrap:anywhere}}li:last-child{{border:0}}li>a{{font-weight:600}}.meta{{display:block;color:var(--mute);font-size:12px}}
.game{{display:grid;grid-template-columns:24px minmax(0,1fr) auto 46px;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--line)}}
.wl{{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:6px;font-size:12px;font-weight:800;color:#fff}}.wl.w{{background:#1f7a3d}}.wl.l{{background:#b00}}
.opp{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.sc{{font-weight:800}}.dt{{color:var(--mute);font-size:12px;text-align:right}}.note{{color:#b8860b;font-size:11px;font-weight:700}}
.lg{{width:18px;height:18px;vertical-align:-4px;margin-right:6px}}.lgb{{width:40px;height:40px}}.hs{{width:30px;height:30px;border-radius:50%;background:#eee}}
.pros{{display:flex;align-items:center;gap:10px}}.pros .nm{{flex:1;font-weight:600}}.rk{{width:28px;height:28px;border-radius:50%;background:var(--blk);color:var(--gold);display:grid;place-items:center;font-size:12px;font-weight:800}}
.pos{{font-size:11px;font-weight:700;background:#fdf1cf;border-radius:6px;padding:2px 6px}}.pl{{display:flex;flex-direction:column}}.pl .nm{{font-weight:700}}.pl .st{{color:var(--mute);font-size:12.5px}}
.lvl{{font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);margin-top:10px}}
.today .tm{{display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--line)}}.tn{{flex:1;font-weight:800;font-size:17px}}.tsc{{font-size:26px;font-weight:800}}.tmeta{{color:var(--mute);font-size:13px;padding-top:8px}}.tmeta a{{color:#b8860b;font-weight:700}}
.stand table{{width:100%;border-collapse:collapse;font-size:14px}}.stand th{{font-size:11px;color:var(--mute);text-align:right;padding:4px}}.stand td{{padding:6px 4px;border-bottom:1px solid var(--line);text-align:right}}.stand td:first-child{{text-align:left;font-weight:600}}.stand tr.us td{{background:#fff6dc;font-weight:800}}
details summary{{cursor:pointer;color:#b8860b;font-weight:700;font-size:13px;padding:8px 0}}footer{{text-align:center;color:var(--mute);font-size:12px;padding:16px 16px 24px}}footer a{{color:#b8860b}}
@media(max-width:1000px){{.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:700px){{.grid{{grid-template-columns:1fr;gap:12px}}.wide{{grid-column:auto}}.banner h1{{font-size:21px}}.banner img{{width:50px;height:50px}}}}
</style></head><body><header><div class="hd"><a href="../">← Nats Report</a><p>Updated {now}</p></div></header>
<main><div class="banner"><img src="https://assets.nhle.com/logos/nhl/svg/PIT_dark.svg" alt=""><div><h1>{E(TITLE)}</h1><small>{E(sub)}</small></div></div>
<div class="grid">{''.join(tiles)}</div></main>{'<script>setTimeout(function(){location.reload()},300000)</script>' if live else ''}
<footer><a href="../">← Back to the Nats Report</a><br>Data: NHL API · Google News</footer></body></html>"""
open("penguins/index.html","w").write(page); print("penguins: wrote",len(tiles),"tiles")
