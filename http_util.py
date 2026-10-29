"""HTTP取得の共通処理（リトライ・User-Agent付き）。"""
import time

import requests

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept": "application/json"})


def get_json(url: str, params: dict | None = None, headers: dict | None = None,
             retries: int = 3, timeout: int = 20):
    last_err = None
    for i in range(retries):
        try:
            r = _session.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                last_err = RuntimeError(f"HTTP {r.status_code}: {url}")
                time.sleep(5 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last_err = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"取得失敗: {url} ({last_err})")


def get_text(url: str, retries: int = 3, timeout: int = 20) -> str:
    """HTMLページをテキストで取得する（JSON APIがないサイト用）。"""
    last_err = None
    for i in range(retries):
        try:
            r = _session.get(url, headers={"Accept": "text/html"}, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                last_err = RuntimeError(f"HTTP {r.status_code}: {url}")
                time.sleep(5 * (i + 1))
                continue
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            last_err = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"取得失敗: {url} ({last_err})")
