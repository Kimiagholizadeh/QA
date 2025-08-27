# AIQA/vision/yolo_ultra.py
from typing import Optional, Tuple
from PIL import Image
import numpy as np

class YOLOTiles:
    """
    Ultralytics YOLO wrapper for game tiles.
    Classes are tile IDs (e.g., 'edg201', ...).
    """
    def __init__(self, model_path: str, conf: float = 0.40, iou: float = 0.5, device: Optional[str] = None):
        from ultralytics import YOLO
        self.model = YOLO(model_path)
        self.conf = conf
        self.iou = iou
        self.device = device

    def _predict(self, img: Image.Image):
        W, H = img.size
        target_w = 1280
        scale = target_w / W if W > target_w else 1.0
        im_small = img.resize((int(W*scale), int(H*scale))) if scale < 1.0 else img
        res = self.model.predict(
            source=np.asarray(im_small),
            conf=self.conf,
            iou=self.iou,
            device=self.device,
            verbose=False
        )[0]
        return res, scale

    def find_id(self, img: Image.Image, class_name: str) -> Optional[Tuple[int,int,int,int,float]]:
        dets = self.find_all(img, allowed={class_name}, conf_min=0.75)
        return (dets[0]["box"][0], dets[0]["box"][1], dets[0]["box"][2], dets[0]["box"][3], dets[0]["conf"]) if dets else None

    def find_all(self, img: Image.Image, allowed: set[str] | None = None, conf_min: float = 0.75):
        res, scale = self._predict(img)
        names = res.names
        out = []
        for b, c, s in zip(res.boxes.xyxy.cpu().numpy(),
                           res.boxes.cls.cpu().numpy(),
                           res.boxes.conf.cpu().numpy()):
            label = names.get(int(c), str(int(c)))
            if allowed and label not in allowed:
                continue
            if float(s) < conf_min:
                continue
            x1,y1,x2,y2 = b
            if scale < 1.0:
                x1,y1,x2,y2 = x1/scale, y1/scale, x2/scale, y2/scale
            out.append({
                "label": label,
                "conf": float(s),
                "box": (int(x1), int(y1), int(x2-x1), int(y2-y1))
            })
        return out
