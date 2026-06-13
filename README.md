# AutoSynth-Bridge

**Browser-Automated Multi-Model AI Debate and Research Aggregation Framework**

> A system that orchestrates collaborative reasoning across multiple web-based AI models (ChatGPT, Gemini, Claude) through browser automation, requiring zero API keys. AutoSynth-Bridge uses Playwright and Chrome DevTools Protocol to control real browsers, simulate human interaction with web AI interfaces, and expose the aggregated results through a unified FastAPI service.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Core Modules](#core-modules)
- [API Reference](#api-reference)
- [Running Modes](#running-modes)
- [Security Considerations](#security-considerations)
- [Research and Academic Context](#research-and-academic-context)
- [Roadmap](#roadmap)
- [License](#license)
- [Contact](#contact)

---

## Overview

Accessing large language models through official APIs incurs per-token costs and is subject to rate limits, regional restrictions, and model availability constraints. AutoSynth-Bridge takes an alternative approach: it automates real browser sessions to interact with the web interfaces of ChatGPT, Gemini, and Claude, treating each as a participant in a structured multi-round debate.

The system implements a **three-model collaborative debate framework** where each model is assigned a distinct cognitive role (Architect, Critic, Executor, Researcher, or Judge). A debate engine orchestrates multi-round exchanges, computes consensus scores, and generates structured execution plans. The results are persisted through a dual-storage trajectory system (SQLite index + JSON detail) for later retrieval and analysis.

In addition to debate orchestration, the system provides a **paper humanization module** that applies multiple rewriting strategies (sentence restructuring, style injection, academic polishing) to reduce similarity scores in academic texts, leveraging the same browser-automated AI access.

### Comparison with Conventional Approaches

| Dimension | API-Based Approach | AutoSynth-Bridge |
|-----------|-------------------|------------------|
| Cost | Per-token billing | Zero cost (web scraping) |
| Model source | Official API (restricted) | Real web AI interfaces |
| Multi-model collaboration | Paid multi-API calls | Browser automation + debate engine |
| Memory persistence | None or simple cache | TrajectoryStore with SQLite + JSON |
| Paper humanization | API-dependent rewriting | Web AI + multi-strategy rewriting |

---

## Key Features

### Multi-Model Debate Engine

Orchestrates structured debates across multiple AI models with role assignment (Architect, Critic, Executor, Researcher, Judge), multi-round execution, consensus computation, and execution plan generation.

### Browser Automation via Playwright

Controls real browser sessions through Playwright or direct Chrome DevTools Protocol (CDP) WebSocket connections. Supports ChatGPT, Gemini, and Claude web interfaces with configurable CSS selectors.

### Provider Registry and Fallback Chain

A unified registry manages all AI providers (web-based and API-compatible). A fallback chain mechanism automatically switches to the next available provider when the primary fails.

### Trajectory Store (Memory Persistence)

Debate contexts and results are persisted through a dual-storage system: SQLite for indexed metadata queries and JSON files for full debate record archival.

### Paper Humanization

Multiple rewriting strategies for academic text processing:

| Strategy | Effect |
|----------|--------|
| `sentence_restructure` | Sentence pattern variation |
| `logic_reorder` | Paragraph resequencing |
| `style_injection` | Natural expression injection |
| `academic_polish` | Formal register enhancement |
| `deep_rewrite` | Comprehensive combination |

Section-aware processing automatically identifies paper sections (Abstract, Introduction, Methods, Experiment, Discussion, Conclusion) and applies tailored strategies.

### Safety Mechanisms

- `ExecutionPlan.is_step_safe()` -- validates execution steps against forbidden commands and file patterns.
- `SafeExecutor` -- sandboxed code execution with directory allowlists and command blocklists.

---

## Architecture

```
+-------------------------------------------------------+
|                   User Request (HTTP)                  |
+---------------------------+---------------------------+
                            |
                            v
+-------------------------------------------------------+
|              FastAPI Service (main.py, :8090)          |
+-------------------------------------------------------+
                            |
                            v
+-------------------------------------------------------+
|              Bridge Dispatcher (bridge.py)             |
|  +------------------+    +------------------------+   |
|  | Web Debate Mode  |    | Paper Humanization     |   |
|  | DebateEngine     |    | PaperHumanizer         |   |
|  +--------+---------+    +------------------------+   |
|           |                                            |
|  +--------v------------------------------------------+|
|  |         Provider Registry                         ||
|  |  +-- WebProvider (Playwright browser control)     ||
|  |  +-- FallbackChain (multi-provider failover)      ||
|  |  +-- OpenAICompatible (standard API adapter)      ||
|  +---------------------------------------------------+|
+-------------------------------------------------------+
           |
           v
+-------------------------------------------------------+
|              Memory Layer                             |
|  TrajectoryStore (SQLite index + JSON detail)         |
|  MemoryPalace (runs/ directory, debate context)       |
+-------------------------------------------------------+
           |
           v
+-------------------------------------------------------+
|              Target Web AI Interfaces                 |
|  +-- ChatGPT (chatgpt.com)                           |
|  +-- Gemini (gemini.google.com)                       |
|  +-- Claude (claude.ai)                               |
|  +-- Any browser-accessible web AI                    |
+-------------------------------------------------------+
```

### Three-Model Debate Mechanism

```
                  +---------------------+
                  |  DebateJudge (GPT)  |  <-- Judge: evaluates debate quality
                  |  Quality + Consensus|
                  +---------+-----------+
                            |
            +---------------+----------------+
            |                                |
    +-------v-----------+          +---------v----------+
    |  Gemini (Diverger) |          | Claude (Executor)  |
    |  ARCHITECT role    |          | EXECUTOR role      |
    |  Proposes plans    |          | Grounds execution  |
    +--------------------+          +--------------------+
            |                                |
            +-------------+------------------+
                          |
                    +-----v-----+
                    | Consensus |
                    | Output    |
                    +-----------+
```

### Debate Role Definitions

| Role | Responsibility | Keywords |
|------|---------------|----------|
| ARCHITECT | Proposes structure and plans | architecture, design, plan |
| CRITIC | Identifies risks and questions feasibility | risk, problem, infeasible |
| EXECUTOR | Decomposes plans into implementable steps | steps, implementation, execution |
| RESEARCHER | Gathers evidence and background information | evidence, background, facts |
| JUDGE | Synthesizes opinions and generates consensus | conclusion, consensus, summary |

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | Python 3.10+, FastAPI, Uvicorn | API service |
| Browser Automation | Playwright, CDP WebSocket | Web AI interaction |
| Agent Framework | LangGraph, LangChain Core | Debate state machine |
| Embeddings | sentence-transformers, PyTorch | Semantic similarity |
| Provider System | Custom ProviderRegistry, FallbackChain | Multi-provider management |
| Memory | SQLite + JSON dual storage | Trajectory persistence |
| Configuration | pydantic-settings, python-dotenv | Environment management |
| Version Control | GitPython | Diff-based code tracking |

---

## Quick Start

### Prerequisites

- Python 3.10 or later
- Chrome or Edge browser installed
- 8 GB+ RAM recommended

### 1. Install Dependencies

```bash
cd AutoSynth-Bridge
pip install -r requirements.txt
playwright install chrome
```

### 2. Start Chrome with Debug Port

**Windows:**

```bat
chrome.exe --remote-debugging-port=9222 --user-data-dir="./browser_data"
```

**Linux / macOS:**

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir="./browser_data"
```

Or use the provided script:

```bat
1_start_chrome.bat
```

### 3. Start the Service

```bat
python main.py
```

The service runs at `http://127.0.0.1:8090`.

### One-Click Launch

```bat
run.bat
```

This script starts Chrome with the debug port, waits for initialization, then launches the bridge service.

---

## Project Structure

```
AutoSynth-Bridge/
├── main.py                          # FastAPI entry point (port 8090)
├── bridge.py                        # Unified dispatcher (web/humanize/memory)
├── config.py                        # Configuration management (pydantic-settings)
├── state.py                         # Data structure definitions
├── database.py                      # SQLite run log
├── humanize.py                      # Paper humanization engine
├── memory_palace.py                 # Memory persistence
├── cdp_browser.py                   # CDP WebSocket direct connection
├── web_debate.py                    # Playwright web automation
├── providers.py                     # Legacy provider module
│
├── core/                            # Core engine modules
│   ├── debate_engine.py             # Multi-model debate orchestration
│   ├── schemas.py                   # Data structures (DebateRequest, ExecutionPlan)
│   ├── debate_roles.py              # Role definitions and mapping
│   ├── debate_prompts.py            # System prompt templates per role
│   ├── claude_adapter.py            # Claude integration adapter
│   └── safe_executor.py             # Sandboxed code execution
│
├── providers/                       # Provider abstraction layer
│   ├── base.py                      # BaseProvider interface
│   ├── registry.py                  # ProviderRegistry (register/get/health)
│   ├── web_provider.py              # WebProvider (Playwright browser control)
│   ├── fallback_chain.py            # FallbackChain (automatic failover)
│   ├── openai_compatible.py         # OpenAI API compatible adapter
│   └── errors.py                    # Error definitions
│
├── agents/                          # Agent implementations
│   ├── base_agent.py                # Base agent class
│   ├── gpt_agent.py                 # GPT web scraping agent
│   ├── gemini_agent.py              # Gemini web scraping agent
│   └── claude_executor.py           # Claude code execution agent
│
├── graph/                           # LangGraph debate flow
│   ├── debate_graph.py              # State machine control
│   └── convergence.py               # Consensus convergence logic
│
├── memory/                          # Memory module
│   └── trajectory_store.py          # SQLite + JSON dual storage
│
├── api/                             # API routes
│   └── provider_routes.py           # Provider management endpoints
│
├── prompts/                         # Prompt templates
│   ├── system_gpt.md                # GPT system prompt
│   ├── system_gemini.md             # Gemini system prompt
│   └── claude_task_template.md      # Claude task template
│
├── docs/                            # Validation documentation
│   ├── stage3_debate_engine_validation.md
│   ├── stage4_provider_registry_validation.md
│   ├── stage6_safe_executor_validation.md
│   └── stage7_web_provider_validation.md
│
├── 1_start_chrome.bat               # Start Chrome (debug mode)
├── 2_run_bridge.bat                 # Start bridge service
├── run.bat                          # One-click launch
├── Dockerfile                       # Container deployment
├── requirements.txt                 # Python dependencies
├── REPRODUCE.md                     # Reproduction guide
├── SCI_FRAMEWORK.md                 # SCI paper framework
└── README.md
```

---

## Core Modules

### DebateEngine (`core/debate_engine.py`)

The central orchestration module for multi-model debates. Key behaviors:

1. **Participant Resolution** -- maps provider names to roles using `get_default_role_map()`.
2. **Multi-Round Execution** -- each round runs all participants concurrently (`asyncio.gather`), then serializes speech order (Architect -> Critic -> Executor).
3. **Consensus Computation** -- `ConsensusResult` evaluates consistency score, semantic similarity, agreement/disagreement points, and risk factors.
4. **Execution Plan Generation** -- `ExecutionPlan` outputs actionable steps with safety constraints.

### WebProvider (`providers/web_provider.py`)

Browser automation through Playwright or direct CDP connection. Supports configurable CSS selectors per website:

| Website | Input Selector | Submit Button | Response Selector |
|---------|---------------|---------------|-------------------|
| ChatGPT | `textarea` | `button[data-testid="send-button"]` | `[data-testid="turn"] .markdown` |
| Gemini | `div[contenteditable='true']` | `button.send-button` | `.message-content` |
| Claude | `[data-testid="composer-input"]` | `button[aria-label="Send message"]` | `.claude-message` |

### ProviderRegistry (`providers/registry.py`)

Unified management of all AI providers with registration, retrieval, and health-check capabilities.

### FallbackChain (`providers/fallback_chain.py`)

Automatic provider failover: when the primary provider fails, the chain attempts the next registered provider in sequence.

### TrajectoryStore (`memory/trajectory_store.py`)

Dual-storage persistence: SQLite (`trajectory_index` table) for metadata indexing and JSON files (`trajectories/{task_id}.json`) for full debate record archival.

---

## API Reference

### Health Check

```
GET /health
```

Returns service status and provider availability.

### Web Debate

```
POST /api/web/debate
```

Initiates a multi-model debate through browser automation.

**Request Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_requirement` | string | Yes | User query or requirement |
| `topic` | string | Yes | Debate topic |
| `task_type` | string | No | Task type: `sci_paper`, `research`, `analysis` (default: `sci_paper`) |
| `max_rounds` | int | No | Maximum debate rounds (default: 3) |
| `headless` | bool | No | Run browser in headless mode |

**Example:**

```bash
curl -X POST http://127.0.0.1:8090/api/web/debate \
  -H "Content-Type: application/json" \
  -d '{
    "user_requirement": "Analyze innovation points for TCM RAG systems",
    "topic": "TCM RAG",
    "task_type": "sci_paper",
    "max_rounds": 3
  }'
```

### Paper Humanization

```
POST /api/humanize
```

Applies rewriting strategies to academic text for similarity reduction.

```
POST /api/humanize/sections
```

Section-aware humanization that automatically identifies and processes paper sections with tailored strategies.

### Memory and History

```
GET /api/memory/{task_id}           # Get task details
GET /api/memory/{task_id}/context   # Get Claude-compatible context
GET /api/memory/list?limit=20       # List all tasks
GET /api/runs?limit=20              # Debate record history
GET /api/costs                      # Cost statistics (all zero for web scraping)
GET /api/providers/stats            # Provider statistics
```

Full API documentation is available at `http://localhost:8090/docs` when the service is running.

---

## Running Modes

### Web Mode (Primary)

Uses Playwright to control a real browser and interact with web AI interfaces.

- **Advantage**: Zero cost, no API key required.
- **Use case**: Research prototyping, budget-constrained scenarios.
- **Implementation**: `providers/web_provider.py`

### CDP Mode (Alternative)

Direct Chrome DevTools Protocol WebSocket connection, bypassing Playwright.

- **Advantage**: Lower-level control, potentially faster.
- **Use case**: Advanced users requiring custom browser control.
- **Implementation**: `cdp_browser.py`

### OpenAI-Compatible Mode

Standard API adapter for environments where API keys are available.

- **Advantage**: More reliable, higher throughput.
- **Use case**: Production environments with API access.
- **Implementation**: `providers/openai_compatible.py`

---

## Security Considerations

### ExecutionPlan Safety

The `ExecutionPlan` class validates each execution step against forbidden commands and file patterns before allowing execution:

```python
is_safe, reason = plan.is_step_safe(step_description)
```

### SafeExecutor

Provides sandboxed code execution with:

- Directory allowlists -- restricts file access to specified paths.
- Command blocklists -- prevents dangerous operations (e.g., `rm -rf`, `format`).
- Output validation -- verifies execution results before returning.

---

## Research and Academic Context

AutoSynth-Bridge explores the intersection of browser automation, multi-agent debate, and zero-cost AI aggregation. Related academic materials:

- **SCI Paper Framework**: `SCI_FRAMEWORK.md` -- structured outline for a journal submission on browser-automated multi-model collaborative reasoning.

---

## Roadmap

- [ ] Support for additional web AI providers (Perplexity, Copilot, etc.).
- [ ] Automated research workflow execution (ResearchAgent mode).
- [ ] Memory priority ranking algorithm optimization.
- [ ] Custom debate role definitions.
- [ ] WebSocket real-time push for debate progress.
- [ ] Distributed browser pool for concurrent debate sessions.

---

## License

This project is released under the MIT License. See `LICENSE` for details.

---

## Contact

For questions, collaborations, or academic inquiries, please open an issue on the repository or contact the maintainers directly.
