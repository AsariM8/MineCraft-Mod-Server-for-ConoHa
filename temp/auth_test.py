"""
auth_test.py — ConoHa API 認証診断スクリプト（公式ドキュメント準拠）

実行方法:
    .venv\Scripts\python temp\auth_test.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from dotenv import load_dotenv

load_dotenv()

USERNAME    = os.getenv("CONOHA_USERNAME", "")
PASSWORD    = os.getenv("CONOHA_PASSWORD", "")
TENANT_ID   = os.getenv("TENANT_ID", "")
TENANT_NAME = os.getenv("CONOHA_TENANT_NAME", "")

URL = "https://identity.c3j1.conoha.io/v3/auth/tokens"

print("=" * 60)
print("ConoHa API 認証診断（公式ドキュメント準拠）")
print("=" * 60)
print(f"  CONOHA_USERNAME     : {USERNAME!r}")
print(f"  CONOHA_TENANT_NAME  : {TENANT_NAME!r}")
print(f"  TENANT_ID           : {TENANT_ID!r}")
print(f"  PASSWORD            : {'*' * len(PASSWORD) if PASSWORD else '(未設定)'}")
print()

candidates = [
    {
        "label": "方式2: ユーザー名 + project.name（テナント名）",
        "payload": {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": USERNAME,
                            "password": PASSWORD,
                        }
                    },
                },
                "scope": {"project": {"name": TENANT_NAME or USERNAME}},
            }
        },
    },
    {
        "label": "方式1: ユーザーID + project.id（テナントID）",
        "payload": {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "id": USERNAME,
                            "password": PASSWORD,
                        }
                    },
                },
                "scope": {"project": {"id": TENANT_ID}},
            }
        },
    },
]

for c in candidates:
    print(f"[試行] {c['label']}")
    try:
        resp = requests.post(URL, json=c["payload"], timeout=10)
        if resp.status_code == 201:
            token = resp.headers.get("X-Subject-Token", "")
            print(f"  → SUCCESS (201) トークン: {token[:20]}...")
            print()
            print(f"★ 認証成功: {c['label']}")
            sys.exit(0)
        else:
            print(f"  → FAILED ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        print(f"  → エラー: {e}")
    print()

print("=" * 60)
print("全フォーマット失敗。APIユーザーが未作成の可能性が高いです。")
print()
print("【確認手順】")
print("1. https://manage.conoha.jp/ にログイン")
print("2. 左メニュー「API」をクリック")
print("3. 「APIユーザー」欄を確認")
print("   - 存在しない場合 → 「APIユーザー追加」から作成")
print("   - 存在する場合  → そのユーザー名を CONOHA_USERNAME に設定")
print()
print("【.env に設定する値の対応表】")
print("  CONOHA_USERNAME    ← APIユーザー名（テナント名とは別）")
print("  CONOHA_TENANT_NAME ← テナント名（APIページ上部に表示）")
print("  TENANT_ID          ← テナントID（UUIDの形式）")
