# REPRODUCE.md - AutoSynth-Bridge

## Prerequisites

- **Python**: 3.10+
- **OS**: Linux / Windows
- **GPU**: Not required
- **Browser**: Chromium/Chrome (for Playwright)

## Install

```bash
cd AutoSynth-Bridge
pip install -r requirements.txt
playwright install chromium
```

Dependencies: fastapi, uvicorn, pydantic, httpx, langgraph, langchain-core, sentence-transformers, torch, numpy, playwright, GitPython

## Environment Setup

```bash
cp .env.example .env
# Configure API keys for OpenAI/Gemini if using API mode
```

## Smoke Test

```bash
python test_bridge.py
python test_openai_provider_error_mapping.py
```

## Run Server

```bash
python main.py
```

## Expected Outputs

- Browser-automated AI aggregation (zero API cost mode)
- Multi-model debate engine (ChatGPT + Gemini + Claude web)
- MemoryPalace persistent debate context
- FastAPI API endpoints

## Known Issues

- Requires Playwright browser installation (~300MB)
- sentence-transformers + torch are heavy dependencies
- Browser automation is fragile (UI changes break selectors)
- No hardcoded paths in core code, but test files may reference local paths
- First run requires `playwright install chromium`
