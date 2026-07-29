# 智慧工厂比赛项目 - 后端服务

## 项目概述

基于 **FastAPI** 构建的后端服务，通过 MQTT 接收设备传感器数据并实时通过 WebSocket 推送至前端，同时提供 Redis 任务管理和统一的 API 响应格式。

## 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.12 | 运行环境 |
| FastAPI | >=0.110.0 | Web 框架 |
| Uvicorn | >=0.29.0 | ASGI 服务器 |
| paho-mqtt | >=2.0.0 | MQTT 客户端（MQTTv5） |

## 项目结构

```
intelligent_factory_backend_v1.0/
├── main.py                     # 应用入口，FastAPI 生命周期管理
├── requirements.txt            # Python 依赖
├── Dockerfile                  # Docker 镜像构建
├── router/
│   └── websocket_router.py     # WebSocket 接口：/ws
├── service/
│   ├── mqtt_service.py         # MQTT 连接/订阅/发布/ACK/数据校验
│   └── websocket_service.py    # WebSocket 连接池 + MQTT→前端广播
└── utils/
    ├── api_feedBack.py         # 统一 API 响应格式
```

## 核心架构

### 数据流

```
设备(传感器) --[MQTT]--> MqttService --[message_handler]--> WebSocketService --[WS]--> 前端
                              │
                              ├── 数据校验 (type/data/unit/timestamp)
                              └── ACK 回复 → device/ack/{device_id}
```

### 模块职责

**`main.py`** - 应用入口
- `lifespan` 管理服务启停：依次创建 WebSocketService → MqttService → 注册消息处理器 → 启动 MQTT
- 全局 CORS（允许所有来源）
- 请求日志中间件：记录 IP、方法、路径、状态码、耗时
- `RequestValidationError` 全局异常处理，友好返回缺少的字段名

**`service/mqtt_service.py`** - MQTT 服务
- MQTTv5 协议，持久会话（Session Expiry 12h），Keep Alive 10 秒
- 连接后自动订阅 `MQTT_SUB_TOPICS` 环境变量指定的一批主题
- `device/postData_mqtt/{device_id}` 消息到达后自动校验并 ACK 回复

**数据校验规则与 ACK：**

| 字段 | 要求 |
|------|------|
| `type` | 必须为字符串 |
| `data` | 数字或可转为数字的字符串 |
| `unit` | 必须为字符串 |
| `timestamp` | 14 位数字字符串，如 `20260720175940` |

- 校验通过 → `{"code":"200", "message":"发送成功", "timestamp":"..."}`
- 校验失败 → `{"code":"400", "message":"具体错误原因", "timestamp":"..."}`

**`service/websocket_service.py`** - WebSocket 服务
- 前端入口：`ws://<host>:9000/ws`
- 连接池用 `set[WebSocket]` 管理所有活跃连接
- MQTT 消息通过 `run_coroutine_threadsafe` 从 paho 线程投递到 asyncio 主循环广播
- 广播时自动清理失效连接
- 前端心跳支持：收到 `{"type":"ping"}` → 回复 `{"type":"pong","timestamp":"..."}`

## 环境变量

服务通过 `python-dotenv` 加载 `.env` 文件，支持以下变量：

### MQTT 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MQTT_BROKER_HOST` | `localhost` | MQTT Broker 地址 |
| `MQTT_BROKER_PORT` | `1883` | MQTT Broker 端口 |
| `MQTT_USERNAME` | `mqtt_server` | 用户名 |
| `MQTT_PASSWORD` | `zhgc_mqtt_connection` | 密码 |
| `MQTT_CLIENT_ID` | `mqtt_server` | 客户端 ID |
| `MQTT_SUB_TOPICS` | `device/postData_mqtt/+` | 订阅主题（逗号分隔多个） |

## 本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 确保 MQTT Broker（ EMQX ）已启动

# 3. 启动服务
python main.py
# 服务运行在 http://0.0.0.0:9000
# WebSocket: ws://localhost:9000/ws
```

## Docker 部署

```bash
# 构建镜像
docker build -t mqtt_server:v1.0 .
docker build -t 镜像名称:版本号 .

# 运行容器
docker run -d --restart=always --network host \
  --name zhgc-server \         <----- 自定义容器名称
  -e MQTT_BROKER=127.0.0.1 \
  -e MQTT_PORT=1883 \
  mqtt_server:v0.1             <----- 镜像名称:版本号
```

Dockerfile 基于 `python:3.12-slim`，使用清华 PyPI 镜像加速安装，暴露端口 `9000`。

## 接口说明

### WebSocket

| 项目 | 说明 |
|------|------|
| 地址 | `ws://{host}:9000/ws` |
| 心跳 | 发送 `{"type":"ping"}`，服务端回复 `{"type":"pong","timestamp":"..."}` |

### 服务端推送消息格式

```json
{
  "type": "device_data",
  "topic": "device/postData_mqtt/sensor01",
  "device_id": "sensor01",
  "data": {
    "type": "temperature",
    "data": 25.6,
    "unit": "celsius",
    "timestamp": "20260729153045"
  },
  "timestamp": "2026-07-29 15:30:45"
}
```
