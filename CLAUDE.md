# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an internal AI tool API that provides an OpenAI-compatible API interface by connecting to an internal web-based AI tool through browser automation. It solves the enterprise authentication problem by maintaining a persistent Edge browser process with an authenticated session.

## Commands

### Installation
```bash
pip install -r requirements.txt
playwright install chromium
```

### Running the Application (requires two terminals)

**Terminal 1 - Start Edge browser:**
```bash
# Windows
start.bat edge

# Linux/Mac
./start.sh edge
```
Complete login in Edge, then keep it running.

**Terminal 2 - Start API server:**
```bash
# Windows
start.bat api

# Linux/Mac
./start.sh api
```

### Check Status
```bash
# Windows
start.bat status

# Linux/Mac
./start.sh status
```

### Test the API
```bash
curl http://localhost:8000/health
```

## Architecture

The system uses a two-process architecture to maintain authentication:

1. **Persistent Edge Browser** (`app/edge_manager.py`): Launches Edge with a remote debugging port (CDP protocol on port 9222). User logs in once and keeps the browser running. Uses `./edge_data` as isolated user data directory.

2. **FastAPI Server** (`app/main.py`): Connects to the running Edge via CDP to reuse the authenticated session.

### Core Components

- `edge_manager.py`: Singleton `EdgeManager` class that manages Edge process lifecycle and browser sessions. Handles CDP connection, session pooling (max 3 concurrent sessions), and provides `acquire_session()` context manager for thread-safe session access.

- `ai_client.py`: `AIClient` class that interacts with the AI web interface. Handles finding UI elements (input box, send button, response area), sending messages, and streaming responses.

- `routers/chat.py`: OpenAI-compatible `/v1/chat/completions` endpoint. Supports both streaming (SSE) and non-streaming responses.

- `models.py`: Pydantic models matching OpenAI API format (`ChatCompletionRequest`, `ChatCompletionResponse`, etc.).

- `config.py`: Configuration via environment variables (`.env` file). Key settings: `AI_TOOL_URL`, `EDGE_DEBUG_PORT`, `MAX_SESSIONS`, selectors for UI elements.

### Data Flow

```
Client (OpenAI SDK) → FastAPI /v1/chat/completions → AIClient → EdgeManager → CDP → Edge Browser → AI Web Tool
```

## Configuration

Settings can be configured via `.env` file:

- `AI_TOOL_URL`: Target AI tool URL
- `EDGE_DEBUG_PORT`: CDP port (default: 9222)
- `MAX_SESSIONS`: Concurrent session limit (default: 3)
- `RESPONSE_TIMEOUT`: Response timeout in seconds (default: 120)
- `SELECTOR_*`: CSS selectors for UI elements

## Key Implementation Details

- Messages are sent using `Ctrl+Enter` keystroke
- Long text (>500 chars) is injected via JavaScript to avoid typing delays
- Response detection waits for content stability (no changes for 3 checks)
- Debug screenshots are saved to `./debug/` directory on errors
