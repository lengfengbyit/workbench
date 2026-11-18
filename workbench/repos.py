"""Read-only checks on the local git clones: branch state, unmerged commits, whether a sha reached the trunk."""
import os
import time
from datetime import datetime

from .util import git, run


def find_repos(workspace, depth=3):
    """Directories under workspace (up to `depth` levels) that contain a .git entry."""
    found = []
    base = workspace.rstrip(os.sep).count(os.sep)
    for root, dirs, _ in os.walk(workspace):
        if ".git" in dirs or os.path.isfile(os.path.join(root, ".git")):
            found.append(os.path.relpath(root, workspace))
            dirs[:] = []
            continue
        if root.count(os.sep) - base >= depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
    return sorted(found)


def remote_urls(path):
    """[(remote name, url)] of every remote configured in the clone at `path`, origin first (read-only)."""
    out = git(path, "config", "--get-regexp", r"^remote\..*\.url$") or ""
    remotes = []
    for line in out.splitlines():
        key, _, url = line.partition(" ")
        if url:
            remotes.append((key[len("remote."):-len(".url")], url))
    return sorted(remotes, key=lambda r: r[0] != "origin")


OPEN_BRANCH_LIMIT = 10


def open_branches(path, trunk):
    """Remote branches that have commits the trunk does not, newest first, as ({branch, ahead, behind, last}, total).

    A branch that was squash-merged still shows up: git cannot tell its commits reached the trunk."""
    out = git(path, "for-each-ref", "--sort=-committerdate", "--format=%(refname:short)\t%(committerdate:short)",
              "refs/remotes/origin") or ""
    found = []
    for line in out.splitlines():
        ref, _, last = line.partition("\t")
        name = ref.removeprefix("origin/")
        if name in ("HEAD", "origin", trunk):
            continue
        counts = (git(path, "rev-list", "--left-right", "--count", f"origin/{trunk}...{ref}") or "").split()
        if len(counts) == 2 and int(counts[1]):
            found.append({"branch": name, "ahead": int(counts[1]), "behind": int(counts[0]), "last": last})
    return found[:OPEN_BRANCH_LIMIT], len(found)


RECENT_BRANCH_LIMIT = 30


def recent_branches(path, days, now=None):
    """Local and origin branches whose last commit is within `days` days, newest first, as
    ([{branch, last, author, local, remote}], total). A branch that exists both locally and on origin is listed once."""
    out = git(path, "for-each-ref", "--sort=-committerdate",
              "--format=%(refname)\t%(committerdate:unix)\t%(committerdate:short)\t%(authorname)",
              "refs/heads", "refs/remotes/origin") or ""
    cutoff = (now or time.time()) - days * 86400
    found = {}
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) != 4 or not parts[1].isdigit() or int(parts[1]) < cutoff:
            continue
        ref, _, last, author = parts
        if ref.startswith("refs/heads/"):
            name, where = ref[len("refs/heads/"):], "local"
        else:
            name, where = ref[len("refs/remotes/origin/"):], "remote"
        if name == "HEAD":
            continue
        # sorted newest first, so the first ref seen for a name carries its latest commit
        entry = found.setdefault(name, {"branch": name, "last": last, "author": author, "local": False, "remote": False})
        entry[where] = True
    branches = list(found.values())
    return branches[:RECENT_BRANCH_LIMIT], len(branches)


def resolve_path(workspace, repo, mapping=None):
    """Find the local clone for a tracker repo name such as 'owner/name'.

    Order: explicit mapping from config ('repo_paths'), <workspace>/<repo>, <workspace>/<last path segment>.
    """
    candidates = []
    if mapping and repo in mapping:
        candidates.append(os.path.expanduser(mapping[repo]))
    candidates += [os.path.join(workspace, repo), os.path.join(workspace, repo.split("/")[-1])]
    return next((p for p in candidates if os.path.isdir(os.path.join(p, ".git"))), os.path.join(workspace, repo))


def default_branch(path):
    """Name of the remote default branch ('main', 'master', ...), or None when it cannot be determined."""
    head = git(path, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head.removeprefix("origin/")
    for name in ("main", "master", "develop", "trunk"):
        if git(path, "rev-parse", "-q", "--verify", f"origin/{name}") is not None:
            return name
    return None


def collect_repo(path, repo, branches, shas, fetch, recent_days=7):
    info = {"repo": repo, "exists": os.path.isdir(os.path.join(path, ".git")), "branches": {}, "inMaster": {}}
    if not info["exists"]:
        return info
    errors = []
    info["errors"] = errors
    if git(path, "remote", "get-url", "origin") is None:
        # nothing to fetch or compare against: list the active local branches only
        info["recentBranches"], info["recentBranchTotal"] = recent_branches(path, recent_days)
        info["note"] = "没有 origin 远端，只列出本地分支"
        return info
    if fetch:
        code, output = run(["git", "-C", path, "fetch", "-q", "origin"], timeout=120)
        if code != 0:
            errors.append(f"git fetch 失败：{output[:240]}")
    # needs no trunk, so it is filled in even when the default branch cannot be found below
    info["recentBranches"], info["recentBranchTotal"] = recent_branches(path, recent_days)
    trunk = default_branch(path)
    info["trunk"] = trunk
    if not trunk:
        errors.append("找不到 origin 的默认分支，跳过合入状态检查")
        return info
    info["openBranches"], info["openBranchTotal"] = open_branches(path, trunk)
    local = git(path, "branch", "--show-current") or "(detached)"
    status = git(path, "status", "--porcelain") or ""
    info["local"] = {
        "branch": local,
        "dirty": len([x for x in status.splitlines() if x.strip()]),
        "unpushed": int(git(path, "rev-list", "--count", f"origin/{local}..HEAD") or 0),
        "behindRemote": int(git(path, "rev-list", "--count", f"HEAD..origin/{local}") or 0),
        "behindMaster": int(git(path, "rev-list", "--count", f"HEAD..origin/{trunk}") or 0),
    }
    for b in sorted(branches):
        ref = f"origin/{b}"
        if git(path, "rev-parse", "-q", "--verify", ref) is None:
            info["branches"][b] = {"exists": False, "pending": [], "behind": 0}
            continue
        log = git(path, "log", "--no-merges", "--format=%h\t%ad\t%an\t%s", "--date=short", f"origin/{trunk}..{ref}") or ""
        pending = [dict(zip(("sha", "date", "author", "msg"), ln.split("\t", 3))) for ln in log.splitlines() if ln]
        info["branches"][b] = {
            "exists": True, "pending": pending,
            "behind": int(git(path, "rev-list", "--count", f"{ref}..origin/{trunk}") or 0),
            "last": git(path, "log", "-1", "--format=%ad", "--date=short", ref),
        }
    for sha in shas:
        code, _ = run(["git", "-C", path, "merge-base", "--is-ancestor", sha, f"origin/{trunk}"])
        info["inMaster"][sha] = code == 0
    return info


def code_state(commits, in_master):
    """Per (repo, branch) summary of one item's commits: merged into the trunk, last pipeline state, recent commits."""
    groups = {}
    for c in sorted(commits, key=lambda x: x.get("ts") or 0):
        g = groups.setdefault((c["repo"], c["branch"]), {"repo": c["repo"], "branch": c["branch"], "total": 0,
                                                         "pending": 0, "pipeline": None, "recent": []})
        # a provider can vouch for a commit that git cannot see as an ancestor (squash-merged pull requests)
        merged = bool(in_master.get((c["repo"], c["sha"]))) or bool(c.get("merged"))
        g["total"] += 1
        g["pending"] += 0 if merged else 1
        g["pipeline"], g["pipelineUrl"], g["changeUrl"] = c.get("pipeline"), c.get("pipelineUrl"), c.get("changeUrl")
        g["recent"].insert(0, {"sha": c["sha"][:8], "msg": c["msg"], "pipeline": c.get("pipeline"), "merged": merged,
                               "time": datetime.fromtimestamp(c["ts"] / 1000).strftime("%m-%d %H:%M") if c.get("ts") else ""})
        del g["recent"][5:]
    items = list(groups.values())
    if not items:
        state = "none"
    elif all(g["pending"] == 0 for g in items):
        state = "merged"
    else:
        state = "pending"
    return state, items
