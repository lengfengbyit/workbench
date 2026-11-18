// 图表：全部手写 SVG，不依赖外部库

// 横向分段条：Story 按阶段分段，段宽 = 数量
function segBar(stories, h = 8){
  const n = stories.length || 1, parts = D.stages.map(s => ({s: s.name, n: stories.filter(x => x.status === s.name).length})).filter(p => p.n);
  let x = 0;
  const rects = parts.map(p => {
    const w = p.n / n * 100, list = stories.filter(s => s.status === p.s);
    const t = tipBody(`${esc(p.s)} · ${p.n} 个 Story`, [], null, list.map(s => `${s.id} ${esc(cleanTitle(s.title))}`).join("<br>"));
    const r = `<rect x="${x}%" width="${w}%" height="${h}" fill="${stageColor(p.s)}"${tipAttr(t)}/>`; x += w; return r; }).join("");
  const label = parts.map(p => `<span><i style="background:${stageColor(p.s)}"></i>${esc(p.s)} <b class="num">${p.n}</b></span>`).join("");
  return `<svg width="100%" height="${h}" style="border-radius:${h / 2}px;display:block;overflow:hidden" role="img" aria-label="Story 阶段分布">${rects}</svg>
    <div class="legend" style="margin-top:6px">${label}</div>`;
}

// 环形进度
function ring(value, total, color, size = 64){
  const sw = Math.max(4, Math.round(size / 10)), r = size / 2 - sw / 2 - 1, c = 2 * Math.PI * r, p = total ? value / total : 0;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="${value}/${total}" style="flex:none">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="#eef0f3" stroke-width="${sw}"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round"
      stroke-dasharray="${c * p} ${c}" transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="50%" y="50%" dy=".35em" text-anchor="middle" font-size="${Math.round(size / 4.4)}" font-weight="600" class="num">${Math.round(p * 100)}%</text></svg>`;
}

// 阶段步进条：父卡走到哪一步，每个阶段上方标注落在这里的 Story 数
function stepper(r){
  const stages = D.stages.filter(s => !s.offPath), W = 960, H = 58, pad = 30, step = (W - pad * 2) / (stages.length - 1);
  const cur = stageIdx(r.status), curPos = stages.findIndex(s => s.name === r.status);
  let svg = `<line x1="${pad}" x2="${W - pad}" y1="24" y2="24" stroke="#e6e8ec" stroke-width="3" stroke-linecap="round"/>`;
  if (curPos > 0) svg += `<line x1="${pad}" x2="${pad + curPos * step}" y1="24" y2="24" stroke="${stageColor(r.status)}" stroke-width="3" stroke-linecap="round"/>`;
  stages.forEach((s, i) => {
    const x = pad + i * step, on = s.name === r.status, done = stageIdx(s.name) < cur, list = r.stories.filter(z => z.status === s.name), n = list.length, c = stageColor(s.name);
    const t = tipBody(`${esc(s.name)}${on ? "（父卡当前阶段）" : ""}`, [["落在这里的 Story", `${n} 个`]], null,
      list.map(z => `${z.id} ${esc(cleanTitle(z.title))}`).join("<br>"));
    svg += `<g${tipAttr(t)}><circle cx="${x}" cy="28" r="22" fill="transparent"/>`;
    svg += on ? `<circle cx="${x}" cy="24" r="10" fill="${c}" opacity=".18"/><circle cx="${x}" cy="24" r="6" fill="${c}"/>`
              : `<circle cx="${x}" cy="24" r="5" fill="${done ? c : "#fff"}" stroke="${done ? c : "#cbd2db"}" stroke-width="2"/>`;
    svg += `<text x="${x}" y="52" text-anchor="middle" font-size="12" fill="${on ? "#111827" : "#8a94a6"}" font-weight="${on ? 600 : 400}">${esc(s.name)}</text>`;
    if (n) svg += `<text x="${x}" y="9" text-anchor="middle" font-size="11" fill="${c}" font-weight="600">${n} 个 Story</text>`;
    svg += `</g>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px" role="img" aria-label="当前阶段 ${esc(r.status)}">${svg}</svg>`;
}

// 关系图用到的节点和连线：notes.json 里记的节点 + 这个需求实际有提交的仓库
function relModel(r){
  const rel = r.relation || {}, nodes = [...(rel.nodes || [])];
  r.repos.forEach(z => { if (!nodes.includes(z.repo)) nodes.push(z.repo); });
  const edges = (rel.edges || []).filter(e => nodes.includes(e[0]) && nodes.includes(e[1]));
  return {rel, nodes, edges};
}
const EDGE_NUM = "①②③④⑤⑥";

// 图下方：箭头编号说明和「关系还没记录」的提示，跟图放在左列
function relationNotes(r){
  const {rel, edges} = relModel(r);
  const desc = edges.map(([a, b, l], k) => `<div class="small" style="color:var(--text-2);margin-top:4px">${EDGE_NUM[k] || k + 1} ${esc(short(a))} → ${esc(short(b))}：${esc(l)}</div>`).join("");
  const hint = rel.nodes ? "" : `<div class="small muted">仓库之间的关系还没记录，在 workbench/notes.json 里给 ${r.id} 补上</div>`;
  return desc + hint;
}

// 需求备注（黄色框，如上线顺序）：放在右列分支状态表下面，让两列高度更接近
function relationNote(r){
  const note = (r.relation || {}).note;
  return note ? `<div class="note" style="margin-top:16px">${esc(note)}</div>` : "";
}

// 仓库关系图：节点 = 仓库（显示分支和待合数），箭头编号对应「调用关系说明」（来自 notes.json）
function relationGraph(r){
  const {nodes, edges} = relModel(r);
  const NUM = EDGE_NUM, W = 460, n = Math.max(1, nodes.length), gap = 36;
  // 超过 3 个仓库自动换行：4 个排 2×2，5 个及以上每行 3 个。框宽固定，文字不会被挤出框
  const cols = n <= 3 ? n : n === 4 ? 2 : 3, rows = Math.ceil(n / cols), bw = Math.min(160, (W - gap * (cols - 1) - 4) / cols);
  // 文字按框宽估算可放的字符数：仓库名在 - / _ 处折成最多两行，分支名超长截断（悬停看全名）
  const avail = bw - 22, nameMax = Math.max(4, Math.floor(avail / 7.5)), branchMax = Math.max(4, Math.floor(avail / 6.3));
  const cut = (s, n) => s.length > n ? s.slice(0, n - 1) + "…" : s;
  const wrap = (s, n) => {
    const lines = [""];
    (s.match(/[^-/_]+[-/_]?/g) || [s]).forEach(p => { if (lines[lines.length - 1] && (lines[lines.length - 1] + p).length > n) lines.push(p); else lines[lines.length - 1] += p; });
    return (lines.length > 2 ? [lines[0], lines.slice(1).join("")] : lines).map(l => cut(l, n));
  };
  const names = nodes.map(repo => wrap(short(repo), nameMax)), extra = Math.max(1, ...names.map(l => l.length)) - 1;
  const rowOf = i => Math.floor(i / cols), colOf = i => i % cols, bh = 92 + extra * 15;
  // 一行里有跨格子的弧线时，这一行上方要留出弧线的空间；行与行之间留出连线空间
  const arcRow = Array.from({length: rows}, (_, r) => edges.some(([a, b]) => { const i = nodes.indexOf(a), j = nodes.indexOf(b); return rowOf(i) === r && rowOf(j) === r && Math.abs(i - j) > 1; }));
  const rowTop = [];
  arcRow.forEach((hasArc, r) => rowTop.push(r ? rowTop[r - 1] + bh + (hasArc ? 52 : 44) : (hasArc ? 48 : 10)));
  const H = rowTop[rows - 1] + bh + 6;
  const cx = i => 2 + colOf(i) * (bw + gap) + bw / 2, topOf = i => rowTop[rowOf(i)];
  let svg = `<defs><marker id="ar${safe(r.id)}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0L10,5L0,10z" fill="#94a3b8"/></marker></defs>`;
  nodes.forEach((repo, i) => {
    const top = topOf(i), x = cx(i) - bw / 2, items = r.repos.filter(z => z.repo === repo), pend = items.reduce((s, z) => s + z.mine, 0), c = repoColor(repo), y0 = top + extra * 15;
    const t = tipBody(esc(repo), items.map(z => [z.branch, `待合 ${z.mine}${z.behind ? ` · 落后主干 ${z.behind}` : ""}${z.others.length ? ` · 他人 ${z.others.length}` : ""}`]),
      repoCommits(r, repo), items.length ? "" : "本需求在这个仓库没有提交");
    svg += `<g${tipAttr(t)}><rect x="${x}" y="${top}" width="${bw}" height="${bh}" rx="10" fill="#fff" stroke="#e6e8ec"/>
      <rect x="${x}" y="${top}" width="4" height="${bh}" rx="2" fill="${c}"/>
      <text x="${x + 14}" y="${top + 20}" font-size="12.5" font-weight="600">${names[i].map((l, k) => `<tspan x="${x + 14}" dy="${k ? 15 : 0}">${esc(l)}</tspan>`).join("")}</text>`;
    items.slice(0, 3).forEach((z, k) => {
      svg += `<text x="${x + 14}" y="${y0 + 40 + k * 15}" font-size="10.5" fill="#4b5563" font-family="ui-monospace,Menlo,monospace">${esc(cut(z.branch, branchMax))}</text>`;
    });
    svg += items.length ? `<text x="${x + 14}" y="${top + bh - 10}" font-size="11.5" font-weight="600" fill="${pend ? "#b45309" : "#059669"}">${pend ? `● 待合${bw >= 118 ? "主干" : ""} ${pend}` : "✓ 已进主干"}</text>`
                        : `<text x="${x + 14}" y="${y0 + 44}" font-size="11" fill="#8a94a6">本需求无提交</text>`;
    svg += `</g>`;
  });
  edges.forEach(([a, b, l], k) => {
    const i = nodes.indexOf(a), j = nodes.indexOf(b), lab = NUM[k] || k + 1, ti = topOf(i), tj = topOf(j), x1 = cx(i), x2 = cx(j);
    const g = `<g${tipAttr(tipBody(`${lab} ${esc(short(a))} → ${esc(short(b))}`, [], null, esc(l || "")))}>`;
    let d, lx, ly;
    if (rowOf(i) === rowOf(j) && Math.abs(i - j) === 1) {          // 同一行相邻：直线箭头
      const dir = j > i ? 1 : -1, y = ti + bh / 2, xa = x1 + dir * (bw / 2 + 2), xb = x2 - dir * (bw / 2 + 2);
      d = `M${xa},${y} L${xb},${y}`; lx = (xa + xb) / 2; ly = y - 10;
    } else if (rowOf(i) === rowOf(j)) {                            // 同一行不相邻：从上方绕过去
      const my = ti - 38;
      d = `M${x1},${ti} C${x1},${my} ${x2},${my} ${x2},${ti - 2}`; lx = (x1 + x2) / 2; ly = my + 6;
    } else {                                                       // 跨行：从上一行的底边连到下一行的顶边
      const down = rowOf(j) > rowOf(i), ya = down ? ti + bh : ti, yb = down ? tj - 2 : tj + bh + 2, mid = (ya + yb) / 2;
      d = `M${x1},${ya} C${x1},${mid} ${x2},${mid} ${x2},${yb}`;
      lx = x1 + (x2 - x1) * 0.216; ly = ya + (yb - ya) * 0.342;      // 编号放在曲线 30% 处，避免交叉的两条线编号叠在中点
    }
    svg += `${g}<path d="${d}" fill="none" stroke="transparent" stroke-width="14"/>
      <path d="${d}" fill="none" stroke="#94a3b8" stroke-width="1.5" marker-end="url(#ar${safe(r.id)})"/>
      <text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="central" font-size="12" fill="none" stroke="#fff" stroke-width="4">${lab}</text>
      <text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="central" font-size="12" fill="#4b5563">${lab}</text></g>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="仓库关系图">${svg}</svg>`;
}

// 近 30 天提交柱状图（按仓库堆叠）
function activity(W = 560){
  const {days, series} = D.activity, repos = Object.keys(series);
  const H = 190, L = 26, B = 26, bw = (W - L) / days.length;
  const tot = days.map((_, i) => repos.reduce((s, r) => s + series[r][i], 0)), max = Math.max(1, ...tot), stepV = Math.max(1, Math.ceil(max / 4));
  const barW = Math.min(bw - 4, 22);   // 宽画布下柱子不跟着变粗
  let svg = "";
  for (let v = 0; v <= max; v += stepV) { const y = H - B - v / max * (H - B - 8); svg += `<line x1="${L}" x2="${W}" y1="${y}" y2="${y}" stroke="#eef0f3"/><text x="${L - 6}" y="${y + 4}" font-size="10" text-anchor="end" fill="#8a94a6">${v}</text>`; }
  const detailOf = (r, i) => ((D.activity.detail || {})[r] || [])[i] || [];
  days.forEach((d, i) => {
    let y = H - B;
    repos.forEach(r => { const n = series[r][i]; if (!n) return; const h = n / max * (H - B - 8); y -= h;
      const list = detailOf(r, i).map(c => ({...c, msg: c.msg, time: `${c.time} · ${c.branch} · ${lbl(c.id)}`}));
      const t = tipBody(`${esc(short(r))} · ${md(d)}`, [["提交数", `${n} 个`]], list);
      svg += `<rect x="${L + i * bw + (bw - barW) / 2}" y="${y}" width="${barW}" height="${h}" rx="2" fill="${repoColor(r)}"${tipAttr(t)}/>`; });
    if (i % 7 === 2 || i === days.length - 1) svg += `<text x="${L + i * bw + bw / 2}" y="${H - 8}" font-size="10" text-anchor="middle" fill="#8a94a6">${md(d)}</text>`;
  });
  const legend = repos.map(r => `<span><i style="background:${repoColor(r)}"></i>${esc(short(r))} <b class="num">${series[r].reduce((a, b) => a + b, 0)}</b></span>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="近 30 天提交">${svg}</svg><div class="legend">${legend}</div>`;
}
