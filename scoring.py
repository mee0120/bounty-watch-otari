"""案件のスコア（0〜100）。高いほど「狙う価値がある」。

考え方:
  期待値 = 総賞金 ÷ max(提出数+1, 入賞枠数)
    → 全員が同じ確率で勝つと仮定した、自分が出した場合の取り分の目安
  これを対数で点数化し、得意分野・審査方法・締切で加減点する。
"""
import math
from datetime import datetime, timezone

from config import FAVORED_CATEGORIES
from models import Bounty


def expected_value(b: Bounty) -> float | None:
    if b.reward_usd is None:
        return None
    subs = b.submissions or 0
    return b.reward_usd / max(subs + 1, b.winners or 1)


def hours_left(b: Bounty, now: datetime | None = None) -> float | None:
    if b.deadline is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (b.deadline - now).total_seconds() / 3600


def score(b: Bounty, now: datetime | None = None) -> float:
    kind = b.extra.get("type")
    ev = expected_value(b)
    if kind == "grant":
        # 助成金は競争ではなく審査制。最大額だけで点数化（$1,000→40, $10,000→60）
        ev = (b.reward_usd or 0) / 10 if b.reward_usd else None
    if ev is None:
        s = 15.0  # 金額不明（GitHubで読み取れなかった等）→ 通知対象にならない程度に低く
    else:
        s = 20 * math.log10(max(ev, 1))  # $100→40, $1,000→60, $10,000→80

    if b.category.lower() in FAVORED_CATEGORIES:
        s += 15
    elif b.category == "content":
        s -= 5

    # 応募制(Project)は選考・やり取りがあり、提出0件でも当選確率は高くない
    if b.extra.get("type") in ("project", "grant"):
        s -= 15

    # GitHubはコメントの多くが着手宣言(/attempt)。多いものは既に競争が激しい
    if b.source == "github" and (b.submissions or 0) >= 10:
        s -= 25

    # ハッカソンは審査基準が重く、1週間〜の作業になりやすい
    if kind == "hackathon":
        s -= 5
    if b.extra.get("upcoming"):
        s -= 10  # 開始前は条件・競合が読めない
    if b.extra.get("feedback"):
        s += 10  # フィードバック・テスト系は作業が軽く狙い目
    if b.extra.get("restricted"):
        s -= 20  # 学生限定・地域限定などの可能性

    if b.engagement_judged:
        s -= 30  # フォロワー数がものを言う案件は大きく減点

    h = hours_left(b, now)
    if h is not None:
        if h < 0:
            s = 0
        elif h < 24:
            s -= 15  # 間に合わない可能性が高い

    return round(max(0.0, min(100.0, s)), 1)
