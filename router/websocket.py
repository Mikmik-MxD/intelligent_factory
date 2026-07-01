import logging
from service.ws_service import WsServiceManager
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)

ws_service = WsServiceManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
  await ws_service.ws_connect(websocket)
  try:
    while True:
      # 推荐：接收纯文本，把解析和容错的工作交给 Service 层
      # 如果使用 receive_json()，一旦前端发了非 JSON 字符串，这里会直接抛出异常导致连接断开！
      raw_text = await websocket.receive_text()
      
      # 将原始文本丢给 Service 层处理
      await ws_service.receive_msg(websocket, raw_text)
          
  except WebSocketDisconnect:
    ws_service.ws_disconnect(websocket)
  except Exception as e:
    logger.error(f"[WSERROR] 连接异常中断: {e}")
    ws_service.ws_disconnect(websocket)