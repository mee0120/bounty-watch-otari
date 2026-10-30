# Bounty Watch

Bounty Watch collects open hackathons, bounties and grants from several platforms,
scores them, and sends only the ones worth a look to LINE (or Telegram). It runs on
a small VPS with cron and keeps everything in one SQLite file.

> **Otari AI analyst (MozFest Devs Wilding):** the `otari-devs-wilding` branch adds a
> per-user AI analyst built on the Otari gateway with open-weight models.
> See [OTARI.md](OTARI.md).

## Sources

| Source | What is collected |
|---|---|
| Superteam Earn | bounties and projects open to the configured regions (global + Japan by default) |
| Superteam grants | grants open to the configured regions |
| GitHub | issues with a bounty label (Algora style) and no assignee |
| DoraHacks | running online hackathons |
| Solana Hackathons | official hackathons on hackathons.solana.com |
| Devpost | open and upcoming online hackathons |
| AKINDO | WaveHacks |

## Notifications

| Type | When | What |
|---|---|---|
| 🆕 New | every 30 min | new listings with a score of 50 or more |
| 🛡 Watched keywords | every 30 min | new listings whose title, sponsor or notes contain a watched word (security, privacy, ...), whatever their score |
| ⏰ Closing soon | every 30 min | closes within 72 hours, 10 or fewer submissions, not judged on social engagement (once per listing) |
| 📋 Daily digest | every morning | top open listings by score |
| 🔌 New source | once | when a new source is added, its top 5 listings |

## Score (0 to 100)

- Base: `total prize / max(submissions + 1, winner slots)` on a log scale
  ($100 → 40, $1,000 → 60, $10,000 → 80)
- Development and research tasks +15, content tasks −5
- Listings likely judged on X engagement (thread, tweet, meme, ...) −30
- Less than 24 hours left −15
- Hackathons hide their submission count until the deadline, so
  `registrations × 0.4` (× 0.5 for Solana's official hackathons) is used as the
  estimated number of competitors, with 3 winner slots assumed, −5
- Feedback and testnet tasks +10; possibly student-only or region-only −20
- Grants are reviewed, so only the maximum amount counts ($1,000 → 40, $10,000 → 60)
- GitHub bounties have no deadline, so the number of comments (people claiming the
  issue) stands in for the submission count

## Commands

```bash
python3 main.py run            # collect, store, notify (run from cron)
python3 main.py digest         # daily digest
python3 main.py list           # print open listings by score
python3 main.py ignore <url|key|title words>   # hide a listing
python3 main.py thread print   # print a weekly X thread draft of open listings
python3 main.py thread         # send the draft to Telegram and mark the picks as used
python3 main.py test-notify    # send a test message to LINE
# Otari branch only:
python3 main.py ai [user]      # AI analysis of new listings for each user
python3 main.py ai-one <url|key|title> [user]
python3 main.py ai-log
```

## Setup (VPS, Ubuntu 24.04)

```bash
cd /root/bounty_watch
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env        # LINE token and destination; optional GITHUB_TOKEN, Telegram, Otari keys

./venv/bin/python main.py test-notify   # a test message should arrive on LINE
./venv/bin/python main.py run           # first run: stores existing listings without notifying
./venv/bin/python main.py list          # listings by score
```

### Cron

```
CRON_TZ=Asia/Tokyo
*/30 * * * * cd /root/bounty_watch && ./venv/bin/python main.py run >> run.log 2>&1
0 8 * * *    cd /root/bounty_watch && ./venv/bin/python main.py digest >> run.log 2>&1
```

## Settings (`.env`)

| Name | Default | Meaning |
|---|---|---|
| `NOTIFY_MIN_SCORE` | 50 | minimum score for the 🆕 notification |
| `MIN_REWARD_USD` | 100 | listings below this are ignored |
| `DIGEST_TOP_N` | 8 | listings in the daily digest |
| `WATCH_KEYWORDS` | security, privacy, cyber, phishing, scam, fraud, vulnerab, secret | words that always trigger 🛡 (comma-separated, empty to turn off) |
| `X_EXCLUDE` | (empty) | words that keep a listing out of the X thread, e.g. events you enter yourself |

## Troubleshooting

- **A source returns 403**: probably the site's bot protection; check `run.log`.
- **A source fails 3 times in a row**: one error message is sent to LINE.
- **Too many or too few notifications**: raise or lower `NOTIFY_MIN_SCORE`.

## Files

```
main.py            entry point (commands above)
config.py          settings, read from .env
scoring.py         score
db.py              SQLite: de-duplication and submission history
notifier.py        LINE
xthread.py         X thread draft (built from stored data, no AI, never posts)
sources/           one module per platform; fetch() returns a list of Bounty
ai/                Otari analyst (otari-devs-wilding branch)
```

To add a source, put a module with `fetch()` in `sources/` and add one line to
`collect()` in `main.py`.

## License

MIT, see [LICENSE](LICENSE).
