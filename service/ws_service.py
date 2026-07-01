import time
import json
import logging
from typing import Literal
from fastapi import WebSocket
from pydantic import BaseModel, ValidationError


# 日志配置
logging.basicConfig(
  level = logging.INFO,
  format = '%(asctime)s = %(levelname)s - %(message)s' 
)
logger = logging.getLogger(__name__)

# 接收消息 Pydantic
class WsReceive(BaseModel):
  type: str
  msg: str
  timestamp: int

# 发送消息 Pydantic
class WsSend(BaseModel):
  status: Literal[200, 400, 500]
  msg: str
  timestamp: int


class WsServiceManager:
  def __init__(self):
    self.active_connections: list[WebSocket] = []

  def build_msg(self, status: int, msg: str) -> WsSend:
    """构建并校验发送消息，返回 WsSend 模型实例"""
    return WsSend(
      status=status,
      msg=msg,
      timestamp=int(time.time())
    )

  # 注册连接
  async def ws_connect(self, websocket: WebSocket):
    await websocket.accept()
    self.active_connections.append(websocket)
    logger.info(f"[WS] {websocket.client.host} connected")
  
  # 断开连接
  def ws_disconnect(self, websocket: WebSocket):
    if websocket in self.active_connections:
      self.active_connections.remove(websocket)
    logger.info(f"[WS] {websocket.client.host} disconnected")

  # 接收消息
  async def receive_msg(self, websocket: WebSocket, data: str):
    try:
      data_dict = json.loads(data)
      # 校验格式
      WsReceive(**data_dict)
      # 回应成功
      await self.send_msg(websocket, self.build_msg(200, "success"))

      logger.info(f"[WS] message receive_msg {data_dict}")

    except json.JSONDecodeError:
      logger.warning(f"[WS] 收到非 JSON 格式数据: {data}")
      await self.send_msg(websocket, self.build_msg(400, "非 JSON 格式数据"))

    except ValidationError as e:
      logger.warning(f"[WS] 接收-数据格式校验失败: {e.errors()}")
      await self.send_msg(websocket, self.build_msg(400, "数据格式校验失败"))

    except Exception as e:
      logger.warning(f"[WS] 其他错误: {e}")

  async def send_msg(self, websocket: WebSocket, message: WsSend):
    """发送消息，message 已经是校验过的 WsSend 实例"""
    try:
      await websocket.send_text(message.model_dump_json())
    except Exception as e:
      logger.error(f"[WS] 发送消息失败: {e}")
    

