# AIQA/runners/run_lobby_matrix.py
import argparse
from pathlib import Path
import sys, yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.web_selenium import WebSeleniumAdapter
from vision.ocr_factory import get_ocr
from vision.yolo_ultra import YOLOTiles
from vision.locator import Locator
from core.menu_runner import run_lobby
from core.product_config import load_operator_currencies

def load_tiles_map(tiles_path: Path):
    y = yaml.safe_load(tiles_path.read_text(encoding="utf-8")) or {}
    tiles = y.get("tiles", {}) or {}
    id_to_name = dict(tiles)
    name_to_id = {v:k for k,v in tiles.items()}
    return name_to_id, id_to_name

def id_number(label: str) -> int:
    try: return int(str(label).lower().replace("edg",""))
    except: return 0

def main():
    prod_dir = ROOT / "products" / "edgelabs_gen2"
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="https://qa.edgelabs.game/FE/lobby/gen2/")
    p.add_argument("--operator", default="WowVegas", choices=["WowVegas","DotCom"])
    p.add_argument("--currencies", default="SC", help="'All' or comma list e.g. SC,WOW or USD,EUR")
    p.add_argument("--games", default="all", help="'all' or comma list of names (must exist in tiles.yaml)")
    p.add_argument("--tiles", default=str(prod_dir / "plans" / "tiles.yaml"))
    p.add_argument("--targets", default=str(prod_dir / "plans" / "targets.yaml"))
    p.add_argument("--actions", default=str(prod_dir / "plans" / "actions.yaml"))
    p.add_argument("--model", default=str(prod_dir / "models" / "tiles_yolov12.pt"))
    p.add_argument("--ocr", default="auto", choices=["auto","tesseract","paddle","easyocr"])
    p.add_argument("--headless", action="store_true")
    p.add_argument("--wait", type=int, default=15)
    args = p.parse_args()

    name_to_id, id_to_name = load_tiles_map(Path(args.tiles))
    operator_currencies = load_operator_currencies(Path(args.actions))
    if args.games.lower() == "all":
        games = [(gid, id_to_name[gid]) for gid in sorted(id_to_name.keys(), key=id_number)]
    else:
        chosen_names = [s.strip() for s in args.games.split(",") if s.strip()]
        games = [(name_to_id[n], n) for n in chosen_names]

    if args.currencies.lower() == "all":
        currs = operator_currencies.get(args.operator, [])
    else:
        currs = [c.strip() for c in args.currencies.split(",") if c.strip()]

    adapter = WebSeleniumAdapter(headless=args.headless)
    try:
        ocr = get_ocr(args.ocr)
    except Exception as e:
        adapter.quit(); raise SystemExit(f"OCR init failed: {e}")

    yolo = YOLOTiles(args.model, conf=0.20)
    targets_cfg = yaml.safe_load(Path(args.targets).read_text(encoding="utf-8"))
    locator = Locator(targets_cfg=targets_cfg, ocr=ocr, yolo=yolo)

    try:
        run_lobby(
            adapter, locator, yolo,
            entry_url=args.url,
            operator=args.operator,
            currencies=currs,
            games=games,
            wait_seconds=args.wait,
            set_home=False,
            player_id=None,
            operator_currencies=operator_currencies,
            log=print
        )
    finally:
        adapter.quit()

if __name__ == "__main__":
    main()
