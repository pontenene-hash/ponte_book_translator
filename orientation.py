"""Optional local Tesseract orientation detection; never guess from aspect ratio."""
import io,re,shutil,subprocess,tempfile
from pathlib import Path
from PIL import Image
from correction import encode
import numpy as np

def orient(data):
    if not shutil.which('tesseract'):
        return data,'自動の向き判定は未設定です。回転ボタンで文字を上向きにしてください。'
    try:
        with tempfile.TemporaryDirectory(prefix='ponte-orient-') as folder:
            path=Path(folder)/'page.png'
            with Image.open(io.BytesIO(data)) as im:
                im.thumbnail((2200,2200));im.save(path,dpi=(300,300))
            r=subprocess.run(['tesseract',str(path),'stdout','--psm','0','-l','osd'],capture_output=True,text=True,timeout=25)
            angle=re.search(r'Rotate:\s*(\d+)',r.stdout)
            confidence=re.search(r'Orientation confidence:\s*([\d.]+)',r.stdout)
            if r.returncode or not angle or not confidence or float(confidence[1])<8:
                return data,'文字の向きを確実に判定できませんでした。回転ボタンで確認してください。'
            degrees=int(angle[1])
            if degrees not in (0,90,180,270):return data,'向きは手動で確認してください。'
            if not degrees:return data,'文字の向きは正位置と判定しました。仕上がりを確認してください。'
            with Image.open(io.BytesIO(data)) as im:
                result=encode(np.asarray(im.convert('RGB').rotate(-degrees,expand=True)))
            return result,f'文字の向きに合わせて右へ{degrees}度回転しました。'
    except (OSError,subprocess.TimeoutExpired):
        return data,'自動の向き判定を完了できませんでした。回転ボタンで確認してください。'
