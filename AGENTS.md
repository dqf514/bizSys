# Repository Guidelines

## Project Structure & Module Organization

`bizSys` is a pnpm workspace monorepo: Python backend, Vue frontend.

- `backend/` — FastAPI + SQLAlchemy 2 (sync). Each domain in `app/modules/<domain>/` follows the quartet `models.py`, `schemas.py`, `service.py`, `router.py`; shared code in `app/core/`, migrations in `alembic/versions/`, seeds in `app/seeds/`.
- `frontend/` — single-package Vue 3 + TypeScript app (ADR-0003). Domains in `src/modules/<domain>/{pages,components}/`; API clients in `src/api/`, shared UI in `src/components/`, locales in `src/locales/{zh-CN,en-US}/`.
- `docs/` — API contract and ADRs; keep `docs/api-contract.md` in sync with backend changes.
- `deploy/` — Docker Compose, Dockerfiles, nginx config.

## Build, Test, and Development Commands

Root scripts proxy to `frontend` (pnpm 11, Node 24).

- `pnpm install` — install workspace dependencies.
- `pnpm dev` — Vite on `http://localhost:5173`; `/api` proxies to `:8000`.
- `pnpm build` — token build, i18n check, literal scan, `vue-tsc`, Vite build.
- `pnpm lint` / `pnpm typecheck` / `pnpm test` — ESLint (`--max-warnings 0`), `vue-tsc`, Vitest (jsdom).
- `pnpm i18n:check` — assert `zh-CN` and `en-US` key sets match.
- `pnpm scan:literal` — find hardcoded CJK literals; `--strict` fails the build.
- `pnpm token:build` — regenerate `src/styles/tokens.css` from `src/styles/tokens/*.tokens.json`.

Backend (`uv`, Python 3.13), from `backend/`: `uv sync`, `uv run alembic upgrade head`, `uv run python -m app.seeds.init_data`, `uv run uvicorn app.main:app --port 8000`, `uv run ruff check app tests`, `uv run pytest -q`.

## Coding Style & Naming Conventions

Frontend: Prettier (`semi: false`, `singleQuote`, `printWidth: 100`, `trailingComma: all`, LF) with ESLint flat config (`typescript-eslint`, `eslint-plugin-vue`). PascalCase `.vue` components using `defineOptions({ name: '...' })`; camelCase variables; `useXxx` composables; kebab-case CSS classes.

Backend: Ruff, `line-length = 120`, `py313`, rules `E,F,I,UP,B`, `app` first-party. Prefer `Annotated`/`Depends` over call-time defaults.

Two rules CI enforces:

1. **No hardcoded UI strings.** Use `t('domain.key')`; add keys to both `zh-CN` and `en-US`.
2. **No hardcoded colors.** Use `--bs-*` tokens — edit `src/styles/tokens/*.tokens.json`, then `pnpm token:build`.

## UI Consistency Rules

- **Search**: every server-paginated list page must have a `SearchBar` with a keyword field (`q`); add `q` support to the backend list endpoint when missing (follow the existing `filters` pattern). Small client-side full lists get at least a local keyword filter input. Tree tables (menus/depts) are exempt.
- **StatusTabs**: every tab shows a count, including `all`; add a backend `…/counts` endpoint when missing (follow `task counts`). The `all` tab is always leftmost.
- **Close / back / footer buttons**: drawers and dialogs use the built-in top-right `X` only — no duplicate custom close buttons. Page-level back uses the shared `BackButton` (`src/components/common/BackButton.vue`) placed top-right. Dialog/drawer footer buttons: secondary actions left, primary action right.
- **Navigation**: the system-admin zone is pinned to a fixed bottom entry in the side nav (icon + label, visible only with at least one permitted admin menu; clicking opens an upward popover with the admin groups and items). The collapse/expand toggle sits in the same bottom toolbar — never top-left. Collapsed mode shows icons only (native `title` tooltip for names; zone titles and all labels hidden); the system-admin entry stays icon-only and its popover still works. Nav-zone sorting lives in `NavSortDialog`, reachable from the TopBar avatar menu (which also hosts appearance/language).
- **Mobile shell** (<768px, `useIsMobile`): side nav collapses into a hamburger drawer (`MobileNavDrawer`, same zone/menu data and permission filtering); the right context panel becomes a floating button + right drawer; the status bar is hidden. A persistent bottom `MobileDock` shows an enlarged center Workbench button plus 4 user-customizable shortcuts (long-press the dock or the avatar-menu "Dock Shortcuts" entry opens `DockSettingsDialog`; selection persists in user prefs key `dockShortcuts` via `useDock.ts`, permission-filtered with defaults todo/tasks/contracts/OA-apply). Global overlay overrides live in `src/styles/mobile.css`.

## Testing Guidelines

Backend tests in `backend/tests/test_*.py` (pytest). `conftest.py` creates and seeds an isolated `bizsys_test` database — never point tests at the dev DB. Frontend tests are Vitest files colocated with source, named `*.test.ts`. Add a test per bug fix and per new API path.

## Commit & Pull Request Guidelines

Conventional Commits with a Chinese subject: `feat(oa): OA 前端 + 统一流程设计`, `fix(router): 发版后首次打开空白页自愈`, `docs:`, `chore:`. Common scopes: `admin`, `oa`, `flow`, `contract`, `finance`, `frontend`, `scripts`, `layout`. Bodies use short bullets and end with the verification result, e.g. `测试 100 全绿`.

PRs summarize the change, note new Alembic migrations or seed data, list commands run, and include screenshots for UI changes.

## Security & Configuration Tips

Copy `backend/.env.example` to `backend/.env`; never commit it. Replace `JWT_SECRET` and DB credentials before production. Uploads stay in `backend/uploads/` (gitignored). Permission codes follow `module:resource:action` — enforce server-side and log privileged operations to `sys_audit_log`.
