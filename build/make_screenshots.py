"""生成 README 用的界面截图。

用法：
    python build/make_screenshots.py

产物：
    docs/images/screenshot-desktop.png   桌面版全览
    docs/images/screenshot-mobile.png    手机版卡片布局

依赖：本机装有 Microsoft Edge 或 Google Chrome（无头模式调用），
      裁剪时需要 Pillow（没装就跳过裁剪，图会带一点空白）。

为什么要绕这一圈：
    无头浏览器的 --window-size 与页面真实的 CSS 视口宽度并不相等
    （本机实测设 390 时实际视口约 477），直接按 --window-size 截图，
    手机版会把右侧内容裁掉。改用「固定宽度的 iframe 包一层」，
    iframe 的宽度就是精确的 CSS 视口宽度。
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs' / 'images'

BROWSERS = [
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    '/usr/bin/microsoft-edge', '/usr/bin/google-chrome', '/usr/bin/chromium',
]

# 演示用的那一组投料（Knoevenagel 缩合），只是为了截图好看且有代表性
DEMO = r'''
<script>
window.addEventListener('load', function () {
  setTimeout(function () {
    try {
      document.getElementById('runName').value = 'Knoevenagel 缩合（模型反应）';
      var dict = (window.__DICT__ && window.__DICT__.reagents) || [];
      var pick = function (n) {
        for (var i = 0; i < dict.length; i++) if (dict[i].zh === n) return dict[i];
        return null;
      };
      ['苯甲醛', '丙二酸二乙酯', '哌啶'].forEach(function (n) {
        var r = pick(n);
        if (r) { r._src = 'dict'; addReagentToList(r); }
      });
      if (state.rows.length >= 3) {
        applyCellInput(state.rows[1], 'equiv', '1.2');
        applyCellInput(state.rows[2], 'equiv', '10 mol%');
        state.rows[0].role = 'substrate';
        state.rows[1].role = 'reagent';
        state.rows[2].role = 'catalyst';
      }
      var sn = document.getElementById('solventName');
      var sv = document.getElementById('solventVol');
      if (sn) sn.value = '甲苯（无水）';
      if (sv) sv.value = '5 mL';
      if (typeof doRefresh === 'function') doRefresh();
      if (typeof refresh === 'function') refresh();
      document.title = 'DEMO_ROWS=' + state.rows.length;
    } catch (e) {
      document.title = 'DEMO_ERROR=' + e.message;
    }
  }, 300);
});
</script>
'''


def find_browser():
    for b in BROWSERS:
        if os.path.exists(b):
            return b
    sys.exit('没找到 Edge 或 Chrome，无法截图')


def shot(browser, url, out, w, h, scale=2, workdir=None):
    profile = Path(workdir) / ('prof_' + out.stem)
    if profile.exists():
        shutil.rmtree(profile, ignore_errors=True)
    profile.mkdir(parents=True)
    if out.exists():
        out.unlink()
    cmd = [browser, '--headless=new', '--disable-gpu', '--no-first-run',
           '--no-default-browser-check', '--hide-scrollbars',
           '--allow-file-access-from-files',
           '--user-data-dir=' + str(profile),
           '--force-device-scale-factor=' + str(scale),
           '--virtual-time-budget=9000',
           '--window-size=%d,%d' % (w, h),
           '--screenshot=' + str(out), url]
    subprocess.run(cmd, capture_output=True, timeout=300)
    if not out.exists():
        sys.exit('截图失败: %s' % out)
    print('   %-24s %dx%d @%dx' % (out.name, w, h, scale))


def main():
    browser = find_browser()
    dist_html = ROOT / 'dist' / '投料计算器.html'
    if not dist_html.exists():
        sys.exit('找不到 %s，请先跑 python build/build.py' % dist_html)

    OUT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='calc_shot_'))
    try:
        demo = work / '_demo.html'
        demo.write_text(dist_html.read_text(encoding='utf-8').replace('</body>', DEMO + '</body>'),
                        encoding='utf-8')

        # 桌面版
        shot(browser, demo.as_uri(), work / 'desktop_raw.png', 1480, 1340, 2, work)

        # 手机版：套一层固定宽度 iframe
        wrap = work / '_mobile_wrap.html'
        wrap.write_text(
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<style>html,body{margin:0;padding:0;background:#fff;}'
            'iframe{width:390px;height:3000px;border:0;display:block;}</style></head>'
            '<body><iframe src="_demo.html" scrolling="no"></iframe></body></html>',
            encoding='utf-8')
        shot(browser, wrap.as_uri(), work / 'mobile_raw.png', 400, 3200, 2, work)

        # 裁掉多余留白
        try:
            from PIL import Image
        except ImportError:
            print('   （没装 Pillow，跳过裁剪，直接复制原图）')
            shutil.copy2(work / 'desktop_raw.png', OUT / 'screenshot-desktop.png')
            shutil.copy2(work / 'mobile_raw.png', OUT / 'screenshot-mobile.png')
            return

        d = Image.open(work / 'desktop_raw.png').convert('RGB')
        d.crop((276, 35, 2684, 2680)).save(OUT / 'screenshot-desktop.png', optimize=True)
        m = Image.open(work / 'mobile_raw.png').convert('RGB')
        m.crop((0, 0, 780, 2200)).save(OUT / 'screenshot-mobile.png', optimize=True)

        for name in ('screenshot-desktop.png', 'screenshot-mobile.png'):
            p = OUT / name
            print('   -> %s  (%.0f KB)' % (p.relative_to(ROOT), p.stat().st_size / 1024))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
