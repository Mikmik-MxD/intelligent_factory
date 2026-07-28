import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
  """
  前端 WebSocket 入口
  连接地址: ws://<host>:9000/ws
  """
  # 从 app.state 取出在 lifespan 中创建的 WebSocketService
  ws_service = ws.app.state.ws_service

  # 接受连接，加入连接池
  await ws_service.connect(ws)

  try:
    # 持续监听前端发来的消息（心跳 / 将来的指令）
    while True:
      raw = await ws.receive_text()
      await ws_service.handle_client_message(ws, raw)

  except WebSocketDisconnect:
    logger.info("[WS] 客户端主动断开")

  except Exception as e:
    logger.warning(f"[WS] 连接异常: {e}")

  finally:
    # 无论何种原因退出循环，都从连接池移除
    await ws_service.disconnect(ws)