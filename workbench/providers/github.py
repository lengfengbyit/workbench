"""GitHub provider: issues assigned to you are items, sub-issue parents are requirements, pull requests are the code.

config.json:
    "provider": "github",
    "github": {
        "stages": ["Todo", "In Progress", "In Review", "Done"],   # order and names of the workflow
        "closed_stage": "Done",                                  # stage of a closed issue
        "status_field": "Status",                                # Projects v2 single-select field read for the stage
        "date_fields": {"Start date": "devStart", "End date": "devEnd", "Target date": "release"},
        "iteration_field": "Iteration",                          # Projects v2 iteration field, gives the iteration range
        "search": "org:my-org",                                  # extra search qualifiers for "my issues"
        "workspace_only": true,                                  # default: only issues in repos cloned under "workspace"
        "web_url": "https://github.com", "graphql_url": "https://api.github.com/graphql"   # for GitHub Enterprise
    }
Needs a token in GITHUB_TOKEN / GH_TOKEN, or a logged-in `gh` CLI. Reading Projects v2 needs the read:project scope.

With workspace_only (the default) the clones under "workspace" are found recursively, their GitHub remotes are read
and only issues in those repositories are collected. Keys of "repo_paths" count as well. Set it to false to collect
every issue assigned to you. "search" is added to the query either way; with workspace_only use it for filters such
as labels, and use workspace_only=false when it should pick the scope (org:...).
"""
import os
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from ..repos import find_repos, remote_urls
from ..settings import resolve_workspace
from ..util import epoch_ms, iso_date
from .base import DEFAULT_STAGE_COLORS, Provider, ProviderError
from .github_api import ISSUE_FIELDS, TIMELINE, GraphQLClient

DEFAULT_STAGES = ["Todo", "In Progress", "In Review", "Done"]
REPOS_PER_QUERY = 10   # repo: qualifiers per search, so a large workspace does not make one oversized query
ID_RE = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$")
REF_RE = re.compile(r"(?<![\w/.#&-])(?:([\w.-]+/[\w.-]+))?#(\d+)\b")
LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
CHECKS = {"SUCCESS": "PASS", "FAILURE": "FAIL", "ERROR": "FAIL"}


class GitHubProvider(Provider):
    name = "github"

    def __init__(self, config, client=None):
        super().__init__(config)
        o = self.options
        self.stage_names = o.get("stages") or DEFAULT_STAGES
        self.closed_stage = o.get("closed_stage") or self.stage_names[-1]
        self.status_field = o.get("status_field", "Status")
        self.date_fields = o.get("date_fields", {"Start date": "devStart", "End date": "devEnd", "Target date": "release"})
        self.iteration_field = o.get("iteration_field", "Iteration")
        self.extra = o.get("search", "")
        self.web = o.get("web_url", "https://github.com").rstrip("/")
        self.workspace_only = o.get("workspace_only", True)
        self._remote_re = re.compile(
            re.escape(urlparse(self.web).netloc) + r"(?::\d+)?[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", re.IGNORECASE)
        self.client = client or GraphQLClient(o.get("graphql_url", "https://api.github.com/graphql"))
        self._login = None

    # ---- workflow ----
    def workflow(self):
        colors = DEFAULT_STAGE_COLORS
        stages = [{"name": n, "color": colors[i * (len(colors) - 1) // max(1, len(self.stage_names) - 1)]}
                  for i, n in enumerate(self.stage_names)]
        return {"stages": stages, "done": [self.closed_stage], "online": [self.closed_stage],
                "dev": self.stage_names[:max(1, len(self.stage_names) - 2)]}

    def whoami(self):
        if not self._login:
            self._login = self.client.query("query { viewer { login } }")["viewer"]["login"]
        return self._login

    def scope(self):
        return self.options.get("scope", "")

    # ---- normalising issues ----
    def _stage(self, node):
        if node.get("state") == "CLOSED":
            return self.closed_stage
        for v in self._field_values(node):
            if v.get("__typename") == "ProjectV2ItemFieldSingleSelectValue" and (v.get("field") or {}).get("name") == self.status_field:
                return v["name"]
        for label in (node.get("labels") or {}).get("nodes", []):
            if label["name"].lower().startswith("status:"):
                return label["name"].split(":", 1)[1].strip()
        return self.stage_names[0]

    @staticmethod
    def _field_values(node):
        for item in ((node.get("projectItems") or {}).get("nodes")) or []:
            yield from ((item.get("fieldValues") or {}).get("nodes")) or []

    def _item(self, node):
        repo = node["repository"]["nameWithOwner"]
        item = {"id": f"{repo}#{node['number']}", "title": node["title"], "status": self._stage(node), "type": "Issue",
                "num": int((epoch_ms(node.get("createdAt")) or 0) / 1000), "url": node.get("url"),
                "plan": (node.get("milestone") or {}).get("title"), "created": iso_date(node.get("createdAt")),
                "modified": (node.get("updatedAt") or "")[:16].replace("T", " ")}
        parent = node.get("parent")
        if parent:
            item["parent"] = f"{parent['repository']['nameWithOwner']}#{parent['number']}"
            item["parentTitle"] = parent["title"]
        for v in self._field_values(node):
            field = (v.get("field") or {}).get("name")
            if v.get("__typename") == "ProjectV2ItemFieldDateValue" and field in self.date_fields:
                item[self.date_fields[field]] = v.get("date")
            elif v.get("__typename") == "ProjectV2ItemFieldIterationValue" and field == self.iteration_field and v.get("startDate"):
                start = date.fromisoformat(v["startDate"])
                item["iteration"] = [start.isoformat(), (start + timedelta(days=int(v.get("duration") or 1) - 1)).isoformat()]
                item["plan"] = item["plan"] or v.get("title")
        if (node.get("milestone") or {}).get("dueOn") and not item.get("release"):
            item["release"] = iso_date(node["milestone"]["dueOn"])
        return item

    def _scan(self):
        """{'owner/name': clone path} for every GitHub remote of the clones under the workspace, plus repo_paths.
        The first remote of a clone (origin) comes first, so listing one name per path gives its main repository."""
        root = resolve_workspace(self.config)
        found = {}
        for repo, path in (self.config.get("repo_paths") or {}).items():
            found[repo] = os.path.abspath(os.path.expanduser(path))
        if os.path.isdir(root):
            for rel in find_repos(root):
                path = os.path.join(root, rel)
                for _, url in remote_urls(path):
                    m = self._remote_re.search(url.strip())
                    if m:
                        found.setdefault(f"{m.group(1)}/{m.group(2)}", path)
        return found

    def _workspace_repos(self):
        return sorted(self._scan(), key=str.lower)

    def local_repos(self):
        return {name: path for name, path in self._scan().items() if os.path.isdir(os.path.join(path, ".git"))}

    def _scopes(self):
        """Qualifier strings, one search each. [""] means no restriction, [] means nothing to look at."""
        if not self.workspace_only:
            return [""]
        repos = self._workspace_repos()
        return [" ".join(f"repo:{r}" for r in repos[i:i + REPOS_PER_QUERY]) for i in range(0, len(repos), REPOS_PER_QUERY)]

    def _search(self, qualifiers, limit=100):
        out, seen = [], set()
        for scope in self._scopes():
            for node in self._search_one(f"{qualifiers} {scope}".strip(), limit - len(out)):
                key = (node["repository"]["nameWithOwner"], node["number"])
                if key not in seen:
                    seen.add(key)
                    out.append(node)
            if len(out) >= limit:
                break
        return [self._item(n) for n in out]

    def _search_one(self, qualifiers, limit):
        out, after = [], None
        query = """query($q: String!, $after: String) { search(query: $q, type: ISSUE, first: 50, after: $after) {
            pageInfo { hasNextPage endCursor } nodes { ... on Issue { %s } } } }""" % ISSUE_FIELDS
        while len(out) < limit:
            data = self.client.query(query, {"q": f"is:issue assignee:@me archived:false {qualifiers} {self.extra}".strip(), "after": after})["search"]
            out += [n for n in data["nodes"] if n]
            if not data["pageInfo"]["hasNextPage"]:
                break
            after = data["pageInfo"]["endCursor"]
        return out[:limit]

    def list_items(self):
        return self._search("is:open")

    def list_online_items(self, days):
        since = (date.today() - timedelta(days=days)).isoformat()
        return self._search(f"is:closed closed:>={since}")

    def get_parent(self, item_id):
        m = ID_RE.match(item_id)
        if not m:
            raise ProviderError(f"not a GitHub issue id: {item_id!r} (expected owner/repo#number)")
        owner_repo, number = m.groups()
        owner, name = owner_repo.split("/")
        node = self.client.query(
            "query($o: String!, $n: String!, $i: Int!) { repository(owner: $o, name: $n) { issue(number: $i) { body %s } } }" % ISSUE_FIELDS,
            {"o": owner, "n": name, "i": int(number)})["repository"]["issue"]
        item = self._item(node)
        body = node.get("body") or ""
        docs = [{"type": "tracker", "title": t, "url": u, "source": "tracker"} for t, u in LINK_RE.findall(body)
                if not re.search(r"/(issues|pull)/\d+$", u)]
        return {"id": item_id, "num": item["num"], "title": item["title"], "status": item["status"], "type": item["type"],
                "plan": item["plan"], "actualRelease": iso_date(node.get("closedAt")), "modified": iso_date(node.get("updatedAt")),
                "detailText": body[:4000], "docs": docs, "url": item["url"]}

    # ---- code ----
    def dev_info(self, ids):
        out = {i: {"commits": [], "crs": []} for i in ids}
        valid = [i for i in ids if ID_RE.match(i)]
        for start in range(0, len(valid), 10):
            chunk = valid[start:start + 10]
            decls, body, variables = [], [], {}
            for k, item_id in enumerate(chunk):
                owner, name = ID_RE.match(item_id).group(1).split("/")
                decls.append(f"$o{k}: String!, $n{k}: String!, $i{k}: Int!")
                body.append(f"a{k}: repository(owner: $o{k}, name: $n{k}) {{ issue(number: $i{k}) {{ {TIMELINE} }} }}")
                variables.update({f"o{k}": owner, f"n{k}": name, f"i{k}": int(ID_RE.match(item_id).group(2))})
            data = self.client.query(f"query({', '.join(decls)}) {{ {' '.join(body)} }}", variables)
            for k, item_id in enumerate(chunk):
                issue = ((data.get(f"a{k}") or {}).get("issue")) or {}
                prs = {}
                for ev in (issue.get("timelineItems") or {}).get("nodes", []):
                    pr = ev.get("source") or ev.get("subject") or {}
                    if pr.get("__typename") == "PullRequest":
                        prs[pr["url"]] = pr
                out[item_id] = self._code(prs.values())
        return out

    @staticmethod
    def _code(prs):
        commits, crs, seen = [], [], set()
        for pr in prs:
            repo = pr["repository"]["nameWithOwner"]
            status = pr["state"] + (f" · {pr['reviewDecision']}" if pr.get("reviewDecision") else "") + (" · draft" if pr.get("isDraft") else "")
            crs.append({"repo": repo, "branch": pr["headRefName"], "status": status, "msg": pr["title"], "url": pr["url"]})
            if pr["state"] == "CLOSED":
                continue   # closed without merging: its commits are not going anywhere
            rows = [n["commit"] for n in pr["commits"]["nodes"]]
            for i, c in enumerate(rows):
                if (repo, pr["headRefName"], c["oid"]) in seen:
                    continue
                seen.add((repo, pr["headRefName"], c["oid"]))
                last = i == len(rows) - 1
                state = ((c.get("statusCheckRollup") or {}).get("state")) if last else None
                commits.append({"repo": repo, "branch": pr["headRefName"], "sha": c["oid"], "ts": epoch_ms(c["committedDate"]),
                                "msg": c["messageHeadline"], "pipeline": CHECKS.get(state),
                                "pipelineUrl": pr["url"] + "/checks" if state else None, "changeUrl": pr["url"],
                                "merged": pr["state"] == "MERGED"})
        return {"commits": commits, "crs": crs}

    # ---- links ----
    def item_url(self, item_id):
        m = ID_RE.match(item_id)
        return f"{self.web}/{m.group(1)}/issues/{m.group(2)}" if m else ""

    def links(self):
        return {"repo": self.web + "/{repo}", "branch": self.web + "/{repo}/tree/{branch}"}

    def refs_in_message(self, message, repo):
        return {f"{r or repo}#{n}" for r, n in REF_RE.findall(message or "")}

    def doctor(self):
        try:
            login = self.whoami()
        except ProviderError as e:
            return [("fail", str(e))]
        report = [("ok", f"authenticated to GitHub as {login}")]
        if self.workspace_only:
            repos = self._workspace_repos()
            report.append(("ok", f"{len(repos)} GitHub repositories found under the workspace, only their issues are collected "
                                 "(github.workspace_only=false collects everything assigned to you)")
                          if repos else
                          ("warn", "no GitHub remotes found under the workspace, so nothing will be collected. Check \"workspace\" "
                                   "in config.json, or set github.workspace_only to false"))
        return report + [
            ("warn", "stage, dates and iteration come from Projects v2 fields; the token needs the read:project scope "
                     "(`gh auth refresh -s read:project`). Without it, stages fall back to labels `status:<name>` or open/closed.")]
