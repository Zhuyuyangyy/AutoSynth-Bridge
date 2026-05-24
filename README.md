# AutoSynth-Bridge 智研桥

> 用浏览器自动化抓取网页端AI，封装成API接口进行调用。本项目不依赖付费API Key，通过 Playwright / CDP 控制真实浏览器，模拟人工在 ChatGPT、Gemini 网页上提问，解析回复内容后通过 FastAPI 对外提供接口服务。

---

## 核心定位

**AutoSynth-Bridge** 是一款基于浏览器自动化的 AI 聚合研究框架。它通过 Playwright 和 Chrome DevTools Protocol (CDP) 控制真实浏览器，模拟人工操作网页版 AI（ChatGPT、Gemini、Claude），实现零成本的多模型协同辩论与自动化研究。

### 核心优势

| 维度 | 传统方案 | 本项目 |
|------|---------|--------|
| API 成本 | 按 token 付费，成本高昂 | 零成本，纯网页抓取 |
| 模型来源 | 官方 API（受限） | 真实网页 AI（无限制） |
| 多模型协同 | 付费 multi-api 调用 | 浏览器自动化 + 辩论引擎 |
| 人味化降重 | 依赖 API 改写 | 网页 AI + 多策略改写 |
| 记忆持久化 | 无或简单缓存 | MemoryPalace 持久化辩论上下文 |

---

## 系统架构

### 整体架构图

```
用户请求（HTTP API /curl）
     │
     ▼
FastAPI (main.py, port 8090)
     │
     ▼
┌─────────────────────────────────────────────────┐
│           Bridge 调度器（bridge.py）            │
│  ┌───────────────┐    ┌──────────────────────┐ │
│  │ Web辩论模式    │    │ 人味化降重模式        │ │
│  │ DebateEngine  │    │ PaperHumanizer       │ │
│  └───────┬───────┘    └──────────────────────┘ │
│          │                                       │
│  ┌───────▼───────────────────────────────────┐ │
│  │     Provider Registry（提供者注册中心）      │ │
│  │  ├─ WebProvider (Playwright 浏览器控制)    │ │
│  │  ├─ FallbackChain (多提供者链式调用)       │ │
│  │  └─ OpenAICompatible (标准 API 兼容)       │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────┐
│              记忆持久化层                         │
│  TrajectoryStore (SQLite + JSON 双存储)          │
│  MemoryPalace (runs/ 目录，辩论上下文持久化)     │
└─────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────┐
│              目标网页 AI                         │
│  ├─ ChatGPT (chatgpt.com)                      │
│  ├─ Gemini (gemini.google.com)                │
│  ├─ Claude (claude.ai)                         │
│  └─ 任意支持浏览器操作的网页                    │
└─────────────────────────────────────────────────┘
```

### 三模型协同机制

AutoSynth-Bridge 实现了独特的三模型协同辩论框架：

```
                    ┌─────────────────────┐
                    │  DebateJudge (GPT)  │ ← 裁判角色，评判辩论质量
                    │   质量评估 + 共识   │
                    └──────────┬──────────┘
                               │
            ┌──────────────────┴──────────────────┐
            │                                     │
    ┌───────▼───────────┐               ┌────────▼────────┐
    │  Gemini (发散者)   │               │  Claude (落地者) │
    │  ARCHITECT 角色    │               │  EXECUTOR 角色  │
    │  提出方案 + 设计    │               │  落地执行 + 验证 │
    └───────────────────┘               └─────────────────┘
            │                                     │
            └─────────────┬─────────────────────┘
                          │
                    ┌─────▼─────┐
                    │  共识输出  │
                    │ ExecutionPlan│
                    └───────────┘
```

#### 角色定义（DebateRole）

| 角色 | 说明 | 关键词 |
|------|------|--------|
| ARCHITECT | 架构设计者，负责提出方案、设计结构、规划路线 | 架构、设计、方案、规划 |
| CRITIC | 风险审查者，负责找问题、提反对、质疑可行性 | 问题、风险、质疑、不可行 |
| EXECUTOR | 落地工程师，负责把方案拆成步骤、评估落地难度 | 步骤、落地、实施、执行 |
| RESEARCHER | 资料分析者，负责找资料、查事实、补背景 | 资料、背景、事实、依据 |
| JUDGE | 最终裁判，负责综合各方意见、生成共识、给出结论 | 结论、共识、总结 |

---

## 核心功能模块

### 1. Web辩论引擎（DebateEngine）

通过 `DebateEngine` 类实现多模型协同辩论：

```python
from core.debate_engine import DebateEngine
from core.schemas import DebateRequest

engine = DebateEngine()

request = DebateRequest(
    query="分析中医RAG系统的创新点",
    topic="中医RAG",
    task_type="sci_paper",
    participants=["gpt", "gemini", "claude"],
    rounds=3
)

result = await engine.run(request)
```

**辩论流程**：

1. **初始化**：解析参与者列表，分配角色（ARCHITECT/CRITIC/EXECUTOR）
2. **并发生成**：多模型同时生成回复（利用 `asyncio.gather`）
3. **轮次执行**：每轮每个参与者依次发言，形成辩论链
4. **共识计算**：`ConsensusResult` 评估一致性得分
5. **执行计划**：`ExecutionPlan` 输出可执行的步骤计划

**核心数据结构**：

```python
@dataclass
class DebateRequest:
    query: str              # 用户查询
    topic: str              # 辩论主题
    task_type: str          # 任务类型：sci_paper/research/analysis
    participants: list[str] # 参与者列表
    participant_roles: Optional[list[ParticipantRole]]  # 角色分配
    rounds: int = 3         # 辩论轮次

@dataclass
class ExecutionPlan:
    title: str              # 计划标题
    summary: str            # 执行摘要
    goal: str               # 目标描述
    steps: List[str]        # 具体步骤
    constraints: List[str]  # 约束条件
    allowed_commands: List[str]   # 允许的命令
    forbidden_commands: List[str] # 禁止的命令
    acceptance_tests: List[str]   # 验收测试
```

### 2. Playwright 网页自动化（WebProvider）

`WebProvider` 通过 Playwright 控制真实浏览器：

```python
from providers.web_provider import WebProvider, WEBSITE_SELECTORS

provider = WebProvider(
    name="chatgpt",
    website_key="chatgpt",
    cdp_url="ws://localhost:9222"
)

# 自动化交互流程
# 1. 连接到浏览器 CDP
# 2. 导航到目标网页
# 3. 填写输入框
# 4. 点击发送按钮
# 5. 等待加载完成
# 6. 解析响应内容
```

**支持的网站选择器**：

| 网站 | 输入选择器 | 提交按钮 | 响应选择器 |
|------|-----------|---------|-----------|
| ChatGPT | `textarea` | `button[data-testid="send-button"]` | `[data-testid="turn"] .markdown` |
| Gemini | `div[contenteditable='true']` | `button.send-button` | `.message-content` |
| Claude | `[data-testid="composer-input"]` | `button[aria-label="Send message"]` | `.claude-message` |

### 3. FallbackChain 链式调用

当主提供者失败时，`FallbackChain` 自动切换到备用提供者：

```python
from providers.fallback_chain import FallbackChain

chain = FallbackChain(chain_name="main_chain")
chain.add_provider(web_provider_chatgpt)
chain.add_provider(web_provider_gemini)
chain.add_provider(openai_fallback)

# 自动尝试第一个可用提供者
response = await chain.generate(messages)
```

### 4. 记忆优先级（MemoryPriority / TrajectoryStore）

辩论上下文通过 `TrajectoryStore` 持久化存储：

```python
from memory.trajectory_store import TrajectoryStore

store = TrajectoryStore(
    storage_dir="./trajectories",
    db_path="./database/trajectories.db"
)

# 保存辩论结果
record = store.save(debate_result)

# 查询历史
records = store.list_records(limit=20, status="completed")

# 恢复上下文
record = store.get(task_id)
```

**存储结构**：

- **SQLite 索引**：`trajectory_index` 表存储任务元数据
- **JSON 详情**：`trajectories/{task_id}.json` 存储完整辩论记录

### 5. ProviderRegistry 提供者注册中心

统一管理所有 AI 提供者：

```python
from providers.registry import ProviderRegistry

registry = ProviderRegistry()
registry.register("gpt", web_provider_gpt)
registry.register("gemini", web_provider_gemini)

# 健康检查
health = await registry.health_check_all()

# 获取提供者
provider = registry.get("gpt")
```

---

## 快速启动

### 环境要求

- Python 3.10+
- Windows / macOS / Linux
- 建议 8GB+ 内存
- 已安装 Chrome 或 Edge 浏览器

### 1. 安装依赖

```bash
cd D:\ZYY Project\AutoSynth-Bridge
pip install playwright fastapi uvicorn
playwright install chrome
```

### 2. 启动 Chrome（带调试端口）

**Windows**：

```bat
chrome.exe --remote-debugging-port=9222 --user-data-dir="./browser_data"
```

**Linux/macOS**：

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir="./browser_data"
```

或使用项目脚本：

```bat
1_start_chrome.bat
```

### 3. 启动服务

```bat
python main.py
# 服务运行在 http://127.0.0.1:8090
```

---

## API 接口文档

### 健康检查

```http
GET /health
```

**响应示例**：

```json
{
  "status": "ok",
  "version": "1.0.0",
  "providers": {
    "chatgpt": {"status": "available", "type": "web"},
    "gemini": {"status": "available", "type": "web"}
  }
}
```

---

### Web辩论（核心接口）

**POST /api/web/debate**

通过浏览器自动化抓取 ChatGPT 和 Gemini 网页版，进行协同辩论。

```bash
curl -X POST http://127.0.0.1:8090/api/web/debate \
  -H "Content-Type: application/json" \
  -d '{
    "user_requirement": "生成SCI创新方向",
    "topic": "中医RAG",
    "task_type": "sci_paper",
    "max_rounds": 3,
    "headless": true
  }'
```

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_requirement | string | 是 | 用户需求描述 |
| topic | string | 是 | 辩论主题 |
| task_type | string | 否 | 任务类型：sci_paper / research / analysis，默认 sci_paper |
| max_rounds | int | 否 | 最大辩论轮次，默认 3 |
| headless | bool | 否 | 是否无头模式运行 |

**工作原理**：

1. Playwright 启动浏览器，导航到 `chatgpt.com`
2. 自动填入问题，点击发送
3. 等待 AI 生成回复完成
4. 解析网页中的回复内容
5. 切换到 Gemini 网页，重复上述流程
6. 两模型多轮辩论，结果存入 MemoryPalace

**响应字段**：

| 字段 | 说明 |
|------|------|
| task_id | 任务唯一标识 |
| mode | 固定为 "web" |
| debate_result | 辩论结果（JSON） |
| context_for_claude | 供 Claude 使用的完整上下文 |

---

### 人味化降重

**POST /api/humanize**

对论文文本进行人味化降重（通过网页 AI + 改写策略）。

```bash
curl -X POST http://127.0.0.1:8090/api/humanize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "要降重的论文文本...",
    "strategies": ["sentence_restructure", "style_injection", "academic_polish"]
  }'
```

**改写策略说明**：

| 策略 | 效果 |
|------|------|
| sentence_restructure | 句式重组，避免重复句式 |
| logic_reorder | 逻辑重排，调整段落顺序 |
| style_injection | 风格注入，加入人味表达 |
| academic_polish | 学术润色，提升正式程度 |
| deep_rewrite | 深度改写，综合以上所有 |

---

### 按章节降重

**POST /api/humanize/sections**

自动识别论文章节（摘要、引言、方法、实验、讨论、结论），对不同章节使用不同改写策略。

```bash
curl -X POST http://127.0.0.1:8090/api/humanize/sections \
  -H "Content-Type: application/json" \
  -d '{
    "text": "完整论文文本..."
  }'
```

**章节识别逻辑**：

```
摘要 (Abstract) → 学术润色 + 句式简化
引言 (Introduction) → 背景补充 + 逻辑强化
方法 (Methods) → 技术术语保留 + 表达多样化
实验 (Experiment) → 数据呈现优化 + 图表描述增强
讨论 (Discussion) → 观点深化 + 论证强化
结论 (Conclusion) → 总结精简 + 展望扩展
```

---

### 查询记忆

```http
GET /api/memory/{task_id}          # 获取任务详情
GET /api/memory/{task_id}/context # 获取 Claude 上下文格式
GET /api/memory/list?limit=20      # 列出所有任务
```

---

### 辩论历史与成本

```http
GET /api/runs?limit=20              # 辩论记录列表
GET /api/costs                      # 成本统计（均为0，网页抓取免费）
GET /api/providers/stats            # Provider 统计
```

---

## 两种运行模式

### Web模式（当前主推）

使用 Playwright 控制真实浏览器，模拟人工操作：

- **优势**：零成本，无需 API Key
- **适用**：测试调试、预算有限场景
- **文件**：`providers/web_provider.py`

### CDP模式（备选）

直连 Chrome DevTools Protocol WebSocket，绕过 Playwright：

- **优势**：更底层、更快
- **适用**：高级用户，自定义浏览器控制
- **文件**：`cdp_browser.py`

---

## 核心文件说明

| 文件 | 作用 | 关键功能 |
|------|------|----------|
| `main.py` | FastAPI 入口，端口 8090 | 所有 HTTP API 端点 |
| `bridge.py` | 统一调度器 | Web模式/人味化/记忆查询 |
| `core/debate_engine.py` | 辩论引擎核心 | 多模型协同辩论执行 |
| `core/schemas.py` | 数据结构定义 | DebateRequest/Result/ExecutionPlan |
| `core/debate_roles.py` | 角色定义 | ARCHITECT/CRITIC/EXECUTOR/JUDGE/RESEARCHER |
| `core/debate_prompts.py` | 提示词模板 | 各角色系统提示生成 |
| `providers/web_provider.py` | Playwright 执行器 | 浏览器自动化，网页问答 |
| `providers/fallback_chain.py` | 链式调用 | 多提供者自动切换 |
| `providers/registry.py` | 提供者注册中心 | 注册/获取/健康检查 |
| `providers/base.py` | 提供者基类 | 标准化接口定义 |
| `providers/openai_compatible.py` | OpenAI API 兼容 | 标准 OpenAI 接口支持 |
| `memory/trajectory_store.py` | 轨迹存储器 | SQLite + JSON 双存储 |
| `humanize.py` | 论文降重引擎 | 多策略改写，章节拆分 |
| `cdp_browser.py` | CDP 直连接口 | WebSocket 控制浏览器 |
| `database.py` | 运行日志 | SQLite 记录成本与性能 |
| `config.py` | 配置管理 | 环境变量读取 |
| `state.py` | 状态定义 | 数据结构定义 |

---

## 项目文件结构

```
AutoSynth-Bridge/
├── agents/                    # AI Agent 实现
│   ├── gpt_agent.py          # GPT 网页抓取
│   └── gemini_agent.py       # Gemini 网页抓取
├── graph/                    # LangGraph 辩论流程
│   └── debate_graph.py       # 状态机控制
├── prompts/                   # 提示词模板
│   ├── system_gpt.md
│   └── system_gemini.md
├── core/                      # 核心模块
│   ├── debate_engine.py       # 辩论引擎
│   ├── schemas.py            # 数据结构
│   ├── debate_roles.py       # 角色定义
│   ├── debate_prompts.py     # 提示词
│   ├── claude_adapter.py     # Claude 适配器
│   └── safe_executor.py      # 安全执行器
├── providers/                # 提供者模块
│   ├── base.py              # 基类
│   ├── registry.py          # 注册中心
│   ├── web_provider.py      # Web提供者
│   ├── fallback_chain.py    # 链式调用
│   ├── openai_compatible.py # OpenAI兼容
│   └── errors.py             # 错误定义
├── memory/                    # 记忆模块
│   └── trajectory_store.py   # 轨迹存储
├── database/                  # SQLite 数据库
├── runs/                      # MemoryPalace 记忆存储（JSON）
├── outputs/                   # Claude Code 执行目录
├── browser_data/              # 浏览器用户数据目录
├── api/                       # API 路由
│   └── provider_routes.py    # 提供者路由
├── main.py                    # FastAPI 入口（端口 8090）
├── bridge.py                  # 统一调度器
├── web_debate.py             # Playwright 网页自动化
├── cdp_browser.py            # CDP WebSocket 直连
├── humanize.py               # 论文人味化降重
├── memory_palace.py          # 记忆宫殿
├── database.py               # 运行日志
├── config.py                 # 配置管理
├── state.py                  # 状态定义
├── 1_start_chrome.bat       # 启动 Chrome（调试模式）
├── 2_run_bridge.bat         # 启动 Bridge 服务
└── run.bat                  # 一键启动脚本
```

---

## 启动脚本说明

### 1_start_chrome.bat

启动 Chrome 并开启远程调试端口：

```bat
chrome.exe --remote-debugging-port=9222 --user-data-dir="./browser_data"
```

调试端口 9222 是 CDP 客户端的连接入口。

### 2_run_bridge.bat

启动 AutoSynth-Bridge 服务：

```bat
python main.py
```

服务运行在 `http://127.0.0.1:8090`。

### run.bat

一键启动（Chrome + 服务）：

```bat
call 1_start_chrome.bat
timeout /t 5
call 2_run_bridge.bat
```

---

## 实际使用示例

### 示例 1：通过网页 AI 进行学术辩论

```bash
curl -X POST http://127.0.0.1:8090/api/web/debate \
  -H "Content-Type: application/json" \
  -d '{
    "user_requirement": "分析中医RAG系统的创新点",
    "topic": "中医RAG",
    "task_type": "sci_paper",
    "max_rounds": 3
  }'
```

### 示例 2：人味化降重一篇论文

```bash
curl -X POST http://127.0.0.1:8090/api/humanize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "【粘贴论文内容】",
    "strategies": ["sentence_restructure", "deep_rewrite"]
  }'
```

### 示例 3：查询辩论历史

```bash
curl http://127.0.0.1:8090/api/memory/list
```

### 示例 4：多提供者链式调用

```python
from providers.fallback_chain import FallbackChain

chain = FallbackChain("production_chain")
chain.add_provider(gpt_web)
chain.add_provider(gemini_web)
chain.add_provider(claude_web)

# 当 gpt 失败时自动切换到 gemini
response = await chain.generate(messages)
```

---

## 当前实现状态

| 功能 | 状态 | 说明 |
|------|------|------|
| Playwright 网页自动化辩论 | ✅ 已实现 | providers/web_provider.py |
| CDP WebSocket 直连浏览器 | ✅ 已实现 | cdp_browser.py |
| DebateEngine 多模型辩论 | ✅ 已实现 | core/debate_engine.py |
| ProviderRegistry 注册中心 | ✅ 已实现 | providers/registry.py |
| FallbackChain 链式调用 | ✅ 已实现 | providers/fallback_chain.py |
| TrajectoryStore 轨迹存储 | ✅ 已实现 | memory/trajectory_store.py |
| MemoryPalace 记忆持久化 | ✅ 已实现 | runs/ 目录 JSON 存储 |
| 人味化论文降重 | ✅ 已实现 | humanize.py |
| FastAPI 接口暴露 | ✅ 已实现 | main.py，端口 8090 |
| SQLite 运行日志 | ✅ 已实现 | database.py |
| LangGraph 辩论状态机 | ✅ 已实现 | graph/debate_graph.py |

---

## 技术特点

1. **零 API 成本**：完全基于网页抓取，无需付费 Key
2. **真实 AI 交互**：使用的是真实的网页版 AI，非模拟
3. **三模型协同**：GPT裁判 + Gemini发散 + Claude落地
4. **记忆持久化**：辩论上下文持久化到 JSON，支持后续查询
5. **多策略改写**：人味化降重支持多种改写策略组合
6. **双模式支持**：Web 模式和 CDP 模式可切换
7. **链式容错**：FallbackChain 提供多提供者自动切换
8. **ProviderRegistry**：统一管理所有 AI 提供者

---

## 适用场景

- ✅ 学术辩论与 SCI 创新方向生成
- ✅ 论文人味化降重（无需 API 费用）
- ✅ 多模型协同分析（GPT + Gemini + Claude）
- ✅ 测试调试 AI 对话场景
- ✅ 研究流程自动化（ResearchAgent 模式）
- ❌ 生产环境高并发（建议使用官方 API）

---

## 架构详解：DebateEngine 执行流程

### 初始化阶段

```python
def __init__(self, registry_or_providers):
    self.registry = registry_or_providers  # ProviderRegistry 实例或 dict
    self.role_map = get_default_role_map()   # 默认角色映射
```

### 请求解析阶段

`DebateRequest` 被解析为参与者列表，每个参与者分配角色：

```
GEMINI  → ARCHITECT（架构设计者）
GPT     → CRITIC（风险审查者）
CLAUDE  → EXECUTOR（落地工程师）
```

### 辩论轮次执行

每轮执行：
1. **并发生成**：所有参与者同时生成回复
2. **串行发言**：按 ARCHITECT → CRITIC → EXECUTOR 顺序
3. **上下文更新**：将每轮发言加入历史

### 共识计算

辩论结束后，`_compute_consensus()` 计算：
- `consistency_score`：观点一致程度
- `semantic_similarity`：语义相似度
- `agreement_points`：共识点列表
- `disagreement_points`：分歧点列表
- `risks`：潜在风险

### 执行计划生成

`_build_execution_plan()` 根据辩论结果生成：
- `title`：计划标题
- `steps`：具体执行步骤
- `constraints`：约束条件
- `forbidden_commands`：禁止命令（安全约束）

---

## 安全特性

### ExecutionPlan 安全约束

```python
def is_step_safe(self, step: str) -> tuple[bool, str]:
    """检查步骤是否包含安全威胁"""
    # 检查禁止命令
    for cmd in self.forbidden_commands:
        if cmd.lower() in step.lower():
            return False, f"Step contains forbidden command: '{cmd}'"
    # 检查禁止文件
    for f in self.forbidden_files:
        if f.lower() in step.lower():
            return False, f"Step references forbidden file: '{f}'"
    return True, ""
```

### SafeExecutor

专门用于安全执行 LLM 生成的代码：

```python
from core.safe_executor import SafeExecutor

executor = SafeExecutor(
    allowed_dirs=["/project/code"],
    forbidden_patterns=["rm -rf", "format c:", "del /f /s /q"]
)

result = await executor.execute(code_block, context)
```

---

## 配置参考

### 环境变量

```bash
export AUTOSYNTH_BRIDGE_PORT=8090
export CHROME_DEBUG_PORT=9222
export CHROME_USER_DATA_DIR=./browser_data
```

### Provider 配置示例

```python
providers = {
    "gpt": {
        "type": "web",
        "website_key": "chatgpt",
        "cdp_url": "ws://localhost:9222",
        "enabled": True
    },
    "gemini": {
        "type": "web",
        "website_key": "gemini",
        "cdp_url": "ws://localhost:9222",
        "enabled": True
    },
    "claude": {
        "type": "web",
        "website_key": "claude",
        "cdp_url": "ws://localhost:9222",
        "enabled": True
    }
}
```

---

## 未来规划

- [ ] 添加更多网页 AI 支持（Perplexity、Copilot 等）
- [ ] 实现 ResearchAgent 自动化研究流程
- [ ] 优化记忆优先级排序算法
- [ ] 支持自定义辩论角色
- [ ] 添加 WebSocket 实时推送

---

## 许可证

MIT License - 自由使用、修改和分发