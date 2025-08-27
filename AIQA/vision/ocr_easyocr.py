# AIQA/vision/ocr_easyocr.py
from typing import Iterable, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import numpy as np

Box = Tuple[int,int,int,int]
def _clamp(v,lo,hi): return max(lo,min(hi,v))
def _xywh_to_ltrb(roi, W, H):
    x,y,w,h=roi
    if w<=0 or h<=0: return None
    L=_clamp(x,0,W); T=_clamp(y,0,H); R=_clamp(x+w,0,W); B=_clamp(y+h,0,H)
    return None if R<=L or B<=T else (L,T,R,B)

class OCR:
    def __init__(self, langs=["en"], gpu=False):
        import easyocr
        self.reader = easyocr.Reader(langs, gpu=gpu, verbose=False)

    def words(self, img: Image.Image, roi: Optional[Box] = None) -> List[dict]:
        crop=img; ox=oy=0
        if roi:
            ltrb=_xywh_to_ltrb(roi,*img.size)
            if not ltrb: return []
            ox,oy=ltrb[0],ltrb[1]; crop=img.crop(ltrb)
        arr=np.asarray(crop)
        res=self.reader.readtext(arr, detail=1, paragraph=False)
        out=[]
        for bbox, txt, conf in res:
            txt=(txt or "").strip()
            if not txt: continue
            xs=[p[0] for p in bbox]; ys=[p[1] for p in bbox]
            x=int(min(xs))+ox; y=int(min(ys))+oy
            w=int(max(xs)-min(xs)); h=int(max(ys)-min(ys))
            if w>0 and h>0: out.append({"text":txt,"box":(x,y,w,h)})
        return out

    def find(self, img: Image.Image, synonyms: Iterable[str], *, min_score=75, roi=None, exact=False, avoid_below=None, avoid_above=None):
        from rapidfuzz import process, fuzz
        ws=self.words(img, roi=roi)
        if not ws: return None
        filtered=[]
        for w in ws:
            y=w["box"][1]
            if avoid_below is not None and y>=avoid_below: continue
            if avoid_above is not None and y<=avoid_above: continue
            filtered.append(w)
        if not filtered: return None
        choices=[w["text"] for w in filtered]
        best_idx,best_score=-1,-1
        for q in synonyms:
            if exact:
                for i,c in enumerate(choices):
                    if c.strip().lower()==q.strip().lower(): return filtered[i]["box"]
            m=process.extractOne(q,choices,scorer=fuzz.WRatio)
            if m and m[1]>best_score: best_idx,best_score=m[2],m[1]
        return filtered[best_idx]["box"] if best_idx>=0 and best_score>=min_score else None

    def draw_overlay(self, img: Image.Image, *, boxes=None, lines=None, title=""):
        boxes=boxes or []; lines=lines or []
        out=img.copy(); d=ImageDraw.Draw(out)
        try: font=ImageFont.load_default()
        except Exception: font=None
        for (x,y,w,h),color,label in boxes:
            d.rectangle([x,y,x+w,y+h], outline=color, width=2)
            if font and label: d.text((x+2,y-12),label,fill=color,font=font)
        for y,color,label in lines:
            d.line([0,y,img.size[0],y], fill=color, width=2)
            if font and label: d.text((4,y+2),label,fill=color,font=font)
        if font and title: d.text((6,6), title, fill="white", font=font)
        return out
