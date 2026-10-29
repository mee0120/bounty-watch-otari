"""バウンティ監視Bot

使い方:
  python3 main.py run          # 収集して、新着・締切間近をLINE通知（cronで定期実行）
  python3 main.py digest       # 公開中の上位案件をまとめて通知（1日1回）
  python3 main.py list         # 公開中の案件をスコア順に表示（確認用）
  python3 main.py ignore <URL|タイトルの一部>  # 対象外の案件を今後表示しない
  python3 main.py test-notify  # LINE通知のテスト
  python3 main.py ai [user-id]  # 新着案件をユーザーごとにAI分析して通知（Otari経由）
  python3 main.py ai-one <URL|キー> [user-id]  # 1件だけAI分析（デモ用）
  python3 main.py ai-log       # これまでのAI分析とコストを表示
"""
import sys
import traceback
from datetime import datetime, timedelta, timezone

import config
import db
import notifier
from http_util import get_json
from scoring import expected_value, hours_left, score
from sources import (akindo, devpost, dorahacks, github_bounty,
                     solana_hackathons, superteam, superteam_grants)

JST = timezone(timedelta(hours=9))
SOURCE_LABEL = {"superteam": "Superteam", "github": "GitHub", "dorahacks": "DoraHacks",
                "solana_hack": "Solana Hackathons", "st_grant": "Superteam助成金",
                "devpost": "Devpost", "akindo": "AKINDO"}
CAT_LABEL = {"dev": "開発", "design": "デザイン", "content": "コンテンツ",
             "research": "リサーチ", "other": "その他", "": "-"}
COINGECKO_IDS = {"SOL": "solana", "JUP": "jupiter-exchange-solana", "BONK": "bonk"}


def fetch_prices() -> dict:
    try:
        data = get_json("https://api.coingecko.com/api/v3/simple/price",
                        params={"ids": ",".join(COINGECKO_IDS.values()),
                                "vs_currencies": "usd"})
        return {sym: data[cid]["usd"] for sym, cid in COINGECKO_IDS.items()
                if cid in data}
    except Exception:
        return {}


# ---------- 表示 ----------

def _fmt_deadline(iso: str | None) -> str:
    if not iso:
        return "締切なし"
    dt = datetime.fromisoformat(iso)
    h = (dt - datetime.now(timezone.utc)).total_seconds() / 3600
    left = f"あと{h:.0f}時間" if h < 48 else f"あと{h / 24:.0f}日"
    return f"{dt.astimezone(JST):%m/%d %H:%M}（{left}）"


def fmt_row(r) -> str:
    reward = f"${r['reward_usd']:,.0f}" if r["reward_usd"] is not None else "金額不明"
    subs = "-" if r["submissions"] is None else r["submissions"]
    subs_label = "コメント" if r["source"] == "github" else "提出"
    note = r["note"] if "note" in r.keys() else None
    lines = [
        f"■ {r['title']}",
        f"  {SOURCE_LABEL.get(r['source'], r['source'])} / {r['sponsor'] or '-'}"
        f" / {CAT_LABEL.get(r['category'], r['category'])}",
        (f"  賞金 {reward} / {note} / スコア{r['score']:.0f}" if note else
         f"  賞金 {reward}（入賞{r['winners']}枠） {subs_label}{subs}件"
         f" / スコア{r['score']:.0f}"),
        f"  締切 {_fmt_deadline(r['deadline'])}",
    ]
    if r["engagement"]:
        lines.append("  ⚠ Xの反響で審査される可能性あり")
    lines.append(f"  {r['url']}")
    return "\n".join(lines)


def cap_per_repo(rows):
    """GitHub案件は同じリポジトリから上位N件まで（スコア順の rows を前提）。"""
    count: dict[str, int] = {}
    out = []
    for r in rows:
        if r["source"] == "github":
            n = count.get(r["sponsor"], 0)
            if n >= config.GITHUB_MAX_PER_REPO:
                continue
            count[r["sponsor"]] = n + 1
        out.append(r)
    return out


# ---------- 収集 ----------

def collect(con) -> list[str]:
    """全ソースを取得してDBに保存。新規案件のキー一覧を返す。"""
    prices = fetch_prices()
    jobs = {
        "superteam": lambda: superteam.fetch(prices),
        "github": lambda: github_bounty.fetch(db.known_amounts(con, "github")),
        "dorahacks": lambda: dorahacks.fetch(prices),
        "solana_hack": solana_hackathons.fetch,
        "st_grant": lambda: superteam_grants.fetch(prices),
        "devpost": devpost.fetch,
        "akindo": lambda: akindo.fetch(prices),
    }
    new_keys: list[str] = []
    errors: list[str] = []
    added: list[str] = []

    for name, job in jobs.items():
        try:
            items = job()
        except Exception as e:
            fails = int(db.get_meta(con, f"fail:{name}", "0")) + 1
            db.set_meta(con, f"fail:{name}", str(fails))
            print(f"[{name}] 取得失敗({fails}回連続): {e}", file=sys.stderr)
            if fails == 3:  # 3回連続で失敗したら1度だけ知らせる
                errors.append(f"{name}: 3回連続で取得に失敗しています（{e}）")
            continue

        db.set_meta(con, f"fail:{name}", "0")
        source_new = (db.get_meta(con, f"init:{name}") != "1" and not con.execute(
            "SELECT 1 FROM bounties WHERE source=? LIMIT 1", (name,)).fetchone())
        seen = set()
        for b in items:
            seen.add(b.key)
            if db.upsert(con, b, score(b)) and not source_new:
                new_keys.append(b.key)
        if source_new:
            # 追加したばかりの監視先は、既存案件を新着として大量通知しない
            con.execute("UPDATE bounties SET notified_new=1 WHERE source=?", (name,))
            db.set_meta(con, f"init:{name}", "1")
            if db.get_meta(con, "initialized") == "1":
                added.append(name)
        db.mark_gone(con, name, seen)
        print(f"[{name}] {len(items)}件取得")

    con.commit()
    if errors:
        notifier.send("【バウンティ監視】エラー\n" + "\n".join(errors))
    for name in added:
        rows = [r for r in _open_rows(con) if r["source"] == name][:5]
        body = "\n\n".join(fmt_row(r) for r in rows) or "条件に合う公開中の案件はありません。"
        notifier.send(f"🔌 監視先を追加: {SOURCE_LABEL.get(name, name)}（上位{len(rows)}件）\n\n{body}")
    return new_keys


def cmd_run() -> None:
    con = db.connect()
    first_run = db.get_meta(con, "initialized") != "1"
    new_keys = collect(con)

    # 初回は既存の案件を全部「新着」として送らないよう、通知済み扱いにする
    if first_run:
        con.execute("UPDATE bounties SET notified_new=1")
        db.set_meta(con, "initialized", "1")
        con.commit()
        print("初回実行のため新着通知は省略しました（digestで一覧を確認できます）")
        return

    msgs = []
    shown: set[str] = set()

    # 1) 新着でスコアの高いもの
    if new_keys:
        q = ",".join("?" * len(new_keys))
        rows = con.execute(
            f"""SELECT * FROM bounties WHERE key IN ({q}) AND score>=?
                AND ignored=0
                AND (reward_usd IS NULL OR reward_usd>=?) ORDER BY score DESC""",
            (*new_keys, config.NOTIFY_MIN_SCORE, config.MIN_REWARD_USD)).fetchall()
        rows = cap_per_repo(rows)
        if rows:
            msgs.append("🆕 新着案件\n\n" + "\n\n".join(fmt_row(r) for r in rows))
            shown = {r["key"] for r in rows}
        con.execute(f"UPDATE bounties SET notified_new=1 WHERE key IN ({q})",
                    new_keys)

    # 2) 締切が近いのに提出が少ないもの
    limit = (datetime.now(timezone.utc)
             + timedelta(hours=config.CLOSING_HOURS)).isoformat()
    rows = con.execute(
        """SELECT * FROM bounties WHERE status='open' AND notified_closing=0
           AND ignored=0 AND deadline IS NOT NULL AND deadline<=? AND deadline>?
           AND submissions<=? AND engagement=0 AND reward_usd>=?
           ORDER BY score DESC""",
        (limit, datetime.now(timezone.utc).isoformat(),
         config.CLOSING_MAX_SUBMISSIONS, config.MIN_REWARD_USD)).fetchall()
    if rows:
        fresh = [r for r in rows if r["key"] not in shown]  # 新着欄と重複させない
        if fresh:
            msgs.append("⏰ 締切間近・提出少なめ\n\n"
                        + "\n\n".join(fmt_row(r) for r in fresh))
        con.executemany("UPDATE bounties SET notified_closing=1 WHERE key=?",
                        [(r["key"],) for r in rows])

    con.commit()
    if msgs:
        notifier.send("\n\n".join(msgs))
    else:
        print("通知対象なし")


def _open_rows(con, limit: int | None = None, min_score: float = 0):
    sql = """SELECT * FROM bounties WHERE status='open' AND ignored=0
             AND (deadline IS NULL OR deadline>?)
             AND (reward_usd IS NULL OR reward_usd>=?)
             AND score>=?
             ORDER BY score DESC"""
    rows = con.execute(sql, (datetime.now(timezone.utc).isoformat(),
                             config.MIN_REWARD_USD, min_score)).fetchall()
    rows = cap_per_repo(rows)
    return rows[:limit] if limit else rows


def cmd_ignore() -> None:
    if len(sys.argv) < 3:
        print("使い方: main.py ignore <URL か タイトルの一部>")
        sys.exit(1)
    n = db.ignore(db.connect(), " ".join(sys.argv[2:]))
    print(f"{n}件を非表示にしました" if n else "一致する案件がありません")


def cmd_digest() -> None:
    con = db.connect()
    collect(con)
    rows = _open_rows(con, config.DIGEST_TOP_N, min_score=20)
    if not rows:
        notifier.send("📋 本日のバウンティ\n条件に合う公開中の案件はありません。")
        return
    head = f"📋 本日のバウンティ 上位{len(rows)}件（{datetime.now(JST):%m/%d}）"
    notifier.send(head + "\n\n" + "\n\n".join(fmt_row(r) for r in rows))


def cmd_list() -> None:
    con = db.connect()
    for r in _open_rows(con):
        print(fmt_row(r))
        print()


# ---------- AI分析（Otari） ----------

def _ai_deliver(results) -> None:
    from ai import agent
    users = {u["id"]: u for u in agent.load_users()}
    for uid, reports in results.items():
        u = users[uid]
        if not reports:
            continue
        ja = u["language"].lower().startswith("ja")
        head = (f"🤖 AI分析 {len(reports)}件（{u['label']}）" if ja
                else f"🤖 AI analysis, {len(reports)} new ({u['label']})")
        cost = sum(r.get("_cost", 0) for r in reports)
        body = "\n\n".join(agent.format_report(u, r) for r in reports)
        text = f"{head}\n\n{body}\n\n(Otari cost ${cost:.4f})"
        if u.get("notify") == "line":
            notifier.send(text)
        elif u.get("notify") == "telegram":
            from ai import telegram
            telegram.send(text, u.get("telegram_chat_id"))
        else:
            print(text)


def cmd_ai() -> None:
    from ai import agent
    con = db.connect()
    only = sys.argv[2] if len(sys.argv) > 2 else None
    _ai_deliver(agent.run(con, only_user=only))


def cmd_ai_one() -> None:
    from ai import agent
    if len(sys.argv) < 3:
        print("使い方: main.py ai-one <URL|キー> [user-id]")
        sys.exit(1)
    con = db.connect()
    agent.ensure_schema(con)
    t = sys.argv[2]
    row = con.execute("SELECT key FROM bounties WHERE (url=? OR key=? OR title LIKE ?) ORDER BY (status='open') DESC, (deadline > datetime('now')) DESC, first_seen DESC",
                      (t, t, f"%{t}%")).fetchone()
    if not row:
        print("一致する案件がありません")
        sys.exit(1)
    only = sys.argv[3] if len(sys.argv) > 3 else None
    con.execute("DELETE FROM ai_reports WHERE key=?" + (" AND user_id=?" if only else ""),
                (row["key"], only) if only else (row["key"],))
    con.commit()
    _ai_deliver(agent.run(con, keys=[row["key"]], only_user=only, force=True))


def cmd_ai_log() -> None:
    from ai import agent
    con = db.connect()
    agent.ensure_schema(con)
    rows = con.execute("""SELECT a.*, b.title FROM ai_reports a JOIN bounties b
                          ON b.key=a.key ORDER BY a.created_at DESC LIMIT 30""").fetchall()
    total = 0.0
    for r in rows:
        total += r["cost_usd"] or 0
        print(f"{r['created_at']} {r['user_id']:7} {r['stage']:7} {r['verdict']:5} "
              f"fit={r['fit']:<3} ${r['cost_usd']:.4f} fb={r['fallback']} "
              f"{r['models']} | {r['title'][:50]}")
    print(f"total ${total:.4f}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    commands = {"run": cmd_run, "digest": cmd_digest, "list": cmd_list,
                "ignore": cmd_ignore, "ai": cmd_ai, "ai-one": cmd_ai_one,
                "ai-log": cmd_ai_log,
                "test-notify": lambda: notifier.send("バウンティ監視Bot: 通知テストです")}
    if cmd not in commands:
        print(__doc__)
        sys.exit(1)
    try:
        commands[cmd]()
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
