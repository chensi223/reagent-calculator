# -*- coding: utf-8 -*-
"""投料计算器 · 重算一致性校验套件

核心是 invariants()：**每一步操作之后**都按化学定义把整张表重新验一遍 ——
    非参考物： mmol == 当量 x nRef
    所有行：   质量 == mmol x MW / 1000 / 纯度
    溶液：     体积 == mmol / C
    液体：     体积 == 质量 / 密度
    参考物：   当量恒为 1
（用户自己同时填了多个量属于"用户自相冲突"，由程序的冲突提示负责，这里跳过。）

覆盖 5 组：
    R  数据来回换算（同一个量换个入口填，结果应当一致）
    S  切换参考物（绝对量守恒、来回切换后能否完全复原）
    P  单点改动的传播范围（改谁、谁跟着动）
    B  边界与单位混输（mg / mol% / 极小量 / 极大值）
    F  随机操作序列（200 步 + 4 组种子，每步都验不变量）

用法：
    python build/verify_recalc.py
"""
import os, subprocess, sys, re, pathlib, tempfile, shutil
sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/microsoft-edge", "/usr/bin/google-chrome", "/usr/bin/chromium",
] if os.path.exists(p)), None)
if not EDGE:
    sys.exit("没找到 Edge 或 Chrome，无法运行")

TEST = r'''
<pre id="out">RUNNING</pre>
<script>
/* ================= 工具 ================= */
function mk(name, mw, d) {
  return normalizeReagent({ zh: name, mw: mw, density: d, cas: null, _src: 'manual',
    hazard: { grade: 'unknown', h: [], pict: [], signal: null, note: '' } }, 'manual');
}
function setup() {
  state.rows = []; state.refIndex = 0; state.anchorMode = 'ref';
  state.product = { mw: null, targetMass: null, yield: 100 };
  addReagentToList(mk('苯甲醛', 106.124, 1.04));
  addReagentToList(mk('丙二酸二乙酯', 160.169, 1.06));
  addReagentToList(mk('正丁基锂', 64.056, null));
  var r0 = state.rows[0], r1 = state.rows[1], r2 = state.rows[2];
  r0.type = 'solid'; r1.type = 'liquid'; r2.type = 'solution'; r2.concOverride = 2.5;
  applyCellInput(r0, 'mmol', '100');
  applyCellInput(r1, 'equiv', '1.2');
  applyCellInput(r2, 'equiv', '1.1');
  renderTable(); refresh();
}
function set(i, field, val) {
  applyCellInput(state.rows[i], field, (val == null ? '' : String(val)));
  renderTable(); refresh();
}
function setProp(i, k, v) { state.rows[i][k] = v; renderTable(); refresh(); }
function pickRef(i) {
  var el = document.querySelector('tr[data-row="' + i + '"] input[data-field="__ref"]');
  el.checked = true;
  el.dispatchEvent(new Event('change', { bubbles: true }));
}
function V(i, f) { return qv(state.rows[i][f]); }

/* ================= 不变量：按化学定义重新验证整张表 ================= */
var REL = 3e-6;
function close(a, b) { return Math.abs(a - b) <= Math.max(1e-7, Math.abs(b) * REL); }

function invariants() {
  var errs = [];
  var ref = state.rows[state.refIndex];
  var nRef = refMmol(state);
  if (nRef == null || !(nRef > 0)) { errs.push('nRef 无效: ' + nRef); return errs; }
  state.rows.forEach(function (r, i) {
    var nm = '#' + (i + 1) + (r.reagent && r.reagent.zh ? r.reagent.zh : '');
    var w = rowMW(r), pur = rowPurity(r);
    var mm = qv(r.mmol), eq = qv(r.equiv), m = qv(r.mass), v = qv(r.volume);

    // 用户自己给了两个以上的量（比如同时填了 mmol 和 质量）属于用户自相冲突，
    // 程序会用冲突提示提醒他，这不属于「求解器算错」，所以这里整体跳过这一行。
    var absUser = 0;
    ['mmol', 'mass', 'volume'].forEach(function (f) { if (r[f] && r[f].src === 'user') absUser++; });
    var eqUser = r.equiv && r.equiv.src === 'user';
    var conflict = absUser >= 2 || (eqUser && absUser >= 1);

    if (r === ref) {
      if (eq != null && !close(eq, 1)) errs.push(nm + ' 参考物当量应恒为 1，实际 ' + eq);
    } else if (!conflict) {
      if (eq != null && mm != null && !close(mm, eq * nRef))
        errs.push(nm + ' mmol≠当量×nRef: ' + mm.toFixed(5) + ' vs ' + (eq * nRef).toFixed(5));
    }
    if (conflict) return;
    if (mm != null && m != null && w && !close(m, mm * w / 1000 / pur))
      errs.push(nm + ' 质量≠mmol×MW/1000÷纯度: ' + m.toFixed(5) + ' vs ' + (mm * w / 1000 / pur).toFixed(5));
    if (r.type === 'solution') {
      var c = rowConc(r);
      if (c && mm != null && v != null && !close(v, mm / c))
        errs.push(nm + ' 溶液体积≠mmol÷C: ' + v.toFixed(5) + ' vs ' + (mm / c).toFixed(5));
    } else if (r.type === 'liquid') {
      var d = rowDensity(r);
      if (d && m != null && v != null && !close(v, m / d))
        errs.push(nm + ' 液体体积≠质量÷密度: ' + v.toFixed(5) + ' vs ' + (m / d).toFixed(5));
    }
  });
  return errs;
}

var P = 0, F = 0, log = [];
function ok(name, cond, extra) {
  if (cond) P++; else F++;
  log.push((cond ? 'PASS  ' : 'FAIL  ') + name + (extra ? '   [' + extra + ']' : ''));
}
function inv(tag) {
  var e = invariants();
  ok(tag + ' · 全表自洽', e.length === 0, e.slice(0, 2).join(' ｜ '));
}
function sec(t) { log.push(''); log.push('──── ' + t + ' ────'); }

/* ================================================================= */
window.addEventListener('load', function () { setTimeout(function () {
  try {
    /* ---------- R：数据来回换算，能不能原路返回 ---------- */
    sec('R 系列 · 来回换算（同一个量换个入口填，结果应当一致）');

    setup();
    var A = V(0, 'mass');
    set(0, 'mmol', null);
    set(0, 'mass', A);
    ok('R1 固体：mmol→质量→再反推回 mmol', close(V(0, 'mmol'), 100), '得 ' + V(0, 'mmol'));
    inv('R1');

    setup();
    var V1 = V(1, 'volume');
    set(1, 'mmol', null);
    set(1, 'volume', V1);
    ok('R2 液体：mmol→体积→再反推回 mmol', close(V(1, 'mmol'), 120), '得 ' + V(1, 'mmol'));
    inv('R2');

    setup();
    var V2 = V(2, 'volume');
    set(2, 'mmol', null);
    set(2, 'volume', V2);
    ok('R3 溶液：mmol→体积→再反推回 mmol', close(V(2, 'mmol'), 110), '得 ' + V(2, 'mmol'));
    inv('R3');

    setup();
    var V3 = V(1, 'volume');
    set(1, 'mass', null);
    set(1, 'volume', V3);
    ok('R4 液体：质量↔体积 来回', close(V(1, 'mass'), 120 * 160.169 / 1000), '得 ' + V(1, 'mass'));
    inv('R4');

    setup();
    setProp(0, 'purityOverride', 95);
    ok('R5 纯度改 95% → 称量质量 ÷0.95', close(V(0, 'mass'), 100 * 106.124 / 1000 / 0.95), '得 ' + V(0, 'mass'));
    setProp(0, 'purityOverride', 70);
    ok('R5 纯度改 70% → 再折算一次', close(V(0, 'mass'), 100 * 106.124 / 1000 / 0.70), '得 ' + V(0, 'mass'));
    setProp(0, 'purityOverride', 100);
    ok('R5 纯度改回 100% → 复原', close(V(0, 'mass'), 100 * 106.124 / 1000));
    inv('R5');

    setup();
    var vBefore = V(2, 'volume');
    setProp(2, 'concOverride', 1.25);          // 浓度减半
    ok('R6 浓度 2.5→1.25，体积翻倍', close(V(2, 'volume'), vBefore * 2), '得 ' + V(2, 'volume'));
    setProp(2, 'concOverride', 2.5);
    ok('R6 浓度改回 2.5，体积复原', close(V(2, 'volume'), vBefore));
    inv('R6');

    /* ---------- S：切换参考物之后的连锁重算 ---------- */
    sec('S 系列 · 切换参考物（绝对量守恒 + 全表重算）');

    setup();
    pickRef(1);
    ok('S1 新参考物当量恒为 1', close(V(1, 'equiv'), 1), String(V(1, 'equiv')));
    ok('S1 新参考物绝对量守恒（120 mmol）', close(V(1, 'mmol'), 120), '得 ' + V(1, 'mmol'));
    ok('S1 旧参考物绝对量守恒（100 mmol）', close(V(0, 'mmol'), 100), '得 ' + V(0, 'mmol'));
    ok('S1 旧参考物当量重算为 100/120', close(V(0, 'equiv'), 100 / 120), '得 ' + V(0, 'equiv'));
    ok('S1 第三行当量保持用户填的 1.1', close(V(2, 'equiv'), 1.1), '得 ' + V(2, 'equiv'));
    ok('S1 第三行绝对量随新锚点变（1.1×120=132）', close(V(2, 'mmol'), 132), '得 ' + V(2, 'mmol'));
    inv('S1');

    pickRef(0);   // ★ 切回原参考物，整张表应当完全复原
    ok('S2 切回后 行1 当量=1、绝对量=100', close(V(0, 'equiv'), 1) && close(V(0, 'mmol'), 100));
    ok('S2 切回后 行2 当量恢复 1.2', close(V(1, 'equiv'), 1.2), String(V(1, 'equiv')));
    ok('S2 切回后 行2 绝对量恢复 120', close(V(1, 'mmol'), 120), String(V(1, 'mmol')));
    ok('S2 切回后 行3 当量恢复 1.1', close(V(2, 'equiv'), 1.1), String(V(2, 'equiv')));
    ok('S2 切回后 行3 绝对量恢复 110', close(V(2, 'mmol'), 110), String(V(2, 'mmol')));
    inv('S2');

    setup(); pickRef(1); pickRef(2); pickRef(0);   // 三连切之后也要完全复原
    ok('S3 三连切后 行2 当量 1.2 ｜ 绝对量 120',
       close(V(1, 'equiv'), 1.2) && close(V(1, 'mmol'), 120), V(1, 'equiv') + ' ｜ ' + V(1, 'mmol'));
    ok('S3 三连切后 行3 当量 1.1 ｜ 绝对量 110',
       close(V(2, 'equiv'), 1.1) && close(V(2, 'mmol'), 110), V(2, 'equiv') + ' ｜ ' + V(2, 'mmol'));
    ok('S3 三连切后 行1 仍是最初的参考物', close(V(0, 'equiv'), 1) && close(V(0, 'mmol'), 100));
    inv('S3');

    setup(); pickRef(1); set(1, 'mass', '10');
    var n1 = V(1, 'mmol');
    ok('S4 切参考物后改它的质量 → mmol 重算', close(n1, 10 * 1000 / 160.169), '得 ' + n1);
    ok('S4 行1 当量随新锚点重算', close(V(0, 'equiv'), 100 / n1), '得 ' + V(0, 'equiv'));
    ok('S4 行3 当量保持 1.1（用户填的）', close(V(2, 'equiv'), 1.1), String(V(2, 'equiv')));
    ok('S4 行3 绝对量按新锚点 1.1×n1', close(V(2, 'mmol'), 1.1 * n1), String(V(2, 'mmol')));
    ok('S4 行1 体积与质量自洽', close(V(1, 'volume'), 10 / 1.06), '得 ' + V(1, 'volume'));
    inv('S4');

    setup(); pickRef(1); set(0, 'mmol', null); set(0, 'mass', '5');
    ok('S5 切参考物后改旧参考物的质量 → 它自己重算', close(V(0, 'mmol'), 5 * 1000 / 106.124), '得 ' + V(0, 'mmol'));
    ok('S5 新参考物不受影响（120）', close(V(1, 'mmol'), 120));
    ok('S5 行3 按自己的当量算 1.1×120', close(V(2, 'mmol'), 132), '得 ' + V(2, 'mmol'));
    inv('S5');

    setup(); pickRef(2); set(2, 'volume', '44');
    ok('S6 切参考物后按体积给绝对量 → mmol=110', close(V(2, 'mmol'), 44 * 2.5), '得 ' + V(2, 'mmol'));
    inv('S6');

    setup();
    for (var k = 0; k < 6; k++) { pickRef(k % 3); }
    inv('S7 连续切换 6 次后');

    /* ---------- P：改一处，别处怎么动 ---------- */
    sec('P 系列 · 单点改动的传播范围');

    setup(); set(0, 'mmol', '50');
    ok('P1 参考物 100→50，行2 mmol 120→60', close(V(1, 'mmol'), 60), '得 ' + V(1, 'mmol'));
    ok('P1 行3 mmol 110→55', close(V(2, 'mmol'), 55));
    ok('P1 行2 当量仍为 1.2', close(V(1, 'equiv'), 1.2));
    inv('P1');

    setup(); set(1, 'equiv', '2.0');
    ok('P2 改行2 当量 → 它自己 mmol=200', close(V(1, 'mmol'), 200));
    ok('P2 参考物不变（100）', close(V(0, 'mmol'), 100));
    ok('P2 行3 不变（110）', close(V(2, 'mmol'), 110));
    inv('P2');

    setup(); set(1, 'equiv', null); set(1, 'mass', '8');
    var want1 = 8 * 1000 / 160.169;
    ok('P3 清空当量后给质量 → mmol 按质量算', close(V(1, 'mmol'), want1), '得 ' + V(1, 'mmol'));
    ok('P3 当量反推为 mmol/100', close(V(1, 'equiv'), want1 / 100), '得 ' + V(1, 'equiv'));
    ok('P3 参考物不受影响', close(V(0, 'mmol'), 100));
    inv('P3');

    setup(); set(1, 'mass', '8');
    ok('P4 同时有当量和质量 → 报冲突而不是静默改数',
       document.getElementById('warnZone').textContent.indexOf('相差') >= 0,
       document.getElementById('warnZone').textContent.slice(0, 60));

    setup(); set(2, 'volume', '200');
    ok('P5 给溶液体积 200 mL → mmol=500', close(V(2, 'mmol'), 500), '得 ' + V(2, 'mmol'));
    ok('P5 参考物不受影响', close(V(0, 'mmol'), 100));
    inv('P5');

    /* ---------- B：边界与单位混输 ---------- */
    sec('B 系列 · 边界与单位混输');

    setup(); set(0, 'mass', '10612 mg');
    ok('B1 10612 mg 与 10.612 g 等价', close(V(0, 'mass'), 10.612), '得 ' + V(0, 'mass'));
    ok('B1 反推 mmol 仍为 100', close(V(0, 'mmol'), 100));

    setup(); set(1, 'equiv', '10 mol%');
    ok('B2 10 mol% = 0.1 当量', close(V(1, 'equiv'), 0.1));
    ok('B2 mmol = 10', close(V(1, 'mmol'), 10));
    set(1, 'equiv', '0.1');
    ok('B2 写 0.1 与 10 mol% 等价', close(V(1, 'mmol'), 10));

    setup(); set(1, 'equiv', null);
    ok('B3 清空当量后该行无解（mmol 为空）', V(1, 'mmol') == null, 'mmol=' + V(1, 'mmol'));
    inv('B3');

    setup(); set(0, 'mmol', '0.0001');
    ok('B4 极小量不崩', isFinite(V(0, 'mass')) && V(0, 'mass') > 0, '质量 ' + V(0, 'mass'));
    inv('B4');

    setup(); set(0, 'mmol', '100000');
    ok('B5 极大值（100 mol）能算', isFinite(V(1, 'mass')) && V(1, 'mass') > 0, '质量 ' + V(1, 'mass'));
    inv('B5');

    setup(); pickRef(1); set(1, 'mmol', null); set(1, 'volume', '50');
    ok('B6 给液体参考物体积 → 反推 mmol', close(V(1, 'mmol'), 50 * 1.06 * 1000 / 160.169), '得 ' + V(1, 'mmol'));
    inv('B6');

    /* ---------- F：随机操作序列 ---------- */
    sec('F 系列 · 随机操作（200 步，每步都查一遍不变量）');

    function stateLine() {
      return state.rows.map(function (r, k) {
        function c(f) { var x = r[f]; return (x && typeof x.v === 'number') ? x.v.toFixed(3) + '(' + (x.src || '-') + ')' : '—'; }
        return '#' + (k + 1) + '[mmol ' + c('mmol') + ' mass ' + c('mass') + ' eq ' + c('equiv') + ']';
      }).join('  ');
    }
    function fuzz(steps, wantTrace) {
      setup();
      var bad = [], trace = [], seed = 12345;
      function rnd() { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; }
      var FIELDS = ['mmol', 'equiv', 'mass', 'volume'];
      for (var i = 0; i < steps; i++) {
        var kind = Math.floor(rnd() * 10);
        var ri = Math.floor(rnd() * 3);
        var desc;
        if (kind < 3)      { var f = FIELDS[Math.floor(rnd() * 4)]; var v = (rnd() * 40 + 0.1).toFixed(3); desc = 'set(' + ri + ',' + f + ',' + v + ')'; set(ri, f, v); }
        else if (kind < 5) { desc = 'pickRef(' + ri + ')'; pickRef(ri); }
        else if (kind < 7) { var v2 = (rnd() * 3).toFixed(2); desc = 'set(' + ri + ',equiv,' + v2 + ')'; set(ri, 'equiv', v2); }
        else               { var v3 = (rnd() * 20 + 0.1).toFixed(3); desc = 'set(' + ri + ',mass,' + v3 + ')'; set(ri, 'mass', v3); }
        var e = invariants();
        if (e.length) bad.push('第' + (i + 1) + '步 ' + desc + ' → ' + e[0]);
        if (wantTrace && i < 6) trace.push('   ' + (i + 1) + '. ' + desc + '   ref=' + state.refIndex + '   ' + stateLine());
        if (bad.length >= 2) break;
      }
      return { bad: bad, trace: trace };
    }
    var fz = fuzz(200, true);
    ok('F1 随机 200 步后全表仍自洽', fz.bad.length === 0, fz.bad.slice(0, 2).join(' ｜ '));
    if (fz.bad.length) { log.push('   —— 复现轨迹（前 6 步）——'); fz.trace.forEach(function (x) { log.push(x); }); }

    function fuzzSeed(s) {
      setup();
      var bad = [], trace = [], seed = s;
      function rnd() { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; }
      var FIELDS = ['mmol', 'equiv', 'mass', 'volume'];
      for (var i = 0; i < 150; i++) {
        var kind = Math.floor(rnd() * 10), ri = Math.floor(rnd() * 3);
        var desc;
        if (kind < 3)      { var f = FIELDS[Math.floor(rnd() * 4)]; var v = (rnd() * 40 + 0.1).toFixed(3); desc = 'set(' + ri + ',' + f + ',' + v + ')'; set(ri, f, v); }
        else if (kind < 5) { desc = 'pickRef(' + ri + ')'; pickRef(ri); }
        else if (kind < 7) { var v2 = (rnd() * 3).toFixed(2); desc = 'set(' + ri + ',equiv,' + v2 + ')'; set(ri, 'equiv', v2); }
        else               { var v3 = (rnd() * 20 + 0.1).toFixed(3); desc = 'set(' + ri + ',mass,' + v3 + ')'; set(ri, 'mass', v3); }
        trace.push('   ' + (i + 1) + '. ' + desc + '   ref=' + state.refIndex + '   ' + stateLine());
        var e = invariants();
        if (e.length) { bad.push('第' + (i + 1) + '步 ' + desc + ' → ' + e[0]); break; }
      }
      return { bad: bad, trace: trace.slice(-8) };
    }
    var badSeeds = [], traceAll = [];
    [777, 2026, 31337, 987654].forEach(function (s) {
      var b = fuzzSeed(s);
      if (b.bad.length) {
        badSeeds.push('seed' + s + ' → ' + b.bad[0]);
        traceAll.push('  ── seed' + s + ' 最后 8 步 ──');
        b.trace.forEach(function (x) { traceAll.push(x); });
      }
    });
    ok('F2 另外 4 组随机种子都自洽', badSeeds.length === 0, badSeeds.slice(0, 2).join(' ｜ '));
    traceAll.forEach(function (x) { log.push(x); });

  } catch (e) {
    F++; log.push('FAIL  脚本异常: ' + e.message + '\n       ' + (e.stack || '').split('\n')[1]);
  }
  log.push('');
  log.push('======== 通过 ' + P + ' / 失败 ' + F + ' ========');
  document.getElementById('out').textContent = log.join('\n');
}, 500); });
</script>
'''

work = pathlib.Path(tempfile.mkdtemp(prefix="t2_"))
try:
    h = (ROOT / "dist" / "投料计算器.html").read_text(encoding="utf-8")
    tp = work / "_t.html"
    tp.write_text(h.replace("</body>", TEST + "</body>"), encoding="utf-8")
    prof = work / "p"; prof.mkdir()
    r = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-first-run",
                        "--no-default-browser-check", "--user-data-dir=" + str(prof),
                        "--virtual-time-budget=20000", "--dump-dom", tp.as_uri()],
                       capture_output=True, timeout=300)
    dom = r.stdout.decode("utf-8", "replace")
    m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
    print((m.group(1) if m else "(没拿到输出)").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))
finally:
    shutil.rmtree(work, ignore_errors=True)
