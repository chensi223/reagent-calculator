# -*- coding: utf-8 -*-
"""投料计算器 · 数值正确性校验套件

每个用例的期望值都用 Python **独立按化学定义重新推导**，不抄程序里的公式：
    n_pure = n x MW / 1000          纯物质理论量
    m_称取 = n_pure / (纯度/100)     实际要称的量
    V_液体 = m_称取 / ρ              液体按体积量取
    V_溶液 = n / C                   C 单位 mol/L
然后用无头浏览器真跑一遍程序、把结果抓回来逐项比对。

用法：
    python build/verify_numbers.py

覆盖：基础当量、纯度折算、溶液浓度、液体按体积、70% 溶液(w/w 与 w/v)、
      产物反算、按质量反推参考物、mol%、极小量、整体缩放、混合形态。
"""
import os, subprocess, sys, re, json, pathlib, tempfile, shutil
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

# ---------------- 试剂库（分子量/密度取自程序内置词典，先核对过） ----------------
BENZ   = ("苯甲醛",        106.124, 1.04)    # 液体
DEM    = ("丙二酸二乙酯",  160.169, 1.06)
PIP    = ("哌啶",           85.150, 0.862)
NBULI  = ("正丁基锂",       64.056, None)    # 溶液
C100   = ("模拟70%溶液",   100.000, 1.20)    # 自定义，MW=100 便于手算

def R(t, **kw):
    d = dict(name=t[0], mw=t[1], density=kw.pop('density', t[2]), type=kw.pop('type','solid'),
             conc=kw.pop('conc', None), purity=kw.pop('purity', 100.0))
    d.update(kw)
    return d

# ---------------- 独立手算：化学定义 ----------------
# n_pure = n_mmol * MW / 1000                (g，纯物质理论量)
# m_称取 = n_pure / (纯度/100)               (g，实际要称的量)
# V_液体 = m_称取 / ρ                        (mL)
# V_溶液 = n_mmol / C                        (mL，C 单位 mol/L)
def pure(n, mw):      return n * mw / 1000.0
def weigh(n, mw, p):  return pure(n, mw) / (p / 100.0)
def vol_liq(n, mw, p, rho): return weigh(n, mw, p) / rho
def vol_sol(n, c):    return n / c

CASES = []
def case(cid, title, rows, expect, note="", post=None):
    CASES.append(dict(id=cid, title=title, rows=rows, expect=expect, note=note, post=post))

# T1 基础：单试剂固体
n = 100.0
case("T1", "单试剂：100 mmol 固体底物",
     [R(BENZ, type='solid', set={'mmol': 100})],
     [dict(mmol=n, mass=pure(n,106.124), volume=None)])

# T2 两试剂，相对当量
case("T2", "两试剂：底物 100 mmol + 1.2 当量试剂",
     [R(BENZ, type='liquid', set={'mmol': 100}),
      R(DEM,  type='liquid', set={'equiv': 1.2})],
     [dict(mmol=100, mass=pure(100,106.124), volume=vol_liq(100,106.124,100,1.04)),
      dict(mmol=120, mass=pure(120,160.169), volume=vol_liq(120,160.169,100,1.06))])

# T3 固体 + 纯度 95%
case("T3", "固体试剂：纯度 95%，称量质量要折算",
     [R(BENZ, type='solid', purity=95, set={'mmol': 100})],
     [dict(mmol=100, mass=weigh(100,106.124,95), volume=None)],
     "称取 = 理论量 ÷ 0.95")

# T4 液体 + 纯度 95%（按体积量取）
case("T4", "液体试剂：纯度 95% + 密度，体积按折算后的称量质量算",
     [R(BENZ, type='liquid', purity=95, set={'mmol': 100})],
     [dict(mmol=100, mass=weigh(100,106.124,95), volume=vol_liq(100,106.124,95,1.04))])

# T5 溶液试剂：按浓度算体积
case("T5", "溶液试剂：2.5 M，110 mmol → 44 mL",
     [R(BENZ, type='solid', set={'mmol': 100}),
      R(NBULI, type='solution', conc=2.5, set={'mmol': 110})],
     [dict(mmol=100), dict(mmol=110, volume=vol_sol(110, 2.5))],
     "V = n / C = 110 / 2.5")

# T6 ★ 溶液 + 纯度 70%：纯度该不该影响体积？
case("T6", "★ 溶液试剂同时填了「纯度 70%」——体积该不该受影响？",
     [R(BENZ, type='solid', set={'mmol': 100}),
      R(NBULI, type='solution', conc=2.5, purity=70, set={'mmol': 110})],
     [dict(mmol=100), dict(mmol=110, volume=vol_sol(110, 2.5))],
     "摩尔浓度已含一切，纯度不应再影响体积")

# T7 ★ 70% w/w 溶液按「液体」填（密度 + 纯度）
case("T7", "★ 70% (w/w) 溶液：按液体填，纯度 70% + 密度 1.2",
     [R(BENZ, type='solid', set={'mmol': 100}),
      R(C100, type='liquid', purity=70, density=1.2, set={'mmol': 100})],
     [dict(mmol=100), dict(mmol=100, mass=weigh(100,100,70), volume=vol_liq(100,100,70,1.2))],
     "需要纯品 10 g → 70% 溶液 14.2857 g → ÷1.2 = 11.9048 mL")

# T8 ★ 同一个 70% 溶液，先换算成 mol/L 再按「溶液」填
c70 = 1000 * 1.20 * 0.70 / 100.0     # 70% w/w, ρ=1.2, MW=100 → mol/L
case("T8", f"★ 同一个 70% 溶液，换成 {round(c70,4)} mol/L 按「溶液」填",
     [R(BENZ, type='solid', set={'mmol': 100}),
      R(C100, type='solution', conc=c70, density=1.2, set={'mmol': 100})],
     [dict(mmol=100), dict(mmol=100, volume=vol_sol(100, c70))],
     f"C = 1000·ρ·w%/MW = {round(c70,4)} mol/L；应当与 T7 的 11.9048 mL 一致")

# T9 ★ 误把「70」当浓度填（应为 mol/L）
case("T9", "★ 如果把 70 直接填进「浓度(mol/L)」框（单位填错）",
     [R(BENZ, type='solid', set={'mmol': 100}),
      R(C100, type='solution', conc=70, density=1.2, set={'mmol': 100})],
     [dict(mmol=100), dict(mmol=100, volume=vol_sol(100, 70))],
     "程序按 70 mol/L 算 → 1.4286 mL，与正确值差 8.3 倍（这很可能是差异来源）")

# T10 产物反算
case("T10", "按产物反算：产物 MW 176.215、5 g、收率 85%",
     [R(BENZ, type='solid', set={}, product=dict(mw=176.215, mass=5.0, yield_=85))],
     [dict(mmol=5.0/176.215*1000/0.85)],
     "n = 5/176.215×1000 ÷ 0.85")

# T11 按质量反推参考物
case("T11", "某试剂给 5 g + 1.2 当量 → 反推参考物",
     [R(BENZ, type='solid', set={'mmol': None}),
      R(DEM,  type='solid', set={'mass': 5.0, 'equiv': 1.2})],
     [dict(mmol=5.0/160.169*1000/1.2), dict(mmol=5.0/160.169*1000, mass=5.0)])

# T12 mol% 催化剂
case("T12", "催化剂按 10 mol% 写",
     [R(BENZ, type='solid', set={'mmol': 100}),
      R(PIP,  type='solid', set={'equiv': '10 mol%'})],
     [dict(mmol=100), dict(mmol=10, equiv=0.1, mass=pure(10,85.150))])

# T13 多试剂链式（5 行）
case("T13", "五行链式：底物 + 两个试剂 + 催化剂",
     [R(BENZ, type='solid', set={'mmol': 100}),
      R(DEM,  type='solid', set={'equiv': 1.2}),
      R(PIP,  type='solid', set={'equiv': 0.1}),
      R(C100, type='solid', set={'equiv': 2.0}),
      R(DEM,  type='solid', set={'equiv': 1.05})],
     [dict(mmol=100, mass=pure(100,106.124)),
      dict(mmol=120, mass=pure(120,160.169)),
      dict(mmol=10,  mass=pure(10,85.150)),
      dict(mmol=200, mass=pure(200,100)),
      dict(mmol=105, mass=pure(105,160.169))])

# T14 极小量（µL 档）
case("T14", "极小量：参考物 0.005 mmol + 溶液试剂 2 当量 → 4 µL",
     [R(BENZ, type='solid', set={'mmol': 0.005}),
      R(NBULI, type='solution', conc=2.5, set={'equiv': 2.0})],
     [dict(mmol=0.005), dict(mmol=0.01, volume=0.01/2.5)],
     "V = 0.01 mmol ÷ 2.5 mol/L = 0.004 mL")

# T15 给溶液体积反推 mmol
case("T15", "给溶液体积 10 mL + 2.5 M → 反推 25 mmol",
     [R(BENZ, type='solid', set={'mmol': 100}),
      R(NBULI, type='solution', conc=2.5, set={'volume': 10})],
     [dict(mmol=100), dict(mmol=25, volume=10, equiv=0.25)],
     "n = 10 mL × 2.5 mol/L = 25 mmol")

# T16 ★ 70% (w/v)
c_wv = 700.0 / 100.0
case("T16", "★ 70% (w/v) 溶液：700 g/L ÷ MW 100 = 7 mol/L",
     [R(BENZ, type='solid', set={'mmol': 100}),
      R(C100, type='solution', conc=c_wv, density=1.2, set={'mmol': 100})],
     [dict(mmol=100), dict(mmol=100, volume=100/c_wv)],
     "w/v 与 w/w 不是一回事：70% w/v = 700 g/L，跟密度无关")

# T17 整体缩放
case("T17", "整体缩放到 50 mmol",
     [R(BENZ, type='solid', set={'mmol': 100}),
      R(DEM,  type='solid', set={'equiv': 1.2})],
     [dict(mmol=50, mass=pure(50,106.124)),
      dict(mmol=60, mass=pure(60,160.169))],
     post={'scale': 50})

# T18 混合形态
case("T18", "固体 + 液体(纯度98%) + 溶液 三种形态混用",
     [R(BENZ, type='solid', set={'mmol': 100}),
      R(DEM,  type='liquid', purity=98, set={'equiv': 1.2}),
      R(NBULI, type='solution', conc=1.6, set={'equiv': 1.1})],
     [dict(mmol=100, mass=pure(100,106.124)),
      dict(mmol=120, mass=weigh(120,160.169,98), volume=vol_liq(120,160.169,98,1.06)),
      dict(mmol=110, volume=vol_sol(110,1.6))])

print("共 %d 个用例\n" % len(CASES))

# ---------------- 生成注入脚本 ----------------
def js_rows(rows):
    out = []
    for r in rows:
        out.append({
            "name": r["name"], "mw": r["mw"], "density": r.get("density"),
            "type": r["type"], "conc": r.get("conc"), "purity": r.get("purity", 100),
            "set": r.get("set", {}), "product": r.get("product"),
        })
    return out

INJECT = r'''
<pre id="out">RUNNING</pre>
<script>
var CASES = __CASES__;
function mkReagent(name, mw, density) {
  return normalizeReagent({ zh: name, mw: mw, density: density, cas: null, _src: 'manual',
    hazard: { grade: 'unknown', h: [], pict: [], signal: null, note: '' } }, 'manual');
}
function runCase(c) {
  state.rows = []; state.refIndex = 0; state.anchorMode = 'ref';
  state.product = { mw: null, targetMass: null, yield: 100 };
  c.rows.forEach(function (spec, i) {
    addReagentToList(mkReagent(spec.name, spec.mw, spec.density));
    var r = state.rows[i];
    r.type = spec.type;
    if (spec.conc != null) r.concOverride = spec.conc;
    r.purityOverride = spec.purity;
    var S = spec.set || {};
    if (S.mmol != null) applyCellInput(r, 'mmol', String(S.mmol));
    if (S.equiv != null) applyCellInput(r, 'equiv', String(S.equiv));
    if (S.mass != null) applyCellInput(r, 'mass', String(S.mass));
    if (S.volume != null) applyCellInput(r, 'volume', String(S.volume));
  });
  var prod = c.rows[0].product;
  if (prod) {
    state.anchorMode = 'product';
    state.product = { mw: prod.mw, targetMass: prod.mass, yield: prod.yield_ };
  }
  renderTable(); refresh();
  if (c.post && c.post.scale) { scaleTo(state, c.post.scale); refresh(); }
  return state.rows.map(function (r) {
    return { name: rowName(r), equiv: qv(r.equiv), mmol: qv(r.mmol), mass: qv(r.mass), volume: qv(r.volume) };
  });
}
window.addEventListener('load', function () { setTimeout(function () {
  var res = {};
  try { CASES.forEach(function (c) { res[c.id] = runCase(c); }); }
  catch (e) { res.__error = e.message + ' @ ' + (e.stack||'').split('\n')[1]; }
  document.getElementById('out').textContent = JSON.stringify(res);
}, 500); });
</script>
'''

payload = json.dumps(js_rows.__self__ if False else
                     [{k: v for k, v in c.items() if k in ("id", "rows", "post")} for c in CASES],
                     ensure_ascii=False)
work = pathlib.Path(tempfile.mkdtemp(prefix="verify_"))
try:
    h = (ROOT / "dist" / "投料计算器.html").read_text(encoding="utf-8")
    tp = work / "_t.html"
    tp.write_text(h.replace("</body>", INJECT.replace("__CASES__", payload) + "</body>"), encoding="utf-8")
    prof = work / "p"; prof.mkdir()
    r = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-first-run",
                        "--no-default-browser-check", "--user-data-dir=" + str(prof),
                        "--virtual-time-budget=12000", "--dump-dom", tp.as_uri()],
                       capture_output=True, timeout=240)
    dom = r.stdout.decode("utf-8", "replace")
    m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
    if not m:
        print("没拿到输出"); sys.exit(1)
    raw = m.group(1).replace("&lt;","<").replace("&gt;",">").replace("&amp;","&")
    got = json.loads(raw)
finally:
    shutil.rmtree(work, ignore_errors=True)

if "__error" in got:
    print("注入脚本异常:", got["__error"]); sys.exit(1)

# ---------------- 对比 ----------------
def close(a, b, tol=0.005):
    if a is None and b is None: return True
    if a is None or b is None: return False
    return abs(a - b) <= max(tol, abs(b) * 5e-4)

bad = 0
for c in CASES:
    print("=" * 78)
    print("%s  %s" % (c["id"], c["title"]))
    if c["note"]:
        print("      手算依据: %s" % c["note"])
    rows = got.get(c["id"], [])
    for i, exp in enumerate(c["expect"]):
        g = rows[i] if i < len(rows) else {}
        for k in ("equiv", "mmol", "mass", "volume"):
            if k not in exp: continue
            e = exp[k]; a = g.get(k)
            okk = close(a, e)
            if not okk: bad += 1
            unit = {"equiv":"", "mmol":"mmol", "mass":"g", "volume":"mL"}[k]
            print("   %s %-6s 手算 %-14s  程序 %-14s" % (
                  "OK " if okk else "✗✗ ", k,
                  ("%.6g" % e) if e is not None else "—",
                  ("%.6g" % a) if a is not None else "—"))
    print()
print("=" * 78)
print("不一致项: %d" % bad)
