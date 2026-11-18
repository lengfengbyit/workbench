"""Turns provider data plus local git state into the dict the web UI renders (data.json)."""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from .repos import code_state, collect_repo, find_repos, resolve_path
from .settings import ui_config

RECENT_ONLINE_DAYS = 30


def _dkey(url):
    """http / https and trailing slashes count as the same document link."""
    return re.sub(r"^https?://", "", (url or "").split("?")[0].rstrip("/"))


def collect_recent_online(provider, wf, exclude, unfinished, days=RECENT_ONLINE_DAYS):
    """Requirements shipped in the last `days` days, judged by whether the parent item is in an online stage.

    exclude: ids still in progress or archived by hand. unfinished: {parent id: [stories not shipped yet]},
    listed too, with the unfinished stories marked."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    online = set(wf["online"])
    groups = {}
    for c in provider.list_online_items(days):
        groups.setdefault(c.get("parent") or c["id"], []).append(c)
    keys = list(dict.fromkeys(k for k in [*groups, *unfinished] if k not in exclude))

    def head(item_id):   # one retry, then skip this item instead of failing the whole list
        for _ in range(2):
            try:
                return provider.get_parent(item_id)
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        return None

    with ThreadPoolExecutor(4) as ex:
        heads = dict(zip(keys, ex.map(head, keys)))
    skipped = [k for k, p in heads.items() if p is None]
    items = []
    for key, p in heads.items():
        if p is None or p["status"] not in online:
            continue
        shipped = p.get("actualRelease") or p.get("modified")
        if not shipped or shipped < cutoff:
            continue
        items.append({"id": key, "title": p["title"], "type": p.get("type"), "status": p["status"],
                      "onlineDate": shipped, "dateSource": "actual" if p.get("actualRelease") else "modified",
                      "stories": [{"id": c["id"], "title": c["title"]} for c in groups.get(key, []) if c["id"] != key],
                      "pendingStories": [{"id": c["id"], "title": c["title"], "status": c["status"]} for c in unfinished.get(key, [])]})
    ids = [s["id"] for it in items for s in it["stories"] + it["pendingStories"]]
    dev = provider.dev_info(ids) if ids else {}
    for it in items:
        it["repos"] = sorted({c["repo"] for s in it["stories"] + it["pendingStories"]
                              for c in dev.get(s["id"], {}).get("commits", [])})
    return sorted(items, key=lambda x: (x["onlineDate"], x["id"]), reverse=True), skipped


def _activity(dev, today):
    """Commits per repo per day over the last 30 days (deduplicated by sha), with details for the hover tip."""
    days = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    seen, series, detail = set(), {}, {}
    for item_id, d in dev.items():
        for c in d["commits"]:
            if c["sha"] in seen or not c.get("ts"):
                continue
            seen.add(c["sha"])
            t = datetime.fromtimestamp(c["ts"] / 1000)
            day = t.date().isoformat()
            if day in days:
                i = days.index(day)
                series.setdefault(c["repo"], [0] * len(days))[i] += 1
                detail.setdefault(c["repo"], [[] for _ in days])[i].append(
                    {"sha": c["sha"][:8], "msg": c["msg"], "branch": c["branch"], "id": item_id, "time": t.strftime("%H:%M")})
    return {"days": days, "series": series, "detail": detail}


def _clones(settings, provider):
    """{repo name: path} of every clone to list: the ones the provider recognises (named the way its commits name
    them), then any other clone under the workspace, named by its path relative to the workspace. The second value
    holds the names of the latter, which have no page on the tracker to link to."""
    clones, real, unlinked = {}, set(), set()
    for name, path in provider.local_repos().items():
        clones[name] = path
        real.add(os.path.realpath(path))
    root = settings.workspace
    for rel in find_repos(root) if os.path.isdir(root) else []:
        path = os.path.join(root, rel)
        if os.path.realpath(path) not in real:
            real.add(os.path.realpath(path))
            name = rel.replace(os.sep, "/")
            clones[name] = path
            unlinked.add(name)
    return clones, unlinked


def _local_requirements(notes, wf, archived_ids):
    """Requirements created on the page from repos and branches. The first stage stands in for an unknown status."""
    names = [s["name"] for s in wf["stages"]]
    out = {}
    for key, n in notes["requirements"].items():
        if not n.get("manual") or key in archived_ids:
            continue
        out[key] = {"id": key, "title": n.get("title") or key, "status": n.get("status") if n.get("status") in names else names[0],
                    "type": "本地需求", "plan": None, "num": 0, "manual": True, "stories": [], "relation": n}
    return out


def build(settings, provider, notes_store, fetch=True):
    today = date.today()
    wf = provider.workflow()
    online, dev_stages = set(wf["online"]), set(wf["dev"])
    label = lambda i: f"{provider.id_prefix}{i}"   # noqa: E731
    notes = notes_store.load()
    archived_ids = {a["id"] for a in notes["archived"]}
    mapping = settings.config.get("repo_paths")

    cards = provider.list_items()
    parent_ids = sorted({c["parent"] for c in cards if c.get("parent")})
    with ThreadPoolExecutor(8) as ex:
        parents = dict(zip(parent_ids, ex.map(provider.get_parent, parent_ids)))
    dev = provider.dev_info([c["id"] for c in cards])

    branches, shas = {}, {}
    for d in dev.values():
        for c in d["commits"]:
            branches.setdefault(c["repo"], set()).add(c["branch"])
            shas.setdefault(c["repo"], set()).add(c["sha"])
    named_by_tracker = set(branches)
    local_reqs = _local_requirements(notes, wf, archived_ids)
    for r in local_reqs.values():
        for x in r["relation"].get("repos") or []:
            branches.setdefault(x["repo"], set()).add(x["branch"])
    # every clone in the workspace is managed whether or not an item refers to it: one entry per clone
    local, unlinked = _clones(settings, provider)
    mapping = {**local, **(mapping or {})}
    paths = {os.path.realpath(resolve_path(settings.workspace, r, mapping)) for r in branches}
    for name, path in local.items():
        real = os.path.realpath(path)
        if name not in branches and real not in paths:
            paths.add(real)
            branches[name] = set()
    days = ui_config(settings.config)["recent_branch_days"]
    with ThreadPoolExecutor(8) as ex:
        repos = list(ex.map(lambda r: collect_repo(resolve_path(settings.workspace, r, mapping), r,
                                                   branches[r], shas.get(r, set()), fetch, days), sorted(branches)))
    for r in repos:
        if r["repo"] in unlinked and r["repo"] not in named_by_tracker:
            r["noLink"] = True
    repo_map = {r["repo"]: r for r in repos}
    in_master = {(r["repo"], s): v for r in repos for s, v in r["inMaster"].items()}
    trunks = [r["trunk"] for r in repos if r.get("trunk")]
    trunk = max(set(trunks), key=trunks.count) if trunks else "主干"

    alerts, collection_errors = [], []

    def alert(level, item_id, text, kind, links=None):
        alerts.append({"level": level, "id": item_id, "text": text, "kind": kind, "links": links or []})

    reqs, online_parents = {}, {}   # online_parents: parent shipped but some stories not moved on yet
    for c in cards:
        d = dev.get(c["id"], {"commits": [], "crs": []})
        c["codeState"], c["code"] = code_state(d["commits"], in_master)
        c["crs"] = d["crs"]
        c["crCount"] = len(d["crs"])
        c["iteration"] = c.get("iteration") or provider.parse_iteration(c.get("plan"), int((c.get("created") or str(today.year))[:4]))
        key = c.get("parent") or c["id"]
        if key in archived_ids:
            continue
        p = parents.get(c.get("parent")) or {"id": c["id"], "title": c["title"], "status": c["status"], "plan": c.get("plan"),
                                              "type": c.get("type"), "num": c.get("num", 0)}
        req_notes = notes["requirements"].get(str(key), {})
        # the parent decides whether a requirement is still running: once it shipped, leftover stories only get a reminder
        if p["status"] in online and not req_notes.get("track"):
            online_parents.setdefault(key, []).append(c)
            alert("info", c["id"], f"上级需求 {label(key)} 已上线，这个条目仍是「{c['status']}」，需求已按上级归档", "card_lag")
            continue
        r = reqs.setdefault(key, {**p, "stories": [], "relation": req_notes})
        r["stories"].append(c)
        for g in c["code"]:
            if g["pipeline"] == "FAIL":
                links = [{"label": "查看流水线", "url": g["pipelineUrl"]}] if g.get("pipelineUrl") else []
                if g.get("changeUrl"):
                    links.append({"label": "查看评审", "url": g["changeUrl"]})
                alert("warn", c["id"], f"{g['repo']} 分支 {g['branch']} 最近一次提交流水线失败", "pipeline", links)
        if c["codeState"] == "merged" and c["status"] not in online:
            alert("info", c["id"], f"代码已全部进主干，条目仍是「{c['status']}」", "card_lag")
        if c.get("testPlan") and c["testPlan"] < today.isoformat() and c["status"] in dev_stages:
            alert("warn", c["id"], f"计划提测 {c['testPlan']} 已过，条目仍是「{c['status']}」", "overdue")
        if c["iteration"] and c["iteration"][1] < today.isoformat():
            alert("info", c["id"], f"所在迭代已于 {c['iteration'][1]} 结束", "iteration")

    # parents marked "track" in notes.json show up even without an item of mine (or when already in a done stage)
    tracked = [k for k, v in notes["requirements"].items() if v.get("track") and k not in reqs and k not in archived_ids]
    with ThreadPoolExecutor(8) as ex:
        for p in ex.map(provider.get_parent, tracked):
            reqs[p["id"]] = {**p, "stories": [], "relation": notes["requirements"][str(p["id"])]}
    reqs.update({k: v for k, v in local_reqs.items() if k not in reqs})

    # per requirement: which (repo, branch) it touches, and which unmerged commits are its own vs. carried by others
    for key, r in reqs.items():
        own = {s["id"] for s in r["stories"]}
        pairs = {(g["repo"], g["branch"]) for s in r["stories"] for g in s["code"]}
        if r.get("manual"):
            pairs |= {(x["repo"], x["branch"]) for x in r["relation"].get("repos") or []}
        r["repos"] = []
        for repo, b in sorted(pairs):
            bi = repo_map.get(repo, {}).get("branches", {}).get(b, {"exists": False, "pending": [], "behind": 0})
            # a local requirement has no item ids to match commits against: everything on its branches is its own
            mine = bi["pending"] if r.get("manual") else [x for x in bi["pending"] if own & provider.refs_in_message(x["msg"], repo)]
            others = [x for x in bi["pending"] if x not in mine]
            r["repos"].append({"repo": repo, "branch": b, "exists": bi["exists"], "behind": bi["behind"],
                               "mine": len(mine), "others": others, "pending": bi["pending"],
                               "localOnly": bool(repo_map.get(repo, {}).get("note"))})   # no origin: nothing to compare
            if others:
                refs = sorted({label(i) for x in others for i in provider.refs_in_message(x["msg"], repo)})
                alert("info", key, f"{repo} 的 {b} 上还有 {len(others)} 个其他条目的提交（{'、'.join(refs) or '无编号'}），合入时会一起带上", "others")
            if bi["pending"] and bi["behind"]:
                alert("info", key, f"{repo} 的 {b} 落后 {trunk} {bi['behind']} 个提交，合入前要先同步", "behind")
        r["iteration"] = next((s["iteration"] for s in r["stories"] if s["iteration"]), None) \
            or provider.parse_iteration(r.get("plan"), today.year)
        r["mergedAll"] = all(z["mine"] == 0 for z in r["repos"]) if r.get("manual") \
            else all(s["codeState"] != "pending" for s in r["stories"])
        note = notes["requirements"].get(str(key), {})
        r["info"] = note.get("info") or {}
        tracker_docs = r.get("docs", [])   # links the tracker itself carries
        manual = [dict(x, source="manual") for x in note.get("docs", [])]
        seen = {_dkey(x.get("url")) for x in manual}
        r["docs"] = manual + [x for x in tracker_docs if _dkey(x["url"]) not in seen]

    recent = []
    try:
        recent, skipped = collect_recent_online(provider, wf, set(reqs) | archived_ids, online_parents)
        if skipped:
            text = f"近期已上线需求有 {len(skipped)} 个读取失败，已跳过：" + "、".join(label(s) for s in skipped[:10])
            collection_errors.append({"repo": provider.name, "text": text})
            alert("warn", None, text, "collection")
    except Exception as e:  # noqa: BLE001  this block failing must not hide everything else
        text = f"近期已上线需求查询失败：{str(e)[:200]}"
        collection_errors.append({"repo": provider.name, "text": text})
        alert("warn", None, text, "collection")

    for r in repos:
        for error in r.get("errors", []):
            collection_errors.append({"repo": r["repo"], "text": error})
            alert("warn", None, f"{r['repo']}：{error}", "collection")
        loc = r.get("local") or {}
        if loc.get("behindRemote"):
            alert("info", None, f"本地 {r['repo']} 的 {loc['branch']} 落后远端 {loc['behindRemote']} 个提交", "local")
        if loc.get("dirty"):
            alert("info", None, f"本地 {r['repo']} 有 {loc['dirty']} 个未提交 / 未跟踪文件", "local")

    ordered = sorted(reqs.values(), key=lambda r: -max([r.get("num", 0)] + [s.get("num", 0) for s in r["stories"]]))
    ids = {a["id"] for a in alerts if a["id"]} | {a["id"] for a in notes["archived"]}
    for r in [*ordered, *recent]:
        ids |= {r["id"], *(s["id"] for s in r["stories"]), *(s["id"] for s in r.get("pendingStories", []))}
    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "collectionOk": not collection_errors,
        "collectionErrors": collection_errors, "today": today.isoformat(),
        "provider": provider.name, "user": provider.whoami(), "scope": provider.scope(), "idPrefix": provider.id_prefix,
        "trunk": trunk, "links": provider.links(), "urls": {i: provider.item_url(i) for i in sorted(ids)},
        "stages": wf["stages"], "requirements": ordered, "repos": repos, "alerts": alerts,
        "activity": _activity(dev, today), "archived": notes["archived"], "recentOnline": recent,
        "recentOnlineDays": RECENT_ONLINE_DAYS, "uiConfig": ui_config(settings.config),
    }
