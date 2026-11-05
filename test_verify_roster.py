#!/usr/bin/env python3
"""Roster-check policy tests. No network: the MLB fetch is replaced."""
import hashlib, os, subprocess, tempfile, textwrap, unittest
from contextlib import contextmanager

import verify_roster as vr

ZAK = 687849
WOOD = 682928


def zak(team_id=999, team="Leones del Caracas", parent=None):
    ct = {"id": team_id, "name": team}
    if parent is not None:
        ct["parentOrgId"] = parent
    return {"id": ZAK, "fullName": "Zak Kent", "currentTeam": ct}


def wood():
    return {"id": WOOD, "fullName": "James Wood", "currentTeam": {"id": 120, "name": "Washington Nationals", "parentOrgId": 120}}


def install_fetch(people, forty=()):
    by_id = {p["id"]: p for p in people}

    def fetch(path):
        if path.startswith("/teams/affiliates"):
            return {"teams": [{"id": 546}]}
        if "rosterType=40Man" in path:
            return {"roster": [{"person": {"id": i}} for i in forty]}
        if path.startswith("/sports/"):
            return {"people": [{"id": p["id"], "fullName": p["fullName"]} for p in people]}
        if path.startswith("/people"):
            ids = [int(x) for x in path.split("personIds=")[1].split("&")[0].split(",") if x]
            return {"people": [by_id[i] for i in ids]}
        raise AssertionError(path)

    vr.fetch = fetch


@contextmanager
def cd(path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def git(*args, cwd):
    subprocess.check_call(["git", *args], cwd=cwd, stdout=subprocess.DEVNULL)


def init_repo(path):
    git("init", "-b", "main", cwd=path)
    git("config", "user.email", "test@example.com", cwd=path)
    git("config", "user.name", "Test", cwd=path)


def commit_all(path, msg):
    git("add", "-A", cwd=path)
    git("commit", "-m", msg, cwd=path)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


ISSUE2 = '<a href="https://www.mlb.com/player/687849">Zak Kent</a> <span class="pos">40-man</span>'
ISSUE_OK = '<span data-ok="departed" data-pid="687849">Zak Kent</span>'
WOOD_HTML = '<a href="https://www.mlb.com/player/682928">James Wood</a>'


class PolicyTests(unittest.TestCase):
    def test_name_inside_longer_name_is_not_a_second_player(self):
        src = "Luis García Jr. homered."
        ids, ok = vr.player_ids(src, {"Luis García": 1, "Luis García Jr.": 2})
        self.assertEqual(ids, {2})
        self.assertEqual(ok, set())

    def test_links_prospects_and_intentional_mentions(self):
        src = textwrap.dedent("""
            <span data-ok="other" data-pid="42">Trevor Rogers</span>
            <a href="https://www.mlb.com/player/7">Someone</a>
            <a href="https://www.mlb.com/app/atbat/milb/prospects/nationals/eli-willits-816113">Eli</a>
        """)
        ids, ok = vr.player_ids(src, {})
        self.assertEqual(ok, {42})
        self.assertEqual(ids, {7, 816113})

    def test_judge_org_forty_man_intentional_and_flag(self):
        self.assertEqual(vr.judge(wood(), {120}, set(), set())[0], "OK  ")
        self.assertEqual(vr.judge(zak(), {120}, {ZAK}, set())[0], "OK  ")
        self.assertEqual(vr.judge(zak(), {120}, set(), {ZAK})[0], "OK* ")
        self.assertEqual(vr.judge(zak(), {120}, set(), set())[0], "FLAG")
        affiliate = zak(team_id=546, team="Rochester Red Wings", parent=120)
        self.assertEqual(vr.judge(affiliate, {120, 546}, set(), set())[0], "OK  ")

    def test_snapshot_rules(self):
        content = b"same-bytes"
        digest = hashlib.sha256(content).hexdigest()
        manifest = {"newsletter/issue-2.html": digest}
        path = "newsletter/issue-2.html"
        self.assertFalse(vr.snapshot_status(path, content, None, None, content, False)[0])
        self.assertFalse(vr.snapshot_status(path, content, {}, None, content, False)[0])
        self.assertFalse(vr.snapshot_status("newsletter/issue-9.html", content, manifest, manifest, None, False)[0])
        self.assertFalse(vr.snapshot_status(path, b"edited", manifest, manifest, content, False)[0])
        self.assertTrue(vr.snapshot_status(path, content, manifest, manifest, content, False)[0])
        # Hash added after the published baseline is still strict.
        self.assertFalse(vr.snapshot_status(path, content, manifest, {}, content, False)[0])
        # Before any freeze list was published, identical already-published bytes are historical.
        self.assertTrue(vr.snapshot_status(path, content, manifest, None, content, False)[0])
        self.assertFalse(vr.snapshot_status(path, content, manifest, None, None, False)[0])
        self.assertFalse(vr.snapshot_status(path, content, manifest, None, b"other", False)[0])

    def test_manifest_round_trip(self):
        entries = {"newsletter/issue-2.html": "ab" * 32, "newsletter/issue-1.html": "cd" * 32}
        parsed = vr.parse_manifest(vr.render_manifest(entries))
        self.assertEqual(parsed, entries)


class GitPolicyTests(unittest.TestCase):
    def setUp(self):
        self._fetch = vr.fetch
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        init_repo(self.repo)
        self.env = os.environ.get("GITHUB_ACTIONS")

    def tearDown(self):
        vr.fetch = self._fetch
        if self.env is None:
            os.environ.pop("GITHUB_ACTIONS", None)
        else:
            os.environ["GITHUB_ACTIONS"] = self.env
        self.tmp.cleanup()

    def run_main(self, args):
        os.environ.pop("GITHUB_ACTIONS", None)
        with cd(self.repo):
            return vr.main(args)

    def test_published_issue_does_not_block_and_new_issue_does(self):
        install_fetch([zak(), wood()])
        write(os.path.join(self.repo, "newsletter/issue-2.html"), ISSUE2)
        commit_all(self.repo, "publish issue 2")
        old = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        manifest = {"newsletter/issue-2.html": hashlib.sha256(ISSUE2.encode()).hexdigest()}
        write(os.path.join(self.repo, vr.MANIFEST), vr.render_manifest(manifest))
        commit_all(self.repo, "freeze published issues")
        with cd(self.repo):
            code = vr.main(["--manifest", vr.MANIFEST, "--git-base", old, "newsletter/issue-2.html"])
        self.assertEqual(code, 0)
        # A newly published issue is not on the baseline and is not exempt.
        write(os.path.join(self.repo, "newsletter/issue-5.html"), ISSUE2)
        entries = dict(manifest)
        entries["newsletter/issue-5.html"] = hashlib.sha256(ISSUE2.encode()).hexdigest()
        write(os.path.join(self.repo, vr.MANIFEST), vr.render_manifest(entries))
        self.assertEqual(self.run_main(["--manifest", vr.MANIFEST, "--git-base", old, "newsletter/issue-5.html"]), 1)
        # The same bytes pass once the departure is an intentional current-issue claim.
        write(os.path.join(self.repo, "newsletter/issue-5.html"), ISSUE_OK)
        self.assertEqual(self.run_main(["--manifest", vr.MANIFEST, "--git-base", old, "newsletter/issue-5.html"]), 0)
        # And a current Nat still passes strict validation.
        write(os.path.join(self.repo, "newsletter/issue-5.html"), WOOD_HTML)
        self.assertEqual(self.run_main(["--manifest", vr.MANIFEST, "--git-base", old, "newsletter/issue-5.html"]), 0)

    def test_baseline_ref_not_parent_and_update_does_not_freeze_failures(self):
        install_fetch([zak()])
        write(os.path.join(self.repo, "newsletter/issue-2.html"), ISSUE2)
        commit_all(self.repo, "issue 2")
        intro_parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        manifest = {"newsletter/issue-2.html": hashlib.sha256(ISSUE2.encode()).hexdigest()}
        write(os.path.join(self.repo, vr.MANIFEST), vr.render_manifest(manifest))
        commit_all(self.repo, "add manifest")
        with cd(self.repo):
            sha, why = vr.resolve_baseline()
        self.assertEqual(sha, intro_parent)
        self.assertIn("parent", why)

        write(os.path.join(self.repo, "newsletter/issue-5.html"), ISSUE2)
        bad_entries = dict(manifest)
        bad_entries["newsletter/issue-5.html"] = hashlib.sha256(ISSUE2.encode()).hexdigest()
        write(os.path.join(self.repo, vr.MANIFEST), vr.render_manifest(bad_entries))
        commit_all(self.repo, "bad new issue with a hash")
        # No baseline ref yet: still the pre-freeze parent, so the new hash is not trusted.
        with cd(self.repo):
            sha, _ = vr.resolve_baseline()
            self.assertEqual(sha, intro_parent)
            before = open(vr.MANIFEST, encoding="utf-8").read()
            code = vr.main(["--manifest", vr.MANIFEST, "--git-base", sha, "--update-manifest", "newsletter/issue-5.html"])
            self.assertEqual(code, 1)
            self.assertEqual(open(vr.MANIFEST, encoding="utf-8").read(), before)

        # A passing new issue can be recorded, and only the next published baseline honors it.
        write(os.path.join(self.repo, "newsletter/issue-5.html"), ISSUE_OK)
        with cd(self.repo):
            code = vr.main(["--manifest", vr.MANIFEST, "--git-base", intro_parent, "--update-manifest",
                            "newsletter/issue-2.html", "newsletter/issue-5.html"])
            self.assertEqual(code, 0)
            frozen = vr.parse_manifest(open(vr.MANIFEST, encoding="utf-8").read())
        self.assertEqual(frozen["newsletter/issue-5.html"], hashlib.sha256(ISSUE_OK.encode()).hexdigest())
        self.assertEqual(frozen["newsletter/issue-2.html"], manifest["newsletter/issue-2.html"])
        commit_all(self.repo, "freeze passing issue 5")
        published = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        git("branch", vr.BASELINE_REF, published, cwd=self.repo)
        with cd(self.repo):
            sha, why = vr.resolve_baseline()
            self.assertEqual(sha, published)
            self.assertIn(vr.BASELINE_REF, why)
            # The already-published issue still reports Zak Kent and does not block.
            self.assertEqual(vr.main(["--manifest", vr.MANIFEST, "--git-base", sha, "newsletter/issue-2.html"]), 0)
            self.assertEqual(vr.main(["--manifest", vr.MANIFEST, "--git-base", sha, "newsletter/issue-5.html"]), 0)
        # ...but editing that issue brings the strict check back.
        write(os.path.join(self.repo, "newsletter/issue-5.html"), ISSUE2)
        self.assertEqual(self.run_main(["--manifest", vr.MANIFEST, "--git-base", published, "newsletter/issue-5.html"]), 1)

    def test_unrelated_baseline_ref_is_rejected(self):
        write(os.path.join(self.repo, "newsletter/issue-2.html"), ISSUE2)
        commit_all(self.repo, "main")
        git("checkout", "--orphan", "other", cwd=self.repo)
        write(os.path.join(self.repo, "other.txt"), "x")
        commit_all(self.repo, "orphan")
        orphan = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        git("checkout", "main", cwd=self.repo)
        git("branch", vr.BASELINE_REF, orphan, cwd=self.repo)
        with cd(self.repo):
            with self.assertRaises(vr.BaselineError):
                vr.resolve_baseline()

    def test_ci_requires_git_base(self):
        install_fetch([wood()])
        write(os.path.join(self.repo, "newsletter/issue-5.html"), WOOD_HTML)
        write(os.path.join(self.repo, vr.MANIFEST), vr.render_manifest({}))
        commit_all(self.repo, "empty freeze list")
        os.environ["GITHUB_ACTIONS"] = "true"
        with cd(self.repo):
            self.assertEqual(vr.main(["--manifest", vr.MANIFEST, "newsletter/issue-5.html"]), 2)

    def test_historical_output_still_names_the_player(self):
        install_fetch([zak()])
        write(os.path.join(self.repo, "newsletter/issue-2.html"), ISSUE2)
        commit_all(self.repo, "issue 2")
        base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        digest = hashlib.sha256(ISSUE2.encode()).hexdigest()
        write(os.path.join(self.repo, vr.MANIFEST), vr.render_manifest({"newsletter/issue-2.html": digest}))
        commit_all(self.repo, "freeze")
        with cd(self.repo):
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = vr.main(["--manifest", vr.MANIFEST, "--git-base", base, "newsletter/issue-2.html"])
        out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("HIST Zak Kent", out)
        self.assertIn("historical departure", out)
        self.assertNotIn("RESULT: 1 player", out)


class RepoTests(unittest.TestCase):
    def test_published_issues_are_frozen_and_unchanged(self):
        root = os.path.dirname(os.path.abspath(__file__))
        manifest = vr.parse_manifest(open(os.path.join(root, vr.MANIFEST), encoding="utf-8").read())
        self.assertEqual(set(manifest), {f"newsletter/issue-{i}.html" for i in range(1, 5)})
        with cd(root):
            for path, recorded in manifest.items():
                content = open(path, "rb").read()
                self.assertEqual(vr.digest(content), recorded)
                committed = vr.git_blob("origin/main", path)
                self.assertEqual(committed, content, path)
            raw = vr.git_blob("origin/main", vr.MANIFEST)
            base_manifest = vr.parse_manifest(raw.decode()) if raw is not None else None
            for path in manifest:
                content = open(path, "rb").read()
                base_content = vr.git_blob("origin/main", path)
                exempt, reason = vr.snapshot_status(
                    path, content, manifest, base_manifest, base_content, trust_recorded_hash=False)
                self.assertTrue(exempt, f"{path}: {reason}")

    def test_workflow_keeps_strict_check_ahead_of_deploy(self):
        root = os.path.dirname(os.path.abspath(__file__))
        text = open(os.path.join(root, ".github/workflows/build.yml"), encoding="utf-8").read()
        self.assertIn("fetch-depth: 0", text)
        self.assertIn("--print-baseline", text)
        self.assertIn('--git-base "${{ steps.roster-base.outputs.rev }}"', text)
        self.assertIn("--update-manifest", text)
        self.assertIn("newsletter/issue-*.html", text)
        self.assertIn('git push origin "HEAD:refs/heads/roster-baseline"', text)
        self.assertNotIn("--force", text)
        self.assertLess(text.index("--print-baseline"), text.index("Verify newsletter roster"))
        self.assertLess(text.index("Verify newsletter roster"), text.index("Commit refreshed"))
        self.assertLess(text.index("actions/deploy-pages@v4"), text.index('git push origin "HEAD:refs/heads/roster-baseline"'))
        # A gated no-op must not advance the baseline or skip only part of verification.
        advance = text.split("Advance roster baseline", 1)[1]
        self.assertIn("steps.gate.outputs.run == 'true'", advance)


if __name__ == "__main__":
    unittest.main()
