"""設定。値は .env から読み込む（なければデフォルト値）。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")

# --- LINE Messaging API ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_TO = os.getenv("LINE_TO", "")  # 送信先の userId（または groupId）

# --- GitHub（任意。あるとレート制限が緩くなる: 10→30回/分） ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# --- 保存先 ---
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "bounties.db"))

# --- Superteam Earn ---
# 一覧APIの地域指定（※実際には絞り込まれないため、下の許可リストで判定する）
SUPERTEAM_REGION = os.getenv("SUPERTEAM_REGION", "japan")
# 参加できる地域。案件詳細の region がこのどれかなら対象
SUPERTEAM_ALLOWED_REGIONS = [
    r.strip().lower()
    for r in os.getenv("SUPERTEAM_ALLOWED_REGIONS", "global,japan").split(",")
    if r.strip()
]

# --- GitHub ---
# 同じリポジトリの案件は上位この件数まで表示（1リポジトリで一覧が埋まるのを防ぐ）
GITHUB_MAX_PER_REPO = int(os.getenv("GITHUB_MAX_PER_REPO", "3"))
# 除外するリポジトリ（owner/repo をカンマ区切り）
GITHUB_EXCLUDE_REPOS = [
    r.strip().lower()
    for r in os.getenv("GITHUB_EXCLUDE_REPOS", "").split(",")
    if r.strip()
]

# --- 通知の条件 ---
NOTIFY_MIN_SCORE = float(os.getenv("NOTIFY_MIN_SCORE", "50"))   # 新着通知のしきい値
# スコアに関係なく知らせる注目キーワード（小文字・カンマ区切り。空にすると無効）
WATCH_KEYWORDS = [w.strip().lower() for w in os.getenv(
    "WATCH_KEYWORDS", "security,privacy,cyber,phishing,scam,fraud,vulnerab,secret"
).split(",") if w.strip()]
MIN_REWARD_USD = float(os.getenv("MIN_REWARD_USD", "100"))       # これ未満は無視
DIGEST_TOP_N = int(os.getenv("DIGEST_TOP_N", "8"))               # 日次まとめの件数
# 「締切が近いのに提出が少ない」アラート
CLOSING_HOURS = float(os.getenv("CLOSING_HOURS", "72"))
CLOSING_MAX_SUBMISSIONS = int(os.getenv("CLOSING_MAX_SUBMISSIONS", "10"))

# 得意分野（スコア加点）。カンマ区切り
FAVORED_CATEGORIES = [
    c.strip().lower()
    for c in os.getenv("FAVORED_CATEGORIES", "dev,development,research").split(",")
    if c.strip()
]

DRY_RUN = os.getenv("DRY_RUN", "0") == "1"  # 1ならLINE送信せず標準出力のみ
