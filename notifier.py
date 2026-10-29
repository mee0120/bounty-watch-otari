"""LINE Messaging API でプッシュ通知する。"""
import requests

from config import DRY_RUN, LINE_CHANNEL_ACCESS_TOKEN, LINE_TO

PUSH_URL = "https://api.line.me/v2/bot/message/push"
MAX_LEN = 4900  # LINEのテキスト上限は5000文字


def _chunks(text: str):
    while text:
        if len(text) <= MAX_LEN:
            yield text
            return
        cut = text.rfind("\n", 0, MAX_LEN)
        cut = cut if cut > 0 else MAX_LEN
        yield text[:cut]
        text = text[cut:].lstrip("\n")


def send(text: str) -> None:
    if DRY_RUN or not (LINE_CHANNEL_ACCESS_TOKEN and LINE_TO):
        print("----- [通知(未送信)] -----")
        print(text)
        return
    # 1リクエストで最大5メッセージまで送れる
    msgs = [{"type": "text", "text": c} for c in _chunks(text)][:5]
    r = requests.post(
        PUSH_URL,
        headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                 "Content-Type": "application/json"},
        json={"to": LINE_TO, "messages": msgs},
        timeout=20,
    )
    if r.status_code != 200:
        raise RuntimeError(f"LINE送信失敗 {r.status_code}: {r.text[:200]}")
