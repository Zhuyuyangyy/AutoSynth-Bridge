# Q2 评审: AutoSynth-Bridge

> 仅阅读 `main.py` + `README.md` · 7 维简评 · Q2 v1

## 1. 问题清晰度
项目瞄准「零 API key 跨模型协作」的真实痛点:付费/限速/区域限制下,如何让 ChatGPT/Gemini/Claude 协同解决研究/写作任务。README 用对照表把 API 模式与 Web 模式(成本、模型来源、记忆、人味化)对齐,痛点–替代方案–差异点三层信息密度高。`main.py` 暴露的端点(`/api/web/debate`,`/api/debate`,`/api/humanize`,`/api/pipeline/full`,V2 的 `/api/v1/debate2`,`/api/v1/trajectories`)清晰回应「多模型辩论 + 论文人味化 + 全流水线」三条产品线。

## 2. 解决方案合理性
`main.py` 使用 FastAPI `lifespan` 在启动时初始化 `DebateGraph`、`ClaudeExecutor`、`Bridge`、`ProviderRegistry`、`DebateEngine`、`TrajectoryStore` 六个全局单例;通过 `OPENAI_COMPATIBLE_*` 环境变量注册 gpt/gemini 兼容 provider,缺 key 时降级为 web 模式(README 主推路径)。V1/V2 双轨:V1 用 LangGraph 状态机直连 LLM,V2 用 Provider Registry + DebateEngine + TrajectoryStore 的新主链。请求侧把 debate 后的 plan 串到 `ClaudeExecutor` 形成 pipeline,逻辑闭环。设计取舍合理:把「无 key 也能跑」做成 first-class citizen 是真实差异化。

## 3. 技术深度
栈表里同时出现 Playwright + CDP + LangGraph + LangChain + sentence-transformers + PyTorch + pydantic-settings + GitPython,层次丰富但有堆栈风险:每个组件都要维护版本兼容。`main.py` 中 `web_debate` 把 `headless` 暴露成布尔参数,V2 端点用 `asyncio.gather` 隐含并发;V2 `_build_response` 用 `dataclasses.asdict` 反序列化是惯用法。`/api/v1/trajectories/{task_id}` 返回 `record.to_dict()`,需要 TrajectoryStore 实现冻结 schema,深度合理;但 `v2_debate` 失败时构造 `dummy_result` 写轨迹再 500,这种「降级+日志」对学术系统的可复现性加分。

## 4. 工程成熟度
端点覆盖完整(health、web debate、debate、execute、pipeline、runs、costs、providers stats、humanize、humanize/sections、v1 providers health、v1 debate2、v1 trajectories list/get),CORS/异常/认证分层清晰。`/api/runs` 直接用 sqlite3 风格 `db.conn.cursor()` 拼 SQL,虽然能跑但有 SQL 注入面(尽管 `?` 占位防住了,风格仍偏脚本)。`db.create_run` / `db.log_message` / `db.finalize_run` 在多个端点重复拼装,缺少 service 层抽象;若引入 ORM/Repository 会更稳。`requirements.txt` 完备,有 Dockerfile 与 1_start_chrome.bat / 2_run_bridge.bat / run.bat 三套启动脚本,Windows 友好,加分。

## 5. 创新性
「三模型辩论 + 零成本 web 抓取 + 论文人味化 + 轨迹持久化」是清晰组合创新,且公开承认「学术润色」场景,定位差异化明显。README 给出 `Architect / Critic / Executor / Researcher / Judge` 五角色定义与三轮默认,LangGraph state machine 治理轮次,可作为小型 multi-agent 论文的工程支撑。`V2Debate2Request` 显式列出 `participants` 让用户自选模型对,体现「可配置辩论」思想。Inno 维度天然高,但学术新颖性取决于是否在「多模型协商收敛判据」上提出新指标,目前 `convergence` 字段的算法在 main.py 不可见。

## 6. 可验证性
`run.bat` / `1_start_chrome.bat` / `2_run_bridge.bat` 给出 Windows 一键复现路径,`/docs` 自动 Swagger,`/api/runs` 与 `/api/costs` 暴露历史与零成本统计,适合 paper 实验台账。`/api/v1/trajectories/{task_id}` 单点回放支持断点重跑。`tests/` 目录列出 provider contract、provider health、fallback chain、safe executor、debate engine、debate2 route 等多组测试(README 提到「V0.2 P0.5」),但 main.py 没接 pytest 入口或 CI badge,Q3 应补 `pytest + GitHub Actions` 流水线。Web 模式依赖 Chrome debug port 与登录态,可复现性在共享机器上较弱。

## 7. 风险与边界
(1) ToS/合规——自动化访问 ChatGPT/Claude/Gemini 网页接口违反大多数厂商 ToS,README 完全未提示;若投递学术会议或商用,这是首要拦截点。(2) 选择器脆弱——`web_provider` 用 CSS selector(`textarea`,`button[data-testid=send-button]`)抓取 UI,产品前端任何重设计都会让脚本失效;应做选择器回退 + 视觉兜底。(3) 沙箱——`ClaudeExecutor` 暴露 `/api/execute` 接收 `task` 文本,虽然有 `ExecutionPlan.is_step_safe` + `SafeExecutor`,但 main.py 没看到任何「先解析 plan → 再走 SafeExecutor」的中介,直接喂字符串进 executor 有越权风险。(4) PII——辩论与人味化文本可能含敏感内容,主入口无脱敏/审计日志。
