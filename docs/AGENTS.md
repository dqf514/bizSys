# Repository Guidelines

## Project Structure & Module Organization

`bizSys` is a pnpm workspace monorepo: Python backend, Vue frontend.

- `backend/` — FastAPI + SQLAlchemy 2 (sync). Each domain in `app/modules/<domain>/` follows the quartet `models.py`, `schemas.py`, `service.py`, `router.py`; shared code in `app/core/`, migrations in `alembic/versions/`, seeds in `app/seeds/`.
- `frontend/` — single-package Vue 3 + TypeScript app (ADR-0003). Domains in `src/modules/<domain>/{pages,components}/`; API clients in `src/api/`, shared UI in `src/components/`, locales in `src/locales/{zh-CN,en-US}/`.
- `docs/` — API contract and ADRs; keep `docs/api-contract.md` in sync with backend changes. `docs/roadmap-2026-11.md` holds the batch plan for the 2026-11 requirement list (CSV item numbers, dependencies, deliverables) and the fixed path for onboarding a new module.
- `deploy/` — Docker Compose, Dockerfiles, nginx config.

## Build, Test, and Development Commands

Root scripts proxy to `frontend` (pnpm 11, Node 24).

- `pnpm install` — install workspace dependencies.
- `pnpm dev` — Vite on `http://localhost:5173`; `/api` proxies to `:8000`.
- `pnpm build` — token build, i18n check, literal scan, color scan, `vue-tsc`, Vite build.
- `pnpm lint` / `pnpm typecheck` / `pnpm test` — ESLint (`--max-warnings 0`), `vue-tsc`, Vitest (jsdom).
- `pnpm i18n:check` — assert `zh-CN` and `en-US` key sets match.
- `pnpm scan:literal` — find hardcoded CJK literals; `--strict` fails the build.
- `pnpm scan:colors` — find hardcoded hex colors outside tokens/allowlist; fails the build.
- `pnpm token:build` — regenerate `src/styles/tokens.css` from `src/styles/tokens/*.tokens.json`.

Backend (`uv`, Python 3.13), from `backend/`: `uv sync`, `uv run alembic upgrade head`, `uv run python -m app.seeds.init_data`, `uv run uvicorn app.main:app --port 8000`, `uv run ruff check app tests`, `uv run pytest -q`.

## Coding Style & Naming Conventions

Frontend: Prettier (`semi: false`, `singleQuote`, `printWidth: 100`, `trailingComma: all`, LF) with ESLint flat config (`typescript-eslint`, `eslint-plugin-vue`). PascalCase `.vue` components using `defineOptions({ name: '...' })`; camelCase variables; `useXxx` composables; kebab-case CSS classes.

Backend: Ruff, `line-length = 120`, `py313`, rules `E,F,I,UP,B`, `app` first-party. Prefer `Annotated`/`Depends` over call-time defaults.

Two rules CI enforces:

1. **No hardcoded UI strings.** Use `t('domain.key')`; add keys to both `zh-CN` and `en-US`.
2. **No hardcoded colors.** Use `--bs-*` tokens — edit `src/styles/tokens/*.tokens.json`, then `pnpm token:build`.

## UI Consistency Rules

- **Page layout & width**: there is one page skeleton — `src/styles/page.css` (`.bs-page` family) plus the `layout` tokens in `base.tokens.json`. Every page root uses `.bs-page` (16px padding, `--bs-color-bg-app` background) plus one of `--fill` / `--scroll`; single-column form/document pages add `--narrow` **on the root** (960px centered column) instead of an inner wrapper. Never hand-write page padding, `max-width`, or drawer/dialog widths — use `--bs-layout-content-padding`, `--bs-layout-content-narrow-max-width`, `--bs-layout-form-max-width`, `--bs-layout-field-max-width`, and the 5 `--bs-layout-drawer-*` / `--bs-layout-dialog-*` buckets. `.bs-page` must not carry `min-height: 100%`: the list pages' `height:100%` chain feeds `el-table`'s `height="100%"`, and breaking it collapses the table to zero height. Don't change a page's scroll model (table-internal / page / `tab-content`). Page titles come from the shared `PageHeader` component, not per-page CSS.
- **Search**: every server-paginated list page must have a `SearchBar` with a keyword field (`q`); add `q` support to the backend list endpoint when missing (follow the existing `filters` pattern). Small client-side full lists get at least a local keyword filter input. Tree tables (menus/depts) are exempt.
- **Tables fill the content area**: `el-table` stretches only the columns **without** a numeric `width` (EP: `flexColumns = columns.filter(c => !isNumber(c.width))`). If every column has a fixed `width`, the table width collapses to the sum of the fixed widths and the content area keeps a large empty gutter on the right. Keep at least one flexible column per table (`min-width` instead of `width`); `ListTable.vue` enforces this automatically (it converts the last fixed column into a flexible one), but raw `<el-table>` blocks must do it themselves.
- **StatusTabs**: every tab shows a count, including `all`; add a backend `…/counts` endpoint when missing (follow `task counts`). The `all` tab is always leftmost.
- **Close / back / footer buttons**: drawers and dialogs use the built-in top-right `X` only — no duplicate custom close buttons. Page-level back uses the shared `BackButton` (`src/components/common/BackButton.vue`) placed top-right. Dialog/drawer footer buttons: secondary actions left, primary action right.
- **Navigation**: the side nav is **Workbench + 8 business zones + the pinned system-admin zone** (业务中心 / 生产资源 / 库存与资产 / 销售中心 / 经营与协同 / 行政人事 / 流程与办公 / 访客与安全). The system-admin zone is pinned to a fixed bottom entry in the side nav (icon + label, visible only with at least one permitted admin menu; clicking opens an upward popover with the admin groups and items). The collapse/expand toggle sits in the same bottom toolbar — never top-left. Collapsed mode shows icons only (native `title` tooltip for names; zone titles and all labels hidden); the system-admin entry stays icon-only and its popover still works. Nav-zone sorting lives in `NavSortDialog`, reachable from the TopBar avatar menu (which also hosts appearance/language). The menu tree itself is **backend data** (`app/seeds/init_data.py::MENU_TREE`): the seed matches rows by `name` and syncs `title_key/path/component_key/icon/permission/menu_type` but does **not** rewrite `parent_id`/`sort` — structural moves need `uv run python scripts/migrate_nav_zones.py` (idempotent). One permission code may back only one menu; duplicates silently shadow each other.
- **Mobile shell** (<768px, `useIsMobile`): side nav collapses into a hamburger drawer (`MobileNavDrawer`, same zone/menu data and permission filtering); the right context panel becomes a floating button + right drawer; the status bar is hidden. A persistent bottom `MobileDock` shows an enlarged center Workbench button plus 4 user-customizable shortcuts (long-press the dock or the avatar-menu "Dock Shortcuts" entry opens `DockSettingsDialog`; selection persists in user prefs key `dockShortcuts` via `useDock.ts`, permission-filtered with defaults todo/tasks/contracts/OA-apply). Global overlay overrides live in `src/styles/mobile.css`.
- **Motion**: durations/easing come from `motion` tokens in `base.tokens.json` (`--bs-motion-fast/base/slow/enter/exit`, `--bs-motion-curve`) — never hardcode ms or cubic-bezier values in components. Page enters, drawers, dialogs and popovers reference these tokens, and exits are always faster than enters (`--bs-motion-exit` < `--bs-motion-enter`); `src/styles/motion.css` applies the exit compression to EP overlay leave transitions. Keep motion restrained (fade/short translate only) and do not remove existing animations wholesale. `prefers-reduced-motion` must disable non-essential animation globally — `motion.css` carries the kill switch, so new animations must use the tokens and must never rely on motion alone to convey state.

## Testing Guidelines

Backend tests in `backend/tests/test_*.py` (pytest). `conftest.py` creates and seeds an isolated `bizsys_test` database — never point tests at the dev DB. Frontend tests are Vitest files colocated with source, named `*.test.ts`. Add a test per bug fix and per new API path.

## Commit & Pull Request Guidelines

Conventional Commits with a Chinese subject: `feat(oa): OA 前端 + 统一流程设计`, `fix(router): 发版后首次打开空白页自愈`, `docs:`, `chore:`. Common scopes: `admin`, `oa`, `flow`, `contract`, `finance`, `frontend`, `scripts`, `layout`. Bodies use short bullets and end with the verification result, e.g. `测试 100 全绿`.

PRs summarize the change, note new Alembic migrations or seed data, list commands run, and include screenshots for UI changes.

## Security & Configuration Tips

Copy `backend/.env.example` to `backend/.env`; never commit it. Replace `JWT_SECRET` and DB credentials before production. Uploads stay in `backend/uploads/` (gitignored). Permission codes follow `module:resource:action` — enforce server-side and log privileged operations to `sys_audit_log`.
