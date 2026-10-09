# ADR-0001 后端采用 Python + FastAPI（弃 Java/Spring Boot）

- 状态：已接受（2026-10-09）
- 背景：原《技术设计文档》v1.0 定为 Spring Boot 3 + Flowable。开工前环境探明本机仅有 JDK 25（无 21）、无 Maven；用户明确表示熟悉 Python，且系统并发目标 <1000。
- 决策：后端改用 **Python 3.13 + FastAPI + SQLAlchemy 2（同步）+ Alembic + MySQL 8 + Redis + PyJWT/bcrypt**。
- 理由：
  1. 用户熟悉 Python，开发/排错效率与长期维护性优先；
  2. FastAPI（asyncio + 线程池）在 <1000 并发下绰绰有余，瓶颈将在 DB 而非语言层；
  3. 避免本机 Java 工具链（JDK21/Maven）的搭建成本；
  4. 部署镜像更轻（python:3.13-slim vs JVM）。
- 后果：Flowable 生态不可用 → 改为自研轻量审批引擎（见 ADR-0002）；《技术设计文档》v1.1 已同步修订；同步 SQLAlchemy 起步，若压测瓶颈在 DB 连接池，仅替换 driver 为 async（业务层不改，预留）。
