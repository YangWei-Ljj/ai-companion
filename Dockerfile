# AI 智能伴侣 · 第二轮镜像（后端 8001 + 前端 8511）
# 注意：本 Dockerfile 未在本机执行 docker build 验证（按红线：未真实 build 成功前标注"未验证"）。
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
RUN mkdir -p data logs uploads

EXPOSE 8001 8511

# 同时起后端与前端；容器内访问宿主机 Ollama 需把 OLLAMA_BASE_URL 设为
# http://host.docker.internal:11434/v1（compose 加 extra_hosts: host-gateway）
CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 & \
                  python -m streamlit run app/main.py --server.address 0.0.0.0 --server.port 8511"]
