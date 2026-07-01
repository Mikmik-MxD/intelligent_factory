import os
import uuid
import json
import redis.asyncio as redis
from typing import Optional
from datetime import datetime

class RedisManager:
  def __init__(self):
    self._redis_client = redis.Redis(
      host=os.getenv("REDIS_URL", "localhost"),
      port=int(os.getenv("REDIS_PORT", "6379")),
      db=int(os.getenv("REDIS_DB", "1")),
      password=os.getenv("REDIS_PASSWORD"),
      decode_responses=True,
      protocol=2  # 强制使用 RESP2 协议，兼容旧版 Redis
    )
  
  # 创建uuid
  def _create_uuid(self):
    return str(uuid.uuid4())

  # 设置值
  async def set_value(self, status: str, result: Optional[dict] = None) -> str:
    task_id = self._create_uuid()
    await self._redis_client.set(task_id, json.dumps({
      "status": status,
      "created_at": datetime.now().isoformat(),
      "result": result
    }))
    return task_id
  
  # 获取值
  async def get_value(self, task_id: str) -> Optional[dict]:
    raw = await self._redis_client.get(task_id)
    return json.loads(raw) if raw else None

  # 更新已存在的 key 的值（不生成新 UUID）
  async def update_value(self, task_id: str, status: str, result: Optional[dict] = None):
    await self._redis_client.set(task_id, json.dumps({
      "status": status,
      "created_at": datetime.now().isoformat(),
      "result": result
    }))

  # 删除值
  async def del_value(self, task_id: str) -> bool:
    return bool(await self._redis_client.delete(task_id))