"""Project model, bounded image/PDF ingestion and portable checkpoints. No credentials saved."""
from __future__ import annotations
import hashlib, io, json, math, re, uuid, zipfile
from pathlib import Path
from PIL import Image, ImageOps
import fitz

MAX_PAGES = 150
MAX_ARCHIVE = 300 * 1024 * 1024
MAX_IMAGE_BYTES = 15 * 1024 * 1024
DEFAULT_GLOSSARY = 'Occipital Fiber\t後頭線維\nVertebral Adjustment\t椎骨アジャストメント\nSpinous Process\t棘突起\nCephalad\t頭側方向\nSOT\tSOT\nCMRT\tCMRT'

def new_project():
    return {'version': 1, 'id': uuid.uuid4().hex, 'title': '洋書の日本語ノート', 'glossary': DEFAULT_GLOSSARY, 'pages': []}

def normalize_image(data):
    with Image.open(io.BytesIO(data)) as src:
        if src.width * src.height > 50_000_000:
            raise ValueError('画像が大きすぎます。5,000万画素以下にしてください。')
        im = ImageOps.exif_transpose(src).convert('RGB')
        im.thumbnail((2400, 3200))
        b = io.BytesIO(); im.save(b, 'JPEG', quality=92)
        return b.getvalue()

def make_page(image, source, source_page, text=''):
    return {'id': uuid.uuid4().hex, 'image': image, 'source': source,
            'source_page': source_page, 'label': '', 'title': '',
            'original': text, 'translation': '', 'figures': [], 'notes': '',
            'status': '未翻訳', 'error': '', 'history': [], 'usage': {}, 'provider': '', 'model': ''}

def ingest(name, data, remaining=MAX_PAGES):
    if len(data) > 50 * 1024 * 1024: raise ValueError('1ファイル50MB以内で追加してください。')
    suffix = Path(name).suffix.lower()
    if suffix == '.pdf':
        pages = []
        with fitz.open(stream=data, filetype='pdf') as doc:
            if doc.needs_pass: raise ValueError('パスワード付きPDFは、解除したコピーを追加してください。')
            if len(doc) > remaining: raise ValueError(f'残り{remaining}ページまでです。PDFを分けて追加してください。')
            for i, p in enumerate(doc):
                scale = min(2.0, 2400 / max(p.rect.width, p.rect.height))
                pix = p.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                pages.append(make_page(normalize_image(pix.tobytes('png')), name, i + 1, p.get_text()[:100_000]))
        return pages
    if suffix not in ('.jpg', '.jpeg', '.png'): raise ValueError('JPG・PNG・PDFに対応しています。HEICはJPEGに変換してください。')
    if remaining < 1: raise ValueError('ページ上限に達しました。プロジェクトを分けてください。')
    return [make_page(normalize_image(data), name, 1)]

def glossary_dict(text):
    result = {}
    for line in text.splitlines():
        if not line.strip(): continue
        parts = re.split(r'\t|\s*→\s*', line, maxsplit=1)
        if len(parts) != 2 or not all(v.strip() for v in parts):
            raise ValueError('用語は「英語 → 日本語」を1行ずつ入力してください。')
        result[parts[0].strip()] = parts[1].strip()
    return result

def normalize_result(data):
    if not isinstance(data, dict): raise ValueError('翻訳結果はJSONオブジェクトにしてください。')
    for key in ('original', 'translation'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f'翻訳結果の {key} が空です。元の結果を残しました。')
        if len(data[key]) > 100_000: raise ValueError('1ページの文字数が上限を超えています。')
    out = {k: str(data.get(k, ''))[:100_000] for k in ('title', 'label', 'original', 'translation', 'notes')}
    out['figures'] = []
    for figure in data.get('figures', [])[:20]:
        box = figure.get('box') if isinstance(figure, dict) else None
        if not isinstance(box, list) or len(box) != 4: raise ValueError('図の座標は4つの数値で指定してください。')
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box): raise ValueError('図の座標が不正です。')
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 1000): raise ValueError('図の座標は0〜1000で、左上→右下の順です。')
        out['figures'].append({'box': box, 'caption': str(figure.get('caption', ''))[:2000]})
    return out

def parse_result(text):
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text)
    return normalize_result(json.loads(text))

def apply_result(page, result, provider='', model='', usage=None):
    if page['translation']:
        page['history'].append({k: page.get(k) for k in ('title', 'label', 'original', 'translation', 'figures', 'notes', 'status')})
        page['history'] = page['history'][-5:]
    old_label = page['label']
    page.update(result)
    page['label'] = result.get('label', old_label)
    page.update(status='要確認', error='', provider=provider, model=model, usage=usage or {})

def figure_bytes(page, figure):
    with Image.open(io.BytesIO(page['image'])) as im:
        x0,y0,x1,y1=figure['box']
        crop = im.crop((int(x0*im.width/1000), int(y0*im.height/1000), max(1,int(x1*im.width/1000)), max(1,int(y1*im.height/1000))))
        out=io.BytesIO(); crop.save(out,'PNG'); return out.getvalue()

def pack(project):
    meta = {k: project[k] for k in ('version','id','title','glossary')}
    meta['pages'] = []
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for i,p in enumerate(project['pages']):
            row = {k:v for k,v in p.items() if k in {'id','source','source_page','label','title','original','translation','figures','notes','status','error','history','usage','provider','model','correction','photo_reviewed'}}
            row['image_file'] = f'images/{i:04d}.jpg'
            meta['pages'].append(row); z.writestr(row['image_file'],p['image'])
            if p.get('original_image'):
                row['original_image_file']=f'originals/{i:04d}.jpg'
                z.writestr(row['original_image_file'],p['original_image'])
        z.writestr('project.json',json.dumps(meta,ensure_ascii=False))
    return b.getvalue()

def unpack(data):
    if len(data)>MAX_ARCHIVE: raise ValueError('保存ファイルが300MBを超えています。')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist())>MAX_ARCHIVE: raise ValueError('展開後のデータが大きすぎます。')
        if len(z.infolist())>2*MAX_PAGES+1: raise ValueError('保存ファイル内の項目数が多すぎます。')
        if z.getinfo('project.json').file_size>30*1024*1024: raise ValueError('プロジェクト情報が大きすぎます。')
        meta=json.loads(z.read('project.json'))
        if meta.get('version')!=1: raise ValueError('対応していない保存形式です。')
        if not isinstance(meta.get('pages'),list) or len(meta['pages'])>MAX_PAGES: raise ValueError('ページ数が不正です。')
        project=new_project(); project['title']=str(meta.get('title','洋書の日本語ノート'))[:500]
        project['glossary']=str(meta.get('glossary',''))[:30_000]; glossary_dict(project['glossary'])
        for r in meta['pages']:
            name=r['image_file']
            if not re.fullmatch(r'images/\d{4}\.jpg',name): raise ValueError('画像パスが不正です。')
            if z.getinfo(name).file_size>MAX_IMAGE_BYTES: raise ValueError('保存画像が大きすぎます。')
            image_data=z.read(name)
            with Image.open(io.BytesIO(image_data)) as check:
                if check.width*check.height>12_000_000: raise ValueError('保存画像が大きすぎます。')
                check.verify()
            p=make_page(image_data,str(r.get('source',''))[:500],int(r.get('source_page',1)))
            for k in ('label','title','original','translation','notes','provider','model'):
                p[k]=str(r.get(k,''))[:100_000]
            # Validation is reused for figures; empty untranslated pages remain allowed.
            p['figures']=normalize_result({'original':'x','translation':'x','figures':r.get('figures',[])})['figures']
            p['status']=r.get('status') if r.get('status') in ('未翻訳','要確認','確認済み') else '要確認'
            p['history']=[h for h in r.get('history',[]) if isinstance(h,dict)][-5:]
            if r.get('original_image_file'):
                oldname=r['original_image_file']
                if not re.fullmatch(r'originals/\d{4}\.jpg',oldname): raise ValueError('元画像パスが不正です。')
                if z.getinfo(oldname).file_size>MAX_IMAGE_BYTES: raise ValueError('元画像が大きすぎます。')
                old=z.read(oldname)
                with Image.open(io.BytesIO(old)) as check:
                    if check.width*check.height>12_000_000: raise ValueError('元画像が大きすぎます。')
                    check.verify()
                p['original_image']=old
                if isinstance(r.get('correction'),dict):p['correction']=r['correction']
            p['photo_reviewed']=bool(r.get('photo_reviewed',False))
            project['pages'].append(p)
    return project

def fingerprint(project, options=''):
    h=hashlib.sha256(pack(project)); h.update(options.encode()); return h.hexdigest()
