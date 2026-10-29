"""全ソース共通の案件データ形式。"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Bounty:
    source: str                 # "superteam" / "github" など
    uid: str                    # ソース内で一意なID
    title: str
    url: str
    reward_usd: float | None    # 合計賞金（USD換算、不明ならNone）
    deadline: datetime | None   # UTC
    submissions: int | None     # 提出数（GitHubはコメント数で代用）
    winners: int = 1            # 入賞枠の数
    category: str = ""          # dev / content / design / research など
    sponsor: str = ""
    token: str = ""
    engagement_judged: bool = False  # X上の反響で審査される案件か
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.uid}"
