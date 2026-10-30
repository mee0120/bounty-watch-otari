# AI analyst for the bounty watcher, built on Otari

**Demo video (3:21):** https://youtu.be/ZhYsZGAnpRM

The watcher already collects new hackathons, bounties and grants from Devpost,
DoraHacks, Superteam, Solana Hackathons, AKINDO and GitHub, scores them and posts
the best ones to LINE. A score is not a decision, though: to decide whether to
enter, you still have to open every page and read the rules, the eligibility, the
deliverables and what past winners built.

This branch adds an AI analyst that does that reading, **per user**. Each user
says what they want to watch and what they avoid, in their own language and with
their own daily budget. Every model call goes through the hosted
[Otari](https://otari.ai) gateway, using open-weight models only.

```
new listing ──► triage (gpt-oss-20b) ──no──► skipped, reason logged
                     │ yes
                     ▼
               analyst (Qwen3-235B)  ── Otari runs the tools ──►  MCP: submission_trend, user_schedule,
                     │                                                 user_history, search_history
                     │                                            web fetch / web search
                     │                                            code execution (hours left, expected value)
                     ▼
     JSON report in the user's language ──► LINE (user A, Japanese) / Telegram (user B, English)
```

## How each Otari feature is used

| Otari feature | Where | What it does here |
|---|---|---|
| **Open-weight models, two roles** | `ai/agent.py` | `openai/gpt-oss-20b` triages every listing cheaply; `Qwen/Qwen3-235B-A22B-Instruct-2507` writes the full analysis. Both are open-weight. |
| **Routing policies with fallbacks** | Otari dashboard → Routing | The app only sends `model: "watch-triage"` or `model: "watch-analyst"`. `watch-triage` is gpt-oss-20b on DeepInfra with gpt-oss-20b on OVHcloud as backup; `watch-analyst` is Qwen3-235B on DeepInfra with `gpt-oss-120b` on Nebius as backup. A fallback was observed in Activity during testing (attempt 1 absorbed, attempt 2 on Nebius). |
| **Multiple models in distinct roles** | `triage()` / `analyse()` | Small model filters, large model reads and reasons. Most listings never reach the expensive model. |
| **Web fetch and web search** | `tools: otari_web_fetch, otari_web_search` | The analyst reads the listing page; when a page is JavaScript-only it searches for the rules or the organizer's page instead. |
| **Code execution** | `tools: otari_code_execution` | The analyst must compute `hours_left` and `expected_value_usd = cash pool / max(competitors, winners)` in Python, not in its head. |
| **MCP integration** | `ai/mcp_server.py`, `mcp_servers` in the request | A read-only MCP server over data **no website has**: `submission_trend` (the watcher snapshots every listing's submission count every 30 minutes, so it can project the count at the deadline), `user_schedule` (events the user already committed to, so the analyst flags overlapping build periods), `user_history` (what this user already rejected) and `search_history` (similar past listings). Otari connects to it and runs the tool calls. |
| **Budgets** | Otari → Spend & budgets | A workspace ceiling of $0.50/day caps the whole app. |
| **Per-user budgets** | one Otari API key per user | `watcher-user-a` is capped at $0.30/day, `watcher-user-b` at $0.10/day. When a user's budget is spent, Otari refuses that user's calls and the app stops analysing for that user only (`BudgetExceeded`). |
| **Guardrails (requested)** | `guardrails: prompt-injection, monitor` | Every analyst request asks for the prompt-injection guardrail. On hosted otari.ai the verdict currently comes back empty (`valid: null`), so the app also tells the model to treat page content as untrusted and to report any embedded instructions as a red flag. |

## Example report (user A, Japanese, delivered to LINE)

For Solana's "Perps and Prediction Markets" the analyst returned, among others:

- Competition trend: 261 entries now, growing about 3.7 per day, about 401 projected at the deadline (from `submission_trend`)
- Schedule conflicts: overlaps BCH BLAZE build week, the UGREEN finals and Codegeist (from `user_schedule`)
- Expected value about $252 (computed with code execution from the projected count), fit 95/100, verdict "maybe": strong fit, but the calendar is already full

A plain web search could not have produced the last two lines.

## Users

`ai/users.example.json` (copy to `ai/users.json`):

- **user-a**: crypto and web3 events, reports in Japanese, delivered to LINE
- **user-b**: AI agents and developer tools, reports in English, delivered to Telegram

The watcher logic is the same for both; only the profile, the language, the key
and therefore the budget differ. The same code can watch job posts or grant calls
by changing the profile text.

## Run

```bash
pip install -r requirements.txt        # requests; mcp only for the MCP server
cp .env.example .env                   # OTARI_KEY_A, OTARI_KEY_B, MCP_*
python3 -m ai.mcp_server               # or install ai/bounty-mcp.service
python3 main.py ai                     # analyse new listings for every user
python3 main.py ai-one "BCH BLAZE" user-a   # analyse one listing (demo)
python3 main.py ai-log                 # verdicts, models, fallbacks and cost per call
```

Typical cost per analysed listing: about $0.03 to $0.04, of which tool calls are
most of the charge; the triage call is about $0.00004.

## Lessons and limits

- A long tool loop behind a CDN needs streaming; a non-streamed request was cut
  at about 60 s with a 504 before the answer arrived.
- The analyst skipped MCP tools until the system prompt made every step
  mandatory. Activity now shows `code execution ×1 · search history ×1 · user
  history ×1 · web fetch ×1 · web search ×1` on one analysis.
- JavaScript-rendered listing pages (DoraHacks) cannot be fetched; the analyst
  falls back to search.
