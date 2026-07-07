# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MaterialHub is an AI-powered enterprise document management system (DMS) with OCR, LLM-based extraction, and a bid/procurement subsystem. The stack is **React 18 + TypeScript + Vite** (frontend) and **Python FastAPI + SQLite** (backend).

## Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
python main.py          # Starts on port 8201; Swagger UI at /docs
```

### Frontend
```bash
cd frontend
npm install
npm run dev             # Vite dev server on port 5173
npm run build           # TypeScript compile + production build
```

### Docker (recommended)
```bash
docker-compose up -d    # backend on :8101, frontend on :3101
docker-compose logs -f
```

No automated tests exist; there are no test scripts.

## Architecture

### Dual Data Models (Active Migration)

The codebase is mid-migration from a legacy schema to DMS v2. Both coexist in the same SQLite database:

- **Legacy** (`backend/database.py`): `users`, `companies`, `persons`, `materials`, `documents`, `pending_reviews`
- **DMS v2** (`backend/dms_models.py`): all `dms_` prefixed tables — `dms_documents`, `dms_folders`, `dms_entities`, `dms_bid_projects`, etc.

Schema migrations run inline at startup using `ALTER TABLE` + `PRAGMA table_info()` checks (no Alembic). The `v2_migrate` router handles data migration from legacy to DMS tables.

### Backend Structure

`backend/routers/` contains all route modules — `v2_*.py` files are the active DMS v2 API; the non-prefixed files (`materials.py`, `companies.py`, etc.) are the legacy API still in use. Key non-router modules:

- `llm_provider.py` — unified LLM abstraction over DeepSeek/OpenRouter/Anthropic; normalizes tool-calling across providers
- `dms_processor.py` — background upload pipeline (OCR → LLM extraction → entity linking → FTS index)
- `dms_search.py` — FTS5 search with `LIKE` fallback
- `dms_auth.py` — RBAC (`require_role()` as FastAPI `Depends`) and folder-level access filtering
- `ocr_agent.py` — LLM-based information extraction from OCR text
- `chat_tools.py` — tool definitions for the in-app streaming LLM chat agent

LLM configuration is loaded from the database (`dms_system_settings`) first, then falls back to environment variables — it can be changed at runtime via admin settings.

### Upload Processing Pipeline

`POST /api/v2/upload` creates a draft `DmsDocument` synchronously, then spawns a daemon thread:
1. File hash dedup → PDF extraction (PyMuPDF) or image resize
2. OCR via external service at `OCR_SERVICE_URL`
3. LLM analysis → material type, extracted fields, entity names, expiry date
4. DocType resolution + folder auto-routing
5. Entity linking + FTS index update
6. Status transition `draft → active`

Progress is tracked in `meta_json._processing` and polled by the frontend.

### Frontend Structure

No React Router — `App.tsx` maintains a `Page` string-union state and renders the active page component. All navigation goes through `setPage()`.

- `src/services/api-v2.ts` — all DMS v2 API calls
- `src/services/api.ts` — legacy API calls
- `src/types/dms.ts` — TypeScript interfaces for DMS v2 types
- `src/pages/` — page-level components
- `src/components/` — shared UI components

Styling uses Tailwind CSS. No component library.

### MCP Server

`mcp-server/server.py` uses FastMCP to expose MaterialHub's API as tools for LLM clients (Claude Desktop, etc.). Configured via `.mcp.json` with `mh-agent-*` bearer tokens. Two token types: read-only and import.

## Configuration

Copy `.env.example` to `.env`. Key variables:

| Variable | Purpose |
|---|---|
| `DB_PATH` | SQLite file path |
| `PORT` | Backend port (default 8201) |
| `OCR_SERVICE_URL` | External OCR service (e.g. PaddleOCR) |
| `LLM_PROVIDER` | `deepseek` \| `openrouter` \| `anthropic` |
| `DEEPSEEK_API_KEY` / `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` | LLM credentials |
| `AUTH_DEFAULT_USERNAME` / `AUTH_DEFAULT_PASSWORD` | Default admin (`admin` / `admin123`) |

## Key Conventions

- **RBAC** is enforced via `require_role("editor")` as a FastAPI `Depends` in route decorators. Folder access uses `get_accessible_folder_ids()` — returns `None` for admins (unrestricted) or a list of IDs for restricted users.
- **SQLAlchemy models implement `to_dict()`** for serialization; no Pydantic response schemas for DMS endpoints (Pydantic is only used for request bodies).
- **Folder paths** are materialized strings (e.g. `/公司资质/营业执照/`); subtree queries use `LIKE path%`.
- **Document status** transitions: `draft → active → expired → archived`. Bid project status: `planning → active → submitted → won|lost|cancelled`.
- **FTS5 search** tries BM25 prefix matching first, falls back to SQL `LIKE '%query%'` if results are sparse. Tokenizer uses `unicode61` for Chinese character support.
- **Seed data** (`seed_data.py`) populates default folders and document types on first boot when DMS tables are empty.
- UI labels, log messages, and code comments are predominantly in Simplified Chinese.
