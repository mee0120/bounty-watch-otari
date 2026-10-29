"""Superteam Earn の助成金（Grants）。日本から応募できる地域のものだけ。

一覧: /api/grants?context=all&category=All&region=&sponsor=
詳細: /api/grants/{slug}  → region / status / skills
助成金は締切がなく随時審査。賞金は「最大額」で扱う。
"""
import time

from config import SUPERTEAM_ALLOWED_REGIONS
from http_util import get_json
from models import Bounty
from sources.superteam import _category, _to_usd

BASE = "https://superteam.fun"


def fetch(prices: dict | None = None) -> list[Bounty]:
    prices = prices or {}
    items = get_json(f"{BASE}/api/grants",
                     params={"context": "all", "category": "All", "region": "", "sponsor": ""})
    out: list[Bounty] = []
    for it in items or []:
        slug = it.get("slug")
        if not slug:
            continue
        try:
            d = get_json(f"{BASE}/api/grants/{slug}") or {}
            time.sleep(0.5)
        except RuntimeError:
            continue
        if (d.get("status") or "").upper() != "OPEN" or d.get("isPaused") or d.get("isArchived"):
            continue
        region = (d.get("region") or "").strip().lower()
        if region not in SUPERTEAM_ALLOWED_REGIONS:
            continue
        token = it.get("token") or ""
        lo, hi = it.get("minReward") or 0, it.get("maxReward")
        approved = it.get("approvedAmountTotal") or 0
        apps = it.get("totalApplications") or 0
        out.append(Bounty(
            source="st_grant",
            uid=slug,
            title="【助成金】" + (it.get("title") or "").strip(),
            url=f"{BASE}/earn/grants/{slug}",
            reward_usd=_to_usd(hi, token, prices),
            deadline=None,
            submissions=apps,
            winners=1,
            category=_category(d.get("skills")),
            sponsor=((it.get("sponsor") or {}).get("name") or "").strip(),
            token=token,
            extra={"type": "grant",
                   "note": f"{lo:,}〜{hi:,} {token}・応募{apps}件・承認累計{approved:,}"},
        ))
    return out
