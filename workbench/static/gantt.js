// Story 悬停内容：状态、排期、各仓库分支和最近提交
function storyTip(s){
  const range = (a, b) => a ? `${a}${b && b !== a ? " ~ " + b : ""}` : "";
  const code = s.code.map(g => [`${short(g.repo)}`, `${esc(g.branch)}${g.pending ? ` · 待合 ${g.pending}` : " · 已合"}${g.pipeline === "FAIL" ? " · 流水线失败" : ""}`]);
  const commits = s.code.flatMap(g => (g.recent || []).map(c => ({...c, time: `${c.time} · ${short(g.repo)}`}))).sort((a, b) => b.time.localeCompare(a.time));
  return tipBody(`${lbl(s.id)} ${esc(cleanTitle(s.title))}`, [
    ["状态", esc(s.status)], ["开发", range(s.devStart, s.devEnd)], ["计划提测", s.testPlan || ""],
    ["测试", range(s.testStart, s.testEnd)], ["计划上线", s.release || ""], ["QA", esc(s.qa || "")], ...code,
  ], commits.length ? commits : null, s.code.length ? "" : "还没有代码提交");
}

function reqTip(r, a, b){
  const k = reqStats(r);
  return tipBody(`${lbl(r.id)} ${esc(cleanTitle(r.title))}`, [
    ["状态", esc(r.status)], ["Story", `${k.total} 个（代码已进主干 ${k.merged} 个）`], ["时间", a && b ? `${a} ~ ${b}` : ""],
    ["仓库", esc([...new Set(r.repos.map(z => short(z.repo)))].join("、"))], ["待合主干", `${k.pending} 个提交`],
  ]);
}

// 排期甘特图：每个需求一行汇总条，下面每个 Story 一行
function gantt(){
  const day = s => Date.parse(s + "T00:00:00Z") / 864e5;
  const rows = [];
  D.requirements.forEach(r => {
    rows.push({r});
    r.stories.slice().sort((a, b) => (a.devStart || a.created).localeCompare(b.devStart || b.created)).forEach(s => rows.push({s, r}));
  });
  const dates = rows.filter(x => x.s).flatMap(({s}) => [s.devStart, s.devEnd, s.testPlan, s.testStart, s.testEnd, s.release, ...(s.iteration || [])]).filter(Boolean);
  dates.push(D.today);
  const lo = Math.min(...dates.map(day)) - 2, hi = Math.max(...dates.map(day)) + 4;
  const L = 300, W = 1400, RH = 28, top = 34, H = top + rows.length * RH + 8, px = (W - L - 12) / (hi - lo);
  const X = s => L + (day(s) - lo) * px, span = (a, b) => Math.max(px * .8, X(b || a) - X(a) + px);
  let svg = "";
  for (let d = Math.ceil(lo); d <= hi; d++) {
    const dt = new Date(d * 864e5), x = L + (d - lo) * px, wk = dt.getUTCDay();
    if (wk === 0 || wk === 6) svg += `<rect x="${x}" y="${top}" width="${px}" height="${H - top}" fill="#f7f8fa"/>`;
    if (wk === 1) svg += `<line x1="${x}" x2="${x}" y1="${top - 6}" y2="${H}" stroke="#eef0f3"/><text x="${x + 3}" y="${top - 12}" font-size="11" fill="#8a94a6">${dt.getUTCMonth() + 1}/${dt.getUTCDate()}</text>`;
  }
  rows.forEach((row, i) => {
    const y = top + i * RH, c = reqColor(row.r.id);
    if (!row.s) {
      const ss = row.r.stories, a = ss.map(s => s.devStart || s.created).filter(Boolean).sort()[0];
      const b = ss.flatMap(s => [s.release, s.testEnd, s.testPlan, s.devEnd]).filter(Boolean).sort().pop();
      svg += `<g${tipAttr(reqTip(row.r, a, b))}><rect x="0" y="${y}" width="${W}" height="${RH}" fill="#fafbfc"/><line x1="0" x2="${W}" y1="${y}" y2="${y}" stroke="#eef0f3"/>
        <rect x="8" y="${y + 9}" width="10" height="10" rx="3" fill="${c}"/>
        <text x="26" y="${y + 18}" font-size="12.5" font-weight="600">${lbl(row.r.id)} ${esc(cleanTitle(row.r.title).slice(0, 18))}</text>`;
      if (a && b) svg += `<rect x="${X(a)}" y="${y + 11}" width="${span(a, b)}" height="6" rx="3" fill="${c}" opacity=".35"/>`;
      svg += `</g>`;
      return;
    }
    const s = row.s;
    svg += `<rect class="row-hit" x="0" y="${y}" width="${W}" height="${RH}"${tipAttr(storyTip(s))}/>
      <g pointer-events="none"><circle cx="30" cy="${y + 14}" r="3.5" fill="${stageColor(s.status)}"/>
      <text x="40" y="${y + 18}" font-size="12" fill="#374151"><tspan class="num" fill="#8a94a6">${s.id}</tspan> ${esc(cleanTitle(s.title).slice(0, 19))}</text>`;
    if (s.iteration) svg += `<rect x="${X(s.iteration[0])}" y="${y + 4}" width="${span(...s.iteration)}" height="${RH - 8}" rx="4" fill="#eef2ff" opacity=".7"/>`;
    if (s.devStart) svg += `<rect x="${X(s.devStart)}" y="${y + 8}" width="${span(s.devStart, s.devEnd)}" height="5" rx="2.5" fill="#6366f1"/>`;
    if (s.testStart) svg += `<rect x="${X(s.testStart)}" y="${y + 15}" width="${span(s.testStart, s.testEnd)}" height="5" rx="2.5" fill="#f59e0b"/>`;
    if (s.testPlan) {
      const x = X(s.testPlan) + px / 2, late = s.testPlan < D.today && ["新建", "开发中", "开发完成"].includes(s.status);
      svg += `<path d="M${x},${y + 7} l5,7 l-5,7 l-5,-7z" fill="${late ? "#dc2626" : "#111827"}"/>`;
    }
    if (s.release) { const x = X(s.release) + px / 2;
      svg += `<line x1="${x}" x2="${x}" y1="${y + 6}" y2="${y + 22}" stroke="#059669" stroke-width="1.5"/><path d="M${x},${y + 6} h8 l-3,3 l3,3 h-8z" fill="#059669"/>`; }
    svg += `</g>`;
  });
  const tx = X(D.today) + px / 2;
  svg += `<line x1="${tx}" x2="${tx}" y1="${top - 4}" y2="${H}" stroke="#dc2626" stroke-width="1.5" stroke-dasharray="3 3"/>
    <rect x="${tx - 18}" y="${top - 26}" width="36" height="16" rx="8" fill="#dc2626"/><text x="${tx}" y="${top - 14}" font-size="10.5" fill="#fff" text-anchor="middle">今天</text>`;
  return `<div class="tbl-wrap"><svg viewBox="0 0 ${W} ${H}" width="100%" style="min-width:960px" role="img" aria-label="排期甘特图">${svg}</svg></div>
    <div class="legend"><span><i style="background:#eef2ff;border:1px solid #c7d2fe"></i>所在迭代</span><span><i style="background:#6366f1"></i>开发</span>
      <span><i style="background:#f59e0b"></i>测试</span><span>◆ 计划提测（<b style="color:#dc2626">红色</b> = 已过期还没提测）</span>
      <span style="color:#059669">⚑ 计划上线</span><span style="color:#dc2626">┊ 今天</span></div>`;
}
