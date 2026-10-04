"""打「计算器本体」独立包：给不挂服务器、直接双击用的人。

产物：
    dist/投料计算器/投料计算器.html
    dist/投料计算器/快速上手.txt
    dist/投料计算器/使用说明.md
    dist/投料计算器.zip

用法：
    python build/make_standalone_package.py [--no-copy]

    --no-copy   只产出到 dist/，不往桌面复制
"""
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
BUILD = ROOT / 'build'
PKG_NAME = '投料计算器'
PKG = DIST / PKG_NAME


def desktop_dir():
    """找一个桌面目录用来放副本。可用环境变量 CALC_DESKTOP 覆盖。"""
    cands = [os.environ.get('CALC_DESKTOP', ''),
             r'D:\desk',                                        # 本机自定义桌面
             os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop'),
             os.path.join(os.environ.get('HOME', ''), 'Desktop')]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return None


def main():
    src_html = DIST / '投料计算器.html'
    if not src_html.exists():
        sys.exit('找不到 %s，请先跑 python build/build.py' % src_html)

    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True)

    shutil.copy2(src_html, PKG / '投料计算器.html')
    shutil.copy2(BUILD / 'quickstart.txt', PKG / '快速上手.txt')
    shutil.copy2(ROOT / '使用说明.md', PKG / '使用说明.md')

    print('打包目录: %s\n' % PKG)
    total = 0
    for f in sorted(os.listdir(PKG)):
        sz = os.path.getsize(PKG / f)
        total += sz
        print('   %-28s %8.1f KB' % (f, sz / 1024))
    print('\n共 %.0f KB' % (total / 1024))

    zip_path = DIST / (PKG_NAME + '.zip')
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(PKG):
            dirnames.sort()
            for f in sorted(filenames):
                full = os.path.join(dirpath, f)
                z.write(full, os.path.join(PKG_NAME, os.path.relpath(full, PKG)))
    print('\nzip: %s  (%s B)' % (zip_path, format(zip_path.stat().st_size, ',')))

    if '--no-copy' in sys.argv:
        return
    desk = desktop_dir()
    if desk:
        dst = Path(desk) / (PKG_NAME + '.zip')
        shutil.copy2(zip_path, dst)
        print('已复制到桌面: %s' % dst)
    else:
        print('（没找到桌面目录，未复制；可用 CALC_DESKTOP 环境变量指定）')


if __name__ == '__main__':
    main()
