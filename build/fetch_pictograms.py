import sys, os, re, json, base64, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}

for d in ['src', 'dist', 'build']:
    os.makedirs(os.path.join(ROOT, d), exist_ok=True)

pict = {}
for i in range(1, 10):
    k = f'GHS{i:02d}'
    url = f'https://pubchem.ncbi.nlm.nih.gov/images/ghs/{k}.svg'
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        raw = r.read()
    txt = raw.decode('utf-8', 'replace')
    # 去掉 XML 声明与 DOCTYPE（内嵌 data URI 用不到）
    txt = re.sub(r'<\?xml[^>]*\?>', '', txt)
    txt = re.sub(r'<!DOCTYPE[^>]*>', '', txt, flags=re.I)
    txt = txt.strip()
    b = txt.encode('utf-8')
    pict[k] = 'data:image/svg+xml;base64,' + base64.b64encode(b).decode('ascii')
    print(f'{k}: 原始 {len(raw):>6}B -> 清理后 {len(b):>6}B -> dataURI {len(pict[k]):>7}B')

out = os.path.join(ROOT, 'src', 'pictograms.js')
with open(out, 'w', encoding='utf-8') as f:
    f.write('/* GHS 象形图（PubChem 公开 SVG，纯矢量无外部引用，已内嵌为 data URI） */\n')
    f.write('const PICTO = ')
    json.dump(pict, f, ensure_ascii=False, separators=(',', ':'))
    f.write(';\n')
print(f'\nwrote {out}  ({os.path.getsize(out):,} B)')
