# AIQA/core/state_store.py
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class SessionState:
    operator: str = "WowVegas"
    currency: str = "SC"
    home_button_active: bool = False
    free_games_active: bool = False
    player_id: Optional[str] = None
    opened_games: List[str] = field(default_factory=list)
