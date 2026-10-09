# 多架构镜像（linux/arm64 与 linux/amd64 均可构建）
# docker buildx build --platform linux/arm64 -t xiaoxin-server:1.0 .
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
WORKDIR /opt/xiaoxin
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY data ./data
COPY config.yaml .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
