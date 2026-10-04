/* ============================================================
   投料计算器 · 数据获取层
   三条通道（均已实测可用）：
     1) 百度百科开放 API —— JSONP，查中文名 → CAS / 密度 / R-S
     2) PubChem PUG-REST —— CORS，查 CAS / 英文名 → 分子式 + CID
     3) 本地词典 —— 离线优先
   ============================================================ */

/* ---------- 百度百科 JSONP ---------- */
function baikeJsonp(keyword, timeoutMs = 12000) {
  return new Promise((resolve, reject) => {
    const cbName = '__baike_cb_' + Math.random().toString(36).slice(2);
    const script = document.createElement('script');
    let settled = false;
    const timer = setTimeout(() => { if (!settled) { settled = true; cleanup(); reject(new Error('timeout')); } }, timeoutMs);
    function cleanup() {
      clearTimeout(timer);
      try { delete window[cbName]; } catch (e) { window[cbName] = undefined; }
      if (script.parentNode) script.parentNode.removeChild(script);
    }
    window[cbName] = function (data) {
      if (settled) return;
      settled = true; cleanup();
      resolve(data);
    };
    script.onerror = function () {
      if (settled) return;
      settled = true; cleanup();
      reject(new Error('neterr'));
    };
    script.src = 'https://baike.baidu.com/api/openapi/BaikeLemmaCardApi'
      + '?scope=103&format=json&appid=379020'
      + '&bk_key=' + encodeURIComponent(keyword)
      + '&bk_length=2000&callback=' + cbName;
    document.head.appendChild(script);
  });
}

function baikeCardValue(json, key) {
  if (!json || !Array.isArray(json.card)) return null;
  for (const c of json.card) {
    if (c && c.key === key) {
      const vals = Array.isArray(c.value) ? c.value : [c.value];
      return vals.filter(v => v != null).join(' ');
    }
  }
  return null;
}

/* 百科 → 结构化字段 */
function parseBaike(json) {
  if (!json || !json.key) return null;
  const raw = k => baikeCardValue(json, k);
  const formulaRaw = stripTags(raw('m38_chemicalFormula') || '');
  const formula = formulaRaw ? normalizeFormula(formulaRaw) : null;
  const densRaw = stripTags(raw('m38_density') || '');
  let density = null;
  if (densRaw) {
    const dm = densRaw.match(/(\d+\.?\d*)\s*g\s*\/\s*(?:cm³|cm3|mL|ml|立方厘米)/i)
      || densRaw.match(/(\d+\.?\d*)/);
    if (dm) {
      const v = parseFloat(dm[1]);
      if (isFinite(v) && v > 0 && v < 30) density = v;
    }
  }
  const aliasRaw = stripTags(raw('m38_othername') || '');
  const alias = aliasRaw
    ? aliasRaw.split(/[、；;，,\/|\s]+/).map(s => s.trim()).filter(s => s && s !== json.key)
    : [];
  const enRaw = stripTags(raw('m38_foreignName') || '');
  return {
    zh: json.key,
    en: enRaw || null,
    alias: [...new Set(alias)].slice(0, 12),
    cas: extractCas(raw('m38_CAS')),
    casRaw: stripTags(raw('m38_CAS') || '') || null,
    formula,
    density,
    densityRaw: densRaw || null,
    hazardBaike: parseBaikeHazard(
      raw('m38_hazardsymbols'), raw('m38_hazarddesc'), raw('m38_security'),
      raw('m38_hazardnum'), raw('m38_flashpoint')
    ),
    bp: stripTags(raw('m38_boilingpoint') || '') || null,
    mp: stripTags(raw('m38_meltingpoint') || '') || null
  };
}

/* ---------- PubChem ---------- */
async function pubchemLookup(term, timeoutMs = 15000) {
  const url = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/'
    + encodeURIComponent(term)
    + '/property/MolecularFormula,MolecularWeight/JSON';
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctl.signal });
    clearTimeout(timer);
    if (res.status === 404) return { ok: false, reason: 'notfound' };
    if (!res.ok) return { ok: false, reason: 'http' + res.status };
    const j = await res.json();
    const p = j && j.PropertyTable && j.PropertyTable.Properties && j.PropertyTable.Properties[0];
    if (!p) return { ok: false, reason: 'empty' };
    return {
      ok: true,
      cid: p.CID,
      formula: p.MolecularFormula ? normalizeFormula(p.MolecularFormula) : null,
      mwPubchem: p.MolecularWeight ? parseFloat(p.MolecularWeight) : null
    };
  } catch (e) {
    clearTimeout(timer);
    return { ok: false, reason: e && e.name === 'AbortError' ? 'timeout' : 'neterr' };
  }
}

/* ---------- 物态判断（PubChem Physical Description） ----------
   用于 CAS / 英文名直查时判断该按质量称取还是按体积量取 */
async function fetchPhysicalState(cid, timeoutMs = 15000) {
  if (!cid) return null;
  const url = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/' + cid +
    '/JSON?heading=' + encodeURIComponent('Physical Description');
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctl.signal });
    clearTimeout(timer);
    if (!res.ok) return null;
    const j = await res.json();
    const txt = [];
    (function walk(o) {
      if (!o) return;
      if (Array.isArray(o)) { for (const v of o) walk(v); return; }
      if (typeof o === 'object') {
        if (Array.isArray(o.StringWithMarkup))
          for (const s of o.StringWithMarkup) if (s && s.String) txt.push(s.String);
        for (const k in o) walk(o[k]);
      }
    })(j);
    const blob = txt.join(' ').toLowerCase();
    const lq = (blob.match(/liquid|oil|solution|syrup/g) || []).length;
    const sd = (blob.match(/solid|crystal|powder|platelet|prism|granul|flake/g) || []).length;
    const state = lq > sd ? 'liquid' : (sd > lq ? 'solid' : null);
    return { state, text: txt[0] || null };
  } catch (e) {
    clearTimeout(timer);
    return null;
  }
}

/* ---------- 本地词典索引 ---------- */
function normKey(s) {
  return String(s == null ? '' : s).toLowerCase().replace(/[\s\-_·・,，、.]/g, '');
}

function buildDictIndex(dict) {
  const idx = { byKey: new Map(), list: [] };
  const add = (k, rec, primary) => {
    const s = String(k == null ? '' : k).trim();
    if (!s) return;
    if (!primary) {
      if (/^\d+$/.test(s)) return;                       // "1" 这种被逗号切碎的残片
      if (s.length < 2 && !/[\u4e00-\u9fff]/.test(s)) return;
    }
    const nk = normKey(s);
    if (nk && !idx.byKey.has(nk)) idx.byKey.set(nk, rec);
  };
  for (const r of (dict.reagents || [])) {
    const rec = Object.assign({}, r);
    rec._src = 'dict';
    idx.list.push(rec);
    add(r.zh, rec, true);
    add(r.cas, rec, true);
    // en 里常带缩写或别名，如 "Dichloromethane（DCM）"、"n-Hexane;Hexyl hydride"
    const enParts = [];
    if (r.en) {
      enParts.push(String(r.en).replace(/[（(][^）)]*[）)]/g, ' '));
      const inParen = String(r.en).match(/[（(]([^）)]+)[）)]/g) || [];
      inParen.forEach(x => enParts.push(x.replace(/[（()）]/g, '')));
      String(r.en).split(/[;；,，、\/]+/).forEach(x => enParts.push(x));
    }
    enParts.forEach(x => add(x, rec));
    (r.alias || []).forEach(x => add(x, rec));
    (r.abbr || []).forEach(x => add(x, rec));
  }
  return idx;
}

/* ---------- 统一入口：把任意输入变成完整试剂对象 ---------- */
async function resolveReagent(rawInput, ctx, onProgress) {
  const say = m => { if (onProgress) onProgress(m); };
  const input = String(rawInput || '').trim();
  if (!input) throw new Error('输入为空');

  const t = detectInputType(input);
  const { dictIndex, personal } = ctx;

  // 0) 本地词典 / 个人词典
  const nk = normKey(input);
  const local = (personal && personal.byKey.get(nk)) || dictIndex.byKey.get(nk);
  if (local) {
    say('命中本地词典');
    const out = normalizeReagent(local, 'dict');
    // 有分子式就用本地算法重算分子量，覆盖词典里的值
    // （词典生成时个别元素缺原子量、或走了百科兜底，本地重算能保证一致且更准）
    if (out.formula) {
      const w = mwFromFormula(out.formula);
      if (w) { out.mw = w; out.exact = exactMassFromFormula(out.formula); }
    }
    // 词典里已经带 GHS 数据的直接用；缺危害数据才联网补，且超时给短一点
    const needHz = !out.hazard || out.hazard.grade === 'unknown';
    if (needHz && (out.cid || out.cas)) {
      say('补查危害数据…');
      try {
        if (!out.cid && out.cas) {
          const pc = await pubchemLookup(out.cas, 8000);
          if (pc.ok) {
            out.cid = pc.cid;
            if (!out.formula && pc.formula) {
              out.formula = pc.formula;
              out.mw = mwFromFormula(pc.formula) || out.mw;
              out.exact = exactMassFromFormula(pc.formula);
            }
          }
        }
        if (out.cid) {
          const g2 = await Promise.all([fetchGhsFromPubChem(out.cid, 10000), fetchReactivityAlerts(out.cid)]);
          const g = g2[0];
          if (g2[1]) out.reactTags = g2[1];
          if (g.ok) {
            out.hazard = buildHazard({ ghs: g.data, baike: (out.hazard && out.hazard.baike) || null, cid: out.cid });
          }
        }
      } catch (e) { /* 离线时静默失败，词典数据照用 */ }
      if (!out.hazard) out.hazard = buildHazard({ ghs: null, baike: null, cid: out.cid });
    }
    return out;
  }

  // 1) 分子式直接算，无需联网
  if (t.type === 'formula') {
    say('识别为分子式，本地计算');
    const mw = mwFromFormula(t.formula);
    const ex = exactMassFromFormula(t.formula);
    if (!mw) throw new Error('分子式无法解析：' + input);
    return normalizeReagent({
      zh: t.formula, formula: t.formula, mw, exact: ex,
      hazard: { grade: 'unknown', note: '分子式输入，无 CAS，未查询危害数据', h: [], pict: [] }
    }, 'formula');
  }

  // 2) 联网查询
  let cas = null, cid = null, formula = null, mwPub = null;
  let zh = null, en = null, alias = [], density = null, densityRaw = null;
  let baikeHazard = null, bp = null, casRawSeen = null;
  let netFailed = false;   // 用来区分"没查到"和"网断了"，好给出更准的提示

  if (t.type === 'zh') {
    say('查询百度百科…');
    let bj = null;
    try { bj = await baikeJsonp(input); } catch (e) { say('百科查询失败：' + e.message); netFailed = true; }
    if (bj && bj.key) {
      const p = parseBaike(bj);
      if (p) {
        zh = p.zh; en = p.en; alias = p.alias;
        cas = p.cas; casRawSeen = p.casRaw;
        formula = p.formula; density = p.density; densityRaw = p.densityRaw;
        baikeHazard = p.hazardBaike; bp = p.bp;
        say(cas ? ('百科 → CAS ' + cas) : (p.casRaw ? ('百科 CAS 校验未通过：' + p.casRaw) : '百科无 CAS 字段'));
      }
    } else {
      say('百科未收录该词条');
    }
  }

  // 用 CAS 或原名去 PubChem
  const stem = cas || (t.type === 'cas' ? input : (en || input));
  if (stem) {
    say('查询 PubChem…');
    const pc = await pubchemLookup(stem);
    if (pc.ok) {
      cid = pc.cid;
      if (pc.formula) formula = pc.formula;
      mwPub = pc.mwPubchem;
      say('PubChem 命中 CID ' + cid + (pc.formula ? '（' + pc.formula + '）' : ''));
    } else {
      say('PubChem 未命中（' + pc.reason + '）');
      if (pc.reason === 'neterr' || pc.reason === 'timeout') netFailed = true;
    }
  }

  if (t.type === 'cas') cas = extractCas(input) || input;
  if (!cas && t.type === 'cas' && !casValid(input)) {
    throw new Error('CAS 校验位不通过：' + input + '（请检查是否输错）');
  }

  // 分子量：本地算优先
  let mw = null, exact = null;
  if (formula) {
    mw = mwFromFormula(formula);
    exact = exactMassFromFormula(formula);
  }
  if (mw == null && mwPub != null) mw = mwPub;

  if (mw == null && !cas) {
    throw new Error(netFailed
      ? '本地词典里没有这个词条，且当前网络不可用（离线）。可以：①直接输入该试剂的 CAS 号 —— 试剂瓶上一定印着；②连上网络后再查一次。'
      : '未能解析出该试剂（未获得 CAS 或分子式）。请直接输入 CAS 号。');
  }

  // 3) 危害数据 + 物态 + 反应性标签（三个请求并发，省时间）
  let hazard = null, phys = null, reactTags = null;
  if (cid) {
    say('查询 GHS 危害数据…');
    const trip = await Promise.all([
      fetchGhsFromPubChem(cid),
      fetchPhysicalState(cid),
      fetchReactivityAlerts(cid)
    ]);
    const g = trip[0];
    phys = trip[1];
    reactTags = trip[2];
    if (g.ok) {
      hazard = buildHazard({ ghs: g.data, baike: baikeHazard, cid });
      say('GHS：' + (hazard.signal || '—') + ' / ' + hazard.h.length + ' 条危害代码');
    } else {
      hazard = buildHazard({ ghs: null, baike: baikeHazard, cid });
      hazard.note = g.reason === 'nodata'
        ? '未获取到 GHS 分类数据（该物质在 PubChem 无 GHS 条目）— 请查阅 SDS 或试剂瓶标签'
        : 'GHS 数据查询失败（' + g.reason + '）— 请查阅 SDS 或试剂瓶标签';
    }
  } else {
    hazard = buildHazard({ ghs: null, baike: baikeHazard, cid: null });
  }

  // 物态：手工清单最可靠 → PubChem 物性描述 → 默认固体
  const zhName = zh || (t.type === 'cas' ? null : input);
  let stype = guessState(zhName, density);
  if (zhName && KNOWN_LIQUID_ZH.has(zhName)) stype = 'liquid';
  else if (phys && phys.state) stype = phys.state;

  const rec = {
    zh: zh || (t.type === 'cas' ? (cas || input) : input),
    en, alias, abbr: [],
    cas, formula, cid,
    mw, exact, mwPubchem: mwPub,
    density, densityRaw, bp,
    purity: 100,
    type: stype,
    conc: null, medium: null,
    hazard, baikeHazard,
    physText: phys ? phys.text : null,
    reactTags: reactTags,
    _src: 'net'
  };
  return normalizeReagent(rec, 'net');
}

/* 猜测物态（仅作默认值，用户可在"密度/浓度"里改） */
function guessState(zh, density) {
  if (zh && KNOWN_LIQUID_ZH.has(zh)) return 'liquid';
  return 'solid';
}

/* 兼容两种 hazard 结构：
   内置词典里是 h: [[code, pct], ...]；运行期统一成 h: [{code, pct}, ...] */
function coerceHazard(h) {
  if (!h) return null;
  if (Array.isArray(h.h) && h.h.length && h.h[0] && typeof h.h[0] === 'object' && !Array.isArray(h.h[0])) {
    if (!h.grade) h.grade = gradeHazard(h);
    if (!h.h) h.h = [];
    return h;
  }
  const out = {
    signal: h.signal || null,
    h: (h.h || []).map(x => Array.isArray(x)
      ? { code: String(x[0]), pct: (x[1] == null || x[1] === '') ? null : parseFloat(x[1]) }
      : { code: String(x.code), pct: (x.pct == null) ? null : parseFloat(x.pct) }),
    pict: h.pict || [],
    stat: h.stat || null,
    baike: h.baike || null,
    note: h.note || '',
    src: h.src || ['PubChem / ECHA C&L Inventory']
  };
  out.grade = gradeHazard(out);
  return out;
}

/* 归一化试剂对象，补齐字段、绑定溶液预置 */
function normalizeReagent(r, src) {
  const out = {
    id: r.id || ('r_' + (r.cas || r.zh || Math.random().toString(36).slice(2))),
    zh: r.zh || null,
    en: r.en || null,
    alias: r.alias || [],
    abbr: r.abbr || [],
    cas: r.cas || null,
    formula: r.formula || null,
    cid: r.cid || null,
    mw: r.mw != null ? r.mw : null,
    exact: r.exact != null ? r.exact : null,
    mwPubchem: r.mwPubchem != null ? r.mwPubchem : null,
    density: r.density != null ? r.density : null,
    densityRaw: r.densityRaw || null,
    densityCandidates: r.densityCandidates || [],
    purity: r.purity != null ? r.purity : 100,
    type: r.type || guessState(r.zh, r.density),
    conc: r.conc != null ? r.conc : null,
    medium: r.medium || null,
    bp: r.bp || null,
    physText: r.physText || null,
    reactTags: r.reactTags || null,
    hazard: coerceHazard(r.hazard),
    baikeHazard: r.baikeHazard || (r.hazard && r.hazard.baike) || null,
    note: r.note || '',
    _src: src || r._src || 'manual',
    lastUsedAt: r.lastUsedAt || Date.now()
  };
  // 溶液预置：同 CAS 的商品化标准溶液
  if (out.cas && (!out.conc)) {
    const hit = SOLUTION_PRESETS.filter(p => p.cas === out.cas);
    if (hit.length) {
      out.solutionPresets = hit;
      if (out.type === 'solution') { out.conc = hit[0].conc; out.medium = hit[0].medium; }
    }
  }
  return out;
}

/* ---------- 个人词典 ---------- */
function buildPersonalIndex(list) {
  const idx = { byKey: new Map(), list: list || [] };
  for (const r of idx.list) {
    const rec = Object.assign({}, r, { _src: 'personal' });
    [r.zh, r.cas, r.en, ...(r.alias || []), ...(r.abbr || [])].forEach(k => {
      const nk = normKey(k);
      if (nk && !idx.byKey.has(nk)) idx.byKey.set(nk, rec);
    });
  }
  return idx;
}
