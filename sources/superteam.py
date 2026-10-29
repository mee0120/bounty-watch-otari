"""Superteam Earn の公開中案件を取得する。

一覧API（サイトが内部で使っているもの）:
  /api/listings?context=all&tab=all&status=open&region=japan ...
  → region=japan で「日本から参加できる案件」に絞られる
詳細API:
  /api/listings/details/{slug}
  → 入賞枠(rewards)、スキル、説明文
"""
import re
import time
from datetime import datetime

from config import SUPERTEAM_ALLOWED_REGIONS, SUPERTEAM_REGION
from http_util import get_json
from models import Bounty

BASE = "https://superteam.fun"
STABLES = {"USDC", "USDG", "USDT", "PYUSD", "USD"}

# 「X上の反響で審査される」案件の目印
# タイトル用（広め）と説明文用（審査基準に出てくる語に限定）を分ける
ENGAGEMENT_TITLE_PAT = re.compile(
    r"\b(thread|tweet|x post|meme|viral|content)\b", re.I)
ENGAGEMENT_DESC_PAT = re.compile(
    r"\b(audience engagement|impressions|quote[- ]tweet|likes|retweets|"
    r"engagement metrics|reach)\b", re.I)
SKILL_TO_CAT = {
    "frontend": "dev", "backend": "dev", "blockchain": "dev", "mobile": "dev",
    "development": "dev", "design": "design", "content": "content",
    "growth": "content", "community": "content", "other": "other",
}


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _category(skills) -> str:
    cats = []
    for s in skills or []:
        name = (s.get("skills") if isinstance(s, dict) else str(s)) or ""
        c = SKILL_TO_CAT.get(name.lower())
        if c and c not in cats:
            cats.append(c)
    # スポンサーが最初に挙げたスキルを主カテゴリとする
    # （「開発が1つでも含まれれば開発」にすると、動画案件が開発扱いになることがあった）
    return cats[0] if cats else ""


def _to_usd(amount, token: str, prices: dict) -> float | None:
    if amount is None:
        return None
    token = (token or "").upper()
    if token in STABLES:
        return float(amount)
    p = prices.get(token)
    return float(amount) * p if p else None


def fetch(prices: dict | None = None) -> list[Bounty]:
    prices = prices or {}
    params = {
        "context": "all", "tab": "all", "category": "All", "status": "open",
        "sortBy": "Date", "order": "asc", "region": SUPERTEAM_REGION, "sponsor": "",
    }
    items = get_json(f"{BASE}/api/listings", params=params)
    if isinstance(items, dict):
        items = items.get("listings") or items.get("data") or []

    out: list[Bounty] = []
    for it in items:
        slug = it.get("slug")
        if not slug:
            continue
        # エージェント専用案件は除外
        if (it.get("agentAccess") or "").upper() == "AGENT_ONLY":
            continue

        detail = {}
        try:
            detail = get_json(f"{BASE}/api/listings/details/{slug}") or {}
            time.sleep(0.5)
        except RuntimeError:
            pass  # 詳細が取れなくても一覧情報だけで続行

        # 地域限定案件（日本から参加できないもの）を除外
        region = (detail.get("region") or "").strip().lower()
        if region and region not in SUPERTEAM_ALLOWED_REGIONS:
            continue

        token = it.get("token") or ""
        rewards = detail.get("rewards") or {}
        winners = len(rewards) if isinstance(rewards, dict) and rewards else 1
        amount = it.get("rewardAmount")
        if amount is None and it.get("maxRewardAsk"):
            amount = it.get("maxRewardAsk")  # 応募制(Project)の上限額

        desc = _strip_html(detail.get("description", ""))
        engagement = bool(
            ENGAGEMENT_TITLE_PAT.search(it.get("title", ""))
            or ENGAGEMENT_DESC_PAT.search(desc)
        )
        count = it.get("_count") or {}

        title = it.get("title", "").strip()
        if it.get("type") == "project":
            # 応募制：ポートフォリオ審査・スポンサーとのやり取りがある
            title = "【応募制】" + title

        out.append(Bounty(
            source="superteam",
            uid=slug,
            title=title,
            url=f"{BASE}/earn/listing/{slug}",
            reward_usd=_to_usd(amount, token, prices),
            deadline=_parse_dt(it.get("deadline")),
            submissions=count.get("Submission"),
            winners=winners,
            category=_category(detail.get("skills")),
            sponsor=((it.get("sponsor") or {}).get("name") or "").strip(),
            token=token,
            engagement_judged=engagement,
            extra={
                "type": it.get("type"),
                "region": detail.get("region"),
                "raw_amount": amount,
            },
        ))
    return out
