"""Read-only MCP server over the watcher's own database.

Otari connects to it during an analysis (``mcp_servers`` in the request), so the
analyst model can look up how similar past opportunities went and what this
user has already skipped, without the app pasting the whole history into the
prompt.

Run:  python3 -m ai.mcp_server            (listens on 0.0.0.0:$MCP_PORT)
URL:  http://<server>:$MCP_PORT/mcp/<MCP_PATH_SECRET>

The path secret keeps casual scanners out. Every tool is read-only. The data
is listing metadata collected by the watcher plus each user's own committed
schedule from ai/users.json; no keys or credentials are ever returned.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402  (loads .env)

from mcp.server.fastmcp import FastMCP  # noqa: E402

PORT = int(os.getenv("MCP_PORT", "8787"))
SECRET = os.getenv("MCP_PATH_SECRET", "")
if len(SECRET) < 16:
    raise SystemExit("Set MCP_PATH_SECRET (16+ random characters) in .env")

mcp = FastMCP("bounty-history", host="0.0.0.0", port=PORT,
              streamable_http_path=f"/mcp/{SECRET}", stateless_http=True,
              json_response=True)


def _con():
    con = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _row(r) -> dict:
    return {k: r[k] for k in ("title", "source", "sponsor", "reward_usd", "deadline",
                              "submissions", "winners", "status", "url")}


@mcp.tool()
def search_history(query: str, limit: int = 5) -> list[dict]:
    """Find past and current opportunities whose title or sponsor matches the query
    (for example a sponsor name or a theme such as "perps" or "AI agent").
    Returns reward, deadline, submission count, number of winners and whether the
    listing is still open, so you can compare competition and prize levels."""
    limit = max(1, min(int(limit), 10))
    words = [w for w in query.split() if len(w) > 1][:4] or [query]
    where = " OR ".join("(title LIKE ? OR sponsor LIKE ?)" for _ in words)
    args: list = []
    for w in words:
        args += [f"%{w}%", f"%{w}%"]
    with _con() as con:
        rows = con.execute(
            f"SELECT * FROM bounties WHERE {where} ORDER BY last_seen DESC LIMIT ?",
            (*args, limit)).fetchall()
    return [_row(r) for r in rows]


@mcp.tool()
def user_history(user_id: str, limit: int = 10) -> dict:
    """Return what this user already decided: opportunities they marked as not
    relevant, and the verdicts of earlier analyses. Use it to avoid recommending
    things the user has already rejected."""
    limit = max(1, min(int(limit), 20))
    with _con() as con:
        ignored = [r["title"] for r in con.execute(
            "SELECT title FROM bounties WHERE ignored=1 ORDER BY last_seen DESC LIMIT ?",
            (limit,))]
        try:
            past = [dict(r) for r in con.execute(
                """SELECT b.title, a.verdict, a.fit FROM ai_reports a
                   JOIN bounties b ON b.key=a.key WHERE a.user_id=?
                   ORDER BY a.created_at DESC LIMIT ?""", (user_id, limit))]
        except sqlite3.OperationalError:
            past = []
    return {"ignored_titles": ignored, "past_verdicts": past}


@mcp.tool()
def submission_trend(listing_url: str) -> dict:
    """How the number of submissions (or registrations) of one listing has grown,
    from this watcher's own snapshots taken every 30 minutes. No website publishes
    this history. Returns the snapshots and a linear projection of the count at the
    deadline, which is a better competitor estimate than today's number."""
    with _con() as con:
        b = con.execute("SELECT * FROM bounties WHERE url=? OR key=?",
                        (listing_url, listing_url)).fetchone()
        if not b:
            return {"found": False}
        pts = [(r["at"], r["submissions"]) for r in con.execute(
            "SELECT at, submissions FROM submission_history WHERE key=? ORDER BY at",
            (b["key"],)) if r["submissions"] is not None]
    out = {"found": True, "title": b["title"], "deadline": b["deadline"],
           "current": b["submissions"], "winners": b["winners"],
           "snapshots": pts[-12:]}
    if len(pts) >= 2 and b["deadline"]:
        t0 = datetime.fromisoformat(pts[0][0])
        t1 = datetime.fromisoformat(pts[-1][0])
        days = max((t1 - t0).total_seconds() / 86400, 0.04)
        per_day = (pts[-1][1] - pts[0][1]) / days
        left = (datetime.fromisoformat(b["deadline"]) - datetime.now(timezone.utc)
                ).total_seconds() / 86400
        out["per_day"] = round(per_day, 2)
        out["projected_at_deadline"] = round(pts[-1][1] + max(per_day, 0) * max(left, 0))
    return out


@mcp.tool()
def user_schedule(user_id: str) -> dict:
    """Events this user has already committed to, with their working periods
    (from the user's private profile, not published anywhere). Use it to detect
    when a new listing's build period overlaps work the user already took on."""
    path = Path(os.getenv("AI_USERS_FILE", Path(config.BASE_DIR) / "ai" / "users.json"))
    if not path.exists():
        path = path.with_name("users.example.json")
    for u in json.loads(path.read_text(encoding="utf-8")):
        if u.get("id") == user_id:
            return {"user_id": user_id, "commitments": u.get("commitments", []),
                    "weekly_hours": u.get("weekly_hours")}
    return {"user_id": user_id, "commitments": []}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
