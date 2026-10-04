/* ============================================================
   投料计算器 · 计算引擎
   纯函数为主：分子式解析、分子量、CAS 校验、单位换算、约束传播求解
   ============================================================ */

/* ---------- 分子式解析（支持嵌套括号，如 Ca(OH)2） ---------- */
function parseFormula(str) {
  if (!str) return null;
  let s = String(str).replace(/\s+/g, '');
  // 只保留开头连续的标准分子式片段，遇到中文/备注即停止
  const m = s.match(/^([A-Z][a-z]?\d*|\(|\)\d*)+/);
  if (!m) return null;
  s = m[0];
  let i = 0;
  let bad = false;

  function parseGroup() {
    const out = {};
    while (i < s.length) {
      const c = s[i];
      if (c === '(') {
        i++;
        const inner = parseGroup();
        if (s[i] !== ')') { bad = true; return out; }
        i++;
        let mult = '';
        while (i < s.length && /\d/.test(s[i])) mult += s[i++];
        const k = mult ? parseInt(mult, 10) : 1;
        for (const el in inner) out[el] = (out[el] || 0) + inner[el] * k;
      } else if (c === ')') {
        return out;
      } else if (/[A-Z]/.test(c)) {
        let el = c; i++;
        while (i < s.length && /[a-z]/.test(s[i])) el += s[i++];
        let num = '';
        while (i < s.length && /\d/.test(s[i])) num += s[i++];
        const k = num ? parseInt(num, 10) : 1;
        if (!ATOMIC_WEIGHT[el]) { bad = true; i = s.length; return out; }
        out[el] = (out[el] || 0) + k;
      } else {
        bad = true; i++; return out;
      }
    }
    return out;
  }

  const counts = parseGroup();
  if (bad || !counts || Object.keys(counts).length === 0) return null;
  return counts;
}

/* 分子量（平均原子量） */
function mwFromFormula(str) {
  const c = parseFormula(str);
  if (!c) return null;
  let w = 0;
  for (const el in c) w += ATOMIC_WEIGHT[el] * c[el];
  return w;
}

/* 精确质量（单同位素） */
function exactMassFromFormula(str) {
  const c = parseFormula(str);
  if (!c) return null;
  let w = 0;
  for (const el in c) w += (MONO_MASS[el] || ATOMIC_WEIGHT[el]) * c[el];
  return w;
}

/* 分子式的 Hill 排序规范化（C 优先，H 次之，其余按字母） */
function normalizeFormula(str) {
  const c = parseFormula(str);
  if (!c) return str;
  const els = Object.keys(c);
  const order = [];
  if (c.C) order.push('C');
  if (c.H) order.push('H');
  els.filter(e => e !== 'C' && e !== 'H').sort().forEach(e => order.push(e));
  return order.map(e => e + (c[e] > 1 ? c[e] : '')).join('');
}

/* ---------- CAS 号校验（从右往左 ×1,×2,×3… 求和 mod 10） ---------- */
function casValid(cas) {
  if (!cas) return false;
  const d = String(cas).replace(/-/g, '');
  if (!/^\d{5,10}$/.test(d)) return false;
  const body = d.slice(0, -1);
  const chk = parseInt(d.slice(-1), 10);
  let sum = 0;
  for (let i = 0; i < body.length; i++) {
    sum += parseInt(body[body.length - 1 - i], 10) * (i + 1);
  }
  return sum % 10 === chk;
}

/* 从脏字符串里宽松提取 CAS（不做任何"后面不能跟数字"的负向前瞻） */
const CAS_LOOSE = /(\d{2,7}-\d{2}-\d)/g;
function stripTags(s) {
  return String(s == null ? '' : s)
    .replace(/<sup>.*?<\/sup>/gis, '')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .trim();
}
function extractCas(raw) {
  if (!raw) return null;
  const s = stripTags(raw);
  const cands = s.match(CAS_LOOSE) || [];
  for (const c of cands) if (casValid(c)) return c;
  return null;
}

/* ---------- 输入类型识别 ---------- */
function detectInputType(raw) {
  const s = String(raw || '').trim();
  if (!s) return { type: 'empty' };
  if (/^\d{2,7}-\d{2}-\d$/.test(s)) {
    return { type: 'cas', cas: s, valid: casValid(s) };
  }
  if (/[\u4e00-\u9fff]/.test(s)) return { type: 'zh' };
  if (/^([A-Z][a-z]?\d*|\(|\)\d*)+$/.test(s) && /[A-Z]/.test(s) && parseFormula(s)) {
    return { type: 'formula', formula: normalizeFormula(s) };
  }
  return { type: 'en' };
}

/* ---------- 数量字符串解析（宽容） ---------- */
const UNIT_FACTOR = {
  // 质量 → g
  g: 1, gram: 1, grams: 1, '克': 1,
  mg: 1e-3, '毫克': 1e-3,
  ug: 1e-6, 'µg': 1e-6, 'μg': 1e-6, '微克': 1e-6,
  kg: 1000, '千克': 1000,
  // 体积 → mL
  l: 1000, 'L': 1000, '升': 1000,
  ml: 1, mL: 1, '毫升': 1,
  ul: 1e-3, 'µL': 1e-3, 'μL': 1e-3, 'uL': 1e-3, '微升': 1e-3,
  // 摩尔 → mmol
  mol: 1000, '摩尔': 1000,
  mmol: 1, '毫摩尔': 1,
  umol: 1e-3, 'µmol': 1e-3, 'μmol': 1e-3, '微摩尔': 1e-3
};

/* 返回 {kind:'mass'|'vol'|'mol', value:<g|mL|mmol>} */
function parseQuantity(str) {
  if (str == null) return null;
  const s = String(str).trim().replace(/，/g, ',').replace(/\s+/g, ' ');
  if (!s) return null;
  const m = s.match(/^(-?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Zµμ\u4e00-\u9fff]*)$/);
  if (!m) return null;
  const v = parseFloat(m[1]);
  if (!isFinite(v)) return null;
  let u = m[2] || '';
  if (!u) return { kind: 'bare', value: v };
  const f = UNIT_FACTOR[u] !== undefined ? UNIT_FACTOR[u] : UNIT_FACTOR[u.toLowerCase()];
  if (f === undefined) return { kind: 'bare', value: v };
  if (['g','gram','grams','克','mg','毫克','ug','µg','μg','微克','kg','千克'].includes(u) ||
      ['g','gram','grams','mg','ug','kg'].includes(u.toLowerCase())) {
    return { kind: 'mass', value: v * f, unit: u };
  }
  if (['l','L','升','ml','mL','毫升','ul','µL','μL','uL','微升'].includes(u)) {
    return { kind: 'vol', value: v * f, unit: u };
  }
  return { kind: 'mol', value: v * f, unit: u };
}

/* ---------- 格式化（按 100 mmol 尺度） ---------- */
function fmtMass(g) {
  if (g == null || !isFinite(g)) return '';
  if (g === 0) return '0';
  const a = Math.abs(g);
  if (a < 1e-3) return (g * 1e6).toFixed(1) + ' µg';
  if (a < 1) return (g * 1e3).toFixed(1) + ' mg';
  if (a < 1000) return g.toFixed(g < 10 ? 3 : 3) + ' g';
  return (g / 1000).toFixed(3) + ' kg';
}
function fmtVol(mL) {
  if (mL == null || !isFinite(mL)) return '';
  if (mL === 0) return '0';
  const a = Math.abs(mL);
  if (a < 1e-3) return (mL * 1e6).toFixed(1) + ' nL';
  if (a < 1) return (mL * 1e3).toFixed(1) + ' µL';
  if (a < 1000) return mL.toFixed(2) + ' mL';
  return (mL / 1000).toFixed(3) + ' L';
}
function fmtMol(mmol) {
  if (mmol == null || !isFinite(mmol)) return '';
  const a = Math.abs(mmol);
  if (a === 0) return '0';
  if (a < 0.01) return (mmol * 1000).toFixed(2) + ' µmol';
  if (a < 1) return mmol.toFixed(3);
  if (a < 100) return mmol.toFixed(2);
  return mmol.toFixed(1);
}
function fmtEquiv(e) {
  if (e == null || !isFinite(e)) return '';
  if (e === 0) return '0';
  if (e < 0.01) return e.toFixed(4);
  if (e < 1) return e.toFixed(3);
  return e.toFixed(2);
}
function fmtMW(w) {
  if (w == null || !isFinite(w)) return '';
  return w.toFixed(3);
}

/* ---------- 行内取值辅助 ---------- */
const qv = o => (o && typeof o.v === 'number' && isFinite(o.v)) ? o.v : null;
function setCell(cell, v, src) {
  if (v == null || !isFinite(v)) return false;
  if (qv(cell) === v && cell.src === src) return false;
  cell.v = v; cell.src = src;
  return true;
}
function clearSys(row) {
  for (const k of ['equiv', 'mmol', 'mass', 'volume']) {
    if (row[k].src === 'sys' || row[k].src === 'ref') { row[k].v = null; row[k].src = null; }
  }
}

/* ---------- 行的物性 ---------- */
function rowMW(row) {
  if (row.mwOverride != null && isFinite(row.mwOverride)) return row.mwOverride;
  const r = row.reagent;
  return r && r.mw != null ? r.mw : null;
}
function rowPurity(row) {
  const p = row.purityOverride != null ? row.purityOverride : (row.reagent && row.reagent.purity);
  const v = (p == null || !isFinite(p) || p <= 0) ? 100 : p;
  return v / 100;
}
function rowDensity(row) {
  if (row.densityOverride != null && isFinite(row.densityOverride)) return row.densityOverride;
  const r = row.reagent;
  return r && r.density != null ? r.density : null;
}
/* 摩尔浓度 (mol/L)：溶液用浓度；纯液体用 d*1000/MW；固体返回 null */
function rowConc(row) {
  const t = row.type;
  if (t === 'solution') {
    const c = row.concOverride != null && isFinite(row.concOverride) ? row.concOverride : row.conc;
    return (c != null && isFinite(c) && c > 0) ? c : null;
  }
  if (t === 'liquid') {
    const d = rowDensity(row), w = rowMW(row);
    if (d && w) return d * 1000 / w;
  }
  return null;
}

/* ---------- 参考物摩尔数 ---------- */
function refMmol(state) {
  const rows = state.rows;
  const ref = rows[state.refIndex];
  if (!ref) return null;

  // 产物反算模式优先
  if (state.anchorMode === 'product' && state.product && state.product.mw && state.product.targetMass) {
    const y = (state.product.yield == null || !isFinite(state.product.yield) || state.product.yield <= 0)
      ? 100 : state.product.yield;
    return state.product.targetMass / state.product.mw * 1000 / (y / 100);
  }

  const n = qv(ref.mmol);
  if (n != null) return n;
  const m = qv(ref.mass);
  const w = rowMW(ref);
  if (m != null && w) return m * rowPurity(ref) * 1000 / w;
  const v = qv(ref.volume);
  if (v != null) {
    if (ref.type === 'solution') {
      const c = rowConc(ref);
      if (c) return v * c;
    } else if (ref.type === 'liquid') {
      const d = rowDensity(ref);
      // 纯液体按体积投料时要算纯度：实际有效物 = 体积 × 密度 × 含量
      if (d && w) return v * d * rowPurity(ref) * 1000 / w;
    }
  }

  // 回退：参考物自己没有绝对量时，从其它已知行反推 n_ref = n_i / e_i
  for (const r of rows) {
    if (r === ref) continue;
    const ni = qv(r.mmol), ei = qv(r.equiv);
    if (ni != null && ei != null && ei > 0) return ni / ei;
  }
  return null;
}

/* ---------- 主求解：约束传播 ---------- */
function solve(state) {
  const rows = state.rows;
  if (!rows.length) return [];
  if (state.refIndex < 0 || state.refIndex >= rows.length) state.refIndex = 0;
  const ref = rows[state.refIndex];
  const warnings = [];

  // 1) 清掉上一轮系统推算的值（用户输入保留）
  rows.forEach(clearSys);
  ref.equiv = { v: 1, src: ref.equiv.src === 'user' ? 'user' : 'ref' };

  // 2) 迭代传播
  const MAX = 16;
  for (let pass = 0; pass < MAX; pass++) {
    let changed = false;
    const nRef = refMmol(state);

    for (const r of rows) {
      const w = rowMW(r);
      const pur = rowPurity(r);

      // (a) mmol <-> mass（mass 是实际称量质量，含纯度折算）
      if (qv(r.mmol) == null && qv(r.mass) != null && w) {
        if (setCell(r.mmol, qv(r.mass) * pur * 1000 / w, 'sys')) changed = true;
      }
      if (qv(r.mass) == null && qv(r.mmol) != null && w) {
        if (setCell(r.mass, qv(r.mmol) * w / 1000 / pur, 'sys')) changed = true;
      }

      // (b) 体积
      // 溶液：体积由浓度换算（标称浓度已含一切，不再乘纯度）
      // 纯液体：体积 = 称量质量 ÷ 密度
      //   ★ 必须用含纯度折算的"称量质量"。若从 mmol 直接算，含量 95% 时体积会偏小 5%
      //     （实测踩过：50 mmol 苯甲醛 95% 含量算成 5.054 mL，正确应为 5.319 mL）
      if (r.type === 'solution') {
        const c = rowConc(r);
        if (c) {
          if (qv(r.volume) == null && qv(r.mmol) != null) {
            if (setCell(r.volume, qv(r.mmol) / c, 'sys')) changed = true;
          }
          if (qv(r.mmol) == null && qv(r.volume) != null) {
            if (setCell(r.mmol, qv(r.volume) * c, 'sys')) changed = true;
          }
        }
      } else if (r.type === 'liquid') {
        const d = rowDensity(r);
        if (d) {
          if (qv(r.volume) == null && qv(r.mass) != null) {
            if (setCell(r.volume, qv(r.mass) / d, 'sys')) changed = true;
          }
          if (qv(r.mass) == null && qv(r.volume) != null) {
            if (setCell(r.mass, qv(r.volume) * d, 'sys')) changed = true;
          }
        }
      }

      // (c) equiv <-> mmol
      const nR = refMmol(state);
      if (r === ref) {
        if (state.anchorMode === 'product') {
          // 产物反算模式下，参考物的绝对量完全由「产物量 ÷ 收率」决定。
          // 此时用户之前填的参考物质量/摩尔数不再作为锚点，否则会与产物量自相矛盾
          // （实测踩过：切到产物模式后参考物仍显示旧值，而其余行已按产物重算）。
          if (r.mass.src === 'user') { r.mass = { v: null, src: null }; changed = true; }
          if (r.volume.src === 'user') { r.volume = { v: null, src: null }; changed = true; }
          if (nR != null && qv(r.mmol) !== nR) { setCell(r.mmol, nR, 'sys'); changed = true; }
        } else if (nR != null && qv(r.mmol) == null) {
          // 由其它行反推出的 n_ref 回填到参考物行
          if (setCell(r.mmol, nR, 'sys')) changed = true;
        }
      } else if (nR != null && nR > 0) {
        if (qv(r.equiv) == null && qv(r.mmol) != null) {
          if (setCell(r.equiv, qv(r.mmol) / nR, 'sys')) changed = true;
        }
        if (qv(r.mmol) == null && qv(r.equiv) != null) {
          if (setCell(r.mmol, qv(r.equiv) * nR, 'sys')) changed = true;
        }
      }
      // 参考物：用质量/体积反推 mmol 已由 (a)(b) 处理
    }
    if (!changed) break;
  }

  // 3) 校验
  const nRef = refMmol(state);
  if (nRef == null) {
    warnings.push({ level: 'block', msg: '缺少绝对量：请给出参考物的摩尔数 / 质量 / 体积，或填写目标产物量与产率。' });
  }
  for (const r of rows) {
    const nm = r.reagent ? (r.reagent.zh || r.reagent.cas || '未知试剂') : '未知试剂';
    if (qv(r.mmol) == null && qv(r.mass) == null && qv(r.volume) == null) {
      if (!(r === ref && nRef != null)) {
        warnings.push({ level: 'warn', msg: `${nm}：信息不足，无法求解（需要当量或一个绝对量）。` });
      }
    }
    if (r.type === 'liquid' && qv(r.volume) == null && rowDensity(r) == null && qv(r.mass) != null) {
      warnings.push({ level: 'warn', msg: `${nm}：缺少密度，无法换算体积。请补密度或按质量称取。` });
    }
    if (r.type === 'solution' && rowConc(r) == null) {
      warnings.push({ level: 'warn', msg: `${nm}：溶液试剂缺少浓度，无法换算体积。` });
    }
  }
  return warnings;
}

/* ---------- 冲突检测：用户输入 vs 系统推算 ---------- */
function detectConflicts(state) {
  const rows = state.rows;
  const out = [];
  const nRef = refMmol(state);
  if (nRef == null) return out;
  for (const r of rows) {
    const w = rowMW(r);
    const pur = rowPurity(r);
    const nm = r.reagent ? (r.reagent.zh || r.reagent.cas) : '未知试剂';
    // 用户同时给了 mass 和 equiv → 检查一致性
    if (qv(r.mass) != null && w && r !== state.rows[state.refIndex]) {
      const needMass = qv(r.equiv) != null ? qv(r.equiv) * nRef * w / 1000 / pur
        : (qv(r.mmol) != null ? qv(r.mmol) * w / 1000 / pur : null);
      if (needMass != null && needMass > 0) {
        const diff = Math.abs(qv(r.mass) - needMass) / needMass;
        if (diff > 0.005) {
          out.push({
            row: r, field: 'mass',
            msg: `${nm}：按当量推算质量应为 ${fmtMass(needMass)}，但填的是 ${fmtMass(qv(r.mass))}（相差 ${(diff * 100).toFixed(1)}%）`
          });
        }
      }
    }
  }
  return out;
}

/* ---------- 缩放 ---------- */
function scaleTo(state, newRefMmol) {
  const rows = state.rows;
  const n0 = refMmol(state);
  if (n0 == null || n0 <= 0) return false;
  const k = newRefMmol / n0;
  const ref = rows[state.refIndex];
  for (const r of rows) {
    const m = qv(r.mmol);
    if (m != null && r !== ref) {
      r.mmol = { v: m * k, src: r.mmol.src === 'user' ? 'user' : 'sys' };
      if (qv(r.mass) != null) r.mass = { v: null, src: null };
      if (qv(r.volume) != null) r.volume = { v: null, src: null };
    }
  }
  if (qv(ref.mmol) != null) ref.mmol = { v: qv(ref.mmol) * k, src: ref.mmol.src };
  else if (qv(ref.mass) != null) ref.mass = { v: qv(ref.mass) * k, src: ref.mass.src };
  else if (qv(ref.volume) != null) ref.volume = { v: qv(ref.volume) * k, src: ref.volume.src };
  return true;
}
