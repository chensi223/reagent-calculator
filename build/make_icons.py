import sys, os
sys.stdout.reconfigure(encoding='utf-8')
from PIL import Image, ImageDraw, ImageChops

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dist', 'pwa')
os.makedirs(OUT, exist_ok=True)

BG = (22, 104, 193, 255)
WHITE = (255, 255, 255, 255)
LIQ = (124, 190, 250, 255)


def draw_icon(size):
    """圆角蓝底 + 白色锥形瓶 + 浅蓝液面（液体按瓶身形状裁剪，不溢出）"""
    S = 4
    n = size * S
    k = n / 512.0

    def P(pts):
        return [(x * k, y * k) for x, y in pts]

    # --- 底层：圆角背景 ---
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.22), fill=BG)

    # --- 瓶子层：白色瓶体（瓶口 + 瓶颈 + 锥形瓶身 + 圆底） ---
    flask = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    fd = ImageDraw.Draw(flask)
    fd.rounded_rectangle(P([(222, 92), (290, 124)]), radius=int(10 * k), fill=WHITE)      # 瓶口
    fd.rectangle(P([(234, 118), (278, 232)]), fill=WHITE)                                  # 瓶颈
    fd.polygon(P([(234, 226), (278, 226), (394, 386), (118, 386)]), fill=WHITE)            # 瓶身
    fd.rounded_rectangle(P([(118, 352), (394, 408)]), radius=int(28 * k), fill=WHITE)      # 瓶底圆角
    flask_mask = flask.split()[3]

    # --- 液体层：整条矩形，再用瓶身 mask 裁掉多余部分 ---
    liq = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(liq).rectangle(P([(100, 296), (412, 400)]), fill=LIQ)
    liq.putalpha(ImageChops.multiply(liq.split()[3], flask_mask))

    # --- 合成 ---
    img.alpha_composite(flask)
    img.alpha_composite(liq)

    return img.resize((size, size), Image.LANCZOS)


for s, name in [(192, 'icon-192.png'), (512, 'icon-512.png'),
                (180, 'apple-touch-icon.png'), (64, 'favicon.png')]:
    p = os.path.join(OUT, name)
    draw_icon(s).save(p, 'PNG', optimize=True)
    print(f'  {name:<22} {os.path.getsize(p):,} B')

draw_icon(320).save(os.path.join(OUT, '_preview.png'), 'PNG')
print('  _preview.png 已生成（仅用于肉眼确认，部署时可删）')
