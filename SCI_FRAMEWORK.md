# AutoSynth-Bridge 学术研究三模型协同框架

## SCI_FRAMEWORK.md - 技术框架文档

---

## 1. 项目概述

### 1.1 项目背景

AutoSynth-Bridge（智研桥）是一个基于三模型协同工作流的AI学术研究辅助系统，系统代号 V0.2 P0.5。该系统通过整合GPT裁判的学术逻辑审查、Gemini模型的跨界创新发散、以及Claude Code的工程落地执行能力，实现从研究想法到学术成果的全链路自动化生产。

### 1.2 核心目标

- **学术质量保障**：通过GPT裁判的审稿式审查，确保研究方案符合SCI二区及以上期刊标准
- **创新性增强**：通过Gemini的发散思维，突破常规研究思路，提出跨界创新方案
- **工程可行性验证**：通过Claude Executor将学术方案转化为可执行的代码和实验
- **零成本网页模拟**：通过CDP (Chrome DevTools Protocol) 直接控制浏览器，实现零API消耗的网页自动化

### 1.3 技术栈

| 组件 | 技术选型 | 版本 |
|------|----------|------|
| Web框架 | FastAPI | 0.1+ |
| 状态机 | LangGraph | - |
| 数据库 | SQLite | - |
| 浏览器控制 | CDP (Chrome/Edge) | - |
| 语义嵌入 | SentenceTransformers | - |
| LLM提供者 | OpenAI Compatible API | - |

---

## 2. 三模型协同机制

### 2.1 模型角色定义

#### 2.1.1 GPT Agent (学术裁判)

**角色定位**：扮演SCI期刊审稿专家（IF>5），负责学术逻辑把关。

**核心职责**：
- 审查逻辑漏洞
- 指出学术不合规之处
- 反驳创新点可行性
- 要求证据支撑
- 输出学术合规方案

**Prompt特征**：
```
你是一位资深的SCI期刊审稿专家（IF>5），负责学术逻辑把关。
核心职责：审查逻辑漏洞、指出学术不合规、反驳创新点可行性、要求证据支撑、输出学术合规方案。
用【学术审查】开头回复。
```

**API调用参数**：
```python
temperature = 0.3  # 低温度保证审查严谨性
model = settings.gpt_model
```

#### 2.1.2 Gemini Agent (创新发散者)

**角色定位**：跨界创新专家，负责打破常规、提出新颖科研思路。

**核心职责**：
- 跨学科创新思维
- 拆解技术细节
- 坚持有价值的创新点
- 补充证据
- 输出创新性版本

**Prompt特征**：
```
你是一位跨界创新专家，负责打破常规、提出新颖科研思路。
核心职责：跨学科创新、拆解技术细节、坚持有价值的创新点、补充证据、输出创新性版本。
用【创新发散】开头回复。
```

**API调用参数**：
```python
temperature = 0.9  # 高温度保证创意发散
model = settings.gemini_model
```

#### 2.1.3 Claude Executor (工程落地者)

**角色定位**：带安全壳的代码执行器，负责将学术方案转化为可执行代码。

**核心职责**：
- 任务分解与步骤执行
- 难度评估
- 安全约束执行
- 结果验证与重试

**安全壳设计**：
```python
ALLOWED_EXTENSIONS = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".ipynb", ".sh", ".bat"}
FORBIDDEN_PATTERNS = ["..", "/etc/", "/root/", "/home/", ".env", ".ssh/", "/usr/bin/"]
```

### 2.2 辩论状态机 (DebateGraph)

基于LangGraph实现的三模型辩论状态机，采用以下流程：

```
init → gemini_node (Round 0: 发散)
           ↓
      gpt_review (Round 1: 裁判)
           ↓
      [收敛检查] ─→ 一致性分数 ≥ 阈值 → converge_node → END
           ↓
      gemini_node (Round 2: 回应)
           ↓
      gpt_review (Round 3: 裁判)
           ↓
      [收敛检查] ...
```

**关键决策函数** (`_should_continue`):
```python
def _should_continue(self, state: DebateState) -> Literal["gemini_node", "gpt_review", "converge_node", END]:
    if state["round"] >= settings.debate_rounds:
        return "converge_node"
    
    score = state.get("consistency_score", 0.0)
    if score >= settings.consistency_threshold:
        return "converge_node"
    
    if state["round"] == 0:
        return "gemini_node"
    elif state["round"] % 2 == 1:
        return "gpt_review"
    else:
        return "gemini_node"
```

### 2.3 轮次交互模式

| 轮次 | 角色 | 操作 | 输入 | 输出 |
|------|------|------|------|------|
| Round 0 | Gemini | brainstorm | query | 初始创新方案 |
| Round 1 | GPT | debate | Gemini的方案 | 学术审查/质疑 |
| Round 2 | Gemini | respond | GPT的质疑 | 创新性回应 |
| Round 3 | GPT | debate | Gemini的回应 | 第二轮审查 |
| ... | ... | ... | ... | ... |
| N | converge | 收敛 | 所有轮次内容 | 最终方案 |

### 2.4 并发与串行策略

系统支持两种辩论模式：
- **并发模式** (`enable_concurrent=True`)：同一轮次内所有参与者并行生成观点
- **串行模式** (`enable_concurrent=False`)：严格按照顺序执行每个参与者的生成

```python
async def _run_debate_rounds(self, request: DebateRequest, result: DebateResult, enable_concurrent: bool):
    if enable_concurrent and len(available_participants) > 1:
        round_responses = await self._concurrent_round(round_num, available_participants, request.query, rounds)
        rounds.extend(round_responses)
    else:
        for name, role, provider in available_participants:
            round_resp = await self._single_round(round_num, name, request.query, rounds)
            rounds.append(round_resp)
```

---

## 3. 三段式一致性评分 (Three-Stage Convergence Scoring)

### 3.1 评分体系架构

系统采用三段式评分体系，综合评估辩论参与者的共识程度：

```
最终一致性分数 = 0.4 × 语义相似度 + 0.4 × 结构化合意分数 + 0.2 × 风险消解分数
```

### 3.2 第一段：语义相似度 (Semantic Similarity)

使用SentenceTransformer模型计算两个文本的余弦相似度：

```python
def calculate_similarity(self, text1: str, text2: str) -> float:
    if not self.embedding_model or not (text1 and text2):
        return 0.5  # 默认中间值
    emb1 = self.embedding_model.encode(text1, convert_to_tensor=True)
    emb2 = self.embedding_model.encode(text2, convert_to_tensor=True)
    return float(util.cos_sim(emb1, emb2).item())
```

### 3.3 第二段：结构化合意分数 (Structured Agreement Score)

从四个维度检查双方观点的一致性：

| 维度 | 检查关键词 | 一致性判定 |
|------|------------|------------|
| 创新点对齐 (innovation_aligned) | 创新、novel、创新点、突破、首次、新方法 | 双方提及数量差异≤2 |
| 证据对齐 (evidence_aligned) | 实验、数据、验证、证明、实验设计、ablation | 双方均有/无实验证据 |
| 专利保护范围对齐 (patent_scope_aligned) | 专利、保护、权利要求、实施例 | 双方提及数量差异≤2 |
| 实现路径对齐 (implementation_aligned) | 代码、实现、算法、架构、模块、接口 | 双方提及数量差异≤2 |

```python
def _compute_structured_agreement(self, gpt_text: str, gemini_text: str) -> StructuredAgreementScore:
    score = StructuredAgreementScore(
        innovation_aligned=self._keyword_overlap(gpt_text, gemini_text, "innovation"),
        evidence_aligned=self._keyword_overlap(gpt_text, gemini_text, "evidence"),
        patent_scope_aligned=self._keyword_overlap(gpt_text, gemini_text, "patent_scope"),
        implementation_aligned=self._keyword_overlap(gpt_text, gemini_text, "implementation"),
    )
    score.compute()
    return score
```

### 3.4 第三段：风险消解分数 (Risk Resolution Score)

评估方案的实际可行性风险：

| 风险指标 | 判定条件 |
|----------|----------|
| SCI可行性 (sci_feasibility) | 文本中包含SCI、二区、论文、期刊等关键词 |
| 夸大风险 (exaggeration_risk) | 文本中不包含"声称"、"宣称"等夸大表述 |
| 实现完整性 (missing_implementation) | 文本中包含代码、实现、算法等实现相关关键词 |
| 专利保护 (patent_scope_risk) | 文本中包含专利相关关键词（风险指标为False表示有保护） |

```python
def _compute_risk_resolution(self, gpt_text: str, gemini_text: str) -> RiskResolutionScore:
    combined = gpt_text + " " + gemini_text
    return RiskResolutionScore(
        sci_feasibility=any(kw in combined for kw in self.KEYWORDS["sci_level"]),
        exaggeration_risk="声称" not in combined and "宣称" not in combined,
        missing_implementation=any(kw in combined for kw in self.KEYWORDS["implementation"]),
        patent_scope_risk=not any(kw in combined for kw in self.KEYWORDS["patent_scope"]),
    )
```

### 3.5 分歧点追踪 (Dispute Tracking)

系统自动检测并追踪关键分歧点：

```python
def _extract_disputes(self, gpt_text: str, gemini_text: str) -> list[DisputePoint]:
    disputes = []
    
    # 检测创新点数量差异
    gpt_innov = sum(1 for kw in self.KEYWORDS["innovation"] if kw in gpt_text)
    gemini_innov = sum(1 for kw in self.KEYWORDS["innovation"] if kw in gemini_text)
    if abs(gpt_innov - gemini_innov) >= 2:
        disputes.append(DisputePoint(
            topic="创新点数量差异",
            gpt_position=f"GPT提出 {gpt_innov} 个创新点",
            gemini_position=f"Gemini提出 {gemini_innov} 个创新点",
            severity="high"
        ))
    
    # 检测实验证据缺失
    has_evidence = lambda t: any(kw in t for kw in self.KEYWORDS["evidence"])
    if has_evidence(gpt_text) != has_evidence(gemini_text):
        disputes.append(DisputePoint(
            topic="实验证据缺失",
            severity="critical"
        ))
    
    return disputes
```

### 3.6 收敛判定

```python
@property
def converged(self) -> bool:
    return (self.consistency_score >= settings.consistency_threshold
            and len(self.critical_unresolved) == 0)

# 人工审核触发条件
need_human = len(critical) > 0 or final_score < 0.7
```

---

## 4. Provider注册与Fallback机制

### 4.1 ProviderRegistry

统一的Provider注册与管理中心：

```python
class ProviderRegistry:
    def register(self, name: str, provider: BaseProvider, overwrite: bool = False)
    def get(self, name: str) -> BaseProvider
    def has(self, name: str) -> bool
    async def health_check_all(self) -> dict[str, ProviderHealth]
    def get_available_providers(self) -> dict[str, BaseProvider]
```

### 4.2 FallbackChain

多Provider级联故障转移：

```python
class FallbackChain(BaseProvider):
    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        for provider in self._chain:
            if not provider.enabled:
                continue
            try:
                result = await provider.generate(messages, **kwargs)
                if result.ok:
                    result.metadata["fallback_used"] = provider.name
                    return result
            except Exception as e:
                continue
        
        return ModelResponse(error=f"[FallbackChain] All providers failed")
```

### 4.3 多API支持

系统支持多种API提供者配置：

| 优先级 | 提供者 | 配置项 |
|--------|--------|--------|
| 主路径 | 4SAPI | API_4S_KEY, API_4S_BASE |
| 备用1 | Poe | POE_API_KEY, POE_BASE |
| 备用2 | OpenAI官方 | OPENAI_API_KEY, OPENAI_BASE |

---

## 5. 记忆与轨迹系统

### 5.1 TrajectoryStore

完整的辩论轨迹持久化系统：

```python
class TrajectoryStore:
    def save(self, result: DebateResult) -> TrajectoryRecord:
        # 保存到 JSON 文件
        json_path = self.storage_dir / f"{record.task_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)
        
        # 更新SQLite索引
        self._upsert_index(record)
```

**存储结构**：
- JSON文件：保存完整轨迹数据（轮次内容、共识结果、执行计划）
- SQLite索引：快速检索任务摘要和状态

### 5.2 MemoryPalace

上下文记忆构建，为后续Claude Code执行提供历史上下文：

```python
def build_context_for_claude(self, task_id: str) -> str:
    # 构建包含历史辩论信息的上下文字符串
```

---

## 6. 安全执行框架

### 6.1 ClaudeExecutor安全壳

```python
class ClaudeExecutor:
    def _validate_path(self, path: str) -> bool:
        """验证路径安全"""
        resolved = Path(path).resolve()
        try:
            resolved.resolve().relative_to(self.workspace_dir)
        except ValueError:
            return False  # 路径在workspace之外
        
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in str(resolved):
                return False
        return True
```

### 6.2 执行计划安全约束

```python
class ExecutionPlan:
    allowed_files: List[str] = ["providers/", "core/", "memory/", "tests/"]
    forbidden_files: List[str] = [".env", "data/", "browser_profiles/"]
    allowed_commands: List[str] = ["pytest"]
    forbidden_commands: List[str] = ["rm -rf", "git push --force"]
```

### 6.3 幂等性与重试策略

```python
# 指数退避重试
if "resource" in stderr_text.lower() or "rate_limit" in stderr_text.lower():
    await asyncio.sleep(2 ** retry_count)  # 指数退避
    return await self.execute_task(task, task_id, timeout, retry_count + 1)
```

---

## 7. CDP浏览器自动化

### 7.1 Chrome DevTools Protocol集成

直接通过WebSocket控制Chrome/Edge浏览器，无需Playwright：

```python
class CDPClient:
    async def send(self, method: str, params: dict = None) -> dict:
        """发送CDP命令并等待响应"""
        self._msg_id += 1
        msg_id = self._msg_id
        future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        payload = {"id": msg_id, "method": method}
        if params:
            payload["params"] = params
        await self._ws.send(json.dumps(payload))
        return await future
```

### 7.2 网站自动识别

```python
WEBSITE_SELECTORS = {
    "chat.openai.com": {
        "input": "textarea",
        "response": '[data-testid="turn"] .markdown',
        "send_btn": '[data-testid="send-button"]',
        "model": "GPT-4",
    },
    "gemini.google.com": {
        "input": "div[contenteditable='true']",
        "response": ".message-content",
        "send_btn": '[aria-label="Send"]',
        "model": "Gemini",
    },
}
```

---

## 8. 人味化降重系统

### 8.1 改写策略

| 策略 | 描述 | 典型应用场景 |
|------|------|-------------|
| SENTENCE_RESTRUCTURE | 句式重组（主动↔被动，长句拆短） | 所有章节基础改写 |
| LOGIC_REORDER | 逻辑重排（因果↔果因，总分↔分总） | 引言、讨论部分 |
| STYLE_INJECTION | 风格注入（人类学者写作习惯） | 所有章节 |
| ACADEMIC_POLISH | 学术润色（hedging表达） | 结果、讨论部分 |
| DEEP_REWRITE | 深度改写（综合策略） | 最终降重 |

### 8.2 分章节改写策略

```python
section_strategies = {
    "abstract": [SENTENCE_RESTRUCTURE, STYLE_INJECTION],
    "introduction": [LOGIC_REORDER, STYLE_INJECTION],
    "method": [SENTENCE_RESTRUCTURE],
    "results": [SENTENCE_RESTRUCTURE, ACADEMIC_POLISH],
    "discussion": [DEEP_REWRITE],
    "conclusion": [SENTENCE_RESTRUCTURE, STYLE_INJECTION],
}
```

---

## 9. 核心创新点总结

### 9.1 三模型角色协同机制

| 创新点 | 描述 | 技术实现 |
|--------|------|----------|
| 角色驱动的模型调度 | 不同模型承担不同认知角色，GPT=裁判，Gemini=创新者 | `DebateRole`枚举 + `get_default_role_map()` |
| 轮次交替的辩论 | 发散→裁判→回应→裁判...循环直到收敛 | `DebateGraph._should_continue()` |
| 温度差异化的模型调用 | GPT低温(0.3)严谨，Gemini高温(0.9)发散 | `GPTAgent.generate()` vs `GeminiAgent.generate()` |

### 9.2 三段式收敛评分

| 创新点 | 描述 | 技术实现 |
|--------|------|----------|
| 多维度一致性评估 | 语义相似度 + 结构化合意 + 风险消解 | `ConvergenceChecker.check_convergence()` |
| 分歧点追踪 | 自动识别critical级别的未解决分歧 | `DisputePoint`数据结构 |
| 动态收敛阈值 | 一致性分数+关键分歧双重判定 | `converged`属性 |

### 9.3 安全执行框架

| 创新点 | 描述 | 技术实现 |
|--------|------|----------|
| 沙箱化工作空间 | 限制在指定workspace目录内执行 | `ClaudeExecutor._validate_path()` |
| 结构化执行计划 | 明确allowed/forbidden文件与命令 | `ExecutionPlan`数据类 |
| Git变更追踪 | 执行前后git diff记录变更 | `_git_diff()`函数 |

### 9.4 零成本网页模拟

| 创新点 | 描述 | 技术实现 |
|--------|------|----------|
| CDP直连浏览器 | 绕过Playwright直接使用CDP协议 | `CDPClient` + `Tab`类 |
| 网站自动适配 | 根据URL自动选择正确的选择器 | `WEBSITE_SELECTORS`字典 |

---

## 10. 应用场景

### 10.1 SCI论文辅助写作

```
用户输入研究主题 → 三模型辩论 → 收敛方案 → Claude执行实验 → 人味化降重 → 最终论文
```

### 10.2 专利技术方案生成

```
技术问题描述 → 三模型辩论（专利保护范围检查）→ 收敛方案 → 执行计划 → 专利文档
```

### 10.3 研究可行性评估

```
研究想法 → 三模型辩论（包含风险消解评分）→ 可行性报告 → 人工审核触发点
```

---

## 11. 文件结构

```
AutoSynth-Bridge/
├── agents/                    # Agent实现
│   ├── gpt_agent.py          # GPT学术裁判
│   ├── gemini_agent.py        # Gemini创新发散
│   └── claude_executor.py    # Claude安全执行器
├── api/                       # API路由
│   └── provider_routes.py
├── core/                      # 核心逻辑
│   ├── debate_engine.py       # 辩论引擎
│   ├── debate_roles.py        # 角色定义
│   ├── debate_prompts.py      # 提示词模板
│   ├── schemas.py             # 数据结构
│   └── convergence.py         # 收敛检查器
├── graph/                     # 状态机
│   ├── debate_graph.py        # LangGraph状态机
│   └── convergence.py        # 收敛规则
├── memory/                    # 记忆系统
│   └── trajectory_store.py    # 轨迹存储
├── providers/                  # LLM提供者
│   ├── base.py               # BaseProvider抽象
│   ├── registry.py           # Provider注册表
│   ├── fallback_chain.py     # Fallback链
│   └── openai_compatible.py  # OpenAI兼容接口
├── cdp_browser.py            # CDP浏览器控制
├── bridge.py                 # 统一调度器
├── humanize.py               # 人味化降重
└── main.py                  # FastAPI入口
```

---

*文档版本：V0.2 P0.5*
*生成时间：基于代码审计自动生成*