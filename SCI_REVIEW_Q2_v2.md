# Peer Review Report -- AutoSynth-Bridge (Q2 SCI)

**Project**: AutoSynth-Bridge -- Browser-Automated Multi-Model AI Debate Framework
**Review Date**: 2026-06-01
**Reviewer**: Q2 SCI Peer Review Agent
**Rubric**: 7-Dimension (Novelty 0-20, Literature 0-15, Methodology 0-20, Results 0-20, Discussion 0-10, Writing 0-10, Format 0-5)

---

## Summary Scores

| Dimension | Score | Max | Rationale |
|-----------|-------|-----|-----------|
| Novelty | 4 | 20 | Role-based multi-agent debate is established; keyword-based convergence scoring is trivial |
| Literature | 0 | 15 | Zero academic citations; no related work discussion |
| Methodology | 3 | 20 | Multiple runtime bugs; two incompatible provider systems; unimplemented core modules |
| Results | 0 | 20 | Zero experimental results; all tests use mocks |
| Discussion | 1 | 10 | No limitations analysis; no failure mode discussion |
| Writing | 5 | 10 | Good documentation structure but not academic prose |
| Format | 3 | 5 | Well-organized code; missing LICENSE; Dockerfile port mismatch |
| **TOTAL** | **16** | **100** | |

**Verdict: REJECT**

---

## Dimension 1: Novelty (4/20)

**Claimed Innovations:**
1. Three-model role-based debate (GPT=Critic, Gemini=Architect, Claude=Executor)
2. Three-stage convergence scoring
3. Zero-cost browser automation for LLM access
4. Safety sandbox for code execution

**Assessment:**
- Role-based multi-agent debate is well-established. AutoGen (Microsoft, 2023), CrewAI, ChatDev (2023), and MetaGPT (2023) all implement similar patterns. No comparison with these works.
- Browser automation for AI is a known technique (browser-use, LaVague). "Zero cost" claim is misleading -- relies on free-tier web interfaces subject to rate limits, CAPTCHAs, and ToS violations.
- Convergence scoring (Section 3 of SCI_FRAMEWORK.md) is keyword counting: checking if words like "创新", "实验" appear in text + cosine similarity. Not novel.
- Safety executor is blocklist pattern matching -- not a novel sandboxing technique.

**Evidence from code:**
- `_keyword_overlap_score` (debate_engine.py lines 270-283): set intersection of `\W+`-split tokens
- `_keyword_overlap` (graph/convergence.py lines 111-116): counting substring presence of fixed keyword list

---

## Dimension 2: Literature Review (0/15)

**Fatal Deficiency:**
- Zero academic citations anywhere in the codebase
- No related work section in any document
- SCI_FRAMEWORK.md is auto-generated documentation, not a literature review
- `专利技术交底书.md` describes the system without citing any prior art
- No comparison with AutoGen, CrewAI, ChatDev, MetaGPT, CAMEL
- No discussion of consensus measurement methods
- No discussion of browser automation ethics or ToS implications

---

## Dimension 3: Methodology (3/20)

### Critical Bugs Found:

**Bug 1 -- Missing datetime import (RUNTIME CRASH):**
main.py line 422: `datetime.now().isoformat()` called but `datetime` not imported. NameError on any debate exception.

**Bug 2 -- Broken humanize import:**
humanize.py line 13: `from providers import ProviderRouter` imports from legacy `providers.py`. Bridge._get_humanizer() imports `build_provider_router` from graph.debate_graph. Legacy ProviderRouter vs new ProviderRegistry are incompatible.

**Bug 3 -- SafeExecutor never executes:**
core/safe_executor.py lines 194-199: when dry_run=False and step passes validation, output is `[SIMULATED] Step validated: {step_desc[:200]}`. No actual command execution.

**Bug 4 -- Inverted risk score logic:**
graph/convergence.py lines 47-58: RiskResolutionScore.score computes `1.0 - sum(risks) / len(risks)`. Boolean fields mix positive signals (sci_feasibility=True means good) with negative signals (exaggeration_risk=True means bad).

**Bug 5 -- Convergence defaults to 0.5:**
graph/convergence.py line 103: when sentence-transformers unavailable, calculate_similarity returns 0.5, artificially inflating scores.

### Structural Issues:
- Two parallel provider systems: `providers.py` (legacy) vs `providers/` package (new)
- Two parallel memory systems: `memory_palace.py` (JSON) vs `memory/trajectory_store.py` (SQLite + JSON)
- Two parallel convergence systems: `graph/convergence.py` vs `core/debate_engine.py`
- LangGraph state machine (V1) and custom DebateEngine (V2) coexist without integration
- Hardcoded CSS selectors will break with any UI change

---

## Dimension 4: Results (0/20)

**Fatal Deficiency:**
- Zero experimental results
- `runs/` and `trajectories/` directories contain no actual debate outputs
- No end-to-end integration test with real LLM calls
- All 17 test files use mock providers returning hardcoded strings
- No evaluation of debate quality, convergence accuracy, or output coherence
- No measurement of "zero cost" claim (latency, success rate)
- No comparison with direct API-based multi-agent systems
- No evaluation of humanization module (no before/after similarity scores)

**The system has never been run end-to-end with real LLM calls.**

---

## Dimension 5: Discussion (1/10)

**Critical Deficiencies:**
- No discussion of limitations
- No failure mode analysis
- No ethical discussion of browser automation (ToS violations, CAPTCHA bypass)
- No discussion of keyword-based convergence scoring adequacy
- No discussion of scalability (single-session, no concurrent debate support)
- REPRODUCE.md acknowledges issues but does not discuss analytically

---

## Dimension 6: Writing Quality (5/10)

**Strengths:**
- README.md well-structured with architecture diagrams and API reference
- Code has consistent docstrings and comments
- SCI_FRAMEWORK.md provides comprehensive technical description

**Weaknesses:**
- Mixed Chinese/English throughout without clear language strategy
- SCI_FRAMEWORK.md reads as auto-generated code documentation, not academic prose
- No abstract, no introduction with research questions, no conclusion
- No manuscript exists

---

## Dimension 7: Format (3/5)

**Strengths:**
- Well-organized directory structure
- Consistent Python code style
- requirements.txt and Dockerfile provided

**Weaknesses:**
- LICENSE file referenced in README but does not exist
- Dockerfile exposes port 8000 but main.py runs on port 8090 (mismatch)
- No .env.example referenced in REPRODUCE.md

---

## Top 3 Critical Issues

### Issue 1: Zero Experimental Validation (Fatal)
The system has never been run end-to-end with real LLM calls. All tests use mocks. For Q2 acceptance, run debates on 10+ research topics and measure convergence quality.

### Issue 2: Multiple Runtime Bugs (Critical)
- Missing datetime import causes crash on exception
- SafeExecutor never executes commands (always simulated)
- Humanize module has broken import path

### Issue 3: Two Incompatible Architectures
The project maintains two parallel systems (V1: LangGraph/debate_graph, V2: custom DebateEngine) with incompatible provider and memory systems. This needs to be unified before review.

---

## Critical Issues Table

| Severity | Issue | Location |
|----------|-------|----------|
| CRITICAL | Runtime crash: missing datetime import | main.py:422 |
| CRITICAL | SafeExecutor never executes commands | core/safe_executor.py:194-199 |
| CRITICAL | Humanize module import path broken | humanize.py:13 |
| CRITICAL | Zero experimental results | -- |
| CRITICAL | Zero literature citations | -- |
| HIGH | Two incompatible provider systems | providers.py vs providers/ |
| HIGH | Two incompatible convergence systems | graph/convergence.py vs core/debate_engine.py |
| HIGH | Convergence scoring is trivial keyword counting | debate_engine.py:270-283 |
| MEDIUM | Inverted risk score logic | graph/convergence.py:47-58 |
| MEDIUM | Missing LICENSE file | -- |
| MEDIUM | Dockerfile port mismatch (8000 vs 8090) | Dockerfile |

---

## Recommendation

**REJECT -- Early-stage prototype, not publication-ready**

This project demonstrates competent software engineering (clean architecture, comprehensive test structure, good documentation) but fails as a research contribution because:
1. No experimental results (system never run end-to-end)
2. Zero literature citations
3. Multiple critical runtime bugs in core modules
4. Convergence scoring is trivial keyword counting with no validation
5. Two incompatible parallel architectures

Path to acceptance would require: (1) fixing all runtime bugs, (2) running real experiments with 10+ debates, (3) adding literature review citing AutoGen/CrewAI/MetaGPT, (4) validating convergence scoring against human judgment, (5) unifying the two parallel architectures.