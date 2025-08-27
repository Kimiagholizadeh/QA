# AIQA/core/product_config.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import yaml

def load_operator_currencies(actions_path: Path) -> Dict[str, List[str]]:
    data = yaml.safe_load(Path(actions_path).read_text(encoding="utf-8")) or {}
    actions = data.get("canonical_menu_actions", {}).get("operator_and_currency", [])
    for act in actions:
        if act.get("name") == "select_currency":
            mapping = act.get("constraints", {}).get("allowed_values_by_operator", {})
            return {str(k): list(v) for k, v in mapping.items()}
    raise KeyError("allowed_values_by_operator not found in actions config")
