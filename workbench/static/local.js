// 本地需求：从工作区的仓库和分支组合出一条需求（不依赖任务系统）；以及页面配置
// 表单内容先读进 LR 再整体重绘，增删行、换仓库时不丢已填的内容
let LR = null;   // {id, title, status, note, repos: [{repo, branch}], edges: [[调用方, 被调用方, 说明]]}

function localNew(){
  LR = {id: null, title: "", status: D.stages[0].name, note: "", repos: [{repo: "", branch: ""}], edges: []};
  DRAWER = {mode: "local"}; drawRender();
}
function localEdit(id){
  const r = D.requirements.find(x => x.id === id), n = r.relation || {};
  LR = {id, title: r.title, status: r.status, note: n.note || "",
        repos: (n.repos || []).map(x => ({...x})), edges: (n.edges || []).map(e => [...e])};
  DRAWER = {mode: "local", id}; drawRender();
}

// 分支候选：近 N 天有提交的分支、未合入主干的远端分支、当前本地分支；输入框也可以手填其他分支
function branchOptions(repo){
  const r = D.repos.find(x => x.repo === repo);
  if (!r) return [];
  const cur = r.local && r.local.branch !== "(detached)" ? r.local.branch : null;
  return [...new Set([...(r.recentBranches || []).map(b => b.branch), ...(r.openBranches || []).map(b => b.branch), cur].filter(Boolean))];
}

function localView(){
  // 已选但本机已经没有的仓库也留在下拉里，编辑旧需求时不会被悄悄清空
  const all = [...new Set([...D.repos.filter(r => r.exists).map(r => r.repo), ...LR.repos.map(x => x.repo).filter(Boolean)])];
  const chosen = [...new Set(LR.repos.map(x => x.repo).filter(Boolean))];
  const opt = (v, cur, label) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(label ?? v)}</option>`;
  const del = (kind, i) => `<button type="button" class="btn sm ghost" onclick="lrRemove('${kind}', ${i})">移除</button>`;
  const repoRows = LR.repos.map((x, i) => `<div class="lr-row">
      <span class="lr-n num">${i + 1}</span>
      <select name="repo" onchange="lrSync()" aria-label="第 ${i + 1} 个仓库">${opt("", x.repo, "选择仓库…")}${all.map(r => opt(r, x.repo)).join("")}</select>
      <input name="branch" list="lr-br-${i}" value="${esc(x.branch)}" placeholder="分支" aria-label="第 ${i + 1} 个仓库的分支" autocomplete="off" maxlength="200">
      <datalist id="lr-br-${i}">${branchOptions(x.repo).map(b => `<option value="${esc(b)}">`).join("")}</datalist>${del("repos", i)}</div>`).join("");
  const edgeRows = LR.edges.map((e, i) => `<div class="lr-row">
      <select name="from" aria-label="调用方">${opt("", e[0], "调用方…")}${chosen.map(r => opt(r, e[0], short(r))).join("")}</select>
      <span class="muted" aria-hidden="true">→</span>
      <select name="to" aria-label="被调用方">${opt("", e[1], "被调用方…")}${chosen.map(r => opt(r, e[1], short(r))).join("")}</select>
      <input name="desc" value="${esc(e[2] || "")}" placeholder="说明，如 下单时调用 /orders" maxlength="200">${del("edges", i)}</div>`).join("");
  const r = LR.id && D.requirements.find(x => x.id === LR.id);
  return `<header class="dw-h"><div><div class="small muted">${LR.id ? `${cardLink(LR.id)} · 编辑本地需求` : "新建本地需求"}</div>
      <h3>${LR.id ? esc(cleanTitle(r ? r.title : LR.title)) : "从仓库和分支组合需求"}</h3></div>
      <button class="btn sm" onclick="drawerClose()">关闭</button></header>
    <div class="dw-body"><form class="req-form" id="lr-form" onsubmit="lrSave(event)">
      <label>需求标题<input class="lr-in" name="title" value="${esc(LR.title)}" required maxlength="200" placeholder="如 【支付】下单失败重试"></label>
      <label>当前阶段<select class="lr-in" name="status">${D.stages.map(s => opt(s.name, LR.status)).join("")}</select></label>
      <div class="lr-sec"><div class="lr-h">仓库和分支 <span class="muted small">按调用或上线顺序排列，关系图按这个顺序画</span></div>
        ${all.length ? repoRows : '<div class="dw-empty">workspace 下没有找到 git 仓库，先检查 config.json 里的 workspace</div>'}
        <button type="button" class="btn sm" onclick="lrAdd('repos')">+ 添加仓库</button></div>
      <div class="lr-sec"><div class="lr-h">仓库关系 <span class="muted small">谁调用谁，只能在上面选中的仓库之间选</span></div>
        ${edgeRows || '<div class="muted small">还没有关系</div>'}
        <button type="button" class="btn sm" onclick="lrAdd('edges')"${chosen.length < 2 ? " disabled title=\"至少选两个仓库\"" : ""}>+ 添加关系</button></div>
      <label>备注<textarea name="note" maxlength="2000" placeholder="上线顺序、待确认事项…">${esc(LR.note)}</textarea></label>
      <div><button class="btn primary">${LR.id ? "保存修改" : "创建需求"}</button><button type="button" class="btn" onclick="drawerClose()">取消</button>
        ${LR.id ? `<button type="button" class="btn ghost" style="float:right" onclick="lrDelete()">删除需求</button>` : ""}</div>
    </form></div>`;
}

function lrRead(){
  const f = $("#lr-form");
  if (!f) return;
  const vals = name => [...f.querySelectorAll(`[name=${name}]`)].map(x => x.value.trim());
  const branches = vals("branch"), to = vals("to"), desc = vals("desc");
  LR = {...LR, title: f.elements.title.value, status: f.elements.status.value, note: f.elements.note.value,
        repos: vals("repo").map((repo, i) => ({repo, branch: branches[i]})),
        edges: vals("from").map((a, i) => [a, to[i], desc[i]])};
}
// 重绘后保持抽屉的滚动位置；选了仓库但分支还空着时，先填上它的第一个候选分支
function lrRedraw(){
  const body = $(".dw-body"), top = body ? body.scrollTop : 0;
  LR = {...LR, repos: LR.repos.map(x => x.repo && !x.branch ? {...x, branch: branchOptions(x.repo)[0] || ""} : x)};
  drawRender();
  if ($(".dw-body")) $(".dw-body").scrollTop = top;
}
function lrSync(){ lrRead(); lrRedraw(); }
function lrAdd(kind){
  lrRead();
  LR = {...LR, [kind]: [...LR[kind], kind === "repos" ? {repo: "", branch: ""} : ["", "", ""]]};
  lrRedraw();
}
function lrRemove(kind, i){
  lrRead();
  LR = {...LR, [kind]: LR[kind].filter((_, j) => j !== i)};
  lrRedraw();
}

async function lrSave(e){
  e.preventDefault();
  lrRead();
  const body = {action: LR.id ? "update" : "create", id: LR.id, title: LR.title, status: LR.status, note: LR.note,
                repos: LR.repos.filter(x => x.repo || x.branch), edges: LR.edges.filter(x => x[0] || x[1] || x[2])};
  try {
    const data = await postJson("/api/local-requirement", body);
    LR = null; render(data);
    location.hash = `#req-${safe(data.savedId)}`;
    toast(body.action === "create" ? `已创建 ${lbl(data.savedId)}` : "已保存修改");
  }
  catch (err) { toast("保存失败：" + err.message, true); }
}
async function lrDelete(){
  if (!confirm(`删除本地需求「${LR.title}」？\n只删除工作台里的这条记录，仓库和分支不受影响。`)) return;
  try { const data = await postJson("/api/local-requirement", {action: "delete", id: LR.id}); LR = null; render(data); toast("已删除"); }
  catch (err) { toast("删除失败：" + err.message, true); }
}

// 页面配置：只有这里列出的项可以在页面上改，服务端同样只接受这些键（settings.UI_OPTIONS）
const UI_OPTIONS = [
  {key: "recent_branch_days", label: "活跃分支统计天数", hint: "「仓库与提交」里列出最近多少天内有提交的分支", min: 1, max: 90, unit: "天"},
];

function configOpen(){ DRAWER = {mode: "config"}; drawRender(); }

function configView(){
  const cur = D.uiConfig || {};
  return `<header class="dw-h"><div><h3>配置</h3><div class="small muted">保存后写入数据目录的 config.json，立即重新采集</div></div>
      <button class="btn sm" onclick="drawerClose()">关闭</button></header>
    <div class="dw-body"><form class="req-form" onsubmit="configSave(event)">
      ${UI_OPTIONS.map(o => `<label>${esc(o.label)} <span class="muted small">${esc(o.hint)}</span>
        <span class="cfg-in"><input class="lr-in" type="number" name="${o.key}" value="${esc(cur[o.key] ?? "")}" min="${o.min}" max="${o.max}" step="1" required> ${esc(o.unit)}</span></label>`).join("")}
      <div><button class="btn primary">保存配置</button><button type="button" class="btn" onclick="drawerClose()">取消</button></div>
    </form></div>`;
}

async function configSave(e){
  e.preventDefault();
  const body = Object.fromEntries(UI_OPTIONS.map(o => [o.key, e.target.elements[o.key].value]));
  try { const data = await postJson("/api/config", body); DRAWER = null; render(data); toast("配置已保存"); }
  catch (err) { toast("保存失败：" + err.message, true); }
}
