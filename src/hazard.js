/* ============================================================
   投料计算器 · 危险数据处理
   原则：只引用数据源原文与标准短语，不自创任何操作建议。
         无数据 ≠ 安全 —— 查不到必须显式提示，绝不显示为安全。
   ============================================================ */

const H_CODE_RE = /\b(H\d{3}|EUH\d{3})\b/g;
const H_WITH_PCT = /\b(H\d{3}|EUH\d{3})\s*\((\d+(?:\.\d+)?)\s*%\)/g;
const PICTO_RE = /GHS(\d{2})\.svg/i;

/* ---------- 解析 PubChem PUG-View 的 GHS Classification 响应 ----------
   同一试剂通常有多个来源块（ECHA C&L / NITE / 其它），需要合并：
   - 各 H 代码取最高通报比例
   - 信号词取最严重（Danger > Warning）                                          */
function parseGhsResponse(json) {
  const texts = [];
  const picUrls = [];
  (function walk(o) {
    if (!o) return;
    if (Array.isArray(o)) { for (const v of o) walk(v); return; }
    if (typeof o === 'object') {
      if (Array.isArray(o.StringWithMarkup)) {
        for (const s of o.StringWithMarkup) {
          if (!s) continue;
          if (typeof s.String === 'string') texts.push(s.String);
          // 象形图 URL 藏在 StringWithMarkup[].Markup[].URL 里
          if (Array.isArray(s.Markup)) {
            for (const mk of s.Markup) {
              if (mk && typeof mk.URL === 'string') picUrls.push(mk.URL);
            }
          }
        }
      }
      if (typeof o.URL === 'string') picUrls.push(o.URL);
      for (const k in o) walk(o[k]);
    }
  })(json);

  const blob = texts.join('\n');
  const signal = (/\bDanger\b/.test(blob) || texts.some(t => t.trim() === 'Danger'))
    ? 'Danger'
    : (/\bWarning\b/.test(blob) || texts.some(t => t.trim() === 'Warning') ? 'Warning' : null);

  const hmap = new Map();
  let m;
  H_WITH_PCT.lastIndex = 0;
  while ((m = H_WITH_PCT.exec(blob)) !== null) {
    const code = m[1], pct = parseFloat(m[2]);
    const prev = hmap.get(code);
    if (prev == null || (prev.pct == null) || pct > prev.pct) hmap.set(code, { code, pct });
  }
  H_CODE_RE.lastIndex = 0;
  while ((m = H_CODE_RE.exec(blob)) !== null) {
    const code = m[1];
    if (!hmap.has(code)) hmap.set(code, { code, pct: null });
  }

  const pict = new Set();
  for (const u of picUrls) {
    const pm = PICTO_RE.exec(u);
    if (pm) pict.add('GHS' + pm[1]);
  }

  // 提取 ECHA 通报统计（来自 Note 文本）
  let stat = null;
  const sm = blob.match(/Aggregated GHS information provided per (\d+)\s*reports? by companies from (\d+)/);
  if (sm) stat = { reports: +sm[1], notifications: +sm[2] };

  return {
    signal,
    h: [...hmap.values()],
    pict: [...pict].sort(),
    stat
  };
}

/* ---------- 解析百科的危险字段（旧 R/S 体系，作兜底） ---------- */
function parseBaikeHazard(symbols, rStr, sStr, unStr, flash) {
  const out = { symbols: [], r: [], s: [], un: null, flash: null, raw: {} };
  const cleanSym = stripTags(symbols || '');
  if (cleanSym) {
    out.raw.symbols = cleanSym;
    // "F；C" 或 "F2" / "Xn" → 取字母部分（去掉尾部引用数字）
    const parts = cleanSym.split(/[；;、,，\/\s]+/).filter(Boolean);
    for (const p of parts) {
      const mm = p.match(/^(T\+|F\+|T|F|C|Xn|Xi|O|E|N)/);
      if (mm && !out.symbols.includes(mm[1])) out.symbols.push(mm[1]);
    }
  }
  const cleanR = stripTags(rStr || '');
  if (cleanR) {
    out.raw.r = cleanR;
    const codes = cleanR.match(/R\s?\d{1,2}(?:\/\d{1,2})*/g) || [];
    for (let c of codes) {
      c = c.replace(/\s/g, '');
      if (!out.r.includes(c) && R_CN[c]) out.r.push(c);
    }
  }
  const cleanS = stripTags(sStr || '');
  if (cleanS) {
    out.raw.s = cleanS;
    const codes = cleanS.match(/S\s?\d{1,2}(?:\/\d{1,2})*/g) || [];
    for (let c of codes) {
      c = c.replace(/\s/g, '');
      if (!out.s.includes(c) && S_CN[c]) out.s.push(c);
    }
  }
  const cleanU = stripTags(unStr || '');
  const um = cleanU.match(/(\d{4})/);
  if (um) out.un = um[1];
  const cleanF = stripTags(flash || '');
  if (cleanF) {
    const fm = cleanF.match(/(-?\d+(?:\.\d+)?)\s*℃/);
    out.flash = fm ? fm[1] + ' ℃' : cleanF;
    out.raw.flash = cleanF;
  }
  return out;
}

/* ---------- 危险分级：判定对象是"试剂" ---------- */
function gradeHazard(hz) {
  if (!hz) return 'unknown';
  const high = (hz.h || []).filter(x => H_HIGH.has(x.code) || H_CRITICAL_EXTRA.has(x.code));
  if (high.length) return 'high';
  const med = (hz.h || []).filter(x => H_MEDIUM.has(x.code));
  if (med.length) return 'medium';
  const hasAny = (hz.h && hz.h.length) || (hz.baike && (hz.baike.symbols.length || hz.baike.r.length));
  if (hasAny) return 'low';
  return 'unknown';
}

/* H 代码排序：高危优先，但"无通报比例"的降半级
   —— 单个来源提到的条目不该排在 ECHA 共识条目前面 */
function sortHCodes(h) {
  const rank = x => {
    let r = (H_HIGH.has(x.code) || H_CRITICAL_EXTRA.has(x.code)) ? 0 : 1;
    if (x.pct == null) r += 0.5;
    return r;
  };
  return (h || []).slice().sort((a, b) => {
    const ra = rank(a), rb = rank(b);
    if (ra !== rb) return ra - rb;
    const pa = a.pct == null ? -1 : a.pct;
    const pb = b.pct == null ? -1 : b.pct;
    if (pa !== pb) return pb - pa;
    return a.code.localeCompare(b.code);
  });
}

function hText(code) {
  return H_CN[code] || '';
}

/* ---------- 网络：拉取 PubChem GHS ---------- */
async function fetchGhsFromPubChem(cid, timeoutMs = 20000) {
  if (!cid) return { ok: false, reason: 'nocid' };
  const url = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/' + cid +
    '/JSON?heading=' + encodeURIComponent('GHS Classification');
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctl.signal });
    clearTimeout(timer);
    if (res.status === 404) return { ok: false, reason: 'nodata' };
    if (!res.ok) return { ok: false, reason: 'http' + res.status };
    const json = await res.json();
    return { ok: true, data: parseGhsResponse(json) };
  } catch (e) {
    clearTimeout(timer);
    return { ok: false, reason: e && e.name === 'AbortError' ? 'timeout' : 'neterr' };
  }
}

/* 反应性标签：从 PubChem 的 Reactivity Alerts 里挑出结构化标签
   （原始内容混着 CSL 事故案例编号与长句，需要筛） */
async function fetchReactivityAlerts(cid) {
  const t = await fetchPugViewHeading(cid, 'Reactivity Alerts');
  if (!t) return null;
  const tags = [];
  for (const s of t) {
    const x = String(s).trim();
    if (!x || x.length > 60) continue;
    if (REACTIVITY_TAG_RE.test(x) && !tags.includes(x)) tags.push(x);
  }
  return tags.length ? tags : null;
}

/* 淬灭提示：来自内置的通行做法表（按 CAS）。取不到就不显示，绝不临时编。 */
function quenchTip(cas) {
  if (!cas) return null;
  return QUENCH_TIPS[cas] || null;
}

/* ---------- PubChem PUG-View 通用取文本 ---------- */
function pugViewTexts(json) {
  const out = [];
  (function walk(o) {
    if (!o) return;
    if (Array.isArray(o)) { for (const v of o) walk(v); return; }
    if (typeof o === 'object') {
      if (Array.isArray(o.StringWithMarkup)) {
        for (const s of o.StringWithMarkup) if (s && typeof s.String === 'string') out.push(s.String);
      }
      for (const k in o) walk(o[k]);
    }
  })(json);
  return out.filter(t => t && t.trim());
}

/* 取某个 heading 的全部文本；不存在时 PubChem 返回 404，这里返回 null */
async function fetchPugViewHeading(cid, heading, timeoutMs = 15000) {
  if (!cid) return null;
  const url = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/' + cid +
    '/JSON?heading=' + encodeURIComponent(heading);
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctl.signal });
    clearTimeout(timer);
    if (!res.ok) return null;
    const t = pugViewTexts(await res.json());
    return t.length ? t : null;
  } catch (e) {
    clearTimeout(timer);
    return null;
  }
}

/* 一句话危害概述（点"详情"时用） */
async function fetchHazardsSummary(cid, timeoutMs = 15000) {
  const t = await fetchPugViewHeading(cid, 'Hazards Summary', timeoutMs);
  return t ? t.join(' ').slice(0, 900) : null;
}

/* 安全详情：并发取，省时间 */
async function fetchSafetyDetails(cid) {
  if (!cid) return null;
  const [sum, aid, store, fire, react] = await Promise.all([
    fetchPugViewHeading(cid, 'Hazards Summary'),
    fetchPugViewHeading(cid, 'First Aid Measures'),
    fetchPugViewHeading(cid, 'Handling and Storage'),
    fetchPugViewHeading(cid, 'Fire Fighting'),
    fetchPugViewHeading(cid, 'Stability and Reactivity')
  ]);
  return {
    summary: sum ? sum.join(' ').slice(0, 1200) : null,
    firstAid: aid || null,
    storage: store || null,
    fire: fire || null,
    reactivity: react || null
  };
}

/* 密度候选（PubChem PUG-View 原始文本，供人工确认） */
async function fetchDensityCandidates(cid) {
  const t = await fetchPugViewHeading(cid, 'Density');
  if (!t) return [];
  const out = [];
  const seen = new Set();
  for (const raw of t) {
    const line = { raw: raw.replace(/\s+/g, ' ').trim(), v: null, temp: null };
    let m;
    // 1) 直接带单位的："1.3255 20 °C/4 °C"、"0.7893 g/cm³(20 ℃)"
    m = raw.match(/(\d+\.?\d*)\s*(?:g\/(?:cu )?cm|g\/mL|g\/cm³)\s*(?:at|@)?\s*(\d{1,3})?\s*(?:°|deg)?\s*([CF])?/i);
    if (m) {
      line.v = parseFloat(m[1]);
      if (m[2]) line.temp = m[2] + ' °' + (m[3] || 'C').toUpperCase();
    }
    // 2) "1.046 at 68 °F" / "1.050 at 15 °C"（不带单位，只有 at + 温度）
    if (line.v == null) {
      m = raw.match(/(\d+\.\d+)\s*(?:at|@)\s*(\d{1,3})\s*(?:°|deg)?\s*([CF])/i);
      if (m) { line.v = parseFloat(m[1]); line.temp = m[2] + ' °' + m[3].toUpperCase(); }
    }
    // 3) 范围值 "1.040-1.047" → 取中值
    if (line.v == null) {
      m = raw.match(/(\d+\.\d+)\s*[-–~]\s*(\d+\.\d+)/);
      if (m) line.v = (parseFloat(m[1]) + parseFloat(m[2])) / 2;
    }
    // 4) 相对密度写法："Relative density (water = 1): 1.05"
    if (line.v == null) {
      m = raw.match(/(?:relative\s+density|density)[^\d]{0,24}(\d+\.\d{1,4})/i);
      if (m) line.v = parseFloat(m[1]);
    }
    if (line.v == null || !(line.v > 0.05 && line.v < 25)) continue;
    const key = line.v + '|' + line.temp;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(line);
  }
  // 20–25 °C 的排前面
  out.sort((a, b) => {
    const ta = a.temp && /°C/.test(a.temp) ? Math.abs(parseInt(a.temp) - 22) : 99;
    const tb = b.temp && /°C/.test(b.temp) ? Math.abs(parseInt(b.temp) - 22) : 99;
    return ta - tb;
  });
  return out.slice(0, 8);
}

/* ---------- 汇编成统一 hazard 对象 ---------- */
function buildHazard({ ghs, baike, cid, cas }) {
  const hz = {
    signal: null, h: [], pict: [], stat: null,
    baike: baike || null, src: [], fetchedAt: Date.now(), note: ''
  };
  if (ghs && (ghs.h.length || ghs.signal)) {
    hz.signal = ghs.signal;
    hz.h = sortHCodes(ghs.h);
    hz.pict = ghs.pict || [];
    hz.stat = ghs.stat || null;
    hz.src.push('PubChem / ECHA C&L Inventory');
  }
  if (baike && (baike.symbols.length || baike.r.length || baike.s.length)) {
    hz.src.push('百度百科');
  }
  if (!hz.h.length && !hz.signal) {
    hz.note = baike && (baike.symbols.length || baike.r.length)
      ? '未获取到 GHS 分类数据（PubChem 无此物质条目），以下为百度百科的 R/S 体系数据'
      : '未获取到危害分类数据 — 请查阅 SDS 或试剂瓶标签';
  }
  hz.grade = gradeHazard(hz);
  return hz;
}
