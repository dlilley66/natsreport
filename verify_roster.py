#!/usr/bin/env python3
"""Check that every player named or linked in a page is still in the Nationals organization.

Usage:
  python3 verify_roster.py --manifest historical-newsletters.txt --git-base <sha> newsletter/issue-*.html
  python3 verify_roster.py --print-baseline

Player IDs come from links (mlb.com/player/<id>, prospect URLs ending in -<id>).
Full names in the text are matched against every 2026 MLB player. Each player's
current team must be the Nationals, a Nationals affiliate, or the Nats' 40-man.
A mention marked data-ok="departed" or data-ok="other" (with data-pid) is intentional.

Strict checks fail the process, which blocks the site deploy. Already published
newsletters are historical snapshots: once their exact bytes are recorded in
historical-newsletters.txt AND that record exists at --git-base (the last
revision that actually published), a later departure is reported as HIST and
does not block the daily refresh. The players are still looked up.

A new issue, an edited issue, or a hash that was not on --git-base stays strict.
--update-manifest records hashes only after that strict check has passed, so a
failing newsletter is never frozen. In GitHub Actions, --git-base is required.
"""
import argparse, hashlib, os, re, sys, html, json, subprocess, urllib.request

API = "https://statsapi.mlb.com/api/v1"
MANIFEST = "historical-newsletters.txt"
BASELINE_REF = "roster-baseline"
HEADER = """# Frozen newsletter snapshots (sha256 of the exact file bytes).
# Every issue is still checked. A listed hash is historical only after it was
# already recorded at the last published roster-baseline: departures are
# reported and do not block the daily site deploy. A new issue, an edited
# issue, or a hash that was not on that baseline stays strict, so a current
# roster claim must match the Nationals org (or be marked data-ok) before it
# can ship. A failing issue is never added here.
"""


class BaselineError(Exception):
    pass


class GitRevError(Exception):
    pass


def fetch(path):
    with urllib.request.urlopen(API + path, timeout=30) as r:
        return json.load(r)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def normalize(path):
    return path.replace("\\", "/").lstrip("./")


def parse_manifest(text):
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([0-9a-fA-F]{64})\s+(\S+)$", line)
        if not m:
            raise BaselineError(f"bad historical manifest line: {raw}")
        out[normalize(m.group(2))] = m.group(1).lower()
    return out


def render_manifest(entries):
    lines = [HEADER.rstrip("\n")]
    for path in sorted(entries):
        lines.append(f"{entries[path]}  {path}")
    return "\n".join(lines) + "\n"


def git_run(args):
    return subprocess.run(["git", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def git_blob(rev, path):
    """Exact bytes of path at rev, or None if that path is absent. Bad rev raises."""
    p = git_run(["cat-file", "blob", f"{rev}:{path}"])
    if p.returncode == 0:
        return p.stdout
    err = p.stderr.decode("utf-8", "replace").lower()
    if any(s in err for s in ("invalid object", "not a valid object", "bad revision", "unknown revision", "bad object")):
        raise GitRevError(p.stderr.decode("utf-8", "replace").strip())
    return None


def ref_commit(name):
    for candidate in (f"refs/remotes/origin/{name}", f"refs/heads/{name}"):
        p = git_run(["rev-parse", "--verify", "--quiet", candidate])
        if p.returncode == 0:
            return p.stdout.decode().strip()
    return None


def is_ancestor(ancestor, descendant="HEAD"):
    return git_run(["merge-base", "--is-ancestor", ancestor, descendant]).returncode == 0


def first_added_commit(path):
    p = git_run(["log", "--diff-filter=A", "--format=%H", "--", path])
    if p.returncode != 0:
        raise BaselineError(p.stderr.decode("utf-8", "replace").strip() or f"git log failed for {path}")
    lines = [ln.strip() for ln in p.stdout.decode().splitlines() if ln.strip()]
    return lines[-1] if lines else None


def parent_commit(rev):
    p = git_run(["rev-parse", "--verify", "--quiet", f"{rev}^"])
    if p.returncode != 0:
        return None
    return p.stdout.decode().strip()


def resolve_baseline(manifest_path=MANIFEST, ref=BASELINE_REF):
    """Sha that already published, used to decide which freeze hashes are trusted.

    Prefer the roster-baseline ref (advanced only after a real deploy). Until
    that ref exists, use the parent of the commit that added the manifest, which
    is the site content from before this freeze list. Either way, a newsletter
    that was not already on that revision stays strict.
    """
    sha = ref_commit(ref)
    if sha:
        if not is_ancestor(sha, "HEAD"):
            raise BaselineError(f"{ref} {sha} is not an ancestor of HEAD")
        return sha, f"{ref} ref"
    intro = first_added_commit(manifest_path)
    if not intro:
        raise BaselineError(f"{manifest_path} is not committed, and {ref} does not exist")
    parent = parent_commit(intro)
    if not parent:
        raise BaselineError(f"{intro} has no parent to use before {ref} exists")
    return parent, f"parent of the commit that added {manifest_path}"


def snapshot_status(path, content, manifest, base_manifest, base_content, trust_recorded_hash):
    """Return (exempt, reason). Exempt snapshots are reported and do not fail the run."""
    if not manifest:
        return False, "strict: no freeze list"
    recorded = manifest.get(normalize(path))
    current = digest(content)
    if recorded is None:
        return False, "strict: new or unlisted issue"
    if recorded != current:
        return False, "strict: issue changed since it was frozen"
    if trust_recorded_hash:
        return True, "historical: recorded snapshot (no baseline supplied)"
    if base_manifest is None:
        if base_content is not None and digest(base_content) == current:
            return True, "historical: already published before the freeze list existed"
        return False, "strict: cannot freeze a file that was not already published"
    if base_manifest.get(normalize(path)) == current:
        return True, "historical: unchanged frozen snapshot"
    return False, "strict: freeze hash was added or changed after the published baseline"


def strip_html(src):
    return html.unescape(re.sub(r"<[^>]+>", " ", src))


def player_ids(src, mlb_names):
    """Return (ids, intentional_non_nats_ids) found in one newsletter."""
    ok = set(int(i) for i in re.findall(r'data-ok="(?:departed|other)"[^>]*data-pid="(\d+)"', src))
    ids = set(int(i) for i in re.findall(r"mlb\.com/player/(\d+)", src))
    ids |= set(int(i) for i in re.findall(r"/prospects/nationals/[a-z0-9-]+-(\d+)", src))
    text = strip_html(src)
    found = [n for n in mlb_names if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w|\.\w)", text)]
    # Drop a name that only appears inside a longer matched name ("Luis García" in "Luis García Jr.").
    for n in found:
        if not any(n != m and n in m and text.count(n) == text.count(m) for m in found):
            ids.add(mlb_names[n])
    return ids, ok


def judge(person, org, forty, ok_ids):
    ct = person.get("currentTeam") or {}
    tid = ct.get("id")
    parent = ct.get("parentOrgId", tid)
    in_org = tid in org or parent == 120 or person["id"] in forty
    if in_org:
        tag = "40-man" if person["id"] in forty else "org"
        return "OK  ", tag
    if person["id"] in ok_ids:
        return "OK* ", "non-Nats mention marked intentional"
    return "FLAG", ""


def load_org():
    org = {120} | {t["id"] for t in fetch("/teams/affiliates?teamIds=120")["teams"]}
    forty = {x["person"]["id"] for x in fetch("/teams/120/roster?rosterType=40Man")["roster"]}
    mlb_names = {}
    for sp in (1,):
        for p in fetch(f"/sports/{sp}/players?season=2026")["people"]:
            mlb_names.setdefault(p["fullName"], p["id"])
    return org, forty, mlb_names


def people_for(ids):
    people = []
    idl = sorted(ids)
    for i in range(0, len(idl), 50):
        chunk = ",".join(map(str, idl[i:i + 50]))
        people += fetch("/people?personIds=" + chunk + "&hydrate=currentTeam")["people"]
    return people


def build_parser():
    p = argparse.ArgumentParser(description="Verify Nationals roster claims in newsletter issues.")
    p.add_argument("--manifest", default=MANIFEST, help="freeze list of historical issue hashes")
    p.add_argument("--git-base", help="published revision whose freeze list is already trusted")
    p.add_argument("--update-manifest", action="store_true", help="record hashes after a passing strict check")
    p.add_argument("--print-baseline", action="store_true", help="print the published roster-baseline sha")
    p.add_argument("files", nargs="*")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.print_baseline:
        try:
            sha, why = resolve_baseline(args.manifest)
        except BaselineError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"Roster baseline ({why}) {sha}", file=sys.stderr)
        print(sha)
        return 0
    if not args.files:
        print("usage: python3 verify_roster.py [--manifest FILE] [--git-base REV] [--update-manifest] newsletter/issue-*.html", file=sys.stderr)
        return 2
    if os.environ.get("GITHUB_ACTIONS") == "true" and not args.git_base:
        print("CI must pass --git-base (the published roster baseline).", file=sys.stderr)
        return 2

    manifest = None
    if args.manifest and os.path.isfile(args.manifest):
        try:
            with open(args.manifest, encoding="utf-8") as fh:
                manifest = parse_manifest(fh.read())
        except BaselineError as e:
            print(str(e), file=sys.stderr)
            return 2
    elif args.manifest and args.manifest != MANIFEST and not args.update_manifest:
        print(f"manifest not found: {args.manifest}", file=sys.stderr)
        return 2

    base_manifest = None
    if args.git_base:
        try:
            raw = git_blob(args.git_base, args.manifest) if args.manifest else None
        except GitRevError as e:
            print(f"roster baseline {args.git_base} is not available: {e}", file=sys.stderr)
            return 2
        if raw is not None:
            try:
                base_manifest = parse_manifest(raw.decode("utf-8"))
            except (BaselineError, UnicodeError) as e:
                print(f"roster baseline manifest is unreadable: {e}", file=sys.stderr)
                return 2

    try:
        org, forty, mlb_names = load_org()
    except Exception as e:
        print(f"roster source unavailable: {e}", file=sys.stderr)
        return 2

    bad = hist = 0
    checked = []
    for f in args.files:
        try:
            with open(f, "rb") as fh:
                content = fh.read()
            src = content.decode("utf-8")
        except (OSError, UnicodeError) as e:
            print(f"{f}: {e}", file=sys.stderr)
            return 2
        checked.append((f, content))
        base_content = None
        if args.git_base:
            try:
                base_content = git_blob(args.git_base, f)
            except GitRevError as e:
                print(f"roster baseline {args.git_base} is not available: {e}", file=sys.stderr)
                return 2
        exempt, reason = snapshot_status(
            f, content, manifest, base_manifest, base_content, trust_recorded_hash=not args.git_base)
        ids, ok_ids = player_ids(src, mlb_names)
        if not ids:
            print(f"{f}: no players found [{reason}]")
            continue
        try:
            people = people_for(ids)
        except Exception as e:
            print(f"roster source unavailable: {e}", file=sys.stderr)
            return 2
        mode = "historical" if exempt else "strict"
        print(f"== {f}: {len(people)} players [{mode}; {reason}]")
        for p in sorted(people, key=lambda p: p["fullName"]):
            ct = p.get("currentTeam") or {}
            status, tag = judge(p, org, forty, ok_ids)
            if status == "FLAG" and exempt:
                status = "HIST"
                tag = "departed since this issue was published"
                hist += 1
                print(f"::warning file={f}::{p['fullName']} is no longer in the Nationals org; historical issue, not blocking deploy")
            elif status == "FLAG":
                bad += 1
            print(f"  {status} {p['fullName']:<24} {ct.get('name', '(no team)'):<28} {tag}")

    if bad:
        print(f"\nRESULT: {bad} player(s) not in the Nationals org")
        return 1
    if args.update_manifest:
        if not args.manifest:
            print("--update-manifest needs --manifest", file=sys.stderr)
            return 2
        entries = dict(manifest or {})
        for path, content in checked:
            entries[normalize(path)] = digest(content)
        rendered = render_manifest(entries)
        current = ""
        if os.path.isfile(args.manifest):
            with open(args.manifest, encoding="utf-8") as fh:
                current = fh.read()
        if rendered != current:
            with open(args.manifest, "w", encoding="utf-8") as fh:
                fh.write(rendered)
            print(f"updated {args.manifest}")
    if hist:
        print(f"\nRESULT: all current roster claims passed ({hist} historical departure(s) reported, not blocking)")
    else:
        print("\nRESULT: all players in org")
    return 0


if __name__ == "__main__":
    sys.exit(main())
