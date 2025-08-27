# AIQA/core/strategies.py
from __future__ import annotations
import time
from typing import Iterable, Optional, Tuple

# adapter API expected:
#   screenshot() -> PIL.Image.Image
#   click_css(x,y,repeats=1,jitter=0) -> bool
#   scroll_to(x,y) / scroll_by(dx,dy)
#   dpr() -> float
#   at_bottom() -> bool
#   page_offset_y() -> int
#   viewport_height() -> int
#   back() -> None
#
# locator API expected:
#   locate(img, key, ctx: dict) -> {"box": (x,y,w,h), ...} | None
#   temp_option(text: str) -> None
#
# yolo API expected:
#   find_all(img, allowed: set[str] | None, conf_min: float) -> [{"label": str, "conf": float, "box": (x,y,w,h)}, ...]


# ----------------------------
# Basic geometry & click utils
# ----------------------------
def _center(box: Tuple[int,int,int,int]) -> Tuple[int,int]:
    x, y, w, h = box
    return (x + w // 2, y + h // 2)

def _css_center(adapter, box: Tuple[int,int,int,int]) -> Tuple[int,int]:
    cx, cy = _center(box)
    dpr = adapter.dpr() or 1.0
    return int(cx / dpr), int(cy / dpr)

def _scroll_into(adapter, cx_css: int, cy_css: int, pad_x: int = 800, pad_y: int = 400) -> None:
    adapter.scroll_to(max(0, cx_css - pad_x), max(0, cy_css - pad_y))

def _click_box_center(adapter, box: Tuple[int,int,int,int], *, jitter: int = 1, repeats: int = 1) -> bool:
    x_css, y_css = _css_center(adapter, box)
    _scroll_into(adapter, x_css, y_css)
    return adapter.click_css(x_css, y_css, repeats=repeats, jitter=jitter)

def _wait_until(adapter, predicate, *, timeout_s: float = 3.0, interval_s: float = 0.15) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if predicate():
            return True
        time.sleep(interval_s)
    return False

def _variants(s: str) -> list[str]:
    t = str(s or "").strip()
    out = [t, t.upper(), t.lower(), t.capitalize()]
    # add spaced CamelCase (WowVegas -> Wow Vegas)
    spaced = "".join([(" " + c if c.isupper() else c) for c in t]).strip()
    if spaced != t:
        out += [spaced, spaced.upper(), spaced.lower(), spaced.capitalize()]
    # ".com" family
    if t.lower() in ("dotcom", "dot com"):
        out += [".COM", ".com", ".COM Currency", "DotCom", "Dot Com"]
    return list(dict.fromkeys(out))

def _currency_variants(s: str) -> list[str]:
    base = [s, s.upper(), s.lower(), s.capitalize()]
    # O/0 confusion sometimes in OCR
    swap = s.replace("O", "0").replace("o", "0").upper()
    if swap != s:
        base.append(swap)
    return list(dict.fromkeys(base))


# ----------------------------
# OCR helpers (via locator)
# ----------------------------
def _find_text_box(adapter, locator, text: str, *,
                   exact: bool = True, min_score: int = 75,
                   roi=None, avoid_below: Optional[int] = None, avoid_above: Optional[int] = None):
    """
    Ask the Locator to find `text`. We pass an optional ctx; if the Locator ignores it,
    this still works as a global search.
    """
    img = adapter.screenshot()
    locator.temp_option(text)
    ctx = {"roi": roi, "exact": exact, "min_score": min_score,
           "avoid_below": avoid_below, "avoid_above": avoid_above}
    return locator.locate(img, f"__option__:{text}", ctx)

def _click_text_once(adapter, locator, text: str, **kw) -> bool:
    hit = _find_text_box(adapter, locator, text, **kw)
    return bool(hit and _click_box_center(adapter, hit["box"], jitter=1, repeats=1))


# ---------------------------------------
# Guards and ROIs around labels/values UI
# ---------------------------------------
def _guard_y(adapter, locator) -> Optional[int]:
    """Find a y-threshold above the 'Create/Cancel campaign' panels to avoid clicking inside them."""
    img = adapter.screenshot()
    ys = []
    for t in ("Create Free Game Campaign", "Cancel Free Game Campaign"):
        locator.temp_option(t)
        hit = locator.locate(img, f"__option__:{t}", {"min_score": 72, "exact": True})
        if hit:
            ys.append(hit["box"][1])
    return min(ys) if ys else None

def _value_roi_right_of_label(label_box, img_size, *, width=620, height=72, dy=2):
    """Tight ROI where the currently selected value typically appears (to the right of the label)."""
    W, H = img_size
    x, y, w, h = label_box
    rx = min(max(0, x + w + 12), max(0, W - 1))
    ry = max(0, y - 10 + dy)
    rw = min(width, max(40, W - rx))
    rh = min(height, max(30, H - ry))
    return (rx, ry, rw, rh)

def _dropdown_roi_below_value(value_box, img_size, *, pad_l=220, pad_r=320, pad_t=6, pad_b=560):
    """ROI below the CURRENT value where dropdown items usually render."""
    W, H = img_size
    x, y, w, h = value_box
    rx = max(0, x - pad_l)
    ry = max(0, y + h + pad_t)
    rw = min(W - rx, w + pad_l + pad_r)
    rh = min(H - ry, pad_b)
    return (rx, ry, rw, rh)


# -------------------------------------
# Operator normalization & synonym sets
# -------------------------------------
_OPERATOR_LABEL_KEY = "operator_label"
_CURRENCY_LABEL_KEY = "currency_label"

_OPERATOR_SYNONYMS = {
    "WowVegas": ["WowVegas", "WOWVEGAS", "Wow Vegas"],
    "DotCom":   [".COM Currency", "DotCom", ".com", "DOTCOM", "dotcom", "Dot Com", ".COM"],
}

def _canonical_operator(name: str) -> str:
    n = (name or "").strip().lower()
    if n in ("wowvegas", "wow vegas"):
        return "WowVegas"
    if ".com" in n or "dotcom" in n or "dot com" in n:
        return "DotCom"
    # passthrough if already canonical
    return name

def _operator_variants_for(desired_canonical: str) -> list[str]:
    return _OPERATOR_SYNONYMS.get(desired_canonical, [desired_canonical])


# -----------------------------------
# Verify selected value near a label
# -----------------------------------
def _verify_selected_value(adapter, locator, *, label_key: str, expected: str, min_score=72) -> bool:
    img = adapter.screenshot()
    lab = locator.locate(img, label_key, {"min_score": 70})
    if not lab:
        return False
    roi = _value_roi_right_of_label(lab["box"], img.size)

    if label_key == _OPERATOR_LABEL_KEY:
        for v in _operator_variants_for(_canonical_operator(expected)):
            if _find_text_box(adapter, locator, v, exact=True, min_score=min_score, roi=roi):
                return True
        return False

    # currency: exact match variants
    for v in _variants(expected):
        if _find_text_box(adapter, locator, v, exact=True, min_score=min_score, roi=roi):
            return True
    return False


# --------------------------------------------
# Operator / Currency via OCR + single-click
# --------------------------------------------
def set_operator_via_ocr(adapter, locator, *, desired: str, log=print) -> bool:
    """
    Open operator dropdown by clicking the current value once; then pick `desired`.
    Verification accepts operator synonyms (DotCom/.COM/etc).
    """
    desired_can = _canonical_operator(desired)
    pick_variants = _operator_variants_for(desired_can)

    img = adapter.screenshot()
    lab = locator.locate(img, _OPERATOR_LABEL_KEY, {"min_score": 70})
    if not lab:
        log("[operator] label not found"); return False

    gy = _guard_y(adapter, locator)
    current_opts = _OPERATOR_SYNONYMS["WowVegas"] + _OPERATOR_SYNONYMS["DotCom"]

    def _open_dropdown() -> bool:
        for t in current_opts:
            if _click_text_once(adapter, locator, t, exact=True, min_score=70, avoid_below=gy):
                return True
        # fallback: click to the right/below the label
        cx, cy = _css_center(adapter, lab["box"])
        _scroll_into(adapter, cx + 200, cy + 36)
        return adapter.click_css(cx + 200, cy + 36, repeats=1)

    for attempt in range(1, 4):
        opened = _open_dropdown()
        time.sleep(0.35)

        # Build ROI under current value (if we can detect it), else under the label
        img2 = adapter.screenshot()
        value_roi = _value_roi_right_of_label(lab["box"], img2.size)
        curr_box = None
        for t in current_opts:
            hit = _find_text_box(adapter, locator, t, exact=True, min_score=68, roi=value_roi, avoid_below=gy)
            if hit:
                curr_box = hit["box"]
                break
        roi = _dropdown_roi_below_value(curr_box if curr_box else lab["box"], img2.size)

        picked = False
        for v in pick_variants:
            if _click_text_once(adapter, locator, v, exact=True, min_score=70, roi=roi):
                picked = True
                break
        if not picked:
            # fallback to full-screen
            for v in pick_variants:
                if _click_text_once(adapter, locator, v, exact=True, min_score=70):
                    picked = True
                    break

        ok = picked and _wait_until(
            adapter,
            lambda: _verify_selected_value(adapter, locator, label_key=_OPERATOR_LABEL_KEY, expected=desired_can),
            timeout_s=2.5,
        )
        log(f"[operator] attempt={attempt} open={opened} pick={picked} verified={ok}")
        if ok:
            return True
        time.sleep(0.25)

    return False


def set_currency_via_ocr(adapter, locator, *, desired: str, log=print) -> bool:
    """
    Open currency dropdown by single-clicking the current value (SC/WOW/USD/EUR/GBP),
    then pick the exact `desired` value. Verify the selection next to the label.
    """
    img = adapter.screenshot()
    lab = locator.locate(img, _CURRENCY_LABEL_KEY, {"min_score": 70})
    if not lab:
        log("[currency] label not found"); return False

    gy = _guard_y(adapter, locator)
    current_candidates = ["SC", "WOW", "USD", "EUR", "GBP"]

    def _open_dropdown() -> Tuple[bool, Optional[Tuple[int,int,int,int]]]:
        for t in current_candidates:
            hit = _find_text_box(adapter, locator, t, exact=True, min_score=68, avoid_below=gy)
            if hit and _click_box_center(adapter, hit["box"], jitter=0, repeats=1):
                return True, hit["box"]
        # fallback near label
        cx, cy = _css_center(adapter, lab["box"])
        _scroll_into(adapter, cx + 200, cy + 36)
        ok = adapter.click_css(cx + 200, cy + 36, repeats=1)
        return ok, None

    for attempt in range(1, 4):
        opened, curr_box = _open_dropdown()
        time.sleep(0.35)

        img2 = adapter.screenshot()
        if not curr_box:
            # try to rediscover current box to shape ROI
            value_roi = _value_roi_right_of_label(lab["box"], img2.size)
            for t in current_candidates:
                hit = _find_text_box(adapter, locator, t, exact=True, min_score=68, roi=value_roi, avoid_below=gy)
                if hit:
                    curr_box = hit["box"]
                    break

        roi = _dropdown_roi_below_value(curr_box if curr_box else lab["box"], img2.size)

        picked = False
        for v in _currency_variants(desired):
            if _click_text_once(adapter, locator, v, exact=True, min_score=68, roi=roi):
                picked = True
                break
        if not picked:
            # fallback to full-screen
            for v in _currency_variants(desired):
                if _click_text_once(adapter, locator, v, exact=True, min_score=68):
                    picked = True
                    break

        ok = picked and _wait_until(
            adapter,
            lambda: _verify_selected_value(adapter, locator, label_key=_CURRENCY_LABEL_KEY, expected=desired),
            timeout_s=2.5,
        )
        log(f"[currency] attempt={attempt} open={opened} pick={picked} verified={ok} desired={desired}")
        if ok:
            return True
        time.sleep(0.25)

    return False


# --------------------------
# Generic target/text clicks
# --------------------------
def click_target(adapter, locator, key: str, *, min_score: int = 72) -> bool:
    img = adapter.screenshot()
    hit = locator.locate(img, key, {"min_score": min_score})
    return bool(hit and _click_box_center(adapter, hit["box"], jitter=1, repeats=1))

def click_text(adapter, locator, text: str, synonyms: Optional[Iterable[str]] = None, min_score: int = 75) -> bool:
    img = adapter.screenshot()
    # try synonyms first
    if synonyms:
        for s in synonyms:
            locator.temp_option(s)
            hit = locator.locate(img, f"__option__:{s}", {"min_score": min_score})
            if hit:
                return _click_box_center(adapter, hit["box"], jitter=1, repeats=1)
    locator.temp_option(text)
    hit = locator.locate(img, f"__option__:{text}", {"min_score": min_score})
    return bool(hit and _click_box_center(adapter, hit["box"], jitter=1, repeats=1))

def text_visible(adapter, locator, text: str, synonyms: Optional[Iterable[str]] = None) -> bool:
    img = adapter.screenshot()
    if synonyms:
        for s in synonyms:
            locator.temp_option(s)
            if locator.locate(img, f"__option__:{s}", {"min_score": 72}):
                return True
    locator.temp_option(text)
    return bool(locator.locate(img, f"__option__:{text}", {"min_score": 72}))


# --------------------------------------
# YOLOv12 tile open (conf >= 0.75) logic
# --------------------------------------
def _in_lobby(adapter, locator) -> bool:
    img = adapter.screenshot()
    return bool(locator.locate(img, "select_a_game_header", {"min_score": 70}))

def open_tile_by_id(adapter, locator, yolo, *, tile_id: str, conf_min: float = 0.75,
                    step: int = 520, settle: float = 0.22, max_bottom_passes: int = 2, log=print) -> bool:
    """
    Detect-first loop. On detection:
      1) single click center,
      2) verify lobby header disappears,
      3) if still in lobby, double-click and a slight lower-offset click,
      4) if not found, scroll a bit and retry; reset to top once, then give up.
    """
    bottom_passes = 0
    tried_reset_top = False

    while True:
        dets = yolo.find_all(adapter.screenshot(), allowed={tile_id}, conf_min=conf_min)
        if dets:
            dets.sort(key=lambda d: d["conf"], reverse=True)
            best = dets[0]
            log(f"[yolo] {best['label']} conf={best['conf']:.2f}")
            box = best["box"]

            # 1) click once
            _click_box_center(adapter, box, jitter=2, repeats=1)
            if _wait_until(adapter, lambda: not _in_lobby(adapter, locator), timeout_s=3.0):
                return True

            # 2) double click
            _click_box_center(adapter, box, jitter=1, repeats=2)
            if _wait_until(adapter, lambda: not _in_lobby(adapter, locator), timeout_s=2.0):
                return True

            # 3) slight lower offset
            x, y, w, h = box
            lower_box = (x, y + max(8, h // 6), w, h)
            _click_box_center(adapter, lower_box, jitter=1, repeats=1)
            if _wait_until(adapter, lambda: not _in_lobby(adapter, locator), timeout_s=2.0):
                return True

            # If still in lobby, allow the loop to continue (tiles may have reflowed)
        else:
            y_before = adapter.page_offset_y()
            if adapter.at_bottom():
                bottom_passes += 1
                if not tried_reset_top:
                    adapter.scroll_to(0, 0)
                    tried_reset_top = True
                    time.sleep(settle)
                    continue
                if bottom_passes >= max_bottom_passes:
                    return False
            else:
                adapter.scroll_by(0, step)

            time.sleep(settle)
            if adapter.page_offset_y() == y_before:
                # scroll didn't move; bail
                return False


# --------------------------------------
# Return to lobby (no game testing yet)
# --------------------------------------
def return_to_lobby(adapter, locator) -> None:
    """Try explicit text buttons first (Home/Lobby/Back/Menu), else browser back."""
    for txt in ("Home", "Lobby", "Back", "Menu"):
        if _click_text_once(adapter, locator, txt, exact=True, min_score=72):
            time.sleep(0.6)
            return
    adapter.back()
    time.sleep(0.6)


# ------------------------------------------------
# Compatibility helpers for older Engine mappings
# ------------------------------------------------
def click_label_then_option(adapter, locator, label_key: str, option_text: str, log=print) -> bool:
    """
    Compatibility wrapper:
      - If operator label, route to set_operator_via_ocr().
      - If currency label, route to set_currency_via_ocr().
      - Otherwise try a generic open-then-pick based on label position.
    """
    lk = (label_key or "").lower()
    if "operator" in lk:
        return set_operator_via_ocr(adapter, locator, desired=option_text, log=log)
    if "currency" in lk:
        return set_currency_via_ocr(adapter, locator, desired=option_text, log=log)

    # Generic fallback (single click to the right of label, then pick by exact text)
    img = adapter.screenshot()
    lab = locator.locate(img, label_key, {"min_score": 70})
    if not lab:
        return False
    cx, cy = _css_center(adapter, lab["box"])
    _scroll_into(adapter, cx + 200, cy + 36)
    adapter.click_css(cx + 200, cy + 36, repeats=1)
    time.sleep(0.3)
    return _click_text_once(adapter, locator, option_text, exact=True, min_score=70)

def select_game_by_id(adapter, locator, game_id: str, yolo=None, log=print) -> bool:
    """
    Backward-compat wrapper. If YOLO is provided, use it to open a tile by id.
    """
    if yolo is None:
        log("[select_game_by_id] YOLO model missing")
        return False
    return open_tile_by_id(adapter, locator, yolo, tile_id=game_id, conf_min=0.75, log=log)
