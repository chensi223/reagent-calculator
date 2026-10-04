/* ============================================================
   投料计算器 · 界面与状态
   ============================================================ */

const LS = {
  state: 'clc.state.v1',
  personal: 'clc.personal.v1',
  recent: 'clc.recent.v1'
};

const ROLES = [
  ['substrate', '底物'], ['reagent', '试剂'], ['catalyst', '催化剂'],
  ['ligand', '配体'], ['base', '碱'], ['acid', '酸'],
  ['solvent', '溶剂'], ['additive', '添加剂'], ['product', '产物']
];

let DICT = { reagents: [] };
let dictIndex = null;
let personalIndex = null;
let state = null;
let ctx = null;
let rafPending = false;

/* 象形图：把 9 个 SVG 一次性注入成 CSS 背景类。
   直接往每个 <img src="data:..."> 里塞会把同一个 SVG 重复写进 DOM 几十次，
   改用背景图后 DOM 里只剩一个类名。 */
function injectPictoCss() {
  const css = Object.keys(PICTO).map(k =>
    '.pict-' + k + '{background-image:url("' + PICTO[k] + '")}'
  ).join('\n');
  const s = document.createElement('style');
  s.textContent = css;
  document.head.appendChild(s);
}

function pictHtml(code, small) {
  if (!PICTO[code]) return '';
  const name = PICTO_NAME[code] || code;
  return '<span class="pict pict-' + code + (small ? ' sm' : '') + '" title="' + esc(name) + '"></span>';
}

/* ---------------- 状态 ---------------- */
function todayStr() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function newRow(reagent) {
  return {
    reagent: reagent,
    type: reagent.type || 'solid',
    conc: reagent.conc != null ? reagent.conc : null,
    medium: reagent.medium || null,
    role: 'reagent',
    equiv: { v: null, src: null },
    mmol: { v: null, src: null },
    mass: { v: null, src: null },
    volume: { v: null, src: null },
    mwOverride: null,
    densityOverride: null,
    purityOverride: null,
    concOverride: null,
    locked: []
  };
}

function defaultState() {
  return {
    runName: '',
    runDate: todayStr(),
    anchorMode: 'ref',
    refIndex: 0,
    rows: [],
    product: { mw: null, targetMass: null, yield: 100 },
    solvent: { name: '', volume: null },
    scaleUnit: 'mmol'
  };
}

function loadState() {
  try {
    const raw = localStorage.getItem(LS.state);
    if (raw) {
      const s = JSON.parse(raw);
      if (s && Array.isArray(s.rows)) {
        s.rows = s.rows.map(r => {
          const row = Object.assign(newRow(r.reagent || {}), r);
          ['equiv', 'mmol', 'mass', 'volume'].forEach(k => {
            if (!row[k] || typeof row[k] !== 'object') row[k] = { v: null, src: null };
          });
          return row;
        });
        return Object.assign(defaultState(), s);
      }
    }
  } catch (e) { console.warn('载入状态失败', e); }
  return defaultState();
}

let saveTimer = null;
function saveState() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try { localStorage.setItem(LS.state, JSON.stringify(state)); } catch (e) { }
  }, 300);
}

function loadJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) { return fallback; }
}
function saveJSON(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { }
}

/* ---------------- 最近用过（20 条） ---------------- */
function getRecent() { return loadJSON(LS.recent, []); }

function pushRecent(reagent) {
  let list = getRecent().filter(r => (r.cas || r.zh) !== (reagent.cas || reagent.zh));
  const slim = {
    zh: reagent.zh, en: reagent.en, alias: reagent.alias, abbr: reagent.abbr,
    cas: reagent.cas, formula: reagent.formula, cid: reagent.cid,
    mw: reagent.mw, exact: reagent.exact, density: reagent.density,
    purity: reagent.purity, type: reagent.type, conc: reagent.conc, medium: reagent.medium,
    hazard: reagent.hazard, baikeHazard: reagent.baikeHazard,
    _src: reagent._src, lastUsedAt: Date.now()
  };
  list.unshift(slim);
  list = list.slice(0, 20);
  saveJSON(LS.recent, list);
  renderRecentMenu();
}

function renderRecentMenu() {
  const menu = document.getElementById('recentMenu');
  const list = getRecent();
  if (!list.length) {
    menu.innerHTML = '<div class="empty">还没有用过的试剂</div>';
    return;
  }
  menu.innerHTML = list.map((r, i) =>
    '<div class="recent-item" data-recent="' + i + '">' +
    '<span class="rn">' + esc(r.zh || r.en || r.cas || '?') + '</span>' +
    '<span class="rc">' + esc(r.cas || r.formula || '') + '</span>' +
    (r.mw != null ? '<span class="rm">' + fmtMW(r.mw) + '</span>' : '') +
    '</div>'
  ).join('');
}

/* ---------------- 个人词典 ---------------- */
function getPersonal() { return loadJSON(LS.personal, []); }
function savePersonal(list) {
  saveJSON(LS.personal, list);
  personalIndex = buildPersonalIndex(list);
}
function rememberReagent(reagent) {
  if (!reagent || (!reagent.cas && !reagent.zh)) return;
  const list = getPersonal();
  const key = reagent.cas || reagent.zh;
  const i = list.findIndex(r => (r.cas || r.zh) === key);
  const slim = {
    zh: reagent.zh, en: reagent.en, alias: reagent.alias, abbr: reagent.abbr,
    cas: reagent.cas, formula: reagent.formula, cid: reagent.cid,
    mw: reagent.mw, exact: reagent.exact, density: reagent.density,
    purity: reagent.purity, type: reagent.type, conc: reagent.conc, medium: reagent.medium,
    hazard: reagent.hazard, baikeHazard: reagent.baikeHazard, _src: 'personal'
  };
  if (i >= 0) list[i] = slim; else list.push(slim);
  savePersonal(list);
}

/* ---------------- 工具 ---------------- */
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
function toast(msg, kind) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show ' + (kind || '');
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.className = 'toast'; }, 3200);
}
function rowName(r) {
  const g = r.reagent || {};
  return g.zh || g.en || g.cas || g.formula || '未知';
}
function isUser(cell) { return cell && cell.src === 'user'; }

/* ---------------- 计算 ---------------- */
function recompute() {
  const warns = solve(state);
  const conflicts = detectConflicts(state);
  return { warns, conflicts };
}

/* 同步刷新。
   原先用 requestAnimationFrame 合并重算，但浏览器在后台标签页会暂停 rAF，
   切回窗口时表格还停在旧数值 —— 对投料单来说这是危险的，所以改成同步。 */
function refresh() {
  doRefresh();
}

function doRefresh() {
  const { warns, conflicts } = recompute();
  updateCells();
  renderWarnings(warns, conflicts);
  renderHazardZone();
  updateScaleHint();
  saveState();
}

/* 只更新单元格的值与样式，不重建 DOM（保住输入焦点） */
function updateCells() {
  const tbody = document.getElementById('chargeBody');
  state.rows.forEach((r, i) => {
    const tr = tbody.querySelector('tr[data-row="' + i + '"]');
    if (!tr) return;
    tr.classList.toggle('is-ref', i === state.refIndex);
    const rd = tr.querySelector('input[data-field="__ref"]');
    if (rd) rd.checked = (i === state.refIndex);
    setInput(tr, 'equiv', dispEquiv(qv(r.equiv)), r.equiv.src);
    setInput(tr, 'mmol', dispMol(qv(r.mmol)), r.mmol.src);
    setInput(tr, 'mass', dispMass(qv(r.mass)), r.mass.src);
    setInput(tr, 'volume', dispVol(qv(r.volume)), r.volume.src);
    const pm = tr.querySelector('[data-field="__prop"]');
    if (pm) pm.textContent = propLabel(r);
    const wn = tr.querySelector('[data-field="__warn"]');
    if (wn) {
      const g = r.reagent && r.reagent.hazard ? r.reagent.hazard.grade : 'unknown';
      wn.textContent = (g === 'high') ? '⚠ ' : '';
      wn.title = (g === 'high') ? '高危险试剂，见下方危险提醒' : '';
    }
  });
}

/* 列内显示：一律带单位（用户要求"在质量和体积处加上单位"）。
   输入框仍然接受裸数字（按列单位解释），也接受带单位的写法。 */
function dispMass(g) {
  if (g == null) return '';
  return fmtMass(g);
}
function dispVol(mL) {
  if (mL == null) return '';
  return fmtVol(mL);
}
function dispMol(mmol) {
  if (mmol == null) return '';
  if (Math.abs(mmol) < 0.1) return fmtMol(mmol);
  return mmol.toFixed(mmol < 10 ? 2 : 1);
}
function dispEquiv(e) {
  return fmtEquiv(e);
}

function setInput(tr, field, val, src) {
  const el = tr.querySelector('input[data-field="' + field + '"]');
  if (!el) return;
  if (document.activeElement === el) return;   // 正在编辑就别覆盖
  if (el.value !== val) el.value = val;
  el.classList.toggle('sys', src === 'sys');
  el.classList.toggle('usr', src === 'user');
}

function propLabel(r) {
  const t = r.type;
  if (t === 'solution') {
    const c = r.concOverride != null ? r.concOverride : r.conc;
    return c != null ? (c + ' M' + (r.medium ? ' ' + r.medium : '')) : '浓度未设';
  }
  if (t === 'liquid') {
    const d = r.densityOverride != null ? r.densityOverride : (r.reagent && r.reagent.density);
    return d != null ? (d + ' g/mL') : '密度未设';
  }
  return '固体';
}

/* ---------------- 表格渲染 ---------------- */
function renderTable() {
  const tbody = document.getElementById('chargeBody');
  tbody.innerHTML = '';
  state.rows.forEach((r, i) => {
    const tr = document.createElement('tr');
    tr.dataset.row = i;
    if (i === state.refIndex) tr.classList.add('is-ref');

    const g = r.reagent || {};
    const hzGrade = g.hazard ? g.hazard.grade : 'unknown';
    const warnMark = hzGrade === 'high' ? '<span class="hzw" title="高危险试剂">⚠</span>' : '';

    tr.innerHTML =
      '<td class="c-ref"><input type="radio" name="refsel" data-field="__ref"' + (i === state.refIndex ? ' checked' : '') + '></td>' +
      '<td class="c-name">' +
      '<div class="rn"><span class="hzwrap" data-field="__warn"></span>' + esc(rowName(r)) + '</div>' +
      '<div class="rc">' + esc(g.cas || g.formula || '') + '</div></td>' +
      '<td class="c-mw" data-label="分子量"><span class="mwv">' + fmtMW(rowMW(r)) + '</span></td>' +
      '<td class="c-prop" data-label="密度/浓度"><button class="propbtn" data-field="__prop" type="button">' + esc(propLabel(r)) + '</button></td>' +
      '<td class="c-num" data-label="当量"><input type="text" data-field="equiv" inputmode="decimal"></td>' +
      '<td class="c-num" data-label="mmol"><input type="text" data-field="mmol" inputmode="decimal"></td>' +
      '<td class="c-num" data-label="质量"><input type="text" data-field="mass" inputmode="decimal"></td>' +
      '<td class="c-num" data-label="体积"><input type="text" data-field="volume" inputmode="decimal"></td>' +
      '<td class="c-role" data-label="角色"><select data-field="role">' +
      ROLES.map(x => '<option value="' + x[0] + '"' + (r.role === x[0] ? ' selected' : '') + '>' + x[1] + '</option>').join('') +
      '</select></td>' +
      '<td class="c-act"><button class="delbtn" data-del="' + i + '" type="button" title="删除此行">✕</button></td>';

    tbody.appendChild(tr);
  });
  updateCells();
}

/* ---------------- 警告区 ---------------- */
function renderWarnings(warns, conflicts) {
  const z = document.getElementById('warnZone');
  const items = [];
  for (const w of warns) items.push({ level: w.level, msg: w.msg });
  for (const c of conflicts) items.push({ level: 'conflict', msg: c.msg });
  if (!items.length) { z.innerHTML = '<div class="ok">✓ 计量自洽</div>'; return; }
  z.innerHTML = items.map(it => {
    const cls = it.level === 'block' ? 'err' : (it.level === 'conflict' ? 'conflict' : 'warn');
    const ico = it.level === 'block' ? '⛔' : (it.level === 'conflict' ? '⚠' : '·');
    return '<div class="witem ' + cls + '"><span class="wi">' + ico + '</span>' + esc(it.msg) + '</div>';
  }).join('');
}

/* ---------------- 危险提醒区 ---------------- */
let lastHzSig = '';

function renderHazardZone() {
  const z = document.getElementById('hazardZone');
  const rows = state.rows.filter(r => r.reagent);
  if (!rows.length) { z.innerHTML = ''; lastHzSig = ''; return; }

  // 只有在危险数据或用量变化时才重建 DOM
  const sig = JSON.stringify(rows.map(r => [
    (r.reagent && r.reagent.cas) || (r.reagent && r.reagent.zh),
    r.reagent && r.reagent.hazard ? r.reagent.hazard.grade : '',
    Math.round((qv(r.volume) || 0) * 1000),
    Math.round((qv(r.mass) || 0) * 10000)
  ]));
  if (sig === lastHzSig) return;
  lastHzSig = sig;

  const withHz = rows.map(r => ({ row: r, hz: r.reagent.hazard })).filter(x => x.hz);
  const high = withHz.filter(x => x.hz.grade === 'high');
  const med = withHz.filter(x => x.hz.grade === 'medium');
  const low = withHz.filter(x => x.hz.grade === 'low');
  const unknown = rows.filter(r => !r.reagent.hazard || r.reagent.hazard.grade === 'unknown');

  if (!high.length && !med.length && !low.length && !unknown.length) { z.innerHTML = ''; return; }

  let html = '<div class="hz-head"><span class="hz-t">⚠ 危险提醒</span>';
  if (high.length) html += '<span class="hz-cnt red">' + high.length + ' 项需特别注意</span>';
  html += '</div>';

  for (const { row, hz } of high) html += renderHazardCard(row, hz, true);

  // 注意：unknown 是「行」的数组（不是 {row,hz} 包装），别再解构错
  for (const row of unknown) {
    const hz = row.reagent.hazard;
    const b = hz && hz.baike;
    const hasB = b && (b.symbols.length || b.r.length);
    html += '<div class="hz-card unknown">' +
      '<div class="hz-title"><span class="hz-name">' + esc(rowName(row)) + '</span>' +
      '<span class="hz-cas">' + esc(row.reagent.cas || row.reagent.formula || '') + '</span>' +
      '<span class="hz-use">用量 ' + usageText(row) + '</span></div>' +
      '<div class="hz-note">' + esc((hz && hz.note) || '未获取到危害分类数据 — 请查阅 SDS 或试剂瓶标签') + '</div>' +
      (hasB ? '<div class="hz-baike">百科补充：' +
        (b.symbols.length ? b.symbols.map(s => '<b>' + esc(s) + '</b>（' + esc(SYMBOL_CN[s] || '') + '）').join(' ') : '') +
        (b.r.length ? ' ｜ ' + b.r.map(c => esc(c) + ' ' + esc(R_CN[c] || '')).join('；') : '') +
        '</div>' : '') +
      '</div>';
  }

  if (med.length || low.length) {
    const folded = [...med, ...low];
    html += '<div class="hz-more"><span class="hz-mt">其余需注意：</span>' +
      folded.map(({ row, hz }) => {
        const top = (hz.h || []).slice(0, 3).map(x => esc(x.code)).join('/');
        return '<span class="hz-chip">' + esc(rowName(row)) + (top ? ' <i>' + top + '</i>' : '') + '</span>';
      }).join('') +
      '<button class="hz-toggle" id="hzToggle" type="button">展开全部 ▾</button></div>';
    html += '<div class="hz-folded" id="hzFolded" hidden>' +
      folded.map(({ row, hz }) => renderHazardCard(row, hz, false)).join('') + '</div>';
  }

  html += '<div class="hz-disclaimer">数据来自 PubChem（ECHA C&L Inventory 企业通报汇总）与百度百科，仅供快速参考。' +
    '本程序不提供操作建议，<b>不能替代 SDS</b>。操作前请核对试剂瓶标签与实际批号 SDS。</div>';

  z.innerHTML = html;

  const tg = document.getElementById('hzToggle');
  if (tg) tg.addEventListener('click', () => {
    const f = document.getElementById('hzFolded');
    if (!f) return;
    f.hidden = !f.hidden;
    tg.textContent = f.hidden ? '展开全部 ▾' : '收起 ▴';
  });
}

function usageText(row) {
  const v = qv(row.volume), m = qv(row.mass);
  if (v != null) return fmtVol(v);
  if (m != null) return fmtMass(m);
  return '—';
}

function renderHazardCard(row, hz, expanded) {
  const g = row.reagent || {};
  const sig = hz.signal;
  const picts = (hz.pict || []).map(p => pictHtml(p, false)).join('');
  const hList = sortHCodes(hz.h || []);
  // 只显示"需要看的"：高危清单里的，或有 ≥20% 企业共识的。
  // 否则一个试剂能列出十几条（含"对水生生物有毒"这种与操作无关的），提醒就废了。
  const keep = x => H_HIGH.has(x.code) || H_CRITICAL_EXTRA.has(x.code) || (x.pct != null && x.pct >= 20);
  const shown = hList.filter(keep);
  const hidden = hList.filter(x => !keep(x));
  const hHtml = shown.map(x => {
    const txt = hText(x.code);
    const pct = (x.pct == null) ? '<span class="pct none">—</span>'
      : '<span class="pct' + (x.pct >= 50 ? ' hi' : '') + '">' + x.pct.toFixed(0) + '%</span>';
    const cls = (H_HIGH.has(x.code) || H_CRITICAL_EXTRA.has(x.code)) ? 'hi' : 'mid';
    return '<li class="' + cls + '"><code>' + esc(x.code) + '</code>' + pct +
      '<span class="ht">' + esc(txt || '（无中文对照）') + '</span></li>';
  }).join('') +
    (hidden.length
      ? '<li class="muted">…另有 ' + hidden.length + ' 项低比例或单来源条目：' +
      esc(hidden.slice(0, 8).map(x => x.code).join('、')) + (hidden.length > 8 ? ' 等' : '') + '</li>'
      : '');

  const b = hz.baike;
  const hasB = b && (b.symbols.length || b.r.length || b.s.length);

  // 反应性与淬灭：反应性标签来自 PubChem（引用），淬灭提示来自内置通行做法表
  const rtags = (row.reagent && row.reagent.reactTags) || [];
  const qtip = quenchTip(g.cas);
  const qhtml = (rtags.length || qtip)
    ? '<div class="hz-quench">' +
    '<div class="q-h">⚠ 反应性与淬灭</div>' +
    (rtags.length
      ? '<div class="q-row"><span class="q-k">反应性</span><span class="q-v">' +
      rtags.map(t => '<span class="qtag">' + esc(t) + '</span>').join('') + '</span></div>'
      : '') +
    (qtip
      ? '<div class="q-row"><span class="q-k">淬灭</span><span class="q-v q-tip">' + esc(qtip) + '</span></div>' +
      '<div class="q-note">反应性标签引自 PubChem；淬灭提示为实验室通行做法（非 SDS 原文），请以 SDS 与课题组规程为准。</div>'
      : '<div class="q-note">反应性标签引自 PubChem。</div>') +
    '</div>'
    : '';
  const extra = expanded && hasB
    ? '<div class="hz-baike">百科（旧 R/S 体系）：' +
      (b.symbols.length ? b.symbols.map(s => '<b>' + esc(s) + '</b>（' + esc(SYMBOL_CN[s] || '') + '）').join(' ') : '') +
      (b.r.length ? ' ｜ R：' + b.r.map(c => esc(c) + ' ' + esc(R_CN[c] || '')).join('；') : '') +
      (b.s.length ? ' ｜ S：' + b.s.map(c => esc(c) + ' ' + esc(S_CN[c] || '')).join('；') : '') +
      (b.flash ? ' ｜ 闪点 ' + esc(b.flash) : '') +
      '</div>'
    : '';

  return '<div class="hz-card' + (expanded ? ' high' : '') + '">' +
    '<div class="hz-title">' +
    '<span class="hz-name">' + esc(rowName(row)) + '</span>' +
    '<span class="hz-cas">' + esc(g.cas || g.formula || '') + '</span>' +
    (sig ? '<span class="sig ' + (sig === 'Danger' ? 'danger' : 'warn') + '">' + (sig === 'Danger' ? 'DANGER 危险' : 'WARNING 警告') + '</span>' : '') +
    '<span class="hz-use">用量 ' + usageText(row) + '</span>' +
    '</div>' +
    (picts ? '<div class="hz-picts">' + picts + '</div>' : '') +
    (hHtml ? '<ul class="hz-h">' + hHtml + '</ul>' : '') +
    qhtml +
    extra +
    ((hz.note && hz.grade === 'unknown') ? '<div class="hz-note">' + esc(hz.note) + '</div>' : '') +
    (hz.src && hz.src.length ? '<div class="hz-src">来源：' + esc(hz.src.join(' · ')) +
      (hz.stat ? '（' + hz.stat.reports + ' 份企业通报汇总）' : '') + '</div>' : '') +
    (expanded && hList.length ? '<div class="hz-legend">百分比为企业通报认同率；<b>—</b> 表示该来源未提供比例（多为个别数据库条目，非 ECHA 共识）</div>' : '') +
    (expanded
      ? '<button class="hz-detail" type="button" data-hzdetail="' + state.rows.indexOf(row) + '">▸ 展开更多安全信息（概述 / 急救 / 储存）</button>' +
      '<div class="hz-detail-box" hidden></div>'
      : '') +
    '</div>';
}

/* ---------------- 缩放提示 ---------------- */
function updateScaleHint() {
  const el = document.getElementById('scaleHint');
  if (!el) return;
  const n = refMmol(state);
  el.textContent = n != null ? ('当前规模 ' + fmtMol(n) + ' mmol') : '规模未定';
}
