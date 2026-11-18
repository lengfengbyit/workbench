// 视图（上半部分）：侧栏导航、待办、指标、需求概要卡
const KINDS = {
  pipeline: ["流水线失败", "最近一次提交的流水线没过，合入前先修好"],
  overdue: ["计划提测已过，还没提测", "去任务系统流转状态，或者更新计划提测日期"],
  card_lag: ["代码已进主干，条目状态没跟上", "确认上线后把卡片流转到上线状态"],
  others: ["分支上混有其他卡片的提交", "合入时会一起带上，先和对应负责人对齐"],
  behind: ["分支落后主干", "合入前先把主干合进分支"],
  iteration: ["卡片挂在已结束的迭代上", "把卡片挪到当前迭代"],
  local: ["本地仓库需要同步", "工作台只读，不会替你 pull 或切分支"],
  collection: ["采集不完整", "检查网络、任务系统或对应仓库，刷新后再判断当前状态"],
};

function nav(){
  const item = (href, label, extra = "", dot = "") => `<a class="nav-item" href="${href}">${dot}<span class="grow">${label}</span>${extra}</a>`;
  const warns = D.alerts.filter(a => a.level === "warn").length;
  $("#nav").innerHTML =
    item("#overview", "概览", warns ? `<span class="count warn num">${warns}</span>` : "") +
    (D.requirements.length ? item("#schedule", "排期") : "") +
    `<div class="nav-group">进行中的需求</div>` +
    D.requirements.map(r => { const k = reqStats(r);
      return item(`#req-${safe(r.id)}`, esc(cleanTitle(r.title)), k.warns ? `<span class="count warn num">${k.warns}</span>` : `<span class="count num">${k.total}</span>`,
        `<span class="dot" style="background:${reqColor(r.id)}"></span>`); }).join("") +
    `<div class="nav-group">其他</div>` + item("#docs", "文档库", `<span class="count num">${D.requirements.reduce((n, r) => n + (r.docs || []).length, 0)}</span>`) +
    item("#repos", "仓库与提交") + item("#archived", "已归档", `<span class="count num">${D.archived.length + (D.recentOnline || []).length}</span>`);
}

function reqToolbar(){
  return `<div class="req-tools">
    <input id="req-search" class="search" placeholder="搜索需求、Story、卡号、仓库、分支…" autocomplete="off">
    <select id="req-filter" class="filter"><option value="all">全部需求</option><option value="warn">有待办</option><option value="pending">有待合主干</option><option value="merged">代码已全部进主干</option></select>
  </div>`;
}

function reqEditButton(r){
  return `<button class="btn sm" onclick="reqEdit(${q(r.id)})">${r.manual ? "编辑需求" : "编辑需求配置"}</button>`;
}

function applyReqFilter(){
  const q = ($("#req-search")?.value || "").trim().toLowerCase(), f = $("#req-filter")?.value || "all";
  document.querySelectorAll("[data-req-card]").forEach(el => {
    const r = D.requirements.find(x => safe(x.id) === el.dataset.reqCard), k = reqStats(r);
    const text = [r.title, r.id, r.status, r.plan, ...r.repos.map(x => `${x.repo} ${x.branch}`), ...r.stories.map(x => `${x.title} ${x.id}`)].join(" ").toLowerCase();
    const okQ = !q || text.includes(q), okF = f === "all" || (f === "warn" && k.warns) || (f === "pending" && k.pending) || (f === "merged" && r.stories.length && k.merged === r.stories.length);
    el.hidden = !(okQ && okF);
  });
}

function todo(){
  const idTitle = {};
  D.requirements.forEach(r => { idTitle[r.id] = r.title; r.stories.forEach(s => idTitle[s.id] = s.title); });
  const groups = Object.entries(KINDS).map(([k, [t, hint]]) => ({k, t, hint, items: D.alerts.filter(a => a.kind === k)})).filter(g => g.items.length);
  groups.sort((a, b) => (b.items[0].level === "warn") - (a.items[0].level === "warn"));
  if (!groups.length) return `<div class="card"><h3>待办</h3><div class="empty">没有需要处理的事项</div></div>`;
  const body = groups.map(g => { const warn = g.items[0].level === "warn";
    return `<details ${warn ? "open" : ""}><summary>${st(warn ? "warn" : "info", warn ? "需处理" : "提示")}<span>${esc(g.t)}</span><span class="count num">${g.items.length}</span></summary>
      <div class="hint">${esc(g.hint)}</div>
      <ul>${g.items.map(a => `<li>${a.id ? cardLink(a.id) : '<span class="muted">本地</span>'}<span>${a.id && idTitle[a.id] ? `<b style="font-weight:500;color:var(--text)">${esc(cleanTitle(idTitle[a.id]))}</b> · ` : ""}${esc(a.text)}${(a.links || []).map(l => ` <a href="${esc(l.url)}" target="_blank" rel="noopener" style="white-space:nowrap">${esc(l.label)} ↗</a>`).join("")}</span></li>`).join("")}</ul></details>`; }).join("");
  return `<div class="card todo"><h3>待办 <span class="muted small" style="font-weight:400">按类型归并，需处理的排在前面</span></h3>${body}</div>`;
}

function kpis(){
  const stories = D.requirements.flatMap(r => r.stories), merged = stories.filter(s => s.codeState === "merged").length;
  const branches = D.requirements.flatMap(r => r.repos).filter(z => z.mine), pending = branches.reduce((n, z) => n + z.mine, 0);
  const warn = D.alerts.filter(a => a.level === "warn").length;
  const tile = (v, l, h, color) => `<div class="card kpi"><div class="v num" style="color:${color || "inherit"}">${v}</div><div><div class="l">${l}</div>${h ? `<div class="h">${h}</div>` : ""}</div></div>`;
  return `<div class="grid g-kpi">
    ${tile(D.requirements.length, "进行中的需求", `共 ${stories.length} 个 Story`)}
    ${tile(warn, "需要处理", `另有 ${D.alerts.length - warn} 条提示`, warn ? "var(--warn)" : "")}
    ${tile(pending, "待合主干 的提交", `分布在 ${new Set(branches.map(z => z.repo + z.branch)).size} 个分支`)}
    <div class="card kpi">${ring(merged, stories.length, "#059669", 44)}
      <div><div class="l">代码已进主干</div><div class="h num">${merged} / ${stories.length} 个 Story</div></div></div>
  </div>`;
}

function summaryCard(r){
  const k = reqStats(r), {tags, text} = splitTitle(r.title), canArchive = r.manual || r.status === "已上线" || r.stories.length && r.stories.every(s => s.codeState === "merged");
  const repos = [...new Set(r.repos.map(z => z.repo))].map(repo => { const zs = r.repos.filter(z => z.repo === repo), n = zs.reduce((s, z) => s + z.mine, 0);
    const t = tipBody(esc(repo), zs.map(z => [z.branch, `待合 ${z.mine}${z.behind ? ` · 落后主干 ${z.behind}` : ""}`]), repoCommits(r, repo));
    return `<span class="repo-chip"${tipAttr(t)}><span class="dot" style="background:${repoColor(repo)}"></span>${repoLink(repo)}${n ? st("warn", `${n} 待合`) : st("ok", "已合")}</span>`; }).join("");
  const meta = [r.iteration ? `迭代 ${md(r.iteration[0])}~${md(r.iteration[1])}${r.iteration[1] < D.today ? "（已结束）" : ""}` : "未排迭代",
    k.testPlan ? `提测 ${md(k.testPlan)}` : "", k.release ? `上线 ${md(k.release)}` : ""].filter(Boolean).map(x => `<span>${esc(x)}</span>`).join("");
  return `<article class="card rq" data-req-card="${safe(r.id)}" style="border-top:3px solid ${reqColor(r.id)}">
    <div class="rq-top"><span class="small">${cardLink(r.id)} <span class="muted">${esc(r.type || "")}</span></span>${pill(r.status)}</div>
    <div><div class="rq-title">${esc(text)}</div><div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:4px">${tags.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div></div>
    <div>${r.manual ? `<span class="muted small">本地需求 · ${r.repos.length} 个仓库分支</span>` : segBar(r.stories)}</div>
    <div class="rq-meta">${meta}</div>
    <div class="rq-repos">${repos || '<span class="muted small">还没有代码</span>'}</div>
    <div>${docButtons(r)}</div>
    <div class="rq-foot"><span>${k.warns ? st("warn", `${k.warns} 项需处理`) : st("ok", "没有需处理的事项")}</span>
      <span style="display:flex;gap:8px;align-items:center">${reqEditButton(r)}${canArchive ? `<button class="btn sm" onclick="archive(${q(r.id)})">归档</button>` : ""}<a href="#req-${safe(r.id)}">查看详情 →</a></span></div>
  </article>`;
}
