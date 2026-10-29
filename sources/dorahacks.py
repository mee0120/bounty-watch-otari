"""DoraHacks の開催中ハッカソン／バウンティ（オンライン参加のみ）。

公開API: https://dorahacks.io/api/v1/hub/hackathons?page=N&page_size=24
  → 新しい順。venue_form が "Virtual" ならオンライン、"IRL" は現地参加。
提出数(buidls_count)は締切まで0のまま隠されていることが多いので、
参加登録者数(hackers_count)の4割を「推定提出数」として競争率に使う
（過去の終了済みハッカソンで提出÷登録がおよそ0.4だったため）。
"""
import re
import time
from datetime import datetime, timezone

from http_util import get_json
from models import Bounty

API = "https://dorahacks.io/api/v1/hub/hackathons"
USD_LIKE = {"USD", "USDC", "USDT", "USDG", "DAI", ""}
MAX_PAGES = 6
SUBMIT_RATIO = 0.4

FEEDBACK_PAT = re.compile(r"\b(feedback|bug ?bash|bug bounty|testnet|beta test|ux)\b", re.I)
RESTRICTED_PAT = re.compile(r"\b(youth|student|university|college|women|africa|india|bharat|nigeria)\b", re.I)


def _to_usd(amount, token: str, prices: dict) -> float | None:
    if not amount:
        return None
    token = (token or "").upper()
    if token in USD_LIKE:
        return float(amount)
    p = prices.get(token)
    return float(amount) * p if p else None


def fetch(prices: dict | None = None) -> list[Bounty]:
    prices = prices or {}
    now = datetime.now(timezone.utc).timestamp()
    out: list[Bounty] = []
    for page in range(1, MAX_PAGES + 1):
        data = get_json(API, params={"page": page, "page_size": 24})
        results = data.get("results") or []
        alive = 0
        for r in results:
            end = r.get("timeline_end") or 0
            if end <= now or r.get("winner_announced"):
                continue
            alive += 1
            if r.get("venue_form") != "Virtual":
                continue  # 現地参加のみのものは対象外

            title = (r.get("title") or "").strip()
            tags = r.get("tags") or ""
            text = f"{title} {tags}"
            hackers = r.get("hackers_count") or 0
            buidls = r.get("buidls_count") or 0
            est = max(buidls, round(hackers * SUBMIT_RATIO))
            slug = r.get("uname") or str(r.get("id"))
            start = r.get("timeline_start") or 0

            prefix = ""
            if FEEDBACK_PAT.search(text):
                prefix = "【フィードバック/テスト系】"
            note = f"登録{hackers}人・提出{buidls}件（推定競合{est}件）"
            if start > now:
                note += f"・開始前（{datetime.fromtimestamp(start, timezone.utc):%m/%d}開始）"
            restricted = bool(RESTRICTED_PAT.search(text))
            if restricted:
                note += "・⚠参加資格に制限がありそう"

            out.append(Bounty(
                source="dorahacks",
                uid=slug,
                title=prefix + title,
                url=f"https://dorahacks.io/hackathon/{slug}/detail",
                reward_usd=_to_usd(r.get("bonus_price"), r.get("bonus_token"), prices),
                deadline=datetime.fromtimestamp(end, timezone.utc),
                submissions=est,
                winners=3,  # 入賞枠は詳細ページにしかないので、一般的な3枠と仮定
                category="dev",
                sponsor=((r.get("owner") or {}).get("name") or r.get("ecosystem") or "").strip(),
                token=r.get("bonus_token") or "",
                extra={"type": "hackathon", "note": note,
                       "feedback": bool(prefix), "restricted": restricted},
            ))
        if not results or alive == 0:
            break  # これ以降は終了済みばかり
        time.sleep(1)
    return out
