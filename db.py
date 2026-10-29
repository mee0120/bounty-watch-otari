"""SQLiteへの保存。案件の重複通知を防ぎ、提出数の推移も残す。"""
import sqlite3
from datetime import datetime, timezone

from config import DB_PATH
from models import Bounty

SCHEMA = """
CREATE TABLE IF NOT EXISTS bounties (
    key TEXT PRIMARY KEY,
    source TEXT, uid TEXT, title TEXT, url TEXT,
    reward_usd REAL, deadline TEXT, submissions INTEGER, winners INTEGER,
    category TEXT, sponsor TEXT, token TEXT, engagement INTEGER,
    score REAL,
    status TEXT DEFAULT 'open',          -- open / gone
    first_seen TEXT, last_seen TEXT,
    notified_new INTEGER DEFAULT 0,
    notified_closing INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS submission_history (
    key TEXT, at TEXT, submissions INTEGER
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    # 後から追加した列（既存DBにも足す）
    cols = {r["name"] for r in con.execute("PRAGMA table_info(bounties)")}
    if "ignored" not in cols:
        con.execute("ALTER TABLE bounties ADD COLUMN ignored INTEGER DEFAULT 0")
        con.commit()
    if "note" not in cols:
        con.execute("ALTER TABLE bounties ADD COLUMN note TEXT")
        con.commit()
    return con


def ignore(con, text: str) -> int:
    """URL・キー・タイトルの一部で一致した案件を非表示にする。件数を返す。"""
    cur = con.execute(
        "UPDATE bounties SET ignored=1 WHERE url=? OR key=? OR uid=?",
        (text, text, text))
    if cur.rowcount == 0:
        cur = con.execute("UPDATE bounties SET ignored=1 WHERE title LIKE ?",
                          (f"%{text}%",))
    con.commit()
    return cur.rowcount


def upsert(con, b: Bounty, sc: float) -> bool:
    """保存して、新規だったらTrueを返す。"""
    now = _now()
    row = con.execute("SELECT submissions FROM bounties WHERE key=?",
                      (b.key,)).fetchone()
    vals = dict(
        key=b.key, source=b.source, uid=b.uid, title=b.title, url=b.url,
        reward_usd=b.reward_usd,
        deadline=b.deadline.isoformat() if b.deadline else None,
        submissions=b.submissions, winners=b.winners, category=b.category,
        sponsor=b.sponsor, token=b.token, engagement=int(b.engagement_judged),
        score=sc, now=now, note=b.extra.get("note"),
    )
    if row is None:
        con.execute(
            """INSERT INTO bounties (key, source, uid, title, url, reward_usd,
               deadline, submissions, winners, category, sponsor, token,
               engagement, score, status, first_seen, last_seen, note)
               VALUES (:key,:source,:uid,:title,:url,:reward_usd,:deadline,
               :submissions,:winners,:category,:sponsor,:token,:engagement,
               :score,'open',:now,:now,:note)""", vals)
    else:
        con.execute(
            """UPDATE bounties SET title=:title, url=:url, reward_usd=:reward_usd,
               deadline=:deadline, submissions=:submissions, winners=:winners,
               category=:category, sponsor=:sponsor, token=:token,
               engagement=:engagement, score=:score, status='open', note=:note,
               last_seen=:now WHERE key=:key""", vals)
    if row is None or row["submissions"] != b.submissions:
        con.execute("INSERT INTO submission_history VALUES (?,?,?)",
                    (b.key, now, b.submissions))
    return row is None


def mark_gone(con, source: str, seen_keys: set[str]) -> None:
    rows = con.execute("SELECT key FROM bounties WHERE source=? AND status='open'",
                       (source,)).fetchall()
    for r in rows:
        if r["key"] not in seen_keys:
            con.execute("UPDATE bounties SET status='gone' WHERE key=?", (r["key"],))


def known_amounts(con, source: str) -> dict:
    rows = con.execute(
        "SELECT uid, reward_usd FROM bounties WHERE source=? AND reward_usd IS NOT NULL",
        (source,)).fetchall()
    return {r["uid"]: r["reward_usd"] for r in rows}


def get_meta(con, k: str, default: str = "") -> str:
    r = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def set_meta(con, k: str, v: str) -> None:
    con.execute("INSERT INTO meta VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (k, v))
