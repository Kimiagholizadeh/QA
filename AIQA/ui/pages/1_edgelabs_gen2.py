# AIQA/ui/pages/1_edgelabs_gen2.py

from __future__ import annotations
from pathlib import Path
import os
import sys, yaml, streamlit as st

st.set_page_config(page_title="🎮 EdgeLabs Gen 2", layout="wide")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.web_selenium import WebSeleniumAdapter
from vision.ocr_factory import get_ocr
from vision.yolo_ultra import YOLOTiles
from vision.locator import Locator
from core.menu_runner import run_lobby
from core.product_config import load_operator_currencies

PRODUCT_DIR = ROOT / "products" / "edgelabs_gen2"
ACTIONS_PATH = PRODUCT_DIR / "plans" / "actions.yaml"
TILES_PATH   = PRODUCT_DIR / "plans" / "tiles.yaml"
TARGETS_PATH = PRODUCT_DIR / "plans" / "targets.yaml"
MODEL_PATH   = PRODUCT_DIR / "models" / "tiles_yolov12.pt"
DEFAULT_ENTRY_URL = "https://qa.edgelabs.game/FE/lobby/gen2/"

def id_number(label: str) -> int:
    try: return int(str(label).lower().replace("edg",""))
    except: return 0

def load_tiles_map(tiles_path: Path):
    y = yaml.safe_load(tiles_path.read_text(encoding="utf-8")) or {}
    tiles = y.get("tiles", {}) or {}
    id_to_name = dict(tiles)
    name_to_id = {v:k for k,v in tiles.items()}
    return name_to_id, id_to_name

# logging UI
log_box = st.empty()
if "log_lines" not in st.session_state: st.session_state["log_lines"] = []
def log(msg: str):
    st.session_state["log_lines"].append(msg)
    log_box.text("\n".join(st.session_state["log_lines"][-350:]))
def log_clear():
    st.session_state["log_lines"].clear(); log_box.empty()

st.title("🎮 EdgeLabs Gen 2 — Game Menu Test Runner")

try:
    name_to_id, id_to_name = load_tiles_map(TILES_PATH)
    operator_currencies = load_operator_currencies(ACTIONS_PATH)
    targets_cfg = yaml.safe_load(TARGETS_PATH.read_text(encoding="utf-8"))
except Exception as e:
    st.error(str(e)); st.stop()

with st.sidebar:
    st.subheader("Session Settings")
    entry_url = st.text_input("Lobby URL", value=DEFAULT_ENTRY_URL)
    headless = st.checkbox("Headless", value=False)
    wait_seconds = st.number_input("Wait in-game (sec)", min_value=5, max_value=90, value=15, step=1)
    st.caption("The runner will only open each game, wait, then go back.")
    ocr_engine = st.selectbox("OCR Engine", options=["auto","tesseract","paddle","easyocr"], index=0)
    if st.button("Clear Logs"): log_clear()

colA, colB = st.columns(2)
with colA:
    operator = st.radio("Operator", ["WowVegas", "DotCom"], horizontal=True, index=0)
with colB:
    all_currencies = operator_currencies.get(operator, [])
    currency = st.selectbox("Currency", all_currencies, index=0)

st.subheader("Games")
select_all = st.checkbox("Test ALL games (ID order)", value=False)
game_names = list(name_to_id.keys())
defaults = game_names[:6]
chosen_names = game_names if select_all else st.multiselect("Pick games", options=game_names, default=defaults)

run = st.button("▶ Run Test", type="primary")

if run:
    if not MODEL_PATH.exists():
        st.error(f"YOLO model not found at {MODEL_PATH}"); st.stop()
    games = ([(gid, id_to_name[gid]) for gid in sorted((yaml.safe_load(TILES_PATH.read_text())["tiles"]).keys(), key=id_number)]
             if select_all else [(name_to_id[n], n) for n in chosen_names])

    adapter = WebSeleniumAdapter(headless=headless)
    try:
        ocr = get_ocr(ocr_engine)
    except Exception as e:
        adapter.quit(); st.error(f"OCR init failed: {e}"); st.stop()

    yolo = YOLOTiles(str(MODEL_PATH), conf=0.20)  # conf_min=0.75 enforced in strategy
    locator = Locator(targets_cfg=targets_cfg, ocr=ocr, yolo=yolo)

    try:
        run_lobby(
            adapter, locator, yolo,
            entry_url=entry_url,
            operator=operator,
            currencies=[currency],
            games=games,
            wait_seconds=wait_seconds,
            set_home=False,
            player_id=None,
            operator_currencies=operator_currencies,
            log=log
        )
    except Exception as e:
        st.error(f"Run failed: {e}")
    finally:
        adapter.quit()
