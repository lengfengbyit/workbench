import os
import tempfile
import unittest
from datetime import datetime, timedelta

from workbench.build import build
from workbench.notes import Notes
from workbench.providers.demo import DemoProvider, _git_env, make_workspace
from workbench.settings import Settings
from workbench.util import run


class DemoBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        commits = make_workspace(cls.tmp.name)
        cls.settings = Settings(os.path.join(cls.tmp.name, "_home"), {"provider": "demo", "workspace": cls.tmp.name})
        cls.provider = DemoProvider(cls.settings.config, commits)
        cls.data = build(cls.settings, cls.provider, Notes(cls.settings.notes_path), fetch=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def req(self, rid):
        return next(r for r in self.data["requirements"] if r["id"] == rid)

    def test_trunk_is_detected_not_assumed(self):
        self.assertEqual(self.data["trunk"], "main")

    def test_requirements_group_stories_under_parents(self):
        self.assertEqual({r["id"] for r in self.data["requirements"]}, {"1", "5"})
        self.assertEqual([s["id"] for s in self.req("1")["stories"]], ["2", "3"])

    def test_unmerged_commits_are_pending(self):
        story = self.req("1")["stories"][0]
        self.assertEqual(story["codeState"], "pending")
        branch = next(x for x in self.req("1")["repos"] if x["branch"] == "feature/checkout-api")
        self.assertEqual(branch["mine"], 2)            # WB-2 twice
        self.assertEqual(len(branch["others"]), 1)     # WB-9 rides along
        self.assertEqual(branch["behind"], 1)          # trunk moved on after the branch was cut

    def test_alerts(self):
        kinds = {(a["kind"], a["id"]) for a in self.data["alerts"]}
        self.assertIn(("overdue", "2"), kinds)
        self.assertIn(("pipeline", "4"), kinds)
        self.assertIn(("others", "1"), kinds)
        self.assertIn(("behind", "1"), kinds)

    def test_recent_online_uses_the_parent_state(self):
        recent = self.data["recentOnline"]
        self.assertEqual([r["id"] for r in recent], ["8"])
        self.assertEqual(recent[0]["repos"], ["acme/api"])

    def test_provider_supplies_links_and_labels(self):
        self.assertEqual(self.data["idPrefix"], "WB-")
        self.assertTrue(self.data["urls"]["2"].startswith("https://"))
        self.assertIn("{repo}", self.data["links"]["repo"])


class RepoWithoutItemsTest(unittest.TestCase):
    """A clone no item refers to is still listed, with its unmerged remote branches."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = cls.tmp.name
        commits = make_workspace(root)
        env = _git_env()

        def git(path, *args):
            code, out = run(["git", "-C", path, *args], env=env)
            assert code == 0, out

        origin, solo = os.path.join(root, "_origin", "acme", "solo.git"), os.path.join(root, "acme", "solo")
        os.makedirs(origin)
        git(os.path.dirname(origin), "init", "-q", "--bare", "-b", "main", origin)
        git(os.path.dirname(solo), "clone", "-q", origin, solo)
        git(solo, "checkout", "-q", "-b", "main")
        for name, branch in (("first", None), ("wip", "feature/wip")):
            if branch:
                git(solo, "checkout", "-q", "-b", branch, "main")
            with open(os.path.join(solo, name + ".txt"), "w") as f:
                f.write(name)
            git(solo, "add", "-A")
            git(solo, "commit", "-q", "-m", name)
            git(solo, "push", "-q", "origin", branch or "main")
        git(solo, "checkout", "-q", "main")
        git(solo, "remote", "set-head", "origin", "main")
        git(solo, "fetch", "-q", "origin")

        class Provider(DemoProvider):
            def local_repos(self):
                return {"acme/solo": solo, "acme/solo-alias": solo}   # same clone under two names: listed once

        settings = Settings(os.path.join(root, "_home"), {"provider": "demo", "workspace": root})
        cls.data = build(settings, Provider(settings.config, commits), Notes(settings.notes_path), fetch=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_clone_without_items_is_listed_once_with_open_branches(self):
        repos = {r["repo"]: r for r in self.data["repos"]}
        self.assertEqual(sorted(repos), ["acme/api", "acme/solo", "acme/web"])
        solo = repos["acme/solo"]
        self.assertTrue(solo["exists"])
        self.assertEqual(solo["trunk"], "main")
        self.assertEqual([(b["branch"], b["ahead"]) for b in solo["openBranches"]], [("feature/wip", 1)])
        self.assertEqual(solo["openBranchTotal"], 1)

    def test_clone_with_items_keeps_its_branch_detail(self):
        api = next(r for r in self.data["repos"] if r["repo"] == "acme/api")
        self.assertIn("feature/checkout-api", api["branches"])


class WorkspaceAndLocalRequirementTest(unittest.TestCase):
    """Clones the provider does not recognise are listed too, and a requirement made from repos and branches is built."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = cls.tmp.name
        commits = make_workspace(root)
        env = _git_env()

        def git(path, *args, days=0):
            e = dict(env)
            if days:
                stamp = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
                e["GIT_AUTHOR_DATE"] = e["GIT_COMMITTER_DATE"] = stamp
            code, out = run(["git", "-C", path, *args], env=e)
            assert code == 0, out

        # a clone with no remote at all, two branches: one touched today, one 20 days ago
        plain = os.path.join(root, "scratch")
        os.makedirs(plain)
        git(plain, "init", "-q", "-b", "main")
        for name, branch, days in (("old", "old-work", 20), ("new", "new-work", 0)):
            git(plain, "checkout", "-q", "-b", branch)
            with open(os.path.join(plain, name + ".txt"), "w") as f:
                f.write(name)
            git(plain, "add", "-A")
            git(plain, "commit", "-q", "-m", name, days=days)

        cls.settings = Settings(os.path.join(root, "_home"), {"provider": "demo", "workspace": root})
        notes = Notes(cls.settings.notes_path)
        cls.rid = notes.save_local_requirement({
            "action": "create", "title": "Payment retry", "status": "Doing",
            "repos": [{"repo": "acme/web", "branch": "feature/checkout-ui"}, {"repo": "acme/api", "branch": "feature/checkout-api"}],
            "edges": [["acme/web", "acme/api", "calls /retry"]]})
        cls.data = build(cls.settings, DemoProvider(cls.settings.config, commits), notes, fetch=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_clone_without_tracker_remote_is_listed_with_recent_branches(self):
        scratch = next(r for r in self.data["repos"] if r["repo"] == "scratch")
        self.assertEqual([b["branch"] for b in scratch["recentBranches"]], ["new-work"])   # the 20-day-old one is out
        self.assertTrue(scratch["recentBranches"][0]["local"])
        self.assertTrue(scratch["noLink"])                       # not a tracker repo: no web page to link to
        self.assertIn("origin", scratch["note"])
        self.assertEqual(scratch["errors"], [])                  # a local-only clone is not a collection failure
        self.assertNotIn("noLink", next(r for r in self.data["repos"] if r["repo"] == "acme/api"))
        self.assertEqual(self.data["uiConfig"]["recent_branch_days"], 7)

    def test_local_requirement_lists_its_branches_and_counts_every_pending_commit(self):
        r = next(x for x in self.data["requirements"] if x["id"] == self.rid)
        self.assertTrue(r["manual"])
        self.assertEqual(r["stories"], [])
        api = next(z for z in r["repos"] if z["repo"] == "acme/api")
        self.assertTrue(api["exists"])
        self.assertEqual(api["mine"], len(api["pending"]))
        self.assertEqual(api["others"], [])
        self.assertEqual(r["relation"]["nodes"], ["acme/web", "acme/api"])
        self.assertFalse(r["mergedAll"])

    def test_unknown_status_falls_back_to_the_first_stage(self):
        r = next(x for x in self.data["requirements"] if x["id"] == self.rid)
        self.assertEqual(r["status"], self.data["stages"][0]["name"])


if __name__ == "__main__":
    unittest.main()
