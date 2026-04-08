import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CONOHA_USERNAME = os.getenv("CONOHA_USERNAME")
CONOHA_PASSWORD = os.getenv("CONOHA_PASSWORD")
TENANT_ID = os.getenv("TENANT_ID")
SERVER_ID = os.getenv("SERVER_ID")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
MC_SERVER_HOST = os.getenv("MC_SERVER_HOST", "")
MC_SERVER_PORT = int(os.getenv("MC_SERVER_PORT", "25565"))
AUTO_STOP_MINUTES = int(os.getenv("AUTO_STOP_MINUTES", "10"))

CONOHA_REGION = os.getenv("CONOHA_REGION", "tyo1")
CONOHA_IDENTITY_URL = f"https://identity.{CONOHA_REGION}.conoha.io/v2.0"
CONOHA_COMPUTE_BASE = f"https://compute.{CONOHA_REGION}.conoha.io/v2/{TENANT_ID}"

missing = [
    name for name, val in [
        ("DISCORD_TOKEN", DISCORD_TOKEN),
        ("CONOHA_USERNAME", CONOHA_USERNAME),
        ("CONOHA_PASSWORD", CONOHA_PASSWORD),
        ("TENANT_ID", TENANT_ID),
        ("SERVER_ID", SERVER_ID),
    ]
    if not val
]
if missing:
    raise EnvironmentError(f"必須の環境変数が未設定です: {', '.join(missing)}")
