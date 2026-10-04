"""打「网页部署包」：给帮忙挂服务器的运维/同学。

产物：
    dist/投料计算器_网页部署包/
    ├── 请先看我.md                       ← 给收件人的白话说明
    ├── 部署说明.md                       ← 技术细节（Nginx / 验证 / 注意事项）
    ├── 投料计算器（预览用，不用上传）.html  ← 本地双击预览用
    └── 网站文件/                         ← 这一整个目录才是要上传的 7 个文件
    dist/投料计算器_网页部署包.zip

用法：
    python build/make_package.py [--no-copy]
"""
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
PWA = DIST / 'pwa'
BUILD = ROOT / 'build'
PKG_NAME = '投料计算器_网页部署包'
PKG = DIST / PKG_NAME

WEB_FILES = ['index.html', 'manifest.json', 'sw.js',
             'icon-192.png', 'icon-512.png', 'apple-touch-icon.png', 'favicon.png']


def desktop_dir():
    cands = [os.environ.get('CALC_DESKTOP', ''),
             r'D:\desk',
             os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop'),
             os.path.join(os.environ.get('HOME', ''), 'Desktop')]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return None


def main():
    if not PWA.is_dir():
        sys.exit('找不到 %s，请先跑 python build/build.py' % PWA)
    for f in WEB_FILES:
        if not (PWA / f).exists():
            sys.exit('缺少网站文件: %s' % (PWA / f))

    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True)

    # 1) 网站文件/ —— 这才是要上传的
    web = PKG / '网站文件'
    web.mkdir()
    for f in WEB_FILES:
        shutil.copy2(PWA / f, web / f)

    # 2) 根目录：说明 + 预览用的单文件版
    shutil.copy2(BUILD / 'readme_send.md', PKG / '请先看我.md')
    shutil.copy2(PWA / '部署说明.md', PKG / '部署说明.md')
    shutil.copy2(DIST / '投料计算器.html', PKG / '投料计算器（预览用，不用上传）.html')

    # 3) 列出内容
    print('打包目录: %s\n' % PKG)
    total = 0
    for dirpath, dirnames, filenames in os.walk(PKG):
        dirnames.sort()
        rel = os.path.relpath(dirpath, PKG)
        depth = 0 if rel == '.' else rel.count(os.sep) + 1
        indent = '   ' * depth
        if rel != '.':
            print('%s%s/' % (indent, os.path.basename(dirpath)))
        for f in sorted(filenames):
            sz = os.path.getsize(os.path.join(dirpath, f))
            total += sz
            print('%s   %-42s %8.1f KB' % (indent, f, sz / 1024))
    print('\n共 %.0f KB' % (total / 1024))

    # 4) 打 zip（zipfile 对非 ASCII 名会写 UTF-8 标志位，解压不乱码）
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

    # 5) 复制一份到桌面，方便直接发出去
    if '--no-copy' in sys.argv:
        return
    desk = desktop_dir()
    if desk:
        dst = Path(desk) / (PKG_NAME + '.zip')
        shutil.copy2(zip_path, dst)
        print('已复制到桌面: %s  (%s B)' % (dst, format(dst.stat().st_size, ',')))
    else:
        print('（没找到桌面目录，未复制；可用 CALC_DESKTOP 环境变量指定）')


if __name__ == '__main__':
    main()
