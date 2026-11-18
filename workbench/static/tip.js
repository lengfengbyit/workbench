// 悬停提示：元素上挂 data-tip（HTML 字符串，内部值已转义），全局一个浮层跟随鼠标
const tipAttr = html => ` data-tip="${esc(html)}"`;

// 提示框内容：标题 + 若干行「标签：值」+ 可选提交列表
function tipBody(title, rows = [], commits = null, foot = ""){
  const kv = rows.filter(r => r && r[1] !== undefined && r[1] !== "").map(([k, v]) => `<div class="tip-row"><span>${esc(k)}</span><b>${v}</b></div>`).join("");
  return `<div class="tip-t">${title}</div>${kv}${commits ? commitList(commits) : ""}${foot ? `<div class="tip-foot">${foot}</div>` : ""}`;
}

// 提交列表：sha、说明、时间；未进主干 / 流水线失败加标记
function commitList(list, max = 5){
  if (!list || !list.length) return `<div class="tip-empty">没有提交</div>`;
  const items = list.slice(0, max).map(c => `<li><code>${esc((c.sha || "").slice(0, 8))}</code><span class="m">${esc(c.msg || "")}</span>
    <span class="t">${esc(c.time || c.date || "")}${c.author ? " · " + esc(c.author) : ""}${c.merged === false ? ' · <em class="w">未进主干</em>' : ""}${c.pipeline === "FAIL" ? ' · <em class="b">流水线失败</em>' : ""}</span></li>`).join("");
  return `<ul class="tip-commits">${items}</ul>${list.length > max ? `<div class="tip-foot">还有 ${list.length - max} 个提交</div>` : ""}`;
}

// 某个需求在某仓库的最近提交（合并该仓库下各 Story、各分支）
function repoCommits(r, repo){
  return r.stories.flatMap(s => s.code.filter(g => g.repo === repo).flatMap(g => (g.recent || []).map(c => ({...c, branch: g.branch}))))
    .sort((a, b) => (b.time || "").localeCompare(a.time || ""));
}

(function initTip(){
  const el = document.createElement("div");
  el.className = "tip"; el.hidden = true; el.setAttribute("role", "tooltip");
  document.body.appendChild(el);
  let cur = null;
  const place = e => {
    const pad = 14, w = el.offsetWidth, h = el.offsetHeight;
    let x = e.clientX + pad, y = e.clientY + pad;
    if (x + w > innerWidth - 8) x = e.clientX - w - pad;
    if (y + h > innerHeight - 8) y = Math.max(8, e.clientY - h - pad);
    el.style.left = x + "px"; el.style.top = y + "px";
  };
  document.addEventListener("mouseover", e => {
    const t = e.target.closest && e.target.closest("[data-tip]");
    if (t === cur) return;
    cur = t;
    if (!t) { el.hidden = true; return; }
    el.innerHTML = t.getAttribute("data-tip"); el.hidden = false; place(e);
  });
  document.addEventListener("mousemove", e => { if (!el.hidden) place(e); });
  document.addEventListener("scroll", () => { el.hidden = true; cur = null; }, true);
})();
