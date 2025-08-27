# AIQA/adapters/web_selenium.py
from __future__ import annotations
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
from PIL import Image
from io import BytesIO
import random
import time

class WebSeleniumAdapter:

    def __init__(self, headless: bool = False, window: str = "1600,1000", page_load_timeout: int = 45):
        self._opts = Options()
        if headless:
            self._opts.add_argument("--headless=new")
        self._opts.add_argument(f"--window-size={window}")
        self._opts.add_argument("--disable-gpu")
        self._opts.add_experimental_option("excludeSwitches", ["enable-logging"])
        self._opts.add_argument("--log-level=3")
        # quiet noisy on-device ML logs on Windows
        self._opts.add_argument("--disable-features=OptimizationGuideModelExecution,TextSafetyClassifier,OnDeviceTranslation")
        self._opts.add_argument("--remote-allow-origins=*")

        self._page_load_timeout = page_load_timeout
        self.d: Optional[webdriver.Chrome] = None
        self._last_url: Optional[str] = None
        self._start_driver()

    # ---------- lifecycle ----------
    def _start_driver(self):
        self.d = webdriver.Chrome(options=self._opts)
        self.d.set_page_load_timeout(self._page_load_timeout)

    def _alive(self) -> bool:
        try:
            _ = self.d.title  # type: ignore[union-attr]
            return True
        except InvalidSessionIdException:
            return False
        except Exception:
            return True

    def _ensure(self):
        if self.d is None or not self._alive():
            try:
                self.quit()
            except Exception:
                pass
            self._start_driver()
            if self._last_url:
                try:
                    self.d.get(self._last_url)  # type: ignore[union-attr]
                    time.sleep(0.8)
                except Exception:
                    pass

    # ---------- navigation ----------
    def open(self, url: str):
        self._ensure()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self._last_url = url
        self.d.get(url)  # type: ignore[union-attr]

    def back(self):
        self._ensure()
        try:
            self.d.back()  # type: ignore[union-attr]
        except (InvalidSessionIdException, WebDriverException):
            self._ensure()
            self.d.execute_script("history.back()")  # type: ignore[union-attr]

    # ---------- screen I/O ----------
    def screenshot(self) -> Image.Image:
        self._ensure()
        return Image.open(BytesIO(self.d.get_screenshot_as_png())).convert("RGB")  # type: ignore[union-attr]

    def dpr(self) -> float:
        self._ensure()
        try:
            return float(self.d.execute_script("return window.devicePixelRatio || 1"))  # type: ignore[union-attr]
        except Exception:
            return 1.0

    # ---------- scrolling ----------
    def scroll_to(self, x_css: int, y_css: int):
        self._ensure()
        self.d.execute_script("window.scrollTo(arguments[0], arguments[1]);", x_css, y_css)  # type: ignore[union-attr]

    def scroll_by(self, dx_css: int, dy_css: int):
        self._ensure()
        self.d.execute_script("window.scrollBy(arguments[0], arguments[1]);", dx_css, dy_css)  # type: ignore[union-attr]

    def page_offset_y(self) -> int:
        self._ensure()
        try:
            return int(self.d.execute_script("return window.pageYOffset || 0;"))  # type: ignore[union-attr]
        except Exception:
            return 0

    def viewport_height(self) -> int:
        self._ensure()
        return int(self.d.execute_script("return window.innerHeight || 0;"))  # type: ignore[union-attr]

    def doc_height(self) -> int:
        self._ensure()
        return int(self.d.execute_script("return document.body.scrollHeight || 0;"))  # type: ignore[union-attr]

    def at_bottom(self) -> bool:
        y = self.page_offset_y()
        return y + self.viewport_height() >= self.doc_height() - 4

    # ---------- interactions ----------
    def click_css(self, x_css: int, y_css: int, repeats: int = 1, jitter: int = 0) -> bool:
        """
        Click using CSS viewport coords (safe for canvas/webgl).
        Sends move→down→up→click; by default SINGLE-CLICK (dropdowns!).
        """
        self._ensure()

        def _once(xx: int, yy: int) -> bool:
            try:
                return bool(self.d.execute_script(
                    """
                    const x = arguments[0] - window.pageXOffset;
                    const y = arguments[1] - window.pageYOffset;
                    const el = document.elementFromPoint(x, y);
                    if (!el) return false;
                    // bring element into focus first
                    el.dispatchEvent(new MouseEvent('mousemove', {bubbles:true, view:window, clientX:x, clientY:y}));
                    el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, view:window, clientX:x, clientY:y}));
                    el.dispatchEvent(new MouseEvent('mouseup',   {bubbles:true, view:window, clientX:x, clientY:y}));
                    el.dispatchEvent(new MouseEvent('click',     {bubbles:true, view:window, clientX:x, clientY:y}));
                    return true;
                    """,
                    xx, yy
                ))  # type: ignore[union-attr]
            except (InvalidSessionIdException, WebDriverException):
                self._ensure()
                return False

        ok = False
        for _ in range(max(1, repeats)):
            dx = random.randint(-jitter, jitter) if jitter else 0
            dy = random.randint(-jitter, jitter) if jitter else 0
            ok = _once(x_css + dx, y_css + dy) or ok
            time.sleep(0.05)
        return ok

    def type_text(self, text: str):
        self._ensure()
        self.d.switch_to.active_element.send_keys(text)  # type: ignore[union-attr]

    def quit(self):
        try:
            if self.d is not None:
                self.d.quit()
        except Exception:
            pass
        finally:
            self.d = None
