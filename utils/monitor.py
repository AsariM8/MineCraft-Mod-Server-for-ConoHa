"""
monitor.py — プレイヤー数の監視と自動停止ロジック

Minecraftのサーバーリストピング（SLP）プロトコルを使って
現在のプレイヤー数を取得し、一定時間0人が続いたら自動停止する。
"""

import asyncio
import logging
import socket
import struct
import json
import time
from typing import Callable, Awaitable

import config

logger = logging.getLogger(__name__)


def get_player_count() -> int | None:
    """
    Minecraft Server List Ping (1.7+) でオンラインプレイヤー数を取得する。
    取得失敗時は None を返す。
    """
    host = config.MC_SERVER_HOST
    port = config.MC_SERVER_PORT

    if not host:
        return None

    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            # Handshake パケット
            _send_packet(sock, _build_handshake(host, port))
            # Status Request
            _send_packet(sock, b"\x00")
            # Status Response を受け取る
            data = _recv_packet(sock)
            status = json.loads(_read_string(data))
            return status["players"]["online"]
    except Exception as e:
        logger.debug("プレイヤー数取得失敗: %s", e)
        return None


# ---- SLP ヘルパー --------------------------------------------------------

def _pack_varint(value: int) -> bytes:
    result = b""
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            byte |= 0x80
        result += bytes([byte])
        if not value:
            break
    return result


def _build_handshake(host: str, port: int) -> bytes:
    protocol_version = _pack_varint(47)  # 1.8 互換（SLPは版依存なし）
    host_bytes = host.encode("utf-8")
    host_data = _pack_varint(len(host_bytes)) + host_bytes
    port_data = struct.pack(">H", port)
    next_state = _pack_varint(1)  # 1 = status
    payload = _pack_varint(0x00) + protocol_version + host_data + port_data + next_state
    return payload


def _send_packet(sock: socket.socket, data: bytes) -> None:
    packet = _pack_varint(len(data)) + data
    sock.sendall(packet)


def _recv_varint(sock: socket.socket) -> int:
    result = 0
    shift = 0
    while True:
        byte = ord(sock.recv(1))
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return result


def _recv_packet(sock: socket.socket) -> bytes:
    length = _recv_varint(sock)
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            break
        data += chunk
    return data


def _read_string(data: bytes) -> str:
    # パケットID (varint) をスキップしてから文字列を読む
    idx = 0
    # skip packet id varint
    while data[idx] & 0x80:
        idx += 1
    idx += 1
    # read string length varint
    str_len = 0
    shift = 0
    while True:
        byte = data[idx]
        idx += 1
        str_len |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return data[idx: idx + str_len].decode("utf-8")


# ---- 自動停止ループ -------------------------------------------------------

class AutoStopMonitor:
    """
    一定間隔でプレイヤー数を確認し、
    AUTO_STOP_MINUTES 分間 0 人が続いたら on_auto_stop コールバックを呼ぶ。
    """

    def __init__(self, on_auto_stop: Callable[[], Awaitable[None]]):
        self._on_auto_stop = on_auto_stop
        self._task: asyncio.Task | None = None
        self._empty_since: float | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._empty_since = None
            self._task = asyncio.create_task(self._loop())
            logger.info("自動停止モニター開始")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("自動停止モニター停止")
        self._task = None
        self._empty_since = None

    async def _loop(self) -> None:
        interval = 60  # 1分ごとにチェック
        threshold = config.AUTO_STOP_MINUTES * 60

        while True:
            await asyncio.sleep(interval)
            try:
                count = get_player_count()
            except Exception:
                count = None

            if count is None:
                # 取得失敗はリセットせず継続
                continue

            if count == 0:
                if self._empty_since is None:
                    self._empty_since = time.time()
                    logger.info("プレイヤー 0 人を検知。カウント開始。")
                elif time.time() - self._empty_since >= threshold:
                    logger.info("プレイヤー 0 人が %d 分継続。自動停止します。", config.AUTO_STOP_MINUTES)
                    self.stop()
                    await self._on_auto_stop()
                    return
            else:
                if self._empty_since is not None:
                    logger.info("プレイヤーが参加。カウントリセット。")
                self._empty_since = None
