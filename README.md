# Study Buddy Final

An LMS-integrated AI Study Buddy designed for schools.

## Project Goal

Study Buddy provides students with an AI tutor that:

- Uses **only school-provided materials**
- Acts as a **Socratic tutor** (guides thinking instead of doing assignments)
- Supports schools in reducing reliance on outside AI tools by offering an in-platform alternative with course-grounded answers
- Minimizes hallucinations through a **strict retrieval-augmented generation (RAG) pipeline**

## Core Principles

- **Academic integrity first**: a bouncer check filters unsafe prompts before normal response generation.
- **Grounded responses**: answers are based on retrieved course context only.
- **Course isolation**: content is indexed per course to keep data separated.
- **Cited learning support**: retrieved context includes Moodle links and module metadata.

## High-Level Architecture

- **Backend**: FastAPI (`app/`)
  - LTI 1.3 routes for LMS launch/auth
  - Teacher upload endpoint for course resources
  - Chat endpoint with streaming responses
  - In-memory/session-backed chat context
  - RAG indexing and similarity search
- **Frontend**: React + Vite (`client/`)
  - Chat UI
  - Material upload UI
- **Moodle plugin**: `local/floating_ai`
  - Supports LMS-side integration workflow

## Repository Structure

```text
app/                  FastAPI backend (API, LTI, RAG, services)
client/               React frontend
local/floating_ai/    Moodle local plugin
build_moodle_zip.py   Utility to package Moodle plugin ZIP
docker-compose.yml    Local container setup for API
requirements.txt      Python dependencies
```

## Quick Start

### 1) Backend (Python)

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

API runs on `http://localhost:8000`.

### 2) Frontend (React)

```bash
cd client
npm install
npm run dev
```

UI runs on `http://localhost:5173` (or next available Vite port).

### 3) Docker (API)

```bash
docker compose up --build
```

## Key Endpoints

- `GET /health` — health check
- `POST /api/v1/chat` — streaming chat with RAG + guardrails
- `POST /api/v1/teacher/upload` — upload course materials
- `GET|POST /api/lti/login` — LTI login initiation
- `POST /api/lti/launch` — LTI launch validation and session setup
- `GET /api/lti/me` — current LTI-authenticated user state
- `POST /api/lti/logout` — logout + session clear

## Environment Configuration

Common variables used by the backend:

- `MOODLE_BASE_URL`
- `MOODLE_API_TOKEN`
- `MOODLE_REQUEST_TIMEOUT_SECONDS`
- `MOODLE_DEFAULT_VISIBILITY`
- `FRONTEND_URL`
- `SESSION_SECRET`
- `SESSION_COOKIE_SAMESITE`
- `SESSION_COOKIE_SECURE`
- `EMBEDDING_MODEL_NAME`
- `APP_DATA_DIR`
- `STUDY_BUDDY_DB_PATH`

Use your local `.env` for values.

## Moodle Plugin Packaging

To build an installable Moodle ZIP for the local plugin:

```bash
python build_moodle_zip.py
```

This generates a `local_<plugin>.zip` package from `local/floating_ai`.

## Vision

This project is built around a simple idea: schools should have a safe, course-grounded AI tutor inside their LMS that helps students learn without replacing student work.
