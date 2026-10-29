"""hackathons.solana.com（Solana Foundation 公式ハッカソン）。

JSON APIがないため、一覧ページからスラッグを拾い、各詳細ページの本文から
状態・賞金総額・登録者数・提出数・締切を読み取る。
"""
import html as htmllib
import re
import time
from datetime import datetime, timezone

from http_util import get_text
from models import Bounty

BASE = "https://hackathons.solana.com"
SUBMIT_RATIO = 0.5  # 過去回（Stocklana）は登録1,182人に対し提出604件
SKIP_STATUS = {"COMPLETED", "ENDED", "JUDGING", "SEEKING SPONSORS"}
STATUS_PAT = re.compile(r"All hackathons\s+(SEEKING SPONSORS|[A-Z]+)\b")


def _text(page: str) -> str:
    page = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", page)
    page = re.sub(r"<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", htmllib.unescape(page))


def _num(s: str | None) -> int | None:
    return int(s.replace(",", "")) if s else None


def _find(pat: str, text: str) -> str | None:
    m = re.search(pat, text)
    return m.group(1) if m else None


def parse_detail(slug: str, page: str) -> Bounty | None:
    text = _text(page)
    status = _find(STATUS_PAT.pattern, text) or ""
    if status in SKIP_STATUS:
        return None
    title = _find(r'<meta property="og:title" content="([^"|]+)', page)
    title = (title or slug).strip()
    prize = _num(_find(r"Prize pool \$([\d,]+)", text))
    registered = _num(_find(r"Registered ([\d,]+)", text)) or 0
    subs = _num(_find(r"Submissions ([\d,]+)", text)) or 0
    dl = _find(r"Deadline ([A-Z][a-z]{2} \d{1,2}, \d{4})", text)
    deadline = None
    if dl:
        # 時刻は書かれていないので、その日の終わり(UTC)とみなす
        deadline = datetime.strptime(dl, "%b %d, %Y").replace(
            hour=23, minute=59, tzinfo=timezone.utc)
    est = max(subs, round(registered * SUBMIT_RATIO))
    return Bounty(
        source="solana_hack",
        uid=slug,
        title=title,
        url=f"{BASE}/hackathons/{slug}",
        reward_usd=float(prize) if prize else None,
        deadline=deadline,
        submissions=est,
        winners=3,
        category="dev",
        sponsor="Solana Foundation",
        token="USD",
        extra={"type": "hackathon",
               "note": f"{status}・登録{registered:,}人・提出{subs}件（推定競合{est}件）"},
    )


def fetch() -> list[Bounty]:
    index = get_text(f"{BASE}/hackathons")
    slugs = list(dict.fromkeys(re.findall(r'href="/hackathons/([a-z0-9-]+)"', index)))
    out: list[Bounty] = []
    for slug in slugs:
        try:
            b = parse_detail(slug, get_text(f"{BASE}/hackathons/{slug}"))
        except RuntimeError:
            continue
        if b:
            out.append(b)
        time.sleep(1)
    return out
