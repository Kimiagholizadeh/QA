# AIQA/vision/locator.py
from typing import Any, Dict, Optional
from PIL import Image

def _center(box): x,y,w,h=box; return (x+w//2, y+h//2)

class Locator:
    """
    Text-first locator with transient options via temp_option(text).
    Also supports YOLO IDs when key startswith 'tile:'.
    """
    def __init__(self, targets_cfg: Dict[str, Any], ocr, yolo=None):
        self.cfg = targets_cfg or {"targets": {}}
        self.ocr = ocr
        self.yolo = yolo
        self._temp: Dict[str, Dict[str, Any]] = {}

    def temp_option(self, text: str):
        if not text: return
        self._temp[f"__option__:{text}"] = {"type": "text", "synonyms": [text]}

    def _get_target(self, key: str) -> Optional[Dict[str, Any]]:
        return self._temp.get(key) or (self.cfg.get("targets") or {}).get(key)

    def locate(self, img: Image.Image, key: str, ctx: dict) -> Optional[Dict[str, Any]]:
        # YOLO tiles via key prefix tile:<id>
        if key.startswith("tile:") and self.yolo:
            cls_name = key.split(":",1)[1]
            det = self.yolo.find_id(img, cls_name)
            if det:
                x,y,w,h,score = det
                return {"box": (x,y,w,h), "strategy": "yolo", "confidence": score}
            return None

        t = self._get_target(key)
        if not t: return None
        syn = t.get("synonyms", [key])

        min_score  = ctx.get("min_score", 75)
        roi        = ctx.get("roi")
        exact      = ctx.get("exact", False)
        avoid_below= ctx.get("avoid_below")
        avoid_above= ctx.get("avoid_above")

        box = self.ocr.find(img, syn, min_score=min_score, roi=roi,
                            exact=exact, avoid_below=avoid_below, avoid_above=avoid_above)
        if box:
            return {"box": box, "strategy": "ocr", "confidence": 0.9}
        return None
