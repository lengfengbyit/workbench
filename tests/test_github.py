import os
import subprocess
import tempfile
import unittest

from workbench.providers.github import GitHubProvider


def issue(number, state="OPEN", repo="acme/api", values=None, labels=(), parent=None, **extra):
    return {"number": number, "title": f"Issue {number}", "state": state, "url": f"https://github.com/{repo}/issues/{number}",
            "createdAt": "2026-11-01T08:00:00Z", "updatedAt": "2026-11-10T08:00:00Z", "closedAt": None,
            "repository": {"nameWithOwner": repo}, "labels": {"nodes": [{"name": n} for n in labels]},
            "milestone": extra.get("milestone"), "parent": parent,
            "projectItems": {"nodes": [{"fieldValues": {"nodes": values or []}}]}}


def status(name):
    return {"__typename": "ProjectV2ItemFieldSingleSelectValue", "name": name, "field": {"name": "Status"}}


def pull(state="OPEN", head="feature/x", rollup="FAILURE", number=7):
    return {"__typename": "PullRequest", "number": number, "title": "Add x", "url": f"https://github.com/acme/api/pull/{number}",
            "state": state, "isDraft": False, "reviewDecision": "APPROVED", "headRefName": head, "baseRefName": "main",
            "repository": {"nameWithOwner": "acme/api"},
            "commits": {"nodes": [{"commit": {"oid": "a" * 40, "committedDate": "2026-11-02T10:00:00Z", "messageHeadline": "first",
                                              "statusCheckRollup": None}},
                                  {"commit": {"oid": "b" * 40, "committedDate": "2026-11-03T10:00:00Z", "messageHeadline": "second",
                                              "statusCheckRollup": {"state": rollup}}}]}}


class FakeClient:
    def __init__(self):
        self.queries = []
        self.searches = []

    def query(self, query, variables=None):
        self.queries.append(query)
        if "viewer" in query:
            return {"viewer": {"login": "octocat"}}
        if "search(" in query:
            self.searches.append(variables["q"])
            if "is:closed" in variables["q"]:
                return {"search": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [issue(9, state="CLOSED")]}}
            parent = {"number": 1, "title": "Epic", "state": "OPEN", "url": "u", "repository": {"nameWithOwner": "acme/api"}}
            nodes = [issue(2, values=[status("In Review"), {"__typename": "ProjectV2ItemFieldDateValue", "date": "2026-11-20",
                                                              "field": {"name": "Target date"}},
                                      {"__typename": "ProjectV2ItemFieldIterationValue", "title": "Sprint 3", "startDate": "2026-11-09",
                                       "duration": 14, "field": {"name": "Iteration"}}], parent=parent),
                     issue(3, labels=["bug", "status:In Progress"]), issue(4)]
            return {"search": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}
        if "a0: repository" in query:
            events = [{"__typename": "CrossReferencedEvent", "source": pull()},
                      {"__typename": "ConnectedEvent", "subject": pull(state="MERGED", head="feature/y", rollup="SUCCESS", number=8)},
                      {"__typename": "CrossReferencedEvent", "source": pull(state="CLOSED", head="feature/z", number=9)},
                      {"__typename": "CrossReferencedEvent", "source": {"__typename": "Issue"}}]
            return {"a0": {"issue": {"timelineItems": {"nodes": events}}}}
        if "issue(number: $i)" in query:
            node = issue(1, values=[status("In Progress")])
            node["body"] = "Spec: [Design](https://example.com/design) and [issue](https://github.com/acme/api/issues/5)"
            return {"repository": {"issue": node}}
        raise AssertionError(query)


class GitHubProviderTest(unittest.TestCase):
    def setUp(self):
        self.p = GitHubProvider({"provider": "github", "github": {"workspace_only": False}}, client=FakeClient())

    def test_items_map_status_dates_and_parent(self):
        items = {i["id"]: i for i in self.p.list_items()}
        self.assertEqual(set(items), {"acme/api#2", "acme/api#3", "acme/api#4"})
        two = items["acme/api#2"]
        self.assertEqual((two["status"], two["parent"], two["release"]), ("In Review", "acme/api#1", "2026-11-20"))
        self.assertEqual(two["iteration"], ["2026-11-09", "2026-11-22"])
        self.assertEqual(items["acme/api#3"]["status"], "In Progress")   # from the status:* label
        self.assertEqual(items["acme/api#4"]["status"], "Todo")          # nothing known: first stage

    def test_closed_issues_are_online(self):
        item = self.p.list_online_items(30)[0]
        self.assertEqual(item["status"], "Done")
        self.assertIn(item["status"], self.p.workflow()["online"])

    def test_parent_docs_skip_issue_links(self):
        parent = self.p.get_parent("acme/api#1")
        self.assertEqual([d["url"] for d in parent["docs"]], ["https://example.com/design"])
        self.assertEqual(parent["status"], "In Progress")

    def test_dev_info_commits_and_reviews(self):
        info = self.p.dev_info(["acme/api#2"])["acme/api#2"]
        self.assertEqual({c["branch"] for c in info["commits"]}, {"feature/x", "feature/y"})   # closed PR skipped
        self.assertEqual(len(info["crs"]), 3)
        last = next(c for c in info["commits"] if c["sha"] == "b" * 40 and c["branch"] == "feature/x")
        self.assertEqual(last["pipeline"], "FAIL")
        merged = [c for c in info["commits"] if c["branch"] == "feature/y"]
        self.assertTrue(all(c["merged"] for c in merged))                                     # squash merges
        self.assertIn("MERGED", next(c["status"] for c in info["crs"] if c["branch"] == "feature/y"))

    def test_refs_and_urls(self):
        self.assertEqual(self.p.refs_in_message("fix #12 and acme/web#3, not C#5 or a#b", "acme/api"), {"acme/api#12", "acme/web#3"})
        self.assertEqual(self.p.item_url("acme/api#2"), "https://github.com/acme/api/issues/2")
        self.assertEqual(self.p.item_url("junk"), "")

    def test_workflow_is_configurable(self):
        p = GitHubProvider({"github": {"stages": ["Open", "Doing", "Shipped"], "closed_stage": "Shipped"}}, client=FakeClient())
        wf = p.workflow()
        self.assertEqual([s["name"] for s in wf["stages"]], ["Open", "Doing", "Shipped"])
        self.assertEqual(wf["online"], ["Shipped"])


class WorkspaceScopeTest(unittest.TestCase):
    def clone(self, root, rel, url=None):
        path = os.path.join(root, rel)
        os.makedirs(path)
        subprocess.run(["git", "-C", path, "init", "-q"], check=True)
        if url:
            subprocess.run(["git", "-C", path, "remote", "add", "origin", url], check=True)

    def provider(self, config):
        client = FakeClient()
        return GitHubProvider({"provider": "github", **config}, client=client), client

    def test_remotes_of_all_clones_become_repo_qualifiers(self):
        with tempfile.TemporaryDirectory() as d:
            self.clone(d, "api", "https://github.com/acme/api.git")
            self.clone(d, "team/web", "git@github.com:acme/web.git")
            self.clone(d, "ops", "ssh://git@github.com:22/acme/ops")
            self.clone(d, "other", "https://gitlab.com/x/y.git")   # not GitHub
            self.clone(d, "local-only")                            # no remote
            p, client = self.provider({"workspace": d})
            self.assertEqual(p._workspace_repos(), ["acme/api", "acme/ops", "acme/web"])
            p.list_items()
        self.assertEqual(len(client.searches), 1)
        self.assertIn("repo:acme/api repo:acme/ops repo:acme/web", client.searches[0])

    def test_large_workspace_is_split_into_several_searches(self):
        mapping = {f"acme/r{i:02d}": "~/nowhere" for i in range(12)}
        with tempfile.TemporaryDirectory() as d:
            p, client = self.provider({"workspace": d, "repo_paths": mapping})
            items = p.list_items()
        self.assertEqual(len(client.searches), 2)
        self.assertEqual(sorted(i["id"] for i in items), ["acme/api#2", "acme/api#3", "acme/api#4"])   # duplicates merged

    def test_empty_workspace_collects_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            p, client = self.provider({"workspace": d})
            self.assertEqual(p.list_items(), [])
            self.assertEqual(p.list_online_items(30), [])
            self.assertEqual(p.doctor()[1][0], "warn")
        self.assertEqual(client.searches, [])

    def test_workspace_only_can_be_turned_off(self):
        with tempfile.TemporaryDirectory() as d:
            p, client = self.provider({"workspace": d, "github": {"workspace_only": False, "search": "org:acme"}})
            self.assertEqual(len(p.list_items()), 3)
        self.assertNotIn("repo:", client.searches[0])
        self.assertIn("org:acme", client.searches[0])


if __name__ == "__main__":
    unittest.main()
