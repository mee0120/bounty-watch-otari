> **Otari AI analyst (MozFest Devs Wilding):** see [OTARI.md](OTARI.md) for the per-user AI analyst built on the Otari gateway with open-weight models.

# バウンティ監視Bot（第1段階）

Superteam Earn と GitHub上の懸賞金付きIssue（Algora系）を定期的に集め、
狙い目の案件だけをLINEに通知します。

## 通知の種類

| 種類 | タイミング | 内容 |
|---|---|---|
| 🆕 新着 | 30分ごと | 新しく出た案件のうち、スコア50以上のもの |
| ⏰ 締切間近 | 30分ごと | 締切72時間以内・提出10件以下・反響審査でないもの（1案件1回まで） |
| 📋 日次まとめ | 毎朝8時 | 公開中の案件をスコア順に上位8件 |

## スコアの考え方（0〜100）

- 基本点：`総賞金 ÷ max(提出数+1, 入賞枠)` を対数で点数化（$100→40点、$1,000→60点、$10,000→80点）
- 開発・リサーチ案件は +15、コンテンツ案件は −5
- Xの反響で審査されそうな案件（thread / tweet / meme など）は −30
- 締切24時間未満は −15
- ハッカソンは提出数が締切まで隠れるため「登録者数×0.4（Solana公式は×0.5）」を推定競合数として使い、入賞3枠と仮定。−5
- フィードバック／テストネット系は +10、学生限定・地域限定の可能性があるものは −20
- 助成金は審査制なので最大額のみで点数化（$1,000→40点、$10,000→60点）
- 新しく追加した監視先は、初回だけ「🔌 監視先を追加」として上位5件をまとめて通知します
- GitHubの案件は締切がないため、コメント数（着手宣言の数）を提出数の代わりに使います

## 設置手順（VPS / Ubuntu 24.04）

PowerShellからフォルダごとアップロード:

```powershell
scp -r .\bounty_watch root@<VPSのIP>:/root/
```

VPS上で:

```bash
cd /root/bounty_watch
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env        # LINEのトークンと送信先を入れる（他のBotと同じ値でOK）

./venv/bin/python main.py test-notify   # LINEにテスト通知が届くか
./venv/bin/python main.py run           # 初回（既存案件を登録するだけで通知はしない）
./venv/bin/python main.py list          # 取得できた案件をスコア順に表示
```

`list` で Superteam と GitHub の両方の案件が表示されれば成功です。

### 定期実行（cron）

```bash
crontab -e
```

```
CRON_TZ=Asia/Tokyo
*/30 * * * * cd /root/bounty_watch && ./venv/bin/python main.py run >> run.log 2>&1
0 8 * * *    cd /root/bounty_watch && ./venv/bin/python main.py digest >> run.log 2>&1
```

## 困ったとき

- **Superteamの取得が403になる**：サイト側のボット対策の可能性があります。`run.log` のエラーを共有してください
- **ソースが3回連続で失敗**：LINEにエラー通知が1回だけ届きます
- **通知が多すぎる／少なすぎる**：`.env` の `NOTIFY_MIN_SCORE` を上げ下げしてください

## ファイル構成

```
main.py            実行の入口（run / digest / list / test-notify）
config.py          設定（.env を読み込む）
scoring.py         スコア計算
db.py              SQLite保存（重複通知防止・提出数の推移記録）
notifier.py        LINE通知
sources/
  superteam.py        Superteam Earn（日本から参加可能な案件のみ）
  superteam_grants.py Superteam の助成金（Global / Japan のみ）
  github_bounty.py    GitHubの懸賞金付きIssue
  dorahacks.py        DoraHacks の開催中ハッカソン（オンラインのみ）
  solana_hackathons.py hackathons.solana.com（Solana公式ハッカソン）
```

ソースを増やすときは `sources/` に `fetch()` が `Bounty` のリストを返すファイルを足し、
`main.py` の `collect()` に1行追加します。
