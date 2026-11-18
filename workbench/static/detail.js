// 视图（下半部分）：需求详情、仓库区、已归档；页面装配与初始化

// 每个仓库只列一条 CR：优先挑还没合入的（需要跟进），都合入了就取第一条；n 是该仓库的 CR 总数
function crRows(r){
  const byRepo = new Map();
  r.stories.forEach(s => (s.crs || []).forEach(c => {
    const g = byRepo.get(c.repo) || {n: 0};
    g.n++;
    if (!g.c || (g.c.status === "MERGED" && c.status !== "MERGED")) { g.s = s; g.c = c; }
    byRepo.set(c.repo, g);
  }));
  return [...byRepo.values()];
}

function detail(r){
  const {tags, text} = splitTitle(r.title);
  const rk = reqStats(r);
  const blockers = D.alerts.filter(a => a.level === "warn" && new Set([r.id, ...r.stories.map(s => s.id)]).has(a.id));
  const repoRows = r.repos.map(z => `<tr>
    <td><span class="dot" style="background:${repoColor(z.repo)}"></span> ${repoLink(z.repo)}</td>
    <td><span class="chip">${z.exists ? branchLink(z.repo, z.branch) : esc(z.branch)}</span>${z.exists ? "" : " " + (z.localOnly ? st("info", "无远端，不比较主干") : st("bad", "远端已删"))}</td>
    <td class="num">${z.mine ? st("warn", `${z.mine} 个`) : st("ok", "0")}
      ${z.others.length ? st("info", `+${z.others.length} 他人`, z.others.map(o => `${o.sha} ${o.author} ${o.msg}`).join("\n")) : ""}</td>
    <td class="num">${z.behind ? st(z.mine ? "warn" : "info", `落后 ${z.behind}`) : '<span class="muted">-</span>'}</td></tr>`).join("");
  const storyRows = r.stories.map(s => `<tr>
    <td>${cardLink(s.id)}</td>
    <td>${esc(cleanTitle(s.title))}<div class="muted small">${splitTitle(s.title).tags.map(esc).join(" · ")}</div></td>
    <td>${pill(s.status)}</td>
    <td>${s.code.map(g => `<div style="margin-bottom:2px"><span class="chip" title="${esc(g.repo)}">${repoLink(g.repo)} · ${branchLink(g.repo, g.branch)}</span>
      ${g.pending ? st("warn", `${g.pending} 待合`) : st("ok", "已合")}
      ${g.pipeline === "FAIL" ? `<a href="${esc(g.pipelineUrl)}" target="_blank" rel="noopener">${st("bad", "流水线失败")}</a>` : ""}</div>`).join("") || '<span class="muted">无代码</span>'}</td>
    <td class="num small">${s.devStart ? `${md(s.devStart)}~${md(s.devEnd)}` : '<span class="muted">-</span>'}</td>
    <td class="num small">${s.testPlan ? (s.testPlan < D.today && ["新建", "开发中", "开发完成"].includes(s.status) ? st("bad", md(s.testPlan) + " 已过") : md(s.testPlan)) : "-"}</td>
    <td class="num small">${md(s.release) || "-"}</td>
    <td class="muted small">${esc(s.qa || "-")}</td></tr>`).join("") || '<tr><td colspan="8" class="muted">还没有 Story 卡</td></tr>';
  return `<article class="card" id="req-${safe(r.id)}" style="margin-bottom:16px;border-left:3px solid ${reqColor(r.id)}">
    <div class="dt-h">${cardLink(r.id)}<h3>${esc(text)}</h3>${pill(r.status)}${tags.map(t => `<span class="tag">${esc(t)}</span>`).join("")}
      <span class="muted small" style="margin-left:auto">${esc((r.plan || "").split("/").pop())}${r.iteration ? `（${r.iteration.join(" ~ ")}）` : ""}</span>${reqEditButton(r)}${docButtons(r)}</div>
    <div style="margin:16px 0 8px">${stepper(r)}</div>
    <div class="detail-summary">${r.manual ? `本地需求，${r.repos.length} 个仓库分支，${rk.pending} 个提交待合入主干`
      : r.stories.length ? `Story ${rk.merged}/${rk.total} 已进主干，${rk.pending} 个提交待合入` : "当前还没有 Story"}${blockers.length ? ` · ${blockers.length} 项待处理` : ""}</div>
    ${blockers.length ? `<div class="note">${blockers.map(a => `${esc(a.text)}${(a.links || []).map(l => ` <a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)} ↗</a>`).join("")}`).join("<br>")}</div>` : ""}
    <div class="grid g-2" style="align-items:start">
      <div><h3>仓库关系</h3>${relationGraph(r)}${relationNotes(r)}</div>
      <div><h3>分支状态</h3><div class="tbl-wrap"><table><tr><th>仓库</th><th>分支</th><th>本需求待合主干</th><th>分支落后主干</th></tr>${repoRows}</table></div>${relationNote(r)}</div>
    </div>
    ${r.manual ? "" : `<h3 style="margin-top:20px">Story</h3>
    <div class="tbl-wrap"><table><tr><th>卡片</th><th>标题</th><th>状态</th><th>代码</th><th>开发</th><th>计划提测</th><th>计划上线</th><th>QA</th></tr>${storyRows}</table></div>`}
    ${crRows(r).length ? `<h3 style="margin-top:20px">CR / 评审</h3><div class="tbl-wrap"><table><tr><th>卡片</th><th>仓库</th><th>分支</th><th>状态</th><th>提交说明</th></tr>${crRows(r).map(({s, c, n}) => `<tr><td>${cardLink(s.id)}</td><td>${repoLink(c.repo)}</td><td><span class="chip">${branchLink(c.repo, c.branch)}</span></td><td>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.status || "查看 CR")} ↗</a>` : esc(c.status || "-")}${n > 1 ? ` <span class="muted small">共 ${n} 个</span>` : ""}</td><td>${esc(c.msg || "-")}</td></tr>`).join("")}</table></div>` : ""}
  </article>`;
}

function matrix(titleLen = 10){
  const repos = [...new Set(D.requirements.flatMap(r => r.repos.map(z => z.repo)))].sort();
  const max = Math.max(1, ...D.requirements.flatMap(r => r.repos.map(z => z.mine)));
  const head = D.requirements.map(r => `<th title="${esc(r.title)}"><span class="dot" style="background:${reqColor(r.id)}"></span> ${esc(cleanTitle(r.title).slice(0, titleLen))}</th>`).join("");
  const rows = repos.map(repo => `<tr><td><span class="dot" style="background:${repoColor(repo)}"></span> ${repoLink(repo)}</td>${D.requirements.map(r => {
    const zs = r.repos.filter(z => z.repo === repo);
    if (!zs.length) return '<td></td>';
    const n = zs.reduce((s, z) => s + z.mine, 0), bg = n ? `rgba(245,158,11,${.12 + .5 * n / max})` : "var(--ok-50)";
    const mine = zs.flatMap(z => z.pending.filter(p => !z.others.some(o => o.sha === p.sha)));
    const others = zs.reduce((s, z) => s + z.others.length, 0);
    const t = tipBody(`${esc(short(repo))} × ${esc(cleanTitle(r.title))}`,
      [...zs.map(z => [z.branch, `待合 ${z.mine}${z.behind ? ` · 落后主干 ${z.behind}` : ""}`]), others ? ["他人提交", `${others} 个（合入会一起带上）`] : null],
      n ? mine : repoCommits(r, repo), n ? "以上为本需求还没进主干 的提交" : "本需求在这个仓库的代码已全部进主干，以上为最近提交");
    return `<td style="background:${bg};text-align:center;border-radius:6px"${tipAttr(t)}><b class="num" style="color:${n ? "var(--warn)" : "var(--ok)"}">${n || "✓"}</b></td>`;
  }).join("")}</tr>`).join("");
  return `<div class="tbl-wrap"><table style="border-collapse:separate;border-spacing:3px"><tr><th>仓库</th>${head}</tr>${rows}</table></div>
    <div class="legend"><span><i style="background:var(--ok-50)"></i>✓ 已全部进主干</span><span><i style="background:rgba(245,158,11,.5)"></i>数字 = 本需求待合主干 的提交数</span></div>`;
}

function localRepos(){
  const n = (v, cls) => v ? st(cls, v) : '<span class="muted">0</span>';
  const open = r => (r.openBranches || []).map(b => `<span class="chip">${branchLink(r.repo, b.branch)} <span class="muted">+${b.ahead}${b.last ? ` · ${esc(b.last)}` : ""}</span></span>`).join(" ")
    + (r.openBranchTotal > (r.openBranches || []).length ? ` <span class="muted small">共 ${r.openBranchTotal} 个</span>` : "") || '<span class="muted">-</span>';
  return `<div class="tbl-wrap"><table><tr><th>仓库</th><th>本地分支</th><th>落后远端</th><th>未推送</th><th>落后主干</th><th>未提交</th><th>未合入主干的远端分支</th></tr>
    ${D.repos.map(r => !r.exists ? `<tr><td>${esc(r.repo)}</td><td colspan="6" class="muted">本机没有这个仓库</td></tr>` :
      !r.local ? `<tr><td>${repoLink(r.repo)}</td><td colspan="6" class="muted">${esc((r.errors || []).join("；") || r.note || "没有可检查的状态")}</td></tr>` :
      `<tr><td><span class="dot" style="background:${repoColor(r.repo)}"></span> ${repoLink(r.repo)}</td><td><span class="chip">${r.local.branch === "(detached)" ? esc(r.local.branch) : branchLink(r.repo, r.local.branch)}</span></td>
       <td class="num">${n(r.local.behindRemote, "warn")}</td><td class="num">${n(r.local.unpushed, "warn")}</td><td class="num">${n(r.local.behindMaster, "info")}</td><td class="num">${n(r.local.dirty, "info")}</td><td>${open(r)}</td></tr>`).join("")}</table></div>
    <div class="muted small" style="margin-top:8px">工作台只读：只做 git fetch 和查询，不切分支、不拉代码、不改文件。未合入主干的分支按最后提交时间排序，被 squash 合并的分支也会显示在这里</div>`;
}

// 每个仓库最近 N 天有提交的分支（本地 + 远端，同名只列一次），N 在「配置」里改
function recentBranchCard(){
  const days = (D.uiConfig || {}).recent_branch_days || 7;
  const chip = (repo, b) => `<span class="chip" title="${esc(`${b.author} · 最后提交 ${b.last}${b.remote ? "" : " · 只在本地"}`)}">${b.remote ? branchLink(repo, b.branch) : esc(b.branch)} <span class="muted">${esc(md(b.last))}${b.remote ? "" : " · 本地"}</span></span>`;
  const rows = D.repos.filter(r => r.exists).map(r => { const bs = r.recentBranches || [];
    return `<tr><td><span class="dot" style="background:${repoColor(r.repo)}"></span> ${repoLink(r.repo)}</td>
      <td class="num">${bs.length ? r.recentBranchTotal : '<span class="muted">0</span>'}</td>
      <td>${bs.map(b => chip(r.repo, b)).join(" ")}${r.recentBranchTotal > bs.length ? ` <span class="muted small">只显示最新 ${bs.length} 个</span>` : ""}${bs.length ? "" : '<span class="muted">-</span>'}</td></tr>`; }).join("");
  return `<div class="card" style="margin-top:16px"><h3 style="display:flex;align-items:center;gap:8px">近 ${days} 天有提交的分支
      <button class="btn sm" onclick="configOpen()" title="修改统计天数">修改天数</button></h3>
    ${rows ? `<div class="tbl-wrap"><table><tr><th>仓库</th><th>分支数</th><th>分支（最后提交日期）</th></tr>${rows}</table></div>`
      : '<div class="empty">workspace 下没有找到 git 仓库，检查 config.json 里的 workspace</div>'}</div>`;
}

// 已归档 = 近 N 天已上线（自动，以 Feature 是否上线为准）+ 手动归档
function archived(){
  const recent = D.recentOnline || [], days = D.recentOnlineDays || 30;
  const recentHtml = recent.length ? `<table><tr><th>卡片</th><th>标题</th><th>上线日期</th><th>涉及仓库</th><th>Story</th></tr>${recent.map(r => {
    const {tags, text} = splitTitle(r.title);
    return `<tr><td>${cardLink(r.id)}</td><td>${esc(text)}<div style="display:flex;gap:4px;flex-wrap:wrap">${tags.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div></td>
      <td class="num">${esc(r.onlineDate)}${r.dateSource === "modified" ? ` <span class="muted small" title="卡片没填实际上线日期，按最后修改时间显示">≈</span>` : ""}</td>
      <td>${r.repos.map(p => `<span class="repo-chip"><span class="dot" style="background:${repoColor(p)}"></span>${repoLink(p)}</span>`).join(" ") || '<span class="muted">-</span>'}</td>
      <td class="num">${r.stories.length + (r.pendingStories || []).length}${(r.pendingStories || []).length ? ` ${st("warn", `${r.pendingStories.length} 个未流转`, r.pendingStories.map(s => `${lbl(s.id)} ${s.status} ${cleanTitle(s.title)}`).join("\n"))}` : ""}</td></tr>`; }).join("")}</table>`
    : `<div class="empty" style="padding:24px">近 ${days} 天没有已上线的需求。</div>`;
  const manualHtml = D.archived.length ? `<table><tr><th>卡片</th><th>标题</th><th>归档日期</th></tr>${D.archived.map(a => `<tr><td>${cardLink(a.id)}</td><td>${esc(a.title)}</td><td class="num">${esc(a.date)}</td></tr>`).join("")}</table>`
    : `<div class="empty" style="padding:24px">没有手动归档的需求。父卡已上线、或代码已全部进主干 时，需求卡片上会出现「归档」按钮。</div>`;
  return `<div class="card"><h3>近 ${days} 天已上线 <span class="count num">${recent.length}</span></h3>${recentHtml}</div>
    <div class="card" style="margin-top:16px"><h3>手动归档 <span class="count num">${D.archived.length}</span></h3>${manualHtml}</div>`;
}

const sec = (id, title, sub, body) => `<section id="${id}"><div class="sec-h"><h2>${title}</h2>${sub ? `<span class="sub">${sub}</span>` : ""}</div>${body}</section>`;

// 需求超过 3 个时热力格列太多，两张卡改为各占一行；宽版提交图用更宽的画布，避免等比放大后过高
// 没有需求时只列仓库本身：活跃分支和本地状态
function repoSection(){
  const wide = D.requirements.length > 3;
  const charts = D.requirements.length ? `<div class="grid ${wide ? "" : "g-2"}">
    <div class="card"><h3>待合主干 的提交：仓库 × 需求</h3>${matrix(wide ? 24 : 10)}</div>
    <div class="card"><h3>近 30 天提交</h3>${activity(wide ? 1200 : 560)}</div></div>` : "";
  return charts + recentBranchCard() + `<div class="card" style="margin-top:16px"><h3>本地仓库</h3>${localRepos()}</div>`;
}

function render(data){
  D = data;
  const wk = "日一二三四五六"[new Date(D.today + "T00:00:00").getDay()];
  $("#today").textContent = `${+D.today.slice(5, 7)} 月 ${+D.today.slice(8)} 日 · 周${wk}`;
  $("#who").textContent = `${D.user}${D.scope ? " · " + D.scope : ""}`;
  stamp(); nav();
  const has = D.requirements.length;
  const collection = D.collectionOk === false ? `<div class="card collection-error"><b>本次采集不完整</b><div>${D.collectionErrors.map(x => esc(x.repo + "：" + x.text)).join("<br>")}</div></div>` : "";
  const reqs = has ? `${reqToolbar()}<div class="grid g-req" style="margin-top:16px">${D.requirements.map(summaryCard).join("")}</div>`
    : `<div class="card empty">没有进行中的需求。任务系统里有新条目后点「刷新」，或者<button class="btn sm primary" style="margin-left:6px" onclick="localNew()">用仓库和分支新建需求</button></div>`;
  $("#app").innerHTML = sec("overview", "概览", "", `${has ? kpis() : ""}${todo()}${collection}${reqs}`) +
    (has ? sec("schedule", "排期", "开发、提测、上线时间线", `<div class="card">${gantt()}</div>`) +
           sec("details", "需求详情", "仓库关系、分支和每个 Story", D.requirements.map(detail).join("")) : "") +
    sec("repos", "仓库与提交", "", repoSection()) +
    sec("archived", "已归档", "", archived());
  spy();
  openFromHash();
  const search = $("#req-search"), filter = $("#req-filter");
  if (search) { search.oninput = applyReqFilter; filter.onchange = applyReqFilter; }
}

// 滚动时高亮侧栏当前位置
function spy(){
  const links = [...document.querySelectorAll(".nav-item")], ids = links.map(a => a.getAttribute("href").slice(1));
  const on = id => links.forEach(a => a.classList.toggle("on", a.getAttribute("href") === "#" + id));
  const io = new IntersectionObserver(es => es.filter(e => e.isIntersecting).forEach(e => on(e.target.id)), {rootMargin: "-80px 0px -70% 0px"});
  ids.map(id => document.getElementById(id)).filter(Boolean).forEach(el => io.observe(el));
}

$("#btn-quick").onclick = () => refresh(false);
$("#btn-full").onclick = () => refresh(true);
$("#btn-new").onclick = () => D && localNew();
$("#btn-config").onclick = () => D && configOpen();
setInterval(stamp, 60e3);
api("/api/data").then(render).catch(e => { $("#app").innerHTML = `<div class="card empty">数据加载失败：${esc(e.message)}<br><br><button class="btn primary" onclick="location.reload()">重试</button></div>`; $("#stamp").textContent = "加载失败"; });
