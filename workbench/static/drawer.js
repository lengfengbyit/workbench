// 抽屉：需求信息、需求文档、文档库、需求配置、本地需求表单和页面配置（后两个在 local.js）。默认收起，从需求卡片 / 详情 / 侧栏打开；地址栏 hash 可直接定位
// #info-<父卡号>  #docs-<父卡号>  #docs（文档库）
const DOC_TYPES = [["prd", "需求文档"], ["tech", "技术文档"], ["ui", "UI 设计"], ["test", "测试"], ["other", "其他"], ["tracker", "任务系统关联"]];
const DOC_BADGE = {prd: "PRD", tech: "技术", ui: "UI", test: "测试", other: "其他", tracker: "关联"};
const docTypeName = t => (DOC_TYPES.find(x => x[0] === t) || DOC_TYPES[4])[1];
let DRAWER = null;   // {mode: "info"|"docs"|"lib", id}

function hasInfo(r){ return !!(r.info && (r.info.summary || (r.info.scope || []).length)); }

// 需求卡片 / 详情头部用的两个入口按钮
function docButtons(r){
  const n = (r.docs || []).length;
  return `<span class="res-btns">
    <a class="res-btn" href="#info-${safe(r.id)}" title="需求摘要、我们负责的部分">${hasInfo(r) ? '<i class="dot" style="background:var(--ok)"></i>' : '<i class="dot" style="background:#cbd2db"></i>'}需求信息</a>
    <a class="res-btn" href="#docs-${safe(r.id)}" title="需求文档、技术文档、UI 设计稿等">文档 <b class="num">${n}</b></a></span>`;
}

function reqEdit(id){
  const r = D.requirements.find(x => x.id === id);
  if (r.manual) return localEdit(id);   // 本地需求用组合表单编辑（local.js）
  DRAWER = {mode: "req", id};
  drawRender();
}

// 编号里可能有 / # 等字符（owner/repo#12、local-1），hash 里用的是 safe() 之后的形式
function openFromHash(){
  const h = location.hash.slice(1), m = h.match(/^(info|docs)-(.+)$/), r = m && D && D.requirements.find(x => safe(x.id) === m[2]);
  if (r) DRAWER = {mode: m[1], id: r.id};
  else if (h === "docs") DRAWER = {mode: "lib"};
  else DRAWER = null;
  drawRender();
}
function drawerClose(){
  if (/^(info|docs)(-.+)?$/.test(location.hash.slice(1))) history.pushState("", "", location.pathname + location.search);
  DRAWER = null; drawRender();
}

function drawRender(){
  let el = $("#drawer");
  if (!el) {
    document.body.insertAdjacentHTML("beforeend", `<div class="drawer-mask" id="drawer-mask" hidden></div><aside class="drawer" id="drawer" role="dialog" aria-modal="true" hidden></aside>`);
    el = $("#drawer");
    $("#drawer-mask").onclick = drawerClose;
    document.addEventListener("keydown", e => { if (e.key === "Escape" && DRAWER) drawerClose(); });
  }
  const open = !!(DRAWER && D);
  el.hidden = $("#drawer-mask").hidden = !open;
  document.body.classList.toggle("noscroll", open);
  if (!open) return;
  const r = D.requirements.find(x => x.id === DRAWER.id);
  const views = {lib: libView, req: () => reqConfigView(r), local: localView, config: configView};
  el.innerHTML = (views[DRAWER.mode] || (() => reqDrawer(r)))();
  const q = $("#doc-q"); if (q) { q.oninput = () => { $("#lib-body").innerHTML = libList(q.value.trim()); }; q.focus(); }
}

function reqConfigView(r){
  const n = r.relation || {};
  return `<header class="dw-h"><div><div class="small muted">${cardLink(r.id)} · 需求配置</div><h3>${esc(cleanTitle(r.title))}</h3></div>
      <button class="btn sm" onclick="drawerClose()">关闭</button></header>
    <div class="dw-body"><form class="req-form" onsubmit="reqSave(event, ${q(r.id)})">
      <label class="check"><input type="checkbox" name="track" ${n.track ? "checked" : ""}> 即使还没有我名下的 Story，也显示这条需求</label>
      <label>需求备注<textarea name="note" maxlength="2000" placeholder="记录范围、上线顺序、待确认事项…">${esc(n.note || "")}</textarea></label>
      <label>仓库节点 <span class="muted small">每行一个，按调用或上线顺序填写</span><textarea name="nodes" rows="5" placeholder="my-org/api&#10;my-org/web">${esc((n.nodes || []).join("\n"))}</textarea></label>
      <label>仓库关系 <span class="muted small">JSON 数组：[调用方, 被调用方, 说明]</span><textarea name="edges" rows="6" placeholder='[["调用方","被调用方","说明"]]'>${esc(JSON.stringify(n.edges || [], null, 2))}</textarea></label>
      <div><button class="btn primary">保存需求配置</button><button type="button" class="btn" onclick="drawerClose()">取消</button></div>
    </form></div>`;
}

function reqDrawer(r){
  const {tags, text} = splitTitle(r.title), tab = (m, l) => `<a class="tab ${DRAWER.mode === m ? "on" : ""}" href="#${m}-${safe(r.id)}">${l}</a>`;
  return `<header class="dw-h"><div><div class="small muted">${cardLink(r.id)} · ${esc(r.type || "")} ${pill(r.status)}</div>
      <h3>${esc(text)}</h3><div style="display:flex;gap:4px;flex-wrap:wrap">${tags.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div></div>
      <button class="btn sm" onclick="drawerClose()" aria-label="关闭">关闭</button></header>
    <nav class="dw-tabs">${tab("info", "需求信息")}${tab("docs", `文档 <b class="num">${(r.docs || []).length}</b>`)}</nav>
    <div class="dw-body">${DRAWER.mode === "info" ? infoView(r) : docsView(r)}</div>`;
}

function infoView(r){
  const i = r.info || {}, scope = i.scope || [], ours = scope.filter(x => x.ours), others = scope.filter(x => !x.ours);
  const tracker = r.detailText ? `<details class="dw-sec"><summary>条目描述</summary><div class="pre">${esc(r.detailText)}</div></details>` : "";
  if (!hasInfo(r)) return `<div class="dw-empty"><b>还没有整理需求信息</b>
      <p>把需求文档、技术方案发给 AI，说"整理一下 ${lbl(r.id)} 的需求信息"，它会总结摘要并标出我们负责的部分，写进 notes.json。</p>
      ${(r.docs || []).length ? `<p>这个需求已经有 ${(r.docs || []).length} 个文档，可以直接让 AI 读：<a href="#docs-${safe(r.id)}">查看文档</a></p>` : ""}</div>${tracker}`;
  const item = x => `<li><div class="sc-n">${esc(x.name)}${x.owner && !x.ours ? ` <span class="tag">${esc(x.owner)}</span>` : ""}</div>
      ${x.desc ? `<div class="sc-d">${esc(x.desc)}</div>` : ""}
      ${(x.repos || []).length ? `<div class="sc-r">${x.repos.map(p => `<span class="chip">${esc(short(p))}</span>`).join(" ")}</div>` : ""}</li>`;
  const list = (title, arr) => arr && arr.length ? `<section class="dw-sec"><h4>${title}</h4><ul class="plain">${arr.map(x => `<li>${esc(x)}</li>`).join("")}</ul></section>` : "";
  const ms = (i.milestones || []).length ? `<section class="dw-sec"><h4>时间节点</h4><div class="ms">${i.milestones.map(m =>
      `<div class="${m.date && m.date < D.today ? "past" : ""}"><span class="num">${esc(md(m.date || "") || m.date || "")}</span>${esc(m.name)}</div>`).join("")}</div></section>` : "";
  return `<section class="dw-sec"><h4>需求摘要</h4><p class="summary">${esc(i.summary || "")}</p>
      ${i.background ? `<p class="muted small">${esc(i.background)}</p>` : ""}</section>
    ${ours.length ? `<section class="dw-sec ours"><h4>我们负责 <span class="count num">${ours.length}</span></h4><ul class="scope">${ours.map(item).join("")}</ul></section>` : ""}
    ${others.length ? `<details class="dw-sec" ${ours.length ? "" : "open"}><summary>其他团队负责 <span class="count num">${others.length}</span></summary><ul class="scope dim">${others.map(item).join("")}</ul></details>` : ""}
    ${list("目标", i.goals)}${ms}${list("风险与待确认", i.risks)}${tracker}
    <div class="dw-foot muted small">${i.source ? `来源：${esc(i.source)}` : ""}${i.updated ? ` · 整理于 ${esc(i.updated)}` : ""}</div>`;
}

function docRow(d, id, withReq){
  const r = withReq && D.requirements.find(x => x.id === id);
  return `<li class="doc"><span class="doc-t t-${esc(d.type)}">${esc(DOC_BADGE[d.type] || "其他")}</span>
    <div class="doc-m"><a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.title)} ↗</a>
      <div class="small muted">${r ? `<a href="#docs-${safe(id)}">${esc(cleanTitle(r.title).slice(0, 18))}</a> · ` : ""}${esc(d.note || "")}${d.added ? ` ${esc(d.added)}` : ""}${d.source === "tracker" ? " 来自任务系统" : ""}</div></div>
    ${d.source === "manual" && !withReq ? `<button class="btn sm ghost" onclick="docEdit(${q(id)}, ${esc(JSON.stringify(d.url))})" title="修改标题、链接、类型、备注">编辑</button><button class="btn sm ghost" onclick="docDelete(${q(id)}, ${esc(JSON.stringify(d.url))})" title="从工作台移除，不影响原文档">移除</button>` : ""}</li>`;
}

function docsView(r){
  const docs = r.docs || [];
  const groups = DOC_TYPES.map(([t, name]) => ({t, name, list: docs.filter(d => d.type === t)})).filter(g => g.list.length);
  const body = groups.length ? groups.map(g => `<section class="dw-sec"><h4>${esc(g.name)} <span class="count num">${g.list.length}</span></h4>
      <ul class="docs">${g.list.map(d => docRow(d, r.id)).join("")}</ul></section>`).join("")
    : `<div class="dw-empty"><b>还没有文档</b><p>在下面添加链接，或者把文档发给 AI 让它整理进来。</p></div>`;
  return body + `<details class="dw-sec add" id="doc-add" ${groups.length ? "" : "open"}><summary id="doc-add-sum">+ 添加文档链接</summary>
    <form class="doc-form" onsubmit="docAdd(event, ${q(r.id)})">
      <input type="hidden" name="old_url">
      <select name="type">${DOC_TYPES.filter(x => x[0] !== "tracker").map(([t, n]) => `<option value="${t}">${n}</option>`).join("")}</select>
      <input name="title" placeholder="标题，如 结算改版 PRD v1.2" required maxlength="200">
      <input name="url" placeholder="链接 https://…" required type="url">
      <input name="note" placeholder="备注（可选）" maxlength="300">
      <button class="btn primary sm" id="doc-submit">添加</button>
      <button type="button" class="btn sm" id="doc-cancel" onclick="docEditCancel()" hidden>取消修改</button></form></details>`;
}

function libView(){
  const total = D.requirements.reduce((n, r) => n + (r.docs || []).length, 0);
  return `<header class="dw-h"><div><h3>文档库</h3><div class="small muted">进行中需求的全部文档，共 ${total} 个</div></div>
      <button class="btn sm" onclick="drawerClose()">关闭</button></header>
    <div class="dw-body"><input id="doc-q" class="search" placeholder="搜索标题、备注、需求名…" autocomplete="off"><div id="lib-body">${libList("")}</div></div>`;
}
function libList(q){
  const k = q.toLowerCase(), all = D.requirements.flatMap(r => (r.docs || []).map(d => ({d, r})))
    .filter(({d, r}) => !k || [d.title, d.note, r.title, docTypeName(d.type)].join(" ").toLowerCase().includes(k));
  if (!all.length) return `<div class="dw-empty">${q ? "没有匹配的文档" : "还没有文档。打开某个需求的「文档」添加。"}</div>`;
  return DOC_TYPES.map(([t, name]) => ({name, list: all.filter(x => x.d.type === t)})).filter(g => g.list.length)
    .map(g => `<section class="dw-sec"><h4>${esc(g.name)} <span class="count num">${g.list.length}</span></h4><ul class="docs">${g.list.map(x => docRow(x.d, x.r.id, true)).join("")}</ul></section>`).join("");
}

async function docAdd(e, id){
  e.preventDefault();
  const f = new FormData(e.target), body = Object.fromEntries(f.entries()), editing = !!body.old_url;
  try { render(await api("/api/doc", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...body, id, action: editing ? "update" : "add"})})); toast(editing ? "已保存修改" : "已添加"); }
  catch (err) { toast((editing ? "修改失败：" : "添加失败：") + err.message, true); }
}
// 点「编辑」：把这条文档填进下方表单，提交时按 old_url 找到原记录更新
function docEdit(id, url){
  const r = D.requirements.find(x => x.id === id), d = r && (r.docs || []).find(x => x.url === url), box = $("#doc-add");
  if (!d || !box) return;
  const f = box.querySelector("form"), el = f.elements;   // form.title 是 DOM 自带属性，必须走 elements
  el.old_url.value = d.url; el.type.value = d.type; el.title.value = d.title; el.url.value = d.url; el.note.value = d.note || "";
  box.open = true; $("#doc-add-sum").textContent = "修改文档链接"; $("#doc-submit").textContent = "保存修改"; $("#doc-cancel").hidden = false;
  box.scrollIntoView({block: "nearest"}); el.title.focus();
}
function docEditCancel(){
  const box = $("#doc-add"), f = box.querySelector("form");
  f.reset(); f.elements.old_url.value = "";
  $("#doc-add-sum").textContent = "+ 添加文档链接"; $("#doc-submit").textContent = "添加"; $("#doc-cancel").hidden = true;
}
async function docDelete(id, url){
  if (!confirm("从工作台移除这个文档链接？原文档不受影响。")) return;
  try { render(await api("/api/doc", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id, url, action: "delete"})})); toast("已移除"); }
  catch (err) { toast("移除失败：" + err.message, true); }
}

window.addEventListener("hashchange", openFromHash);

async function reqSave(e, id){
  e.preventDefault();
  const f = new FormData(e.target), body = Object.fromEntries(f.entries());
  body.track = e.target.track.checked;
  try { render(await api("/api/requirement", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...body, id})})); toast("需求配置已保存"); }
  catch (err) { toast("保存失败：" + err.message, true); }
}
