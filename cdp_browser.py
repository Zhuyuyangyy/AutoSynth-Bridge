
"""
CDP Browser Agent - 直连 Chrome/Edge DevTools Protocol，通过 WebSocket 控制浏览器
替代 Playwright 笨重的 Python API，直接与浏览器内核对话

启动浏览器时带上调试端口：
    Chrome:  chrome.exe --remote-debugging-port=9222 --user-data-dir="./profile"
    Edge:    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
             --remote-debugging-port=9222 --user-data-dir="./edge_profile"

CDP 文档：https://chromedevtools.github.io/devtools-protocol/
"""
import asyncio
import json
import time
import base64
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class CDPBrowserConfig:
    ws_url: str = "ws://127.0.0.1:9222/devtools/browser"
    viewport_width: int = 1280
    viewport_height: int = 800
    browser: str = "auto"  # "chrome", "edge", "auto"


class CDPClient:
    """Chrome DevTools Protocol WebSocket 客户端"""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._ws = None
        self._msg_id = 0
        self._pending: dict = {}
        self._listeners: list = []
        self._connected = False

    async def connect(self) -> bool:
        """连接到浏览器 CDP WebSocket"""
        try:
            import websockets
            self._ws = await websockets.connect(self.ws_url, open_timeout=10)
            self._connected = True
            asyncio.create_task(self._read_loop())
            return True
        except ImportError:
            print("[CDP] websockets not installed: pip install websockets")
            return False
        except Exception as e:
            print(f"[CDP] Connect failed: {e}")
            return False

    async def _read_loop(self):
        """持续读取 CDP 消息，分发到响应 Future 或事件监听器"""
        while self._connected:
            try:
                msg = await asyncio.wait_for(self._ws.recv(), timeout=30)
                data = json.loads(msg)
                msg_id = data.get("id")
                if msg_id is not None and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if "error" in data:
                        fut.set_exception(Exception(data["error"].get("message", "CDP Error")))
                    else:
                        fut.set_result(data.get("result", {}))
                else:
                    for listener in self._listeners:
                        try:
                            listener(data.get("method", ""), data.get("params", {}))
                        except Exception:
                            pass
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self._connected:
                    print(f"[CDP] Read error: {e}")
                break

    async def send(self, method: str, params: dict = None) -> dict:
        """发送 CDP 命令并等待响应"""
        if not self._connected or self._ws is None:
            raise RuntimeError("Not connected")
        self._msg_id += 1
        msg_id = self._msg_id
        future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        payload = {"id": msg_id, "method": method}
        if params:
            payload["params"] = params
        await self._ws.send(json.dumps(payload))
        return await future

    def add_listener(self, listener: Callable):
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable):
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def close(self):
        self._connected = False
        if self._ws:
            await self._ws.close()


class Tab:
    """单个浏览器 Tab"""

    def __init__(self, tab_id: str, cdp: "CDPClient", url: str = ""):
        self.tab_id = tab_id
        self.cdp = cdp
        self.url = url

    async def activate(self):
        await self.cdp.send("Target.activateTarget", {"targetId": self.tab_id})

    async def navigate(self, url: str) -> dict:
        result = await self.cdp.send("Page.navigate", {"url": url})
        self.url = url
        await self._wait_for_load()
        return result

    async def _wait_for_load(self, timeout: int = 30):
        event = asyncio.Event()

        def handler(method: str, params: dict):
            if method == "Page.loadEventFired":
                event.set()

        self.cdp.add_listener(handler)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            self.cdp.remove_listener(handler)

    async def reload(self):
        await self.cdp.send("Page.reload")

    async def evaluate(self, expression: str, return_by_value: bool = True) -> dict:
        result = await self.cdp.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": return_by_value}
        )
        return result.get("result", {})

    async def query_selector(self, selector: str) -> Optional[dict]:
        try:
            result = await self.cdp.send(
                "Runtime.evaluate",
                {
                    "expression": f"(function(){{ const e=document.querySelector('{selector}'); "
                    f"if(!e)return null; "
                    f"return {{tag:e.tagName,text:e.innerText.slice(0,200),"
                    f"rect:e.getBoundingClientRect().toJSON()}}; }})()",
                    "returnByValue": True
                }
            )
            val = result.get("value")
            return val if val else None
        except Exception:
            return None

    async def get_element_text(self, selector: str) -> str:
        result = await self.evaluate(
            f"document.querySelector('{selector}')?.innerText || ''"
        )
        return result.get("value", "") or ""

    async def click(self, selector: str):
        await self.evaluate(
            f"document.querySelector('{selector}')?.click()"
        )

    async def type_text(self, selector: str, text: str, delay_ms: int = 50):
        # 先清空
        await self.evaluate(
            f"(function(){{ const e=document.querySelector('{selector}'); "
            f"if(e){{ e.value=''; e.dispatchEvent(new Event('input',{{bubbles:true}})); }} }})()"
        )
        await asyncio.sleep(0.1)
        # 模拟逐字输入
        for char in text:
            await self.cdp.send("Input.insertText", {"text": char})
            await asyncio.sleep(delay_ms / 1000)

    async def press_enter(self):
        await self.cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter"})
        await asyncio.sleep(0.05)
        await self.cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter"})

    async def wait_for_selector(self, selector: str, timeout: int = 15) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            node = await self.query_selector(selector)
            if node:
                return True
            await asyncio.sleep(0.5)
        return False

    async def get_all_text(self, selector: str) -> list:
        result = await self.evaluate(
            f"Array.from(document.querySelectorAll('{selector}')).map(e=>e.innerText)"
        )
        return result.get("value", []) or []

    async def take_screenshot(self, path: str = None) -> bytes:
        await self.cdp.send("Page.enable")
        result = await self.cdp.send("Page.captureScreenshot", {"format": "png"})
        img_data = base64.b64decode(result.get("data", ""))
        if path:
            with open(path, "wb") as f:
                f.write(img_data)
        return img_data

    async def scroll_to_bottom(self):
        await self.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.3)


# ────────────────────────────────────────────────────────────
# 网站自动识别 + 对应选择器
# ────────────────────────────────────────────────────────────
WEBSITE_SELECTORS = {
    "chat.openai.com": {
        "input": "textarea",  # GPT-4 输入框
        "response": '[data-testid="turn"] .markdown',
        "send_btn": '[data-testid="send-button"]',
        "model": "GPT-4",
    },
    "chatgpt.com": {
        "input": "textarea",
        "response": '[data-testid="turn"] .markdown',
        "send_btn": '[data-testid="send-button"]',
        "model": "GPT-4o",
    },
    "gemini.google.com": {
        "input": "div[contenteditable='true']",
        "response": ".message-content",
        "send_btn": '[aria-label="Send"]',
        "model": "Gemini",
    },
    "claude.ai": {
        "input": '[data-testid="composer-input"]',
        "response": ".claude-message",
        "send_btn": '[data-testid="send-button"]',
        "model": "Claude",
    },
}


def detect_website(url: str) -> Optional[dict]:
    """根据 URL 返回对应选择器配置"""
    url_lower = url.lower()
    for host, selectors in WEBSITE_SELECTORS.items():
        if host in url_lower:
            return selectors
    return None


def extract_messages_from_page(tab: "Tab", website_cfg: dict) -> list[str]:
    """从页面提取所有 AI 回复（同步，需在 asyncio.run 里用）"""
    # 这个是简化版，实际在 bridge 里用 await 版
    return []


# ────────────────────────────────────────────────────────────
# CDPBrowser 主类
# ────────────────────────────────────────────────────────────
class CDPBrowser:
    """
    CDP 浏览器管理器，同时支持 Chrome 和 Edge（Chromium 内核，CDP 协议完全兼容）

    用法：
        browser = CDPBrowser()
        await browser.start()  # 连接到已运行的浏览器

        tab = await browser.new_tab("https://chat.openai.com")
        await tab.type_text("textarea", "Hello!")
        await tab.press_enter()

        await asyncio.sleep(5)
        texts = await tab.get_all_text(".markdown")

        await browser.close()
    """

    def __init__(self, config: CDPBrowserConfig = None):
        self.config = config or CDPBrowserConfig()
        self.cdp = CDPClient(self.config.ws_url)
        self._tabs: list = []

    async def start(self) -> bool:
        """连接到运行中的浏览器（Chrome 或 Edge）"""
        if not await self.cdp.connect():
            return False
        await asyncio.sleep(0.5)
        try:
            tabs = await self.cdp.send("Target.getTargets", {})
            for t in tabs.get("targetInfos", []):
                if t.get("type") == "page":
                    tab = Tab(t["targetId"], self.cdp, t.get("url", ""))
                    self._tabs.append(tab)
            return True
        except Exception as e:
            print(f"[CDP] Failed to get tabs: {e}")
            return False

    async def new_tab(self, url: str = "about:blank") -> Optional["Tab"]:
        try:
            result = await self.cdp.send("Target.createTarget", {"url": url})
            tab_id = result.get("targetId")
            if tab_id:
                tab = Tab(tab_id, self.cdp, url)
                self._tabs.append(tab)
                return tab
        except Exception as e:
            print(f"[CDP] Create tab failed: {e}")
        return None

    async def close_tab(self, tab: "Tab"):
        try:
            await self.cdp.send("Target.closeTarget", {"targetId": tab.tab_id})
            if tab in self._tabs:
                self._tabs.remove(tab)
        except Exception:
            pass

    async def close(self):
        for tab in list(self._tabs):
            await self.close_tab(tab)
        await self.cdp.close()


# ────────────────────────────────────────────────────────────
# 启动脚本用：自动查找浏览器路径（Chrome 或 Edge）
# ────────────────────────────────────────────────────────────
import shutil as _shutil
import subprocess as _subprocess
import os as _os

# 浏览器候选路径（Windows）
_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    _shutil.which("chrome"),
    _shutil.which("google-chrome"),
]

_EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    _shutil.which("msedge"),
]


def find_browser(browsers: list[str] = None) -> Optional[tuple[str, str]]:
    """
    自动查找可用的浏览器路径。
    返回 (name, path)，name 为 "chrome" 或 "edge"
    """
    targets = {
        "chrome": _CHROME_PATHS,
        "edge": _EDGE_PATHS,
    }
    if browsers:
        targets = {k: v for k, v in targets.items() if k in browsers}

    for name, paths in targets.items():
        for p in paths:
            if p and _os.path.exists(p):
                return name, p
    return None


def build_launch_command(browser_name: str, profile_dir: str = None,
                          port: int = 9222, urls: list = None) -> list:
    """
    构建浏览器启动命令。
    示例: build_launch_command("chrome") -> [...]
    """
    _, exe_path = find_browser([browser_name]) or (None, None)
    if not exe_path:
        return []

    profile_dir = profile_dir or f"./{browser_name}_debug_profile"
    cmd = [
        exe_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--new-window",
    ]
    if urls:
        cmd.extend(urls)
    return cmd


# ────────────────────────────────────────────────────────────
# Demo
# ────────────────────────────────────────────────────────────
async def cdp_demo():
    """最小 Demo"""
    browser_info = find_browser()
    if not browser_info:
        print("[ERROR] No browser found (Chrome or Edge required)")
        return

    browser_name, browser_path = browser_info
    print(f"[CDP] Found: {browser_name} at {browser_path}")
    print("[CDP] Connecting to CDP port 9222...")

    config = CDPBrowserConfig()
    browser = CDPBrowser(config)
    if not await browser.start():
        print("[ERROR] Cannot connect to browser.")
        print(f"Run: {browser_path} --remote-debugging-port=9222 --user-data-dir=./{browser_name}_profile")
        return

    print(f"[CDP] Found {len(browser._tabs)} existing tabs")
    print("[CDP] Opening GPT tab...")

    tab = await browser.new_tab("https://chat.openai.com")
    if not tab:
        print("[ERROR] Failed to open GPT tab")
        return

    await asyncio.sleep(3)
    print("[CDP] Sending message...")
    await tab.type_text("textarea", "Say hello in one sentence.", delay_ms=80)
    await tab.press_enter()
    await asyncio.sleep(5)

    print("[CDP] Reading response...")
    texts = await tab.get_all_text('[data-testid="turn"] .markdown')
    for t in texts[-3:]:
        print(f"  >> {t[:200]}")

    await tab.take_screenshot("./cdp_demo.png")
    print("[CDP] Screenshot saved to ./cdp_demo.png")
    await browser.close()


if __name__ == "__main__":
    print("CDP Browser Agent - AutoSynth-Bridge V0.2")
    print("Supports: Chrome and Edge (both use Chromium + CDP protocol)")
    print("Prerequisites:")
    print("  chrome.exe --remote-debugging-port=9222 --user-data-dir=./chrome_profile")
    print("  (or msedge.exe for Edge)")
    print("  pip install websockets")
    asyncio.run(cdp_demo())
