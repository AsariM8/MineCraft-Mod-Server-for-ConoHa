import time
import requests
import config

_token: str | None = None
_token_expires: float = 0.0


def _get_token() -> str:
    """ConoHa APIトークンを取得・キャッシュして返す。"""
    global _token, _token_expires
    now = time.time()
    if _token and now < _token_expires:
        return _token

    url = f"{config.CONOHA_IDENTITY_URL}/tokens"
    payload = {
        "auth": {
            "passwordCredentials": {
                "username": config.CONOHA_USERNAME,
                "password": config.CONOHA_PASSWORD,
            },
            "tenantId": config.TENANT_ID,
        }
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    _token = data["access"]["token"]["id"]
    # ConoHa トークン有効期限は24h。安全マージンとして23h後に再取得
    _token_expires = now + 23 * 3600
    return _token


def _headers() -> dict:
    return {"X-Auth-Token": _get_token(), "Content-Type": "application/json"}


def _retry(fn, retries: int = 3, delay: float = 2.0):
    """失敗時にリトライ。認証エラー(401)はトークン再取得後に再試行。"""
    global _token, _token_expires
    last_exc = None
    for attempt in range(retries):
        try:
            return fn()
        except requests.HTTPError as e:
            last_exc = e
            if e.response is not None and e.response.status_code == 401:
                # トークンを無効化して次回再取得させる
                _token = None
                _token_expires = 0.0
            if attempt < retries - 1:
                time.sleep(delay)
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(delay)
    raise last_exc


def get_server_status() -> str:
    """サーバーの現在のステータス文字列を返す（ACTIVE / SHUTOFF / BUILD など）。"""
    def _call():
        url = f"{config.CONOHA_COMPUTE_BASE}/servers/{config.SERVER_ID}"
        resp = requests.get(url, headers=_headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()["server"]["status"]

    return _retry(_call)


def start_server() -> None:
    """サーバーを起動する。"""
    def _call():
        url = f"{config.CONOHA_COMPUTE_BASE}/servers/{config.SERVER_ID}/action"
        resp = requests.post(url, json={"os-start": None}, headers=_headers(), timeout=15)
        resp.raise_for_status()

    _retry(_call)


def stop_server() -> None:
    """サーバーを停止する。"""
    def _call():
        url = f"{config.CONOHA_COMPUTE_BASE}/servers/{config.SERVER_ID}/action"
        resp = requests.post(url, json={"os-stop": None}, headers=_headers(), timeout=15)
        resp.raise_for_status()

    _retry(_call)


def wait_for_status(
    target_status: str,
    timeout_sec: int = 300,
    interval_sec: int = 10,
) -> bool:
    """
    サーバーが target_status になるまでポーリングする。
    timeout_sec 以内に達成できれば True、タイムアウトなら False を返す。
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            status = get_server_status()
            if status == target_status:
                return True
        except Exception:
            pass
        time.sleep(interval_sec)
    return False
