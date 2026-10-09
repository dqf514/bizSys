# 前端镜像：pnpm 构建 → nginx 托管 SPA（/api 反代 backend）
FROM node:24-slim AS build
RUN corepack enable && corepack prepare pnpm@11 --activate
WORKDIR /app
COPY pnpm-workspace.yaml package.json ./
COPY frontend/package.json frontend/
RUN pnpm install --frozen-lockfile || pnpm install
COPY frontend ./frontend
RUN pnpm build

FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 80
