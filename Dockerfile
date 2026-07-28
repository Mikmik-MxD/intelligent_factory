FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（netcat 用于健康检查等待等场景）
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目源码
COPY . .

# 暴露服务端口
EXPOSE 9000

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
