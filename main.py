import time
import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from utils.api_feedBack import error_feedback
from service.mqtt_service import MqttService
from service.websocket_service import WebSocketService
from router.websocket_router import router as ws_router

load_dotenv()

# 日志配置
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s = %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
  # ===== 启动 =====

  # 1. 创建 WebSocket 服务（必须在 asyncio 线程中拿 loop）
  loop = asyncio.get_running_loop()
  ws_service = WebSocketService(loop)
  app.state.ws_service = ws_service

  # 2. 创建 MQTT 服务
  mqtt_service = MqttService()
  app.state.mqtt_service = mqtt_service

  # 3. 把 WebSocket 推送注册为 MQTT 的消息处理器
  mqtt_service.add_message_handler(ws_service.on_mqtt_message)

  # 4. 启动 MQTT
  mqtt_service.start()
  logger.info("[APP] 所有服务已启动")

  yield

  # ===== 关闭 =====
  mqtt_service.stop()
  await ws_service.close_all()
  logger.info("[APP] 所有服务已停止")


app = FastAPI(
  title="智慧工厂比赛项目",
  version="1.0.0",
  description="接口文档",
  max_upload_size=1024 * 1024 * 200,
  lifespan=lifespan,
)

# CORS 跨域配置
app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

# 注册 WebSocket 路由
app.include_router(ws_router)


# 全局参数校验
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
  missing_fields = []

  for error in exc.errors():
    loc_parts = []
    for part in error["loc"]:
      if part not in ("body", "json", "__root__"):
        loc_parts.append(str(part))

    if loc_parts:
      field_name = ".".join(loc_parts)
      missing_fields.append(field_name)
    else:
      error_type = error.get("type", "")
      if error_type == "missing":
        missing_fields.append("请求体不完整（未提供任何字段）")
      else:
        missing_fields.append(error.get("msg", "未知验证错误"))

  if missing_fields:
    msg = f"缺少必填字段: {', '.join(missing_fields)}"
  else:
    msg = f"请求参数校验失败: {exc.errors()}"

  return JSONResponse(
    status_code=500,
    content=error_feedback(msg, {"missing_fields": missing_fields})
  )


# 请求日志中间件
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
  start_time = time.time()
  client_ip = request.client.host if request.client else "unknown"
  method = request.method
  path = request.url.path

  logger.info(f"➡ 请求进入 | IP: {client_ip} | {method} {path}")

  response = await call_next(request)

  elapsed = time.time() - start_time
  logger.info(
    f"⬅ 请求完成 | IP: {client_ip} | {method} {path} "
    f"| 状态: {response.status_code} | 耗时: {elapsed:.3f}s"
  )

  return response


if __name__ == '__main__':
  uvicorn.run(
    "main:app",
    host="0.0.0.0",
    port=9000,
    reload=True,
  )