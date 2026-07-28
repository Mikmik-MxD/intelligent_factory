import json
import asyncio
import logging
from datetime import datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)

class WebSocketService:
  """WebSocket 连接管理 + MQTT→前端 广播推送"""

  def __init__(self, loop: asyncio.AbstractEventLoop):
    # 主线程的 asyncio 事件循环（用于跨线程投递）
    self._loop = loop
    # 所有活跃的前端连接
    self._connections: set[WebSocket] = set()

  # ==================== 连接管理 ====================

  async def connect(self, ws: WebSocket):
    """接受连接并加入连接池"""
    await ws.accept()
    self._connections.add(ws)
    logger.info(f"[WS] 客户端已连接，当前连接数: {len(self._connections)}")

  async def disconnect(self, ws: WebSocket):
    """从连接池移除"""
    self._connections.discard(ws)
    logger.info(f"[WS] 客户端已断开，当前连接数: {len(self._connections)}")

  async def close_all(self):
    """服务关闭时，优雅断开所有前端连接"""
    for ws in list(self._connections):
      try:
        await ws.close(code=1001, reason="服务器关闭")
      except Exception:
        pass
    self._connections.clear()
    logger.info("[WS] 所有连接已关闭")

  # ==================== MQTT → WebSocket 桥接 ====================

  def on_mqtt_message(self, topic: str, data: dict):
    """
    由 MqttService 的 message_handlers 调用。
    ⚠ 此方法运行在 paho 后台线程，不能直接 await，
        必须通过 run_coroutine_threadsafe 投递回 asyncio 事件循环。
    """
    message = self._build_message(topic, data)
    asyncio.run_coroutine_threadsafe(self._broadcast(message), self._loop)

  # ==================== 广播 ====================

  async def _broadcast(self, message: dict):
    """向所有已连接的前端客户端广播消息"""
    if not self._connections:
      return

    dead: list[WebSocket] = []

    for ws in self._connections:
      try:
        await ws.send_json(message)
      except Exception:
        dead.append(ws)

    # 清理已失效的连接
    for ws in dead:
      self._connections.discard(ws)

    if dead:
      logger.warning(
        f"[WS] 清理 {len(dead)} 个失效连接，"
        f"剩余: {len(self._connections)}"
      )

  # ==================== 消息构建 ====================

  @staticmethod
  def _build_message(topic: str, data: dict) -> dict:
    """将 MQTT 原始数据包装成统一信封格式"""
    device_id = ""
    prefix = "device/postData_mqtt/"
    if topic.startswith(prefix):
      device_id = topic[len(prefix):]

    return {
      "type": "device_data",
      "topic": topic,
      "device_id": device_id,
      "data": data,
      "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

  # ==================== 处理前端发来的消息 ====================

  async def handle_client_message(self, ws: WebSocket, raw: str):
    """
    处理前端主动发来的文本消息。
    目前只有心跳，将来可扩展 subscribe / unsubscribe 等指令。
    """
    logger.info(f"[WS] 收到前端消息: {raw[:100]}")  
    str_raw = json.loads(raw.strip().lower())
    if str_raw['type'] == "ping":
      text = {
        "type": "pong",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      }
      await ws.send_text(json.dumps(text))
      return

    logger.debug(f"[WS] 收到未识别的前端消息: {raw[:100]}")