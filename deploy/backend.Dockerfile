# 后端镜像：uv 装依赖 → 启动时 alembic 迁移 + 种子 + uvicorn
FROM python:3.13-slim

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
# 统一容器时区为东八区：后端业务时间取 datetime.now()，必须与 MySQL --default-time-zone 一致
ENV TZ=Asia/Shanghai

RUN pip install --no-cache-dir uv

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.seeds.init_data && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
