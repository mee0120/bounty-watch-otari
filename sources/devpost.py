"""Devpost の開催中・開催予定ハッカソン（オンライン参加のみ）。

公開API: https://devpost.com/api/hackathons?status[]=open&status[]=upcoming&page=N
  → 1ページ9件前後。meta.total_count で総数が分かる。
提出数は一覧にないので、登録者数(registrations_count)の一部を「推定提出数」とする。
Devpostは登録だけして提出しない人が多い（大型AIハッカソンで5〜10%程度）ため、
DoraHacks(0.4)よりかなり低い 0.08 を使う。
締切は "Aug 26 - Oct 30, 2026" のような日付文字列しかなく時刻が不明なので、
早めに見積もるため締切日の 00:00 UTC（日本時間 9:00）とする。
"""
import re
import time
from datetime import datetime, timezone

from http_util import get_json
from models import Bounty

API = "https://devpost.com/api/hackathons"
MAX_PAGES = 15
SUBMIT_RATIO = 0.08
# 登録者が少ない大会（特に開始前）は今後増えるので、推定競合数に下限を設ける
MIN_COMPETITORS_OPEN = 25
MIN_COMPETITORS_UPCOMING = 50
# 賞金の通貨記号 → USDレート（おおよそ）。不明な通貨は金額不明扱い
CURRENCY = {"$": 1.0, "€": 1.08, "£": 1.27, "₹": 0.012, "¥": 0.0067}

FEEDBACK_PAT = re.compile(r"\b(feedback|bug ?bash|beta test)\b", re.I)
# 学生限定・地域限定・企業パートナー限定などの可能性
RESTRICTED_PAT = re.compile(
    r"\b(student|students|university|college|high school|youth|women|"
    r"partner|employees?|internal|india|nigeria|africa|canada|u\.?s\.? only)\b", re.I)


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _prize_usd(raw: str) -> float | None:
    text = _strip_tags(raw)
    m = re.search(r"([$€£₹¥])\s*([0-9][0-9,]*(?:\.[0-9]+)?)", text)
    if not m:
        return None
    rate = CURRENCY.get(m.group(1))
    v = float(m.group(2).replace(",", ""))
    return v * rate if rate and v > 0 else None


def _end_date(period: str) -> datetime | None:
    """'Aug 26 - Oct 30, 2026' / 'Oct 05 - 27, 2026' /
    'Dec 15, 2026 - Jan 10, 2027' / 'Oct 27, 2026' から締切日を取り出す。"""
    if not period:
        return None
    parts = [p.strip() for p in period.split(" - ")]
    start, end = parts[0], parts[-1]
    year = re.search(r"(\d{4})\s*$", end)
    if not year:
        return None
    y = int(year.group(1))
    body = end[:year.start()].rstrip(", ").strip()
    if re.fullmatch(r"\d{1,2}", body):  # 'Oct 05 - 27, 2026' → 月は開始側から
        mon = re.match(r"([A-Za-z]{3})", start)
        if not mon:
            return None
        body = f"{mon.group(1)} {body}"
    try:
        d = datetime.strptime(f"{body} {y}", "%b %d %Y")
    except ValueError:
        return None
    return d.replace(tzinfo=timezone.utc)


def fetch(prices: dict | None = None) -> list[Bounty]:
    out: list[Bounty] = []
    now = datetime.now(timezone.utc)
    for page in range(1, MAX_PAGES + 1):
        data = get_json(API, params={"status[]": ["open", "upcoming"], "page": page})
        items = data.get("hackathons") or []
        if not items:
            break
        for h in items:
            loc = ((h.get("displayed_location") or {}).get("location") or "").strip()
            if loc.lower() != "online":
                continue  # 現地参加のみのものは対象外
            if h.get("invite_only"):
                continue
            state = h.get("open_state") or ""
            if state not in ("open", "upcoming"):
                continue
            deadline = _end_date(h.get("submission_period_dates") or "")
            if deadline and deadline < now:
                continue

            title = (h.get("title") or "").strip()
            themes = ", ".join(t.get("name", "") for t in h.get("themes") or [])
            text = f"{title} {themes} {h.get('organization_name') or ''}"
            regs = h.get("registrations_count") or 0
            floor = MIN_COMPETITORS_UPCOMING if state == "upcoming" else MIN_COMPETITORS_OPEN
            est = max(round(regs * SUBMIT_RATIO), floor)
            counts = h.get("prizes_counts") or {}
            cash = counts.get("cash") or 0
            other = counts.get("other") or 0
            reward = _prize_usd(h.get("prize_amount") or "")
            # 賞金総額には現金以外（クレジット・機材など）も含まれるため、
            # 現金の枠の割合でざっくり割り引く
            if reward and other and cash:
                reward *= cash / (cash + other)
            elif reward and other and not cash:
                reward = None  # 現金の賞金がない

            prefix = "【フィードバック/テスト系】" if FEEDBACK_PAT.search(text) else ""
            note = f"登録{regs:,}人（推定競合{est:,}件）・現金賞{cash}枠"
            if other:
                note += f"＋現金以外{other}枠（賞金額は割引済み）"
            if state == "upcoming":
                note += "・開始前（登録者はこれから増える）"
            note += "・締切時刻と参加可能な国は要確認"
            restricted = bool(RESTRICTED_PAT.search(text))
            if restricted:
                note += "・⚠参加資格に制限がありそう"

            out.append(Bounty(
                source="devpost",
                uid=str(h.get("id")),
                title=prefix + title,
                url=h.get("url") or "",
                reward_usd=reward,
                deadline=deadline,
                submissions=est,
                winners=max(cash, 1),
                category="dev",
                sponsor=(h.get("organization_name") or "").strip(),
                token="USD",
                extra={"type": "hackathon", "note": note, "upcoming": state == "upcoming",
                       "feedback": bool(prefix), "restricted": restricted},
            ))
        total = (data.get("meta") or {}).get("total_count")
        if total is not None and page * max(len(items), 1) >= total:
            break
        time.sleep(1)
    return out
