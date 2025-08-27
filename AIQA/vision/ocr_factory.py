# AIQA/vision/ocr_factory.py
from __future__ import annotations
import os, shutil, importlib
from pathlib import Path

TESS_WIN_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

def _tess_cmd_path() -> str | None:
    cmd = os.environ.get("TESSERACT_CMD") or os.environ.get("TESSERACT_EXE")
    if cmd and Path(cmd).is_file():
        return cmd
    for p in TESS_WIN_PATHS:
        if Path(p).is_file(): return p
    exe = shutil.which("tesseract")
    return exe

def _module_available(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False
def _try_tesseract():
    if not _module_available("pytesseract"):
        raise RuntimeError("Missing package: pytesseract")
    from .ocr_tesseract import OCR
    # Point to the exe if we can find it; rely on TESSDATA_PREFIX for data
    tess_exe = _tess_cmd_path()
    # If we know the standard install, also set TESSDATA_PREFIX if not present
    if tess_exe:
        base = Path(tess_exe).parent
        if "TESSDATA_PREFIX" not in os.environ:
            os.environ["TESSDATA_PREFIX"] = str(base)
    return OCR(tesseract_cmd=tess_exe)


def _try_paddle():
    if not _module_available("paddleocr") or not (_module_available("paddle") or _module_available("paddlepaddle")):
        raise RuntimeError("Missing packages: paddleocr + paddle(paddlepaddle)")
    from .ocr_paddle import OCR
    return OCR(lang="en", use_gpu=False)

def _try_easyocr():
    if not _module_available("easyocr"):
        raise RuntimeError("Missing package: easyocr (and torch)")
    from .ocr_easyocr import OCR
    return OCR(langs=["en"], gpu=False)

def get_ocr(engine: str = "auto"):
    e = (engine or "auto").strip().lower()
    if e in ("tess","tesseract"): return _try_tesseract()
    if e in ("paddle","paddleocr"): return _try_paddle()
    if e in ("easy","easyocr"): return _try_easyocr()

    errors = []
    for ctor in (_try_tesseract, _try_paddle, _try_easyocr):
        try:
            return ctor()
        except Exception as ex:
            errors.append(str(ex))
    raise RuntimeError("No OCR backend is available.\n" + "\n".join(f"- {e}" for e in errors))
