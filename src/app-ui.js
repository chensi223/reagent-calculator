/* ============================================================
   投料计算器 · 交互、弹层、导出、初始化
   ============================================================ */

/* ---------------- 单元格输入 ---------------- */
function applyCellInput(row, field, raw) {
  const txt = String(raw == null ? '' : raw).trim();
  if (txt === '') { row[field] = { v: null, src: null }; return; }
  // 用户显式改了这行的某个量 → 该行预填的"默认值"让位
  // （否则第一行预填的 100 mmol 会一直压着，改质量时摩尔数不跟着变）
  for (const k of ['equiv', 'mmol', 'mass', 'volume']) {
    if (k !== field && row[k] && row[k].src === 'default') row[k] = { v: null, src: null };
  }
  // 当量列额外支持 mol% 写法（催化剂/配体常用）："10 mol%" 或 "10%"
  if (field === 'equiv') {
    const mp = txt.match(/^([\d.]+)\s*(?:mol\s*%|%)$/i);
    if (mp) {
      const v = parseFloat(mp[1]);
      if (isFinite(v)) { row.equiv = { v: v / 100, src: 'user' }; return; }
    }
  }
  const q = parseQuantity(txt);
  if (!q) return;
  const put = (f, v) => { row[f] = { v: v, src: 'user' }; };
  if (q.kind === 'bare') { put(field, q.value); return; }
  if (field === 'mass') {
    if (q.kind === 'mass') put('mass', q.value);
    else if (q.kind === 'mol') put('mmol', q.value);
    else if (q.kind === 'vol') put('volume', q.value);
  } else if (field === 'volume') {
    if (q.kind === 'vol') put('volume', q.value);
    else if (q.kind === 'mol') put('mmol', q.value);
    else if (q.kind === 'mass') put('mass', q.value);
  } else if (field === 'mmol') {
    if (q.kind === 'mol') put('mmol', q.value);
    else if (q.kind === 'mass') put('mass', q.value);
    else if (q.kind === 'vol') put('volume', q.value);
  } else {
    put(field, q.value);
  }
}

function bindTableEvents() {
  const tbody = document.getElementById('chargeBody');

  tbody.addEventListener('input', e => {
    const el = e.target;
    if (!el.dataset || !el.dataset.field) return;
    const tr = el.closest('tr');
    if (!tr) return;
    const i = +tr.dataset.row;
    const row = state.rows[i];
    if (!row) return;
    const f = el.dataset.field;
    if (f === 'equiv' || f === 'mmol' || f === 'mass' || f === 'volume') {
      applyCellInput(row, f, el.value);
      refresh();
    }
  });

  tbody.addEventListener('change', e => {
    const el = e.target;
    const tr = el.closest('tr');
    if (!tr) return;
    const i = +tr.dataset.row;
    const row = state.rows[i];
    if (!row) return;
    if (el.dataset.field === '__ref') {
      const keepMmol = qv(state.rows[i].mmol);   // 切换前先记住新参考物的绝对量
      state.refIndex = i;
      state.rows.forEach((r, k) => { if (k !== i && r.equiv.src === 'ref') r.equiv = { v: null, src: null }; });
      if (keepMmol != null) state.rows[i].mmol = { v: keepMmol, src: 'user' };
      renderTable(); refresh();
    } else if (el.dataset.field === 'role') {
      row.role = el.value; saveState();
    }
  });

  tbody.addEventListener('click', e => {
    const del = e.target.closest('[data-del]');
    if (del) {
      const i = +del.dataset.del;
      const nm = rowName(state.rows[i]);
      if (confirm('删除「' + nm + '」这一行？')) {
        state.rows.splice(i, 1);
        if (state.refIndex >= state.rows.length) state.refIndex = Math.max(0, state.rows.length - 1);
        else if (i < state.refIndex) state.refIndex--;
        renderTable(); refresh();
      }
      return;
    }
    const pb = e.target.closest('[data-field="__prop"]');
    if (pb) {
      const i = +pb.closest('tr').dataset.row;
      openPropModal(i);
    }
  });

  tbody.addEventListener('focusin', e => {
    // 格子里现在带单位（如 "10.612 g"），聚焦时全选，方便直接改写
    if (e.target.tagName === 'INPUT' && e.target.dataset.field !== '__ref') {
      try { e.target.select(); } catch (err) { }
    }
  });
  tbody.addEventListener('blur', e => {
    if (e.target.tagName === 'INPUT') refresh();
  }, true);
  tbody.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') { e.target.blur(); }
  });
}

/* ---------------- 最近用过 ---------------- */
function bindRecent() {
  const btn = document.getElementById('recentBtn');
  const menu = document.getElementById('recentMenu');
  btn.addEventListener('click', e => {
    e.stopPropagation();
    menu.classList.toggle('open');
  });
  menu.addEventListener('click', async e => {
    const it = e.target.closest('[data-recent]');
    if (!it) return;
    const list = getRecent();
    const rec = list[+it.dataset.recent];
    if (!rec) return;
    menu.classList.remove('open');
    if (!rec.formula && !rec.mw && rec.cas) {
      toast('正在补全该试剂信息…');
      try {
        const full = await resolveReagent(rec.cas, ctx, m => { });
        addReagentToList(full);
        return;
      } catch (err) { toast('补全失败，用已有信息添加', 'warn'); }
    }
    addReagentToList(rec);
  });
  document.addEventListener('click', () => menu.classList.remove('open'));
}

function addReagentToList(reagent) {
  const r = normalizeReagent(reagent, reagent._src || 'recent');
  const row = newRow(r);
  if (state.rows.length > 0) row.role = 'reagent';
  else row.role = 'substrate';
  // 第一条自动成为参考物
  if (state.rows.length === 0) {
    state.refIndex = 0;
    row.equiv = { v: 1, src: 'ref' };
    // 默认给一个 100 mmol 起点。标成 'default' 而不是 'user'：
    // 用户一旦改了这行的其它量（比如填质量），这个预填值就让位、由质量反算摩尔数。
    row.mmol = { v: 100, src: 'default' };
  }
  state.rows.push(row);
  pushRecent(r);
  rememberReagent(r);
  renderTable();
  refresh();
}

/* ---------------- 添加试剂弹层 ---------------- */
let pendingReagent = null;
let lookupSeq = 0;

function openAddModal(initial) {
  pendingReagent = null;
  const m = document.getElementById('addModal');
  m.classList.add('open');
  const inp = document.getElementById('addInput');
  inp.value = initial || '';
  document.getElementById('addPreview').innerHTML = '';
  document.getElementById('addProgress').textContent = '';
  document.getElementById('addConfirmBtn').disabled = true;
  updateAddHint();
  setTimeout(() => inp.focus(), 30);
}

function closeAddModal() {
  document.getElementById('addModal').classList.remove('open');
}

function updateAddHint() {
  const v = document.getElementById('addInput').value.trim();
  const hint = document.getElementById('addHint');
  const t = detectInputType(v);
  const map = { cas: 'CAS 号', zh: '中文名', en: '英文名/缩写', formula: '分子式', empty: '' };
  let extra = '';
  if (t.type === 'cas' && !t.valid) extra = ' ⚠ 校验位不通过';
  hint.textContent = v ? ('识别为：' + map[t.type] + extra) : '';
  hint.className = 'add-hint' + (t.type === 'cas' && !t.valid ? ' bad' : '');
}

async function doAddLookup() {
  const v = document.getElementById('addInput').value.trim();
  if (!v) return;
  const seq = ++lookupSeq;
  const prog = document.getElementById('addProgress');
  const prev = document.getElementById('addPreview');
  document.getElementById('addConfirmBtn').disabled = true;
  prev.innerHTML = '';
  prog.textContent = '查询中…';
  try {
    const r = await resolveReagent(v, ctx, msg => { if (seq === lookupSeq) prog.textContent = msg; });
    if (seq !== lookupSeq) return;
    pendingReagent = r;
    prog.textContent = '查询完成';
    prev.innerHTML = renderAddPreview(r);
    document.getElementById('addConfirmBtn').disabled = false;
    bindPreviewEvents(r);
  } catch (e) {
    if (seq !== lookupSeq) return;
    prog.textContent = '';
    prev.innerHTML = '<div class="add-err">✕ ' + esc(e.message || '查询失败') + '</div>' +
      '<div class="add-tip">提示：试剂瓶标签上一定印着 CAS 号，直接输 CAS 最可靠。<br>' +
      '如果是自己合成的化合物，在下面手动填个分子量就能建一条。</div>';
    document.getElementById('addConfirmBtn').disabled = true;
    openManualSection(v);
  }
}

function renderAddPreview(r) {
  const rows = [];
  rows.push(['中文名', r.zh || '—']);
  rows.push(['英文名', r.en || '—']);
  if (r.alias && r.alias.length) rows.push(['别名', r.alias.join('、')]);
  rows.push(['CAS', r.cas ? (r.cas + (casValid(r.cas) ? ' ✓' : ' ⚠校验位不通过')) : '—']);
  rows.push(['分子式', r.formula || '—']);
  rows.push(['分子量', r.mw != null ? (fmtMW(r.mw) + '（本地计算）') : '—']);
  if (r.exact != null) rows.push(['精确质量', r.exact.toFixed(4)]);
  rows.push(['密度', r.density != null ? (r.density + ' g/cm³' + (r.densityRaw ? '（百科原文 ' + r.densityRaw + '）' : '')) : '—']);
  if (r.mwPubchem != null && r.mw != null && Math.abs(r.mwPubchem - r.mw) > 0.02) {
    rows.push(['交叉核对', 'PubChem 给 ' + r.mwPubchem + '，本地算 ' + fmtMW(r.mw) + '（以本地为准）']);
  }
  let hz = '';
  if (r.hazard && (r.hazard.grade === 'high' || r.hazard.grade === 'medium' || r.hazard.grade === 'low')) {
    const p = (r.hazard.pict || []).map(x => pictHtml(x, true)).join('');
    const hs = sortHCodes(r.hazard.h || []).slice(0, 6).map(x =>
      '<span class="hchip ' + ((H_HIGH.has(x.code) || H_CRITICAL_EXTRA.has(x.code)) ? 'hi' : '') + '">' + esc(x.code) +
      (x.pct != null ? ' ' + x.pct.toFixed(0) + '%' : '') + '</span>').join('');
    hz = '<div class="add-hz"><span class="lbl">危害</span>' +
      (r.hazard.signal ? '<span class="sig ' + (r.hazard.signal === 'Danger' ? 'danger' : 'warn') + '">' + r.hazard.signal + '</span>' : '') +
      p + '<div class="hchips">' + hs + '</div></div>';
  } else if (r.hazard) {
    hz = '<div class="add-hz unknown"><span class="lbl">危害</span><span class="hznote">' +
      esc(r.hazard.note || '未获取到危害分类数据 — 请查阅 SDS') + '</span></div>';
    const b = r.hazard.baike;
    if (b && (b.symbols.length || b.r.length)) {
      hz += '<div class="hznote" style="padding-left:64px">百科补充：' +
        b.symbols.map(s => esc(s) + '（' + esc(SYMBOL_CN[s] || '') + '）').join(' ') +
        (b.r.length ? ' ｜ ' + b.r.slice(0, 6).map(c => esc(c)).join('、') : '') + '</div>';
    }
  }
  const body = rows.map(x =>
    '<div class="pv-row"><span class="pv-k">' + esc(x[0]) + '</span><span class="pv-v">' + esc(x[1]) + '</span></div>'
  ).join('');
  return body + hz +
    '<div class="pv-row"><span class="pv-k">形态</span><span class="pv-v">' +
    '<select id="pvType">' +
    ['solid:固体', 'liquid:液体', 'solution:溶液'].map(s => {
      const [v, t] = s.split(':');
      return '<option value="' + v + '"' + (r.type === v ? ' selected' : '') + '>' + t + '</option>';
    }).join('') + '</select>' +
    (r.solutionPresets && r.solutionPresets.length ? '<span class="hintmini">常见浓度：' +
      r.solutionPresets.map(s => s.conc + ' M/' + s.medium).join('、') + '</span>' : '') +
    '</span></div>' +
    '<div class="pv-row" id="pvConcRow" ' + (r.type === 'solution' ? '' : 'hidden') + '>' +
    '<span class="pv-k">浓度</span><span class="pv-v"><input id="pvConc" type="number" step="0.01" value="' +
    (r.conc != null ? r.conc : '') + '" placeholder="mol/L"> M　介质 <input id="pvMedium" type="text" value="' +
    esc(r.medium || '') + '" placeholder="如 正己烷"></span></div>';
}

function bindPreviewEvents(r) {
  const sel = document.getElementById('pvType');
  if (sel) sel.addEventListener('change', () => {
    const row = document.getElementById('pvConcRow');
    if (row) row.hidden = sel.value !== 'solution';
  });
}

function confirmAdd() {
  if (!pendingReagent) return;
  const r = normalizeReagent(pendingReagent, pendingReagent._src);
  const sel = document.getElementById('pvType');
  if (sel) r.type = sel.value;
  if (r.type === 'solution') {
    const c = parseFloat(document.getElementById('pvConc').value);
    if (isFinite(c) && c > 0) r.conc = c;
    const md = document.getElementById('pvMedium').value.trim();
    if (md) r.medium = md;
  }
  closeAddModal();
  addReagentToList(r);
  toast('已添加：' + (r.zh || r.cas || r.formula));
}

/* ---------------- 手动输入：自定义化合物 ---------------- */
/* 场景：知道结构但查不到名字/CAS；或分子式不好写（盐、水合物、混合物、聚合物）；
   或分子量来自文献/实测，不想让程序去猜。 */
function bindManualSection() {
  const tg = document.getElementById('manualToggle');
  const box = document.getElementById('manualBox');
  const fIn = document.getElementById('manFormula');
  const mwIn = document.getElementById('manMW');
  if (!tg || !box) return;

  tg.addEventListener('click', () => {
    const willOpen = box.hidden;
    box.hidden = !willOpen;
    tg.classList.toggle('open', willOpen);
    if (willOpen) setTimeout(() => document.getElementById('manName').focus(), 30);
  });

  // 填了分子式就本地算分子量（IUPAC 原子量，不联网）
  fIn.addEventListener('input', () => {
    const note = document.getElementById('manFormulaNote');
    const v = fIn.value.trim();
    if (!v) { note.textContent = ''; note.className = 'hintmini'; return; }
    const w = mwFromFormula(v);
    if (w == null || !isFinite(w)) {
      note.textContent = '⚠ 这个分子式解析不了';
      note.className = 'hintmini bad';
      return;
    }
    const cur = parseFloat(mwIn.value);
    if (!mwIn.value.trim() || !isFinite(cur)) {
      mwIn.value = w;
      note.textContent = '✓ 已算出 ' + fmtMW(w);
      note.className = 'hintmini ok';
    } else if (Math.abs(cur - w) > 0.001) {
      // 不擅自覆盖用户填的值，只提示差异
      note.textContent = '分子式算出 ' + fmtMW(w) + '，与上面填的不一致';
      note.className = 'hintmini bad';
    } else {
      note.textContent = '✓ 与分子式一致';
      note.className = 'hintmini ok';
    }
  });

  document.getElementById('manualAddBtn').addEventListener('click', addManualReagent);
}

// 查询失败时自动展开手动输入，并把刚输的内容带过去
function openManualSection(prefill) {
  const box = document.getElementById('manualBox');
  const tg = document.getElementById('manualToggle');
  if (!box) return;
  box.hidden = false;
  if (tg) tg.classList.add('open');
  const v = (prefill || '').trim();
  if (v) {
    const t = detectInputType(v);
    if (t.type === 'formula') {
      const fIn = document.getElementById('manFormula');
      if (fIn && !fIn.value.trim()) { fIn.value = v; fIn.dispatchEvent(new Event('input')); }
    } else if (t.type !== 'cas') {
      // CAS 号填进「名称」没意义，留给用户自己填
      const nIn = document.getElementById('manName');
      if (nIn && !nIn.value.trim()) nIn.value = v;
    }
  }
  setTimeout(() => {
    const el = document.getElementById('manMW').value.trim()
      ? document.getElementById('manName') : document.getElementById('manMW');
    if (el) el.focus();
  }, 30);
}

function addManualReagent() {
  const name = document.getElementById('manName').value.trim();
  const formulaRaw = document.getElementById('manFormula').value.trim();
  const mwRaw = document.getElementById('manMW').value.trim();
  const densRaw = document.getElementById('manDensity').value.trim();

  if (!name) { toast('请先填一个名称'); document.getElementById('manName').focus(); return; }
  const mw = parseFloat(mwRaw);
  if (!isFinite(mw) || mw <= 0) { toast('请填一个大于 0 的分子量'); document.getElementById('manMW').focus(); return; }

  let formula = null, exact = null;
  if (formulaRaw) {
    const norm = normalizeFormula(formulaRaw);
    if (norm) { formula = norm; exact = exactMassFromFormula(norm); }
  }
  let density = parseFloat(densRaw);
  if (!isFinite(density) || density <= 0) density = null;

  const r = normalizeReagent({
    zh: name,
    cas: null,
    formula: formula,
    mw: Math.round(mw * 1000) / 1000,
    exact: exact,
    density: density,
    type: density != null ? 'liquid' : 'solid',
    // 没有 CAS 就查不到 GHS 数据。给一个显式的 unknown，危险提醒区会原样显示这段话，
    // 而不是让这一行在危险提醒里"消失"（消失会被误读成"安全"）。
    hazard: {
      signal: null, h: [], pict: [], stat: null, baike: null, src: [],
      grade: 'unknown',
      note: '自定义化合物 —— 程序查不到它的危害数据，请查阅 SDS 或试剂瓶标签'
    },
    note: '自定义化合物（分子量为手工输入）'
  }, 'manual');

  closeAddModal();
  addReagentToList(r);
  toast('已添加自定义化合物：' + name);
}

/* ---------------- 物性弹层 ---------------- */
let propRowIndex = -1;

function openPropModal(i) {
  const row = state.rows[i];
  if (!row) return;
  propRowIndex = i;
  const g = row.reagent || {};
  document.getElementById('propTitle').textContent = rowName(row) + (g.cas ? '  ' + g.cas : '');
  document.getElementById('propType').value = row.type;
  document.getElementById('propDensity').value = (row.densityOverride != null ? row.densityOverride : (g.density != null ? g.density : ''));
  document.getElementById('propDensitySrc').textContent = g.densityRaw ? ('百科原文：' + g.densityRaw) : (g.density != null ? '' : '（未获取到密度，可手工输入）');
  document.getElementById('propConc').value = (row.concOverride != null ? row.concOverride : (row.conc != null ? row.conc : ''));
  document.getElementById('propMedium').value = row.medium || '';
  document.getElementById('propPurity').value = (row.purityOverride != null ? row.purityOverride : (g.purity != null ? g.purity : 100));
  document.getElementById('propMW').value = (row.mwOverride != null ? row.mwOverride : (g.mw != null ? g.mw : ''));
  document.getElementById('propMWNote').textContent = g.formula ? ('按分子式 ' + g.formula + ' 计算') : '';
  const cbox = document.getElementById('propDensityCands');
  cbox.hidden = true; cbox.innerHTML = '';
  const qbtn = document.getElementById('propDensityQuery');
  qbtn.disabled = !g.cid;
  qbtn.textContent = g.cid ? '查 PubChem 候选' : '（无 PubChem 记录）';
  syncPropFields();
  document.getElementById('propModal').classList.add('open');
}

/* 拉 PubChem 的密度原始值，列出候选让用户点选（PubChem 密度是多来源混杂文本，不能自动填死） */
async function queryDensityCandidates() {
  const row = state.rows[propRowIndex];
  const cid = row && row.reagent && row.reagent.cid;
  const box = document.getElementById('propDensityCands');
  const btn = document.getElementById('propDensityQuery');
  if (!cid) return;
  btn.disabled = true;
  box.hidden = false;
  box.innerHTML = '<div class="dens-loading">查询中…</div>';
  const list = await fetchDensityCandidates(cid);
  btn.disabled = false;
  if (!list.length) {
    box.innerHTML = '<div class="dens-loading">PubChem 未提供可用密度值，请手工填写或查 SDS。</div>';
    return;
  }
  box.innerHTML = '<div class="dens-h">PubChem 原始值（点一条填入）：</div>' +
    list.map((x, i) =>
      '<div class="dens-item" data-dens="' + i + '">' +
      '<b>' + x.v + '</b> g/cm³' +
      (x.temp ? '<span class="dt">' + esc(x.temp) + '</span>' : '<span class="dt">温度未标</span>') +
      '<span class="dr">' + esc(x.raw.slice(0, 90)) + '</span></div>'
    ).join('') +
    '<div class="dens-note">PubChem 的密度是多个数据库的原始文本汇总，同一物质常有多条不同来源的值，请按你手上试剂的实际条件选择。</div>';
  box.querySelectorAll('[data-dens]').forEach(el => {
    el.addEventListener('click', () => {
      const x = list[+el.dataset.dens];
      document.getElementById('propDensity').value = x.v;
      box.querySelectorAll('.dens-item').forEach(y => y.classList.remove('sel'));
      el.classList.add('sel');
    });
  });
}

function syncPropFields() {
  const t = document.getElementById('propType').value;
  document.getElementById('propDensityRow').hidden = (t !== 'liquid');
  document.getElementById('propConcRow').hidden = (t !== 'solution');
}

function confirmProp() {
  const row = state.rows[propRowIndex];
  if (!row) return;
  row.type = document.getElementById('propType').value;
  const d = parseFloat(document.getElementById('propDensity').value);
  row.densityOverride = isFinite(d) && d > 0 ? d : null;
  const c = parseFloat(document.getElementById('propConc').value);
  row.concOverride = isFinite(c) && c > 0 ? c : null;
  if (row.concOverride != null) row.conc = row.concOverride;
  row.medium = document.getElementById('propMedium').value.trim() || null;
  const p = parseFloat(document.getElementById('propPurity').value);
  row.purityOverride = isFinite(p) && p > 0 && p !== 100 ? p : null;
  const w = parseFloat(document.getElementById('propMW').value);
  const baseW = row.reagent && row.reagent.mw != null ? row.reagent.mw : null;
  row.mwOverride = (isFinite(w) && w > 0 && (baseW == null || Math.abs(w - baseW) > 1e-6)) ? w : null;
  document.getElementById('propModal').classList.remove('open');
  renderTable(); refresh();
}

/* ---------------- 缩放 ---------------- */
function doScale() {
  const n0 = refMmol(state);
  if (n0 == null) { toast('先确定当前规模', 'warn'); return; }
  const v = prompt('当前规模 ' + fmtMol(n0) + ' mmol。\n输入新的参考物摩尔数（mmol）：', n0.toFixed(2));
  if (v == null) return;
  const nv = parseFloat(v);
  if (!isFinite(nv) || nv <= 0) { toast('请输入正数', 'warn'); return; }
  if (scaleTo(state, nv)) { renderTable(); refresh(); toast('已缩放到 ' + fmtMol(nv) + ' mmol'); }
  else toast('缩放失败', 'warn');
}

/* ---------------- 导出 ---------------- */
function cjkWidth(s) {
  let w = 0;
  for (const ch of String(s)) w += /[\u2E80-\u9FFF\uFF00-\uFF60\u3000-\u303F]/.test(ch) ? 2 : 1;
  return w;
}
function pad(s, width) {
  s = String(s == null ? '' : s);
  const w = cjkWidth(s);
  if (w >= width) return s;
  return s + ' '.repeat(width - w);
}
function padL(s, width) {
  s = String(s == null ? '' : s);
  const w = cjkWidth(s);
  if (w >= width) return s;
  return ' '.repeat(width - w) + s;
}

function buildExportRows() {
  const out = [];
  const ref = state.rows[state.refIndex];
  for (const r of state.rows) {
    const g = r.reagent || {};
    const w = rowMW(r);
    const isSol = r.type === 'solution';
    const isRef = (r === ref);
    let qty = '';
    if (isSol) {
      qty = qv(r.volume) != null ? fmtVol(qv(r.volume)) : '';
    } else {
      const parts = [];
      if (qv(r.mass) != null) parts.push(fmtMass(qv(r.mass)));
      if (qv(r.volume) != null) parts.push('(' + fmtVol(qv(r.volume)) + ')');
      qty = parts.join(' ');
    }
    out.push({
      name: g.zh || g.en || g.cas || '?',
      cas: g.cas || '',
      mw: isSol ? ((r.conc != null ? r.conc + ' M' : '') + (r.medium ? ' ' + r.medium : '')) : (w != null ? w.toFixed(2) : ''),
      eq: isRef ? '1.00 (ref)' : (qv(r.equiv) != null ? fmtEquiv(qv(r.equiv)) + ' equiv' : ''),
      mmol: qv(r.mmol) != null ? fmtMol(qv(r.mmol)) : '',
      qty: qty,
      role: (ROLES.find(x => x[0] === r.role) || [, ''])[1]
    });
  }
  return out;
}

function buildMarkdown() {
  const rows = buildExportRows();
  const n0 = refMmol(state);
  let s = '';
  s += (state.runName || '投料单') + '    ' + (state.runDate || todayStr()) +
    (n0 != null ? ('    ' + fmtMol(n0) + ' mmol 规模') : '') + '\n';
  s += '='.repeat(72) + '\n\n';
  s += pad('试剂', 20) + pad('CAS', 14) + pad('M.W./浓度', 18) + pad('当量', 14) +
    pad('mmol', 10) + pad('用量', 18) + '\n';
  s += '-'.repeat(94) + '\n';
  for (const r of rows) {
    s += pad(r.name, 20) + pad(r.cas, 14) + pad(r.mw, 18) + pad(r.eq, 14) +
      pad(r.mmol, 10) + pad(r.qty, 18) + '\n';
  }
  if (state.solvent.volume != null) {
    s += '\n' + (state.solvent.name || '溶剂') + '（溶剂）：' + fmtVol(state.solvent.volume) + '\n';
  }
  return s;
}

function doExportMarkdown() {
  download('投料单_' + (state.runDate || todayStr()) + '.md', buildMarkdown(), 'text/markdown;charset=utf-8');
  toast('已导出 Markdown');
}

function buildCsv() {
  const rows = buildExportRows();
  const lines = [];
  lines.push(['试剂', 'CAS', 'MW或浓度', '当量', 'mmol', '用量', '角色'].join(','));
  for (const r of rows) {
    lines.push([r.name, r.cas, r.mw, r.eq, r.mmol, r.qty, r.role]
      .map(x => '"' + String(x == null ? '' : x).replace(/"/g, '""') + '"').join(','));
  }
  if (state.solvent.volume != null) {
    lines.push(['"' + (state.solvent.name || '溶剂') + '（溶剂）"', '', '', '', '', '"' + fmtVol(state.solvent.volume) + '"', '溶剂'].join(','));
  }
  return '\ufeff' + lines.join('\r\n');
}

function doExportCsv() {
  download('投料单_' + (state.runDate || todayStr()) + '.csv', buildCsv(), 'text/csv;charset=utf-8');
  toast('已导出 CSV');
}

function download(filename, content, mime) {
  const blob = new Blob([content], { type: mime || 'text/plain;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

/* ---------------- 词典管理 ---------------- */
function openDictModal() {
  const list = getPersonal();
  const body = document.getElementById('dictBody');
  let html = '<div class="dict-stat">内置词典 ' + (DICT.reagents || []).length + ' 条 ｜ 个人词典 ' + list.length + ' 条</div>';
  if (!list.length) {
    html += '<div class="empty">还没有个人词条。查询过的试剂会自动记到这里，下次离线也能查到。</div>';
  } else {
    html += '<table class="dict-table"><thead><tr><th>中文名</th><th>CAS</th><th>MW</th><th>来源</th><th></th></tr></thead><tbody>';
    html += list.map((r, i) => '<tr><td>' + esc(r.zh || '') + '</td><td>' + esc(r.cas || '') + '</td><td>' +
      (r.mw != null ? r.mw.toFixed(3) : '') + '</td><td>' + esc(r._src || '') + '</td>' +
      '<td><button class="delbtn" data-deldict="' + i + '">✕</button></td></tr>').join('');
    html += '</tbody></table>';
  }
  body.innerHTML = html;
  document.getElementById('dictModal').classList.add('open');
}

function doExportDict() {
  const data = { personal: getPersonal(), recent: getRecent(), exportedAt: new Date().toISOString() };
  download('投料计算器_个人词典.json', JSON.stringify(data, null, 2), 'application/json');
  toast('已导出');
}

function doImportDict() {
  const inp = document.createElement('input');
  inp.type = 'file';
  inp.accept = '.json,application/json';
  inp.onchange = () => {
    const f = inp.files && inp.files[0];
    if (!f) return;
    const fr = new FileReader();
    fr.onload = () => {
      try {
        const j = JSON.parse(fr.result);
        let added = 0;
        const cur = getPersonal();
        const keys = new Set(cur.map(r => r.cas || r.zh));
        for (const r of (j.personal || j.reagents || [])) {
          const k = r.cas || r.zh;
          if (k && !keys.has(k)) { cur.push(r); keys.add(k); added++; }
        }
        savePersonal(cur);
        toast('已导入 ' + added + ' 条');
        openDictModal();
      } catch (e) { toast('导入失败：文件格式不对', 'warn'); }
    };
    fr.readAsText(f, 'utf-8');
  };
  inp.click();
}

/* ---------------- 危险详情展开 ---------------- */
function renderSafetyDetails(d) {
  const sec = (title, body) => {
    if (!body || (Array.isArray(body) && !body.length)) {
      return '<div class="hz-sec"><div class="hz-sec-h">' + title + '</div>' +
        '<div class="hz-sec-b none">该条目不提供</div></div>';
    }
    const arr = Array.isArray(body) ? body : [body];
    const html = arr.filter(Boolean).map(x => '<div>' + esc(x) + '</div>').join('');
    return '<div class="hz-sec"><div class="hz-sec-h">' + title + '</div>' +
      '<div class="hz-sec-b">' + html + '</div></div>';
  };
  return '<div class="hz-detail-inner">' +
    sec('危害概述', d && d.summary) +
    sec('反应性与稳定性', d && d.reactivity) +
    sec('急救措施', d && d.firstAid) +
    sec('储存与操作', d && d.storage) +
    sec('灭火（UN ERG 摘录）', d && d.fire) +
    '<div class="hz-detail-note">以上为 PubChem 汇总的数据库原文（英文），仅供查阅，不构成操作建议。' +
    '原文往往比分类代码更具体，遇到不确定的说法请以 SDS 为准。</div>' +
    '</div>';
}

async function toggleHazardDetail(btn) {
  const idx = +btn.dataset.hzdetail;
  const row = state.rows[idx];
  const box = btn.nextElementSibling;
  if (!row || !box || !box.classList.contains('hz-detail-box')) return;
  const label = '▸ 展开更多安全信息（概述 / 急救 / 储存）';
  if (!box.hidden) {
    box.hidden = true;
    btn.textContent = label;
    return;
  }
  if (box.dataset.loaded === '1') {
    box.hidden = false;
    btn.textContent = '▴ 收起';
    return;
  }
  const cid = row.reagent && row.reagent.cid;
  if (!cid) {
    box.innerHTML = '<div class="hz-detail-inner"><div class="hz-sec"><div class="hz-sec-b none">' +
      '该试剂没有 PubChem 记录（CID 缺失），无法获取更多信息。</div></div></div>';
    box.hidden = false; box.dataset.loaded = '1'; btn.textContent = '▴ 收起';
    return;
  }
  btn.disabled = true;
  btn.textContent = '查询中…';
  try {
    const d = await fetchSafetyDetails(cid);
    box.innerHTML = renderSafetyDetails(d);
  } catch (e) {
    box.innerHTML = '<div class="hz-detail-inner"><div class="hz-sec"><div class="hz-sec-b none">' +
      '查询失败（' + esc(e.message || '网络错误') + '）。可稍后重试。</div></div></div>';
  }
  btn.disabled = false;
  box.hidden = false;
  box.dataset.loaded = '1';
  btn.textContent = '▴ 收起';
}

/* ---------------- 初始化 ---------------- */
function bindTopEvents() {
  document.getElementById('addRowBtn').addEventListener('click', () => openAddModal(''));
  document.getElementById('addLookupBtn').addEventListener('click', doAddLookup);
  document.getElementById('addInput').addEventListener('input', updateAddHint);
  document.getElementById('addInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); doAddLookup(); }
  });
  document.getElementById('addConfirmBtn').addEventListener('click', confirmAdd);
  document.getElementById('addCancelBtn').addEventListener('click', closeAddModal);
  document.getElementById('addModal').addEventListener('click', e => {
    if (e.target.id === 'addModal') closeAddModal();
  });
  bindManualSection();

  document.getElementById('propType').addEventListener('change', syncPropFields);
  document.getElementById('propDensityQuery').addEventListener('click', queryDensityCandidates);
  document.getElementById('propOk').addEventListener('click', confirmProp);
  document.getElementById('propCancel').addEventListener('click', () => {
    document.getElementById('propModal').classList.remove('open');
  });

  document.getElementById('dictBtn').addEventListener('click', openDictModal);
  document.getElementById('hazardZone').addEventListener('click', e => {
    const b = e.target.closest('[data-hzdetail]');
    if (b) toggleHazardDetail(b);
  });
  document.getElementById('dictClose').addEventListener('click', () => {
    document.getElementById('dictModal').classList.remove('open');
  });
  document.getElementById('dictExport').addEventListener('click', doExportDict);
  document.getElementById('dictImport').addEventListener('click', doImportDict);
  document.getElementById('dictBody').addEventListener('click', e => {
    const b = e.target.closest('[data-deldict]');
    if (!b) return;
    const i = +b.dataset.deldict;
    if (!confirm('从个人词典中删除这条？')) return;
    const list = getPersonal();
    list.splice(i, 1);
    savePersonal(list);
    openDictModal();
  });

  document.getElementById('scaleBtn').addEventListener('click', doScale);
  document.getElementById('exportMdBtn').addEventListener('click', doExportMarkdown);
  document.getElementById('exportCsvBtn').addEventListener('click', doExportCsv);
  document.getElementById('printBtn').addEventListener('click', () => window.print());
  document.getElementById('clearBtn').addEventListener('click', () => {
    if (!confirm('清空当前投料表？（个人词典和最近用过不受影响）')) return;
    state = defaultState();
    renderTable(); refresh();
  });

  ['runName', 'runDate'].forEach(id => {
    document.getElementById(id).addEventListener('input', e => {
      if (id === 'runName') state.runName = e.target.value;
      else state.runDate = e.target.value;
      saveState();
    });
  });
  document.getElementById('solventName').addEventListener('input', e => {
    state.solvent.name = e.target.value; saveState();
  });
  document.getElementById('solventVol').addEventListener('input', e => {
    const q = parseQuantity(e.target.value);
    state.solvent.volume = q ? (q.kind === 'vol' ? q.value : q.value) : null;
    saveState();
  });

  document.querySelectorAll('input[name="anchorMode"]').forEach(el => {
    el.addEventListener('change', () => {
      state.anchorMode = el.value;
      document.getElementById('refPanel').hidden = (state.anchorMode !== 'ref');
      document.getElementById('productPanel').hidden = (state.anchorMode !== 'product');
      refresh();
    });
  });
  ['prodMass', 'prodYield', 'prodMW'].forEach(id => {
    document.getElementById(id).addEventListener('input', e => {
      const v = parseFloat(e.target.value);
      const val = isFinite(v) ? v : null;
      if (id === 'prodMass') state.product.targetMass = val;
      else if (id === 'prodYield') state.product.yield = val;
      else state.product.mw = val;
      refresh();
    });
  });
}

function applyStateToInputs() {
  document.getElementById('runName').value = state.runName || '';
  document.getElementById('runDate').value = state.runDate || todayStr();
  document.getElementById('solventName').value = state.solvent.name || '';
  document.getElementById('solventVol').value = state.solvent.volume != null ? state.solvent.volume : '';
  document.querySelectorAll('input[name="anchorMode"]').forEach(el => {
    el.checked = (el.value === state.anchorMode);
  });
  document.getElementById('refPanel').hidden = (state.anchorMode !== 'ref');
  document.getElementById('productPanel').hidden = (state.anchorMode !== 'product');
  document.getElementById('prodMass').value = state.product.targetMass != null ? state.product.targetMass : '';
  document.getElementById('prodYield').value = state.product.yield != null ? state.product.yield : 100;
  document.getElementById('prodMW').value = state.product.mw != null ? state.product.mw : '';
}

function init() {
  DICT = window.__DICT__ || { reagents: [] };
  injectPictoCss();
  dictIndex = buildDictIndex(DICT);
  personalIndex = buildPersonalIndex(getPersonal());
  ctx = { dictIndex: dictIndex, personal: personalIndex };
  state = loadState();

  bindTopEvents();
  bindTableEvents();
  bindRecent();
  applyStateToInputs();
  renderTable();
  renderRecentMenu();
  refresh();

  const n = (DICT.reagents || []).length;
  const badge = document.getElementById('dictBadge');
  if (badge) badge.textContent = '内置词典 ' + n + ' 条';

  if (!state.rows.length) {
    document.getElementById('chargeBody').innerHTML =
      '<tr class="empty-row"><td colspan="10">点上面的「+ 添加试剂行」开始 —— 输入中文名或 CAS 号即可自动带出分子量</td></tr>';
  }
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
