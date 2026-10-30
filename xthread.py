"""Draft an English X (Twitter) thread of open bounties and hackathons.

The thread is built from the watcher's own data, without an AI model, so every
number in it (prize, deadline, submissions) is what the platform API returned.
The draft is sent to Telegram (or printed); a person reads it and posts it.
Nothing here posts to X.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

SOURCE_NAME = {"superteam": "Superteam Earn", "github": "GitHub", "dorahacks": "DoraHacks",
               "solana_hack": "Solana Hackathons", "st_grant": "Superteam Grants",
               "devpost": "Devpost", "akindo": "AKINDO"}
REPO_URL = os.getenv("X_REPO_URL", "github.com/mee0120/bounty-watch-otari")
MIN_USD = float(os.getenv("X_MIN_USD", "300"))
MAX_DAYS = int(os.getenv("X_MAX_DAYS", "45"))      # only listings closing within N days
REPEAT_DAYS = int(os.getenv("X_REPEAT_DAYS", "6"))  # don't repeat a pick within N days
# Comma-separated words; listings whose title or sponsor contains one are skipped
# (for example events you are entering yourself).
EXCLUDE = [w.strip().lower() for w in os.getenv("X_EXCLUDE", "").split(",") if w.strip()]

URL_RE = re.compile(r"https?://\S+")


def x_len(text: str) -> int:
    """Approximate X's weighted length: URLs count 23, CJK and emoji count 2."""
    n = 0
    for part in URL_RE.split(text):
        n += sum(2 if ord(c) > 0x10FF else 1 for c in part)
    return n + 23 * len(URL_RE.findall(text))


def _days_left(deadline: datetime, now: datetime) -> str:
    d = (deadline - now).total_seconds() / 86400
    if d < 1:
        return f"{int(d * 24)}h left"
    return f"{int(d)} day{'s' if int(d) != 1 else ''} left"


def pick(con, n: int = 5, now: datetime | None = None) -> list:
    now = now or datetime.now(timezone.utc)
    rows = con.execute(
        """SELECT * FROM bounties WHERE status='open' AND ignored=0
           AND engagement=0 AND reward_usd>=? AND deadline IS NOT NULL
           AND deadline>? AND deadline<=? ORDER BY score DESC""",
        (MIN_USD, (now + timedelta(hours=24)).isoformat(),
         (now + timedelta(days=MAX_DAYS)).isoformat())).fetchall()
    recent = {r["k"][len("xthread:"):] for r in con.execute(
        "SELECT k FROM meta WHERE k LIKE 'xthread:%' AND v>?",
        ((now - timedelta(days=REPEAT_DAYS)).isoformat(),))}
    out, per_source = [], {}
    for r in rows:
        text = f"{r['title']} {r['sponsor'] or ''}".lower()
        if r["key"] in recent or any(w in text for w in EXCLUDE):
            continue
        if per_source.get(r["source"], 0) >= 2:  # keep the list varied
            continue
        per_source[r["source"]] = per_source.get(r["source"], 0) + 1
        out.append(r)
        if len(out) >= n:
            break
    return out


def _item(i: int, r, now: datetime) -> str:
    dl = datetime.fromisoformat(r["deadline"])
    if dl.tzinfo is None:
        dl = dl.replace(tzinfo=timezone.utc)
    reward = f"${r['reward_usd']:,.0f}"
    if r["token"] and r["token"].upper() not in ("USD", "USDC", "USDT"):
        reward += f" in {r['token']}"
    # Devpost's prize count is often wrong (one entry can hold many prizes), so
    # the number of winners is shown only for sources that report it reliably.
    if r["winners"] and r["winners"] > 1 and r["source"] not in ("devpost",):
        reward += f" · {r['winners']} winners"
    elif r["source"] == "devpost":
        reward += " in prizes"
    lines = [f"💰 {reward}",
             f"⏳ Closes {dl:%b} {dl.day} ({_days_left(dl, now)})"]
    if r["source"] in ("superteam",) and r["submissions"] is not None:
        lines.append(f"👥 {r['submissions']} submissions so far")
    elif r["submissions"]:
        lines.append(f"👥 {r['submissions']:,} registered so far")
    by = r["sponsor"] or ""
    where = SOURCE_NAME.get(r["source"], r["source"])
    lines.append(f"🏷️ {by + ' · ' if by else ''}{where}")
    tail = "\n".join(lines) + f"\n{r['url']}"
    title = r["title"].strip()
    head = f"{i}/ {title}"
    while x_len(head + "\n" + tail) > 280 and len(title) > 10:
        title = title[:-4].rstrip() + "…"
        head = f"{i}/ {title}"
    return head + "\n" + tail


def build(rows, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    n = len(rows)
    picks = f"{n} pick{'s' if n != 1 else ''}"
    first = (f"1/ Open dev bounties and hackathons worth a look this week ({now:%b} {now.day}) 🛠️\n\n"
             f"{picks} still open, with prize, deadline and how many people "
             f"have entered so far 🧵")
    tweets = [first]
    tweets += [_item(i + 2, r, now) for i, r in enumerate(rows)]
    tweets.append(
        f"{n + 2}/ That's this week's list. Always check the official page before you "
        f"build: rules and deadlines can change.\n\n"
        f"I pull these with a small open-source watcher: {REPO_URL}\n"
        f"Follow for next week's list.")
    return tweets


def draft(con, n: int = 5, mark: bool = True) -> str:
    now = datetime.now(timezone.utc)
    rows = pick(con, n, now)
    if not rows:
        return "No listings matched for this week's thread."
    tweets = build(rows, now)
    if mark:
        con.executemany("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)",
                        [(f"xthread:{r['key']}", now.isoformat()) for r in rows])
        con.commit()
    parts = []
    for t in tweets:
        warn = "" if x_len(t) <= 280 else "  ⚠️ over 280"
        parts.append(f"{t}\n[{x_len(t)}/280]{warn}")
    return ("📝 X thread draft (check, then post by hand)\n\n"
            + "\n\n────────\n\n".join(parts))
