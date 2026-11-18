"""notes.json: the hand-maintained part (repo relations, summaries, doc links, tracking, archive)."""
import json
import os
import re
import threading
from datetime import date

DOC_TYPES = {"prd", "tech", "ui", "test", "other"}
LOCAL_PREFIX = "local-"
MAX_LOCAL_REPOS = 30
MAX_EDGES = 50


def _text(value, limit):
    return str(value or "").strip()[:limit]


def _local_fields(body):
    """Validated title, status, repos (in call order), nodes, edges and note of a local requirement."""
    title = _text(body.get("title"), 200)
    if not title:
        raise ValueError("请填写需求标题")
    repos, seen = [], set()
    for x in body.get("repos") or []:
        repo, branch = _text((x or {}).get("repo"), 200), _text((x or {}).get("branch"), 200)
        if not repo or not branch:
            raise ValueError("每个仓库都要选好分支")
        if (repo, branch) not in seen:
            seen.add((repo, branch))
            repos.append({"repo": repo, "branch": branch})
    if not repos:
        raise ValueError("至少选择一个仓库和分支")
    if len(repos) > MAX_LOCAL_REPOS:
        raise ValueError(f"最多 {MAX_LOCAL_REPOS} 个仓库分支")
    nodes = list(dict.fromkeys(x["repo"] for x in repos))
    edges = []
    for e in body.get("edges") or []:
        if not isinstance(e, (list, tuple)) or len(e) < 2:
            raise ValueError("仓库关系格式不对：需要 [调用方, 被调用方, 说明]")
        caller, callee, desc = _text(e[0], 200), _text(e[1], 200), _text(e[2] if len(e) > 2 else "", 200)
        if caller not in nodes or callee not in nodes:
            raise ValueError("仓库关系里只能用这个需求选中的仓库")
        if caller == callee:
            raise ValueError("调用方和被调用方不能是同一个仓库")
        edges.append([caller, callee, desc])
    if len(edges) > MAX_EDGES:
        raise ValueError(f"最多 {MAX_EDGES} 条仓库关系")
    return {"title": title, "status": _text(body.get("status"), 50), "repos": repos, "nodes": nodes,
            "edges": edges, "note": _text(body.get("note"), 2000)}


class Notes:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()   # read-modify-write must be serial, or concurrent requests overwrite each other

    def load(self):
        if not os.path.exists(self.path):
            return {"requirements": {}, "archived": []}
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("requirements", {})
        # ids are strings; older files used numbers under "seq"
        data["archived"] = [{**a, "id": str(a.get("id", a.get("seq")))} for a in data.get("archived", [])]
        return data

    def _save(self, notes):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def save_doc(self, body):
        """Add / update / delete a doc link under requirements.<id>.docs."""
        rid, action = str(body["id"]), body.get("action")
        with self.lock:
            notes = self.load()
            req = notes["requirements"].setdefault(rid, {})
            docs = req.setdefault("docs", [])
            if action in ("add", "update"):
                url, title = str(body.get("url", "")).strip(), str(body.get("title", "")).strip()[:200]
                if not re.match(r"^https?://", url) or len(url) > 2000:
                    raise ValueError("链接需要以 http:// 或 https:// 开头")
                if not title:
                    raise ValueError("请填写文档标题")
                old_url = body.get("old_url") if action == "update" else None
                if any(d.get("url") == url and d.get("url") != old_url for d in docs):
                    raise ValueError("这个链接已经添加过")
                item = {"type": body.get("type") if body.get("type") in DOC_TYPES else "other", "title": title,
                        "url": url, "note": str(body.get("note", "")).strip()[:300], "added": date.today().isoformat()}
                if action == "add":
                    docs.append(item)
                else:
                    i = next((i for i, d in enumerate(docs) if d.get("url") == old_url), -1)
                    if i < 0:
                        raise ValueError("找不到要修改的文档，可能已被移除，请刷新后重试")
                    item["added"] = docs[i].get("added") or item["added"]
                    docs[i] = item
            elif action == "delete":
                req["docs"] = [d for d in docs if d.get("url") != body.get("url")]
            else:
                raise ValueError("action 只能是 add、update 或 delete")
            self._save(notes)

    def save_requirement(self, body):
        rid = str(body["id"])
        with self.lock:
            notes = self.load()
            req = notes["requirements"].setdefault(rid, {})
            if str(body.get("track", "")).lower() in {"1", "true", "on", "yes"}:
                req["track"] = True
            else:
                req.pop("track", None)
            req["note"] = str(body.get("note", "")).strip()[:2000]
            req["nodes"] = [x.strip() for x in str(body.get("nodes", "")).splitlines() if x.strip()][:30]
            try:
                edges = json.loads(body.get("edges", "[]") or "[]")
            except ValueError as e:
                raise ValueError("仓库关系必须是合法 JSON") from e
            if not isinstance(edges, list):
                raise ValueError("仓库关系必须是数组")
            req["edges"] = edges[:50]
            self._save(notes)

    def save_local_requirement(self, body):
        """Create / update / delete a requirement made on the page from repos and branches (no tracker item).
        Stored under requirements.<id> with manual: true, so docs, info and archive work as for tracker items.
        Returns the id."""
        action = body.get("action")
        with self.lock:
            notes = self.load()
            reqs = notes["requirements"]
            if action == "create":
                taken = [int(k[len(LOCAL_PREFIX):]) for k in reqs if re.fullmatch(LOCAL_PREFIX + r"\d+", k)]
                rid = f"{LOCAL_PREFIX}{max(taken, default=0) + 1}"
                old = {}
            else:
                rid = str(body.get("id", ""))
                old = reqs.get(rid)
                if not old or not old.get("manual"):
                    raise ValueError("找不到这个本地需求，可能已被删除，请刷新后重试")
            if action == "delete":
                del reqs[rid]
            elif action in ("create", "update"):
                reqs[rid] = {**old, **_local_fields(body), "manual": True}
            else:
                raise ValueError("action 只能是 create、update 或 delete")
            self._save(notes)
            return rid

    def archive(self, rid, title):
        rid = str(rid)
        with self.lock:
            notes = self.load()
            if rid not in {a["id"] for a in notes["archived"]}:
                notes["archived"].append({"id": rid, "title": str(title)[:200], "date": date.today().isoformat()})
                self._save(notes)
