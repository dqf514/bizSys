# ADR-0003 前端首期单应用 + modules/* 目录分域（推迟 pnpm packages 拆分）

- 状态：已接受（2026-10-09）
- 背景：原方案规划 pnpm workspace 多包（design-system/locales/api-client/module-*）。实际首期仅 6 个页面域。
- 决策：首期为**单 Vite 应用**，按 `src/modules/{workbench,admin,crm,contract,task}` 目录分域 + 路由懒加载分包；`pnpm-workspace.yaml` 已预留，待模块数 >6 再拆 `packages/`。
- 理由：避免首期工程化负担（跨包类型引用、构建编排）；路由级 code-split 已达成按需加载；模块边界由目录约定 + 权限码保证。
- 后果：设计系统/语言包暂住 `src/styles` 与 `src/locales`，拆包时平移即可；跨模块引用必须经 `components/` 公共层，禁止直接 import 其他 modules 内部文件（lint 约束）。
