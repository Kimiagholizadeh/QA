# AIQA/core/menu_runner.py
from __future__ import annotations
import time
from typing import Sequence, Optional, Iterable

from .strategies import set_operator_via_ocr, set_currency_via_ocr, open_tile_by_id, return_to_lobby

class MenuBehaviorRunner:
    def __init__(self, adapter, locator, yolo, *, id_to_name: dict[str,str], operator_currencies: dict[str,list[str]], log=print):
        self.adapter, self.locator, self.yolo = adapter, locator, yolo
        self.id_to_name = id_to_name
        self.operator_currencies = operator_currencies
        self.log = log

    def set_operator_and_currency(self, operator: str, currency: str) -> tuple[bool,bool]:
        ok_op = set_operator_via_ocr(self.adapter, self.locator, desired=operator, log=self.log)
        time.sleep(0.25)
        ok_cu = set_currency_via_ocr(self.adapter, self.locator, operator=operator, desired=currency, log=self.log)
        # wait for lobby header to re-appear
        for _ in range(40):
            img = self.adapter.screenshot()
            if self.locator.locate(img, "select_a_game_header", {"min_score": 70}):
                break
            time.sleep(0.4)
        return ok_op, ok_cu

    def open_game_by_id(self, tile_id: str, *, wait_seconds: int = 15) -> bool:
        ok = open_tile_by_id(self.adapter, self.yolo, tile_id=tile_id, conf_min=0.75, log=self.log)
        if not ok: return False
        time.sleep(wait_seconds)
        return_to_lobby(self.adapter, self.locator)
        # ensure lobby is back
        for _ in range(60):
            img = self.adapter.screenshot()
            if self.locator.locate(img, "select_a_game_header", {"min_score": 70}):
                break
            time.sleep(0.5)
        return True

    def run_matrix(self, operators: Iterable[str], currency_mode: str, single_currency_by_operator: Optional[dict[str,str]],
                   games_edg_ids: Sequence[str], *, wait_seconds: int, stop_on_fail: bool=False):
        for op in operators:
            cur_list = (self.operator_currencies.get(op, []) if currency_mode=="All"
                        else [ (single_currency_by_operator or {}).get(op) ])
            cur_list = [c for c in cur_list if c]
            for i, cur in enumerate(cur_list, 1):
                self.log(f"\n=== {op} / {cur} [{i}/{len(cur_list)}] ===")
                ok_op, ok_cu = self.set_operator_and_currency(op, cur)
                self.log(f"select_one_operator -> {ok_op}")
                self.log(f"select_currency     -> {ok_cu}")
                if stop_on_fail and (not ok_op or not ok_cu): return
                for edg_id in games_edg_ids:
                    pretty = self.id_to_name.get(edg_id, edg_id)
                    self.log(f"  • {pretty} ({edg_id})")
                    ok = self.open_game_by_id(edg_id, wait_seconds=wait_seconds)
                    self.log(f"    ↳ open -> {ok}")

def run_lobby(adapter, locator, yolo, *, entry_url: str, operator: str,
              currencies: Sequence[str], games: Sequence[tuple[str,str]],
              wait_seconds: int = 15, set_home: bool = False, player_id: Optional[str] = None,
              operator_currencies: Optional[dict[str, list[str]]] = None, log=print) -> None:

    id_to_name = {gid: name for gid, name in games}
    runner = MenuBehaviorRunner(adapter, locator, yolo,
                                id_to_name=id_to_name,
                                operator_currencies=operator_currencies or {},
                                log=log)

    log(f"Navigating to {entry_url}")
    adapter.open(entry_url)
    time.sleep(1.8)

    # home toggle & player id omitted for now per your request (only open+back)

    for cur in currencies:
        log(f"\n=== {operator} / {cur} ===")
        ok_op, ok_cu = runner.set_operator_and_currency(operator, cur)
        log(f"select_one_operator -> {ok_op}")
        log(f"select_currency     -> {ok_cu}")
        for gid, _ in games:
            runner.log(f"  • {id_to_name.get(gid, gid)} ({gid})")
            ok = runner.open_game_by_id(gid, wait_seconds=wait_seconds)
            runner.log(f"    ↳ open -> {ok}")

    log("\n✅ Finished.")
