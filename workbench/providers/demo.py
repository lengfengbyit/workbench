"""Offline demo provider. `workbench serve --demo` builds throw-away git repos and serves fictional items,
so the UI can be tried without an account. The same fixture backs the end-to-end tests."""
import os
import re
from datetime import date, datetime, timedelta

from ..util import run
from .base import Provider

STAGES = [("Backlog", "#94a3b8"), ("In Progress", "#3b82f6"), ("In Review", "#a855f7"), ("Testing", "#f59e0b"),
          ("Done", "#10b981")]

# repo -> branch -> [(commit message, days ago)]; "main" is the trunk and "merged" branches are folded into it
SPEC = {
    "acme/api": {
        "branches": {
            "feature/checkout-api": [("WB-2 add checkout endpoint", 5), ("WB-2 validate cart", 3), ("WB-9 fix typo in docs", 2)],
            "feature/rate-limit": [("WB-4 token bucket limiter", 1)],
        },
        "merged": {"feature/search-filters": [("WB-6 search filter parameters", 9)]},
        "trunk_after": [("chore: bump dependencies", 1)],
    },
    "acme/web": {
        "branches": {"feature/checkout-ui": [("WB-3 checkout form", 4), ("WB-3 order summary", 2)]},
        "merged": {},
        "trunk_after": [],
    },
}


def _git_env():
    return {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_AUTHOR_NAME": "Demo", "GIT_AUTHOR_EMAIL": "demo@example.com",
            "GIT_COMMITTER_NAME": "Demo", "GIT_COMMITTER_EMAIL": "demo@example.com"}


def make_workspace(root):
    """Create clones under root/<owner>/<name> with their origins in root/_origin. Returns {repo: {branch: [commit]}}."""
    env = _git_env()
    commits = {}

    def git(path, *args, when=None):
        e = dict(env)
        if when is not None:
            stamp = (datetime.now() - timedelta(days=when)).strftime("%Y-%m-%dT%H:%M:%S")
            e["GIT_AUTHOR_DATE"] = e["GIT_COMMITTER_DATE"] = stamp
        code, out = run(["git", "-C", path, *args], env=e)
        if code != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {out}")
        return out

    def commit(path, repo, branch, msg, days):
        slug = re.sub(r"\W+", "-", msg)[:40]
        with open(os.path.join(path, f"{slug}.txt"), "w", encoding="utf-8") as f:
            f.write(msg + "\n")
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", msg, when=days)
        commits.setdefault(repo, {}).setdefault(branch, []).append(
            {"sha": git(path, "rev-parse", "HEAD"), "msg": msg, "ts": int((datetime.now() - timedelta(days=days)).timestamp() * 1000)})

    for repo, spec in SPEC.items():
        origin = os.path.join(root, "_origin", repo + ".git")
        path = os.path.join(root, repo)
        os.makedirs(origin)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        git(os.path.dirname(origin), "init", "-q", "--bare", "-b", "main", origin)
        git(os.path.dirname(path), "clone", "-q", origin, path)
        git(path, "checkout", "-q", "-b", "main")
        commit(path, repo, "main", "initial commit", 20)
        git(path, "push", "-q", "origin", "main")
        git(path, "remote", "set-head", "origin", "main")
        for branch, items in spec["merged"].items():
            git(path, "checkout", "-q", "-b", branch, "main")
            for msg, days in items:
                commit(path, repo, branch, msg, days)
            git(path, "checkout", "-q", "main")
            git(path, "merge", "-q", "--no-ff", "-m", f"Merge {branch}", branch, when=0)
            git(path, "push", "-q", "origin", "main", branch)
        for branch, items in spec["branches"].items():
            git(path, "checkout", "-q", "-b", branch, "main")
            for msg, days in items:
                commit(path, repo, branch, msg, days)
            git(path, "push", "-q", "origin", branch)
            git(path, "checkout", "-q", "main")
        for msg, days in spec["trunk_after"]:
            commit(path, repo, "main", msg, days)
            git(path, "push", "-q", "origin", "main")
        git(path, "fetch", "-q", "origin")
    return commits


def _day(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


class DemoProvider(Provider):
    name = "demo"
    id_prefix = "WB-"

    def __init__(self, config, commits=None):
        super().__init__(config)
        self.commits = commits or {}

    def workflow(self):
        return {"stages": [{"name": n, "color": c} for n, c in STAGES], "done": ["Done"], "online": ["Done"],
                "dev": ["Backlog", "In Progress"]}

    def whoami(self):
        return "demo-user"

    def scope(self):
        return "demo workspace"

    def item_url(self, item_id):
        return f"https://example.com/items/{item_id}"

    def links(self):
        return {"repo": "https://example.com/repos/{repo}", "branch": "https://example.com/repos/{repo}/tree/{branch}"}

    def refs_in_message(self, message, repo):
        return set(re.findall(r"WB-(\d+)", message))

    def _parents(self):
        return {
            "1": {"id": "1", "num": 1, "title": "【Web】Checkout redesign", "status": "In Progress", "type": "Feature",
                  "plan": "Sprint 12", "actualRelease": None, "modified": _day(-1), "detailText": "Rebuild the checkout flow.",
                  "docs": [{"type": "tracker", "title": "Design brief", "url": "https://example.com/design-brief", "source": "tracker"}]},
            "5": {"id": "5", "num": 5, "title": "【Platform】Rate limiting", "status": "In Review", "type": "Feature",
                  "plan": "Sprint 12", "actualRelease": None, "modified": _day(-1), "detailText": "", "docs": []},
            "8": {"id": "8", "num": 8, "title": "【Search】Search filters", "status": "Done", "type": "Feature",
                  "plan": "Sprint 11", "actualRelease": _day(-5), "modified": _day(-5), "detailText": "", "docs": []},
        }

    def list_items(self):
        base = {"type": "Story", "qa": "", "created": _day(-14), "modified": _day(-1)}
        return [
            {**base, "id": "2", "num": 2, "parent": "1", "title": "Checkout API", "status": "In Progress", "plan": "Sprint 12",
             "devStart": _day(-10), "devEnd": _day(3), "testPlan": _day(-2), "release": _day(10), "iteration": [_day(-10), _day(4)],
             "url": self.item_url("2")},
            {**base, "id": "3", "num": 3, "parent": "1", "title": "Checkout UI", "status": "In Review", "plan": "Sprint 12",
             "devStart": _day(-9), "devEnd": _day(2), "testPlan": _day(2), "release": _day(10), "iteration": [_day(-10), _day(4)]},
            {**base, "id": "4", "num": 4, "parent": "5", "title": "Token bucket limiter", "status": "Testing", "plan": "Sprint 12",
             "devStart": _day(-8), "devEnd": _day(-1), "testPlan": _day(-1), "release": _day(6), "iteration": [_day(-14), _day(-1)]},
        ]

    def list_online_items(self, days):
        return [{"id": "6", "num": 6, "parent": "8", "title": "Search filter parameters", "status": "Done", "modified": _day(-5)}]

    def get_parent(self, item_id):
        return self._parents().get(str(item_id)) or {
            "id": str(item_id), "num": int(item_id), "title": f"Item {item_id}", "status": "Backlog", "type": "Feature",
            "plan": None, "actualRelease": None, "modified": _day(0), "detailText": "", "docs": []}

    def _commits(self, repo, branch, pipeline=None, change=None):
        rows = self.commits.get(repo, {}).get(branch, [])
        return [{"repo": repo, "branch": branch, "sha": c["sha"], "ts": c["ts"], "msg": c["msg"],
                 "pipeline": pipeline if i == len(rows) - 1 else "PASS", "pipelineUrl": "https://example.com/ci/1" if pipeline else None,
                 "changeUrl": change} for i, c in enumerate(rows)]

    def dev_info(self, ids):
        table = {
            "2": {"commits": self._commits("acme/api", "feature/checkout-api"),
                  "crs": [{"repo": "acme/api", "branch": "feature/checkout-api", "status": "OPEN", "msg": "Checkout API", "url": "https://example.com/cr/1"}]},
            "3": {"commits": self._commits("acme/web", "feature/checkout-ui"), "crs": []},
            "4": {"commits": self._commits("acme/api", "feature/rate-limit", "FAIL", "https://example.com/cr/2"), "crs": []},
            "6": {"commits": self._commits("acme/api", "feature/search-filters"), "crs": []},
        }
        return {i: table.get(i, {"commits": [], "crs": []}) for i in ids}
