# AutoSynth-Bridge 智研桥 V0.2 - CDP版

## 核心升级：CDP WebSocket 替代 Playwright

### 为什么是 CDP

| | Playwright 模式 | CDP WebSocket 模式 |
|---|---|---|
| **延迟** | Python → CDP → 浏览器，多层转发 | AI 直连浏览器内核，零中间层 |
| **稳定性** | 选择器失效即崩溃 | AI 实时理解 DOM，自己找元素 |
| **速度** | 每步都要 sleep 等待 | 全异步，CDP 事件驱动 |
| **可扩展** | 受限于 Playwright API | 完整 DevTools 协议能力 |

---

## 快速启动（Windows）

### 第一步：安装依赖（只需一次）

```cmd
pip install websockets playwright fastapi uvicorn
playwright install chromium
```

### 第二步：启动 Chrome 调试模式

双击运行 `1_start_chrome.bat`，或手动在 CMD 执行：

```cmd
chrome.exe --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome_debug_profile"
```

### 第三步：登录 ChatGPT 和 Gemini

在打开的 Chrome 窗口中正常登录 chat.openai.com 和 gemini.google.com

### 第四步：运行辩论

双击 `2_run_bridge.bat`

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `cdp_browser.py` | CDP WebSocket 核心引擎（替代 `web_debate.py`） |
| `bridge.py` | 统一桥接器（支持 api/web/cdp 三种模式） |
| `memory_palace.py` | 记忆宫殿（存储辩论历史） |
| `main.py` | FastAPI 服务入口（端口 8090） |
| `agents/gpt_agent.py` | GPT 学术裁判 |
| `agents/gemini_agent.py` | Gemini 创新发散 |
| `agents/claude_executor.py` | Claude Code 落地执行 |
| `1_start_chrome.bat` | 启动 Chrome 调试模式 |
| `2_run_bridge.bat` | 运行 CDP 辩论引擎 |

---

## API 接口

```
GET  http://127.0.0.1:8090/health          # 健康检查
POST http://127.0.0.1:8090/api/cdp/debate  # CDP模式辩论
POST http://127.0.0.1:8090/api/debate      # API模式辩论
POST http://127.0.0.1:8090/api/pipeline/full # 全流程
```

---

## CDP 模式请求示例

```json
POST /api/cdp/debate
{
  "user_requirement": "为TCM-Mind-RAG系统设计SCI论文创新方向",
  "topic": "中医RAG幻觉检测",
  "task_type": "sci_paper",
  "max_rounds": 3,
  "gpt_tab": "existing",   # 使用已登录的GPT Tab
  "gemini_tab": "new"       # 创建新的Gemini Tab
}
```

---

## 架构

```
用户需求
    ↓
GPT ⇄ Gemini  网页互搏层
    ↓
CDP WebSocket 直连浏览器（Tab操作：输入/点击/提取）
    ↓
MemoryPalace 记忆捕获（JSON结构化存储）
    ↓
Claude Code 落地执行（读取记忆 → 生成论文/专利）
    ↓
用户验收
```

---

## 常见问题

**Q: Chrome 调试端口连不上**
```cmd
# 检查端口是否在监听
netstat -ano | findstr 9222

# 确认 Chrome 进程
tasklist | findstr chrome
```

**Q: 显示"Cannot connect to Chrome"**
确保用 `--remote-debugging-port=9222` 启动 Chrome，且不要加 `--headless`

**Q: pip install websockets 失败**
```cmd
pip install websockets --user
```
