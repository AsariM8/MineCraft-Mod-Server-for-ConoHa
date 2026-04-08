"""
bot.py — Discord Bot メインエントリーポイント

コマンド一覧:
  /start   — サーバー起動
  /stop    — サーバー停止（Adminロール必須）
  /restart — サーバー再起動（Adminロール必須）
  /status  — サーバー状態確認
"""

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
import conoha_api
from utils.monitor import AutoStopMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---- Discord クライアント設定 -----------------------------------------------

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# 自動停止モニター（インスタンスは1つだけ）
_monitor: AutoStopMonitor | None = None


# ---- ユーティリティ ----------------------------------------------------------

def _has_admin_role(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    return any(r.name == config.ADMIN_ROLE_NAME for r in interaction.user.roles)


async def _notify_channel(message: str) -> None:
    """設定済みチャンネルに通知を送る。"""
    if not config.DISCORD_CHANNEL_ID:
        return
    channel = bot.get_channel(config.DISCORD_CHANNEL_ID)
    if channel and isinstance(channel, discord.TextChannel):
        await channel.send(message)


def _get_monitor() -> AutoStopMonitor:
    global _monitor
    if _monitor is None:
        _monitor = AutoStopMonitor(on_auto_stop=_auto_stop_handler)
    return _monitor


async def _auto_stop_handler() -> None:
    """自動停止トリガー時に呼ばれる非同期コールバック。"""
    await _notify_channel(
        f"プレイヤーが {config.AUTO_STOP_MINUTES} 分間 0 人のためサーバーを自動停止します..."
    )
    try:
        await asyncio.to_thread(conoha_api.stop_server)
        reached = await asyncio.to_thread(
            conoha_api.wait_for_status, "SHUTOFF", 300, 10
        )
        if reached:
            await _notify_channel("サーバーを停止しました。")
        else:
            await _notify_channel("停止タイムアウト。手動で確認してください。")
    except Exception as e:
        logger.exception("自動停止中にエラー: %s", e)
        await _notify_channel(f"自動停止中にエラーが発生しました: {e}")


# ---- スラッシュコマンド -------------------------------------------------------

@tree.command(name="status", description="Minecraftサーバーの現在の状態を確認します")
async def cmd_status(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    try:
        status = await asyncio.to_thread(conoha_api.get_server_status)
    except Exception as e:
        await interaction.followup.send(f"状態取得に失敗しました: {e}")
        return

    labels = {"ACTIVE": "起動中", "SHUTOFF": "停止中", "BUILD": "起動処理中"}
    label = labels.get(status, status)
    await interaction.followup.send(f"サーバー状態: **{label}** (`{status}`)")


@tree.command(name="start", description="Minecraftサーバーを起動します")
async def cmd_start(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)

    try:
        status = await asyncio.to_thread(conoha_api.get_server_status)
    except Exception as e:
        await interaction.followup.send(f"状態取得に失敗しました: {e}")
        return

    if status == "ACTIVE":
        await interaction.followup.send("既に起動しています。")
        return
    if status == "BUILD":
        await interaction.followup.send("現在起動処理中です。しばらくお待ちください。")
        return

    try:
        await asyncio.to_thread(conoha_api.start_server)
    except Exception as e:
        await interaction.followup.send(f"起動APIの呼び出しに失敗しました: {e}")
        return

    await interaction.followup.send("起動開始しました。ACTIVEになるまでお待ちください...")

    # バックグラウンドでポーリングして完了通知
    async def _wait_and_notify():
        reached = await asyncio.to_thread(conoha_api.wait_for_status, "ACTIVE", 300, 10)
        if reached:
            msg = "サーバーが起動しました！"
            await interaction.followup.send(msg)
            # 自動停止モニター開始
            _get_monitor().start()
        else:
            await interaction.followup.send(
                "起動タイムアウト（5分）。`/status` で確認してください。"
            )

    asyncio.create_task(_wait_and_notify())


@tree.command(name="stop", description="Minecraftサーバーを停止します（Adminロール必須）")
async def cmd_stop(interaction: discord.Interaction) -> None:
    if not _has_admin_role(interaction):
        await interaction.response.send_message(
            f"`/stop` は **{config.ADMIN_ROLE_NAME}** ロールのみ使用できます。", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    try:
        status = await asyncio.to_thread(conoha_api.get_server_status)
    except Exception as e:
        await interaction.followup.send(f"状態取得に失敗しました: {e}")
        return

    if status == "SHUTOFF":
        await interaction.followup.send("既に停止しています。")
        return

    try:
        await asyncio.to_thread(conoha_api.stop_server)
    except Exception as e:
        await interaction.followup.send(f"停止APIの呼び出しに失敗しました: {e}")
        return

    # 自動停止モニターを止める
    _get_monitor().stop()

    await interaction.followup.send("停止処理を開始しました...")

    async def _wait_and_notify():
        reached = await asyncio.to_thread(conoha_api.wait_for_status, "SHUTOFF", 300, 10)
        if reached:
            await interaction.followup.send("サーバーを停止しました。")
        else:
            await interaction.followup.send(
                "停止タイムアウト（5分）。`/status` で確認してください。"
            )

    asyncio.create_task(_wait_and_notify())


@tree.command(name="restart", description="Minecraftサーバーを再起動します（Adminロール必須）")
async def cmd_restart(interaction: discord.Interaction) -> None:
    if not _has_admin_role(interaction):
        await interaction.response.send_message(
            f"`/restart` は **{config.ADMIN_ROLE_NAME}** ロールのみ使用できます。", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    # 停止フェーズ
    try:
        status = await asyncio.to_thread(conoha_api.get_server_status)
        if status == "ACTIVE":
            await asyncio.to_thread(conoha_api.stop_server)
            _get_monitor().stop()
            await interaction.followup.send("停止中... 完了後に再起動します。")
            reached = await asyncio.to_thread(conoha_api.wait_for_status, "SHUTOFF", 300, 10)
            if not reached:
                await interaction.followup.send("停止タイムアウト。再起動を中断しました。")
                return
        elif status != "SHUTOFF":
            await interaction.followup.send(
                f"再起動できない状態です: `{status}`"
            )
            return
    except Exception as e:
        await interaction.followup.send(f"停止処理に失敗しました: {e}")
        return

    # 起動フェーズ
    try:
        await asyncio.to_thread(conoha_api.start_server)
        await interaction.followup.send("再起動（起動）開始しました...")
    except Exception as e:
        await interaction.followup.send(f"起動APIの呼び出しに失敗しました: {e}")
        return

    async def _wait_and_notify():
        reached = await asyncio.to_thread(conoha_api.wait_for_status, "ACTIVE", 300, 10)
        if reached:
            await interaction.followup.send("サーバーの再起動が完了しました！")
            _get_monitor().start()
        else:
            await interaction.followup.send(
                "再起動タイムアウト（5分）。`/status` で確認してください。"
            )

    asyncio.create_task(_wait_and_notify())


# ---- Bot イベント ------------------------------------------------------------

@bot.event
async def on_ready() -> None:
    await tree.sync()
    logger.info("Bot 起動完了: %s (ID: %s)", bot.user, bot.user.id)
    logger.info("スラッシュコマンドを同期しました。")

    # Bot 起動時にサーバーがすでに ACTIVE なら自動停止モニターを開始
    try:
        status = await asyncio.to_thread(conoha_api.get_server_status)
        if status == "ACTIVE":
            _get_monitor().start()
            logger.info("既存の ACTIVE サーバーに対し自動停止モニターを開始しました。")
    except Exception as e:
        logger.warning("起動時のサーバー状態取得に失敗: %s", e)


# ---- エントリーポイント -------------------------------------------------------

if __name__ == "__main__":
    bot.run(config.DISCORD_TOKEN)
