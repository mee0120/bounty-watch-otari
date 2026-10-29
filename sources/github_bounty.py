"""GitHub上の懸賞金付きIssue（主にAlgora経由）を取得する。

Algoraは懸賞金の付いたIssueに「💎 Bounty」ラベルを付けるので、
GitHubの検索APIでそのラベルの未解決Issueを探す。
金額はタイトル・ラベル・本文、なければAlgoraボットのコメントから読み取る。
"""
import re
import time
from datetime import datetime, timedelta, timezone

from config import GITHUB_EXCLUDE_REPOS, GITHUB_TOKEN
from http_util import get_json
from models import Bounty

API = "https://api.github.com"
BOUNTY_LABEL = "💎 Bounty"
# 既に誰かが取り組み済み・支払い済みを示すラベル
SKIP_LABELS = {"🙋 bounty claim", "💰 rewarded", "rewarded", "claimed"}
AMOUNT_PAT = re.compile(r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k)?", re.I)
LOOKBACK_DAYS = 45


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _amount(text: str) -> float | None:
    best = None
    for m in AMOUNT_PAT.finditer(text or ""):
        v = float(m.group(1).replace(",", ""))
        if m.group(2):
            v *= 1000
        if 10 <= v <= 100_000:
            best = max(best or 0, v)
    return best


def _amount_from_comments(comments_url: str) -> float | None:
    try:
        comments = get_json(comments_url, params={"per_page": 30},
                            headers=_headers())
    except RuntimeError:
        return None
    for c in comments:
        login = ((c.get("user") or {}).get("login") or "").lower()
        if "algora" in login:
            v = _amount(c.get("body", ""))
            if v:
                return v
    return None


def fetch(known_amounts: dict | None = None) -> list[Bounty]:
    """known_amounts: 既にDBにある {uid: 金額}。コメント取得を省くために使う。"""
    known_amounts = known_amounts or {}
    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).date()
    q = f'label:"{BOUNTY_LABEL}" state:open is:issue no:assignee created:>={since}'
    data = get_json(f"{API}/search/issues",
                    params={"q": q, "sort": "created", "order": "desc",
                            "per_page": 50},
                    headers=_headers())

    out: list[Bounty] = []
    lookups = 0
    for it in data.get("items", []):
        labels = [l.get("name", "") for l in it.get("labels", [])]
        if any(l.lower() in SKIP_LABELS for l in labels):
            continue

        repo = it.get("repository_url", "").replace(f"{API}/repos/", "")
        if repo.lower() in GITHUB_EXCLUDE_REPOS:
            continue

        uid = str(it["id"])
        amount = _amount(it.get("title", "")) or _amount(" ".join(labels)) \
            or _amount(it.get("body") or "")
        if amount is None:
            amount = known_amounts.get(uid)
        # 新規で金額不明なものだけコメントを見に行く（API節約のため1回最大15件）
        if amount is None and lookups < 15:
            amount = _amount_from_comments(it["comments_url"])
            lookups += 1
            time.sleep(0.5)

        out.append(Bounty(
            source="github",
            uid=uid,
            title=it.get("title", "").strip(),
            url=it.get("html_url", ""),
            reward_usd=amount,
            deadline=None,
            # Algoraでは着手宣言(/attempt)がコメントになるので、競争度の目安に使う
            submissions=it.get("comments", 0),
            winners=1,
            category="dev",
            sponsor=repo,
            token="USD",
            engagement_judged=False,
            extra={"labels": labels},
        ))
    return out
