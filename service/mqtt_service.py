import os
import json
import logging
from typing import Callable
from datetime import datetime
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MqttService:
  """基础 MQTT 服务：连接、订阅/取消、发布、消息回调 + 自动 ACK"""

  def __init__(self):
    # 从环境变量读取配置
    self.host = os.getenv("MQTT_BROKER_HOST", "localhost")
    self.port = int(os.getenv("MQTT_BROKER_PORT", 1883))
    self.username = os.getenv("MQTT_USERNAME", "mqtt_server") or None
    self.password = os.getenv("MQTT_PASSWORD", "zhgc_mqtt_connection") or None
    self.client_id = os.getenv("MQTT_CLIENT_ID", "mqtt_server")
    topics = os.getenv("MQTT_SUB_TOPICS", "device/postData_mqtt/+")
    self.sub_topics = [t.strip() for t in topics.split(",") if t.strip()]

    # 创建 MQTT 
    self.client = mqtt.Client(client_id=self.client_id, protocol=mqtt.MQTTv5)

    # 设置回调
    self.client.on_connect = self._on_connect
    self.client.on_message = self._on_message
    self.client.on_disconnect = self._on_disconnect

    if self.password:
      self.client.username_pw_set('', self.password)

    self._running = False

    # 消息处理器列表，外部通过 add_message_handler 注册
    self.message_handlers: list[Callable[[str, dict], None]] = []

  # ---------- 生命周期 ----------
  def start(self):
    """启动连接（心跳 10 秒，持久会话，会话过期 12 小时）"""
    if self._running:
      logger.warning("MQTT 服务已在运行")
      return

    # Clean Start = False （恢复旧会话，保留离线消息）
    self.client.clean_start = mqtt.MQTT_CLEAN_START_FIRST_ONLY

    # 连接属性：会话过期间隔 12 小时
    properties = mqtt.Properties(mqtt.PacketTypes.CONNECT)
    properties.SessionExpiryInterval = 43200  # 12 * 3600 秒

    # 连接，心跳 keepalive=10 秒
    self.client.connect(self.host, self.port, keepalive=10, properties=properties)
    self.client.loop_start()          # 启动后台网络线程
    self._running = True
    logger.info(f"MQTT 服务启动 → {self.host}:{self.port}")

  def stop(self):
    """停止服务"""
    if not self._running:
      return
    self.client.loop_stop()
    self._running = False
    self.client.disconnect()
    logger.info("MQTT 服务已停止")

  # ---------- 订阅 / 取消 / 发布 ----------
  def subscribe(self, topic: str, qos: int = 1):
    """订阅主题"""
    result = self.client.subscribe(topic, qos)
    if result[0] == mqtt.MQTT_ERR_SUCCESS:
      logger.info(f"已订阅: {topic} (QoS {qos})")
    else:
      logger.error(f"订阅失败: {topic}")

  def unsubscribe(self, topic: str):
    """取消订阅"""
    result = self.client.unsubscribe(topic)
    if result[0] == mqtt.MQTT_ERR_SUCCESS:
      logger.info(f"已取消订阅: {topic}")
    else:
      logger.error(f"取消订阅失败: {topic}")

  def publish(self, topic: str, payload, qos: int = 1):
    """发布消息，payload 可以是 str 或 dict（自动转 JSON）"""
    if isinstance(payload, dict):
      payload = json.dumps(payload)
    info = self.client.publish(topic, payload, qos)
    if info.rc == mqtt.MQTT_ERR_SUCCESS:
      logger.debug(f"已发布 → {topic}")
    else:
      logger.error(f"发布失败: {topic}")

  # ---------- 消息回调注册 ----------
  def add_message_handler(self, handler: Callable[[str, dict], None]):
    """注册消息处理器 handler(topic, payload_dict)"""
    if handler not in self.message_handlers:
      self.message_handlers.append(handler)

  def remove_message_handler(self, handler: Callable[[str, dict], None]):
    if handler in self.message_handlers:
      self.message_handlers.remove(handler)

  # ---------- 内部 MQTT 回调 ----------
  def _on_connect(self, client, userdata, flags, rc, properties=None):
    if rc == 0:
      logger.info("MQTT 已连接")
      for topic in self.sub_topics:
        self.client.subscribe(topic, qos=1)
        logger.info(f"已订阅: {topic}")
    else:
      logger.error(f"MQTT 连接失败，返回码: {rc}")

  def _on_disconnect(self, client, userdata, rc, properties=None):
    if rc != 0:
      logger.warning("MQTT 意外断开，paho 将自动重连")
    else:
      logger.info("MQTT 正常断开")

  def _on_message(self, client, userdata, msg):
    try:
      raw = msg.payload.decode("utf-8")
      try:
        data = json.loads(raw)
      except json.JSONDecodeError:
        data = {"raw": raw}

      logger.info(f"收到消息 [{msg.topic}]: {raw[:200]}")

      # ----- 自动 ACK 回复（仅限 device/postData_mqtt/+ 主题） -----
      self._auto_ack(msg.topic, data)

      # 分发给所有注册的外部处理器
      for handler in self.message_handlers:
        try:
          handler(msg.topic, data)
        except Exception as e:
          logger.error(f"消息处理器异常: {e}")

    except Exception as e:
        logger.error(f"消息处理异常: {e}")

  # ---------- ACK 逻辑 ----------
  def _auto_ack(self, topic: str, data: dict):
    """验证消息并回复 ACK"""
    # 仅处理以 'device/postData_mqtt/' 开头的主题
    if not topic.startswith("device/postData_mqtt/"):
      return

    # 提取设备 ID（例如 'device/postData_mqtt/sensor01' → 'sensor01'）
    device_id = topic[len("device/postData_mqtt/"):]
    if not device_id:
      logger.warning(f"无法从主题提取设备 ID: {topic}")
      return

    ack_topic = f"device/ack/{device_id}"

    # 生成当前时间戳（14 位数字，如 '20260725183045'）
    now_ts = datetime.now().strftime("%Y%m%d%H%M%S")

    # 验证数据格式
    code, message = self._validate_payload(data)

    ack_payload = {
      "code": code,
      "message": message,
      "timestamp": now_ts
    }

    # 发送 ACK
    self.client.publish(ack_topic, json.dumps(ack_payload), qos=1)
    if code == "200":
      logger.debug(f"已回复 ACK 成功 → {ack_topic}")
    else:
      logger.warning(f"已回复 ACK 失败 [{code}] → {ack_topic}: {message}")

  def _validate_payload(self, data: dict) -> tuple[str, str]:
    """验证传感器数据格式，返回 (code, message)"""
    # 必须字段检查
    required_fields = ["type", "data", "unit", "timestamp"]
    for field in required_fields:
      if field not in data:
        return "400", f"缺少必要字段: {field}"

    # 检查 type 和 unit 是否为字符串（允许空串）
    if not isinstance(data["type"], str) or not isinstance(data["unit"], str):
      return "400", "字段 'type' 和 'unit' 必须为字符串"

    # 检查 data 是否为数字或数字字符串
    raw_data = data["data"]
    if isinstance(raw_data, (int, float)):
      pass  # 数字直接通过
    elif isinstance(raw_data, str):
      try:
        float(raw_data)  # 尝试转换为数字
      except ValueError:
        return "400", "字段 'data' 必须为数字或数字字符串"
    else:
      return "400", "字段 'data' 类型不正确"

    # 检查 timestamp 格式（14 位数字）
    ts = data["timestamp"]
    if not isinstance(ts, str) or not ts.isdigit() or len(ts) != 14:
      return "400", "字段 'timestamp' 必须为 14 位数字字符串 (如 20260720175940)"

    return "200", "发送成功"