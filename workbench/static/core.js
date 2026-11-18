// 公共：状态、颜色、工具函数、数据加载与刷新
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const short = r => String(r).split("/").pop();
const md = s => s ? s.slice(5).replace("-", "/") : "";   // 2026-11-19 -> 11/19
let D = null;

// 阶段色由 provider 的 workflow 提供（D.stages），颜色之外都配文字，不只靠颜色区分
const REPO_COLORS = ["#6366f1", "#14b8a6", "#f59e0b", "#ec4899", "#0ea5e9", "#8b5cf6", "#84cc16", "#f97316"];
const REQ_COLORS = ["#6366f1", "#14b8a6", "#f59e0b", "#ec4899", "#0ea5e9", "#84cc16"];

// 条目编号可能是 "123"，也可能是 "owner/repo#12"：页面锚点用 safe()，onclick 参数用 q()
const lbl = id => (D && D.idPrefix || "") + id;
const safe = id => String(id).replace(/[^\w-]/g, "_");
const q = v => esc(JSON.stringify(v));

const stageColor = s => ((D && D.stages.find(x => x.name === s)) || {}).color || "#cbd5e1";
const stageIdx = s => Math.max(0, D.stages.findIndex(x => x.name === s));
const repoColor = r => REPO_COLORS[[...short(r)].reduce((a, c) => a + c.charCodeAt(0), 0) % REPO_COLORS.length];
const reqColor = id => REQ_COLORS[Math.max(0, D.requirements.findIndex(r => r.id === id)) % REQ_COLORS.length];
const cardUrl = id => (D.urls || {})[id] || "";
const cardLink = id => cardUrl(id)
  ? `<a href="${esc(cardUrl(id))}" target="_blank" rel="noopener" class="num">${esc(lbl(id))}</a>`
  : `<span class="num">${esc(lbl(id))}</span>`;
// 仓库 / 分支页面：模板由 provider 提供。{repo} 保留路径分隔符，{branch} 单次转义，{branch2} 双重转义
const encPath = p => String(p).split("/").map(encodeURIComponent).join("/");
const fillUrl = (tpl, repo, branch) => tpl && tpl
  .replace("{repo}", encPath(repo))
  .replace("{branch2}", encodeURIComponent(encodeURIComponent(branch || "")))
  .replace("{branch}", encodeURIComponent(branch || ""));
// 工作区里任务系统不认识的仓库（noLink）没有网页可打开，只显示文字
const noLink = repo => (D.repos || []).some(r => r.repo === repo && r.noLink);
const repoUrl = repo => noLink(repo) ? "" : fillUrl((D.links || {}).repo, repo);
const branchUrl = (repo, branch) => noLink(repo) ? "" : fillUrl((D.links || {}).branch, repo, branch);
const linkOrText = (url, text, title) => url
  ? `<a class="repo-link" href="${esc(url)}" target="_blank" rel="noopener" title="${esc(title)}">${esc(text)}</a>` : esc(text);
const repoLink = (repo, text) => linkOrText(repoUrl(repo), text ?? short(repo), `打开 ${repo}`);
const branchLink = (repo, branch) => linkOrText(branchUrl(repo, branch), branch, `打开分支 ${branch}`);
const pill = s => `<span class="pill"><i style="background:${stageColor(s)}"></i>${esc(s)}</span>`;
const st = (cls, text, title) => `<span class="st ${cls}"${title ? ` title="${esc(title)}"` : ""}>${esc(text)}</span>`;

// 卡片标题拆成"标签 + 正文"：【Web】【支付】xxx -> tags=[Web, 支付], text=xxx
function splitTitle(t){
  const tags = []; let text = String(t || "");
  while (/^\s*【[^】]*】/.test(text)) text = text.replace(/^\s*【([^】]*)】/, (_, x) => (tags.push(x), ""));
  return {tags, text: text.trim() || t};
}
const cleanTitle = t => splitTitle(t).text;

// 每个需求的汇总数字，概要卡、侧栏、详情共用
function reqStats(r){
  const total = r.stories.length;
  const merged = r.stories.filter(s => s.codeState === "merged").length;
  const pending = r.repos.reduce((n, z) => n + z.mine, 0);
  const ids = new Set([r.id, ...r.stories.map(s => s.id)]);
  const warns = D.alerts.filter(a => a.level === "warn" && ids.has(a.id)).length;
  const pick = k => r.stories.map(s => s[k]).filter(Boolean).sort();
  return {total, merged, pending, warns, testPlan: pick("testPlan").pop(), release: pick("release").pop()};
}

function toast(msg, isErr){
  const t = $("#toast");
  t.textContent = msg; t.className = "toast" + (isErr ? " err" : ""); t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => t.hidden = true, isErr ? 8000 : 2500);
}
function busy(on, label){
  $("#progress").hidden = !on;
  ["#btn-quick", "#btn-full"].forEach(id => $(id).disabled = on);
  if (label) $("#stamp").textContent = label;
}
async function api(url, opts){
  const r = await fetch(url, opts);
  let j; try { j = await r.json(); } catch { throw new Error(`服务返回 ${r.status}`); }
  if (!r.ok || j.error) throw new Error(j.error || r.statusText);
  return j;
}
const postJson = (url, body) => api(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
async function refresh(full){
  busy(true, full ? "正在采集数据并同步各仓库…" : "正在采集数据…");
  try {
    const data = await api(full ? "/api/refresh" : "/api/refresh?nofetch", {method: "POST"});
    render(data); toast(`已刷新${data.refreshMs ? `，耗时 ${(data.refreshMs / 1000).toFixed(1)} 秒` : ""}`);
  }
  catch (e) { toast("刷新失败：" + e.message, true); stamp(); }
  finally { busy(false); }
}
async function archive(id){
  const r = D.requirements.find(x => x.id === id);
  if (!confirm(`归档 ${lbl(id)}「${cleanTitle(r.title)}」？\n归档后它不再出现在进行中列表，可在页面底部「已归档」里看到。`)) return;
  busy(true);
  try { render(await api("/api/archive", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id, title: r.title})})); toast(`${lbl(id)} 已归档`); }
  catch (e) { toast("归档失败：" + e.message, true); }
  finally { busy(false); }
}
function stamp(){
  if (!D) return;
  const t = new Date(D.generatedAt.replace(" ", "T")), mins = Math.round((Date.now() - t) / 6e4);
  $("#stamp").textContent = `数据更新于 ${D.generatedAt.slice(5, 16)}（${mins < 1 ? "刚刚" : mins + " 分钟前"}）· ${D.user}${D.scope ? " · " + D.scope : ""}`;
}
