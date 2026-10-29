"""AKINDO の WaveHack（Buildathon）。数週間ごとの「Wave」ごとに助成金が配られる形式。

公開API: https://api.akindo.io/public/wave-hacks?page=N  → {"items": [...], "meta": {...}}
  開催中のものが先頭に並び、activeWave を持つ。
  activeWave.submissionDeadline が未来なら「提出受付中」、過ぎていれば審査中。
  審査中のものは次のWaveが始まると submissionDeadline が更新されるので、
  そのときに新着として通知される。
賞金はWave 1回分の助成金額（activeWave.grantAmount）。
助成金はポイント制で複数チームに配分されるため、入賞枠は多めの5、
推定競合は参加者数(builderCount)の15%とする（Waveごとの提出は参加者の一部）。
"""
import time
from datetime import datetime, timezone

from http_util import get_json
from models import Bounty

API = "https://api.akindo.io/public/wave-hacks"
MAX_PAGES = 3
SUBMIT_RATIO = 0.15
MIN_COMPETITORS = 10
USD_LIKE = {"USD", "USDC", "USDT", "USDG", "DAI", "USDFC"}


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch(prices: dict | None = None) -> list[Bounty]:
    prices = prices or {}
    now = datetime.now(timezone.utc)
    out: list[Bounty] = []
    for page in range(1, MAX_PAGES + 1):
        data = get_json(API, params={"page": page})
        items = data.get("items") or []
        if not items:
            break
        active_on_page = 0
        for w in items:
            wave = w.get("activeWave")
            if not wave or not w.get("isPublic", True):
                continue
            active_on_page += 1
            deadline = _dt(wave.get("submissionDeadline"))
            if not deadline or deadline <= now:
                continue  # 審査中（次のWave待ち）

            token = ((w.get("grantDenomination") or {}).get("name") or "").upper()
            amount = float(wave.get("grantAmount") or 0)
            if token in USD_LIKE:
                reward = amount
            else:
                p = prices.get(token)
                reward = amount * p if p else None
            builders = w.get("builderCount") or 0
            est = max(round(builders * SUBMIT_RATIO), MIN_COMPETITORS)
            pool = float(w.get("totalIncomingDepositAmount") or w.get("initialDepositAmount") or 0)
            tags = ", ".join(((t.get("tag") or {}).get("name") or "")
                             for t in w.get("waveHackTags") or [])
            note = (f"Wave{wave.get('waveCount')}・1回{amount:,.0f} {token}"
                    f"（総額{pool:,.0f}）・参加{builders}人（推定競合{est}件）")
            if tags:
                note += f"・{tags}"

            out.append(Bounty(
                source="akindo",
                uid=f"{w.get('id')}:{wave.get('id')}",  # Waveが変わると新着になる
                title=(w.get("title") or "").strip(),
                url=f"https://app.akindo.io/wave-hacks/{w.get('id')}",
                reward_usd=reward,
                deadline=deadline,
                submissions=est,
                winners=5,
                category="dev",
                sponsor=((w.get("community") or {}).get("name") or "").strip(),
                token=token,
                extra={"type": "hackathon", "note": note},
            ))
        if active_on_page == 0:
            break  # これ以降は終了済み
        time.sleep(1)
    return out
