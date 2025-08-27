from typing import Iterable, List, Optional, Tuple
from PIL import Image, ImageOps, ImageDraw, ImageFont
import os
import pytesseract
from rapidfuzz import process, fuzz

Box = Tuple[int, int, int, int]  # (x, y, w, h)

def _clamp(v: int, lo: int, hi: int) -> int: return max(lo, min(hi, v))
def _xywh_to_ltrb(roi: Box, W: int, H: int):
    x,y,w,h = roi
    if w<=0 or h<=0: return None
    L=_clamp(x,0,W); T=_clamp(y,0,H); R=_clamp(x+w,0,W); B=_clamp(y+h,0,H)
    if R<=L or B<=T: return None
    return (L,T,R,B)

def _ensure_eng_available():
    # If TESSDATA_PREFIX is set, check for ...\tessdata\eng.traineddata
    tdp = os.environ.get("TESSDATA_PREFIX", "")
    if tdp:
        path = os.path.join(tdp, "tessdata", "eng.traineddata")
        if os.path.isfile(path):
            return
    # If not set or missing, try common Windows install
    guess = r"C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata"
    if os.path.isfile(guess):
        # help Tesseract by setting TESSDATA_PREFIX to the parent dir
        os.environ.setdefault("TESSDATA_PREFIX", r"C:\Program Files\Tesseract-OCR")
        return
    raise RuntimeError(
        "Tesseract 'eng.traineddata' not found.\n"
        "• Install Tesseract with English data (eng), or\n"
        "• Place eng.traineddata in: C:\\Program Files\\Tesseract-OCR\\tessdata\\\n"
        "• Or set TESSDATA_PREFIX to the directory that contains a 'tessdata' folder."
    )

class OCR:
    def __init__(self, tesseract_cmd: str | None = None):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        _ensure_eng_available()
        self._config = "--oem 3 --psm 6"   # no --tessdata-dir (use env instead)

    @staticmethod
    def _prep(img: Image.Image) -> Image.Image:
        g = ImageOps.grayscale(img)
        g = ImageOps.autocontrast(g)
        return g.point(lambda p: 255 if p > 180 else 0)

    def words(self, img: Image.Image, roi: Optional[Box] = None) -> List[dict]:
        crop = img; ox=oy=0
        if roi:
            ltrb = _xywh_to_ltrb(roi, *img.size)
            if not ltrb: return []
            ox, oy = ltrb[0], ltrb[1]; crop = img.crop(ltrb)
        b = self._prep(crop)
        # IMPORTANT: use 'eng'
        d = pytesseract.image_to_data(
            b, lang="eng", config=self._config, output_type=pytesseract.Output.DICT
        )
        out: List[dict] = []
        for i, t in enumerate(d["text"]):
            t = (t or "").strip()
            if not t:
                continue
            x = d["left"][i] + ox; y = d["top"][i] + oy
            w = d["width"][i]; h = d["height"][i]
            if w<=0 or h<=0: continue
            out.append({"text": t, "box": (x,y,w,h)})
        return out

    def find(self, img: Image.Image, synonyms: Iterable[str], *,
             min_score: int = 75, roi: Optional[Box] = None, exact: bool = False,
             avoid_below: Optional[int] = None, avoid_above: Optional[int] = None) -> Optional[Box]:
        ws = self.words(img, roi=roi)
        if not ws: return None
        filtered = []
        for w in ws:
            y = w["box"][1]
            if avoid_below is not None and y >= avoid_below: continue
            if avoid_above is not None and y <= avoid_above: continue
            filtered.append(w)
        if not filtered: return None
        choices = [w["text"] for w in filtered]
        best_idx, best_score = -1, -1
        for q in synonyms:
            if exact:
                for i,c in enumerate(choices):
                    if c.strip().lower() == q.strip().lower():
                        return filtered[i]["box"]
            m = process.extractOne(q, choices, scorer=fuzz.WRatio)
            if m and m[1] > best_score:
                best_idx, best_score = m[2], m[1]
        if best_idx >= 0 and best_score >= min_score:
            return filtered[best_idx]["box"]
        return None

    def draw_overlay(self, img: Image.Image, *, boxes=None, lines=None, title: str="") -> Image.Image:
        boxes = boxes or []; lines = lines or []
        out = img.copy(); d = ImageDraw.Draw(out)
        try: font = ImageFont.load_default()
        except Exception: font=None
        for (x,y,w,h), color, label in boxes:
            d.rectangle([x,y,x+w,y+h], outline=color, width=2)
            if font and label: d.text((x+2,y-12), label, fill=color, font=font)
        for y, color, label in lines:
            d.line([0,y,img.size[0],y], fill=color, width=2)
            if font and label: d.text((4,y+2), label, fill=color, font=font)
        if font and title: d.text((6,6), title, fill="white", font=font)
        return out
