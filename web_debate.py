"""Playwright辩论执行器 - 模拟人工网页复制粘贴"""
import asyncio
import random
import time
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

try:
    from playwright.async_api import async_playwright, Playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from memory_palace import MemoryPalace, palace


@dataclass
class DebateConfig:
    max_rounds: int = 3
    gpt_url: str = "https://chat.openai.com/"
    gemini_url: str = "https://gemini.google.com/"
    headless: bool = True
    user_data_dir: str = "./browser_data"
    response_timeout: int = 60
    think_delay_min: float = 3.0
    think_delay_max: float = 7.0


class WebDebateExecutor:
    """Playwright网页辩论执行器"""

    GPT_SELECTORS = [
        "textarea[data-id='root']",
        "textarea[placeholder*='Message']",
        "textarea[placeholder*='message']",
        "div[contenteditable='true']",
        "#prompt-textarea",
        "textarea",
    ]

    GEMINI_SELECTORS = [
        "textarea[data-id='queryInput']",
        "textarea[aria-label*='Enter']",
        "textarea[placeholder*='Enter']",
        "div[contenteditable='true']",
        "rich-textarea textarea",
        "textarea",
    ]

    # 响应内容提取选择器（按优先级）
    GPT_RESPONSE_SELECTORS = [
        ".markdown",
        "[data-message-author-role='assistant']",
        ".agent-turn .markdown",
        ".message-content",
    ]

    GEMINI_RESPONSE_SELECTORS = [
        ".message-content",
        ".response-content",
        "[data-message-author-role='assistant']",
        ".model-response-text",
    ]

    # 停止/生成中指示器
    GPT_LOADING_INDICATORS = [
        "[aria-label='停止']",
        "[aria-label='Stop']",
        "button[aria-label*='stop']",
        "button[aria-label*='Stop']",
    ]

    GEMINI_LOADING_INDICATORS = [
        "[aria-label='停止']",
        "[aria-label='Stop']",
        ".loading-indicator",
        ".generating",
    ]

    def __init__(self, config: DebateConfig = None):
        self.config = config or DebateConfig()
        self.palace: MemoryPalace = palace
        self._rate_limit_delay = 10
        self._last_call_time = 0

    async def _random_delay(self):
        lo, hi = self.config.think_delay_min, self.config.think_delay_max
        await asyncio.sleep(random.uniform(lo, hi))

    async def _find_input_selector(self, page, selectors: list[str], retries: int = 3) -> str:
        """带重试的输入框选择器查找"""
        for attempt in range(retries):
            for sel in selectors:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        return sel
                except Exception:
                    continue
            if attempt < retries - 1:
                print(f"[WebDebate] Input selector not found, retry {attempt + 1}/{retries}")
                await asyncio.sleep(3)
        # 最终fallback
        return selectors[-1]

    async def _wait_for_response(self, page, timeout: int = None, platform: str = "gpt") -> bool:
        """等待AI响应完成，支持多种loading指示器"""
        timeout = timeout or self.config.response_timeout
        indicators = self.GPT_LOADING_INDICATORS if platform == "gpt" else self.GEMINI_LOADING_INDICATORS

        # 先等一下让loading指示器出现
        await asyncio.sleep(1)

        # 尝试等待任意一个loading指示器消失
        for indicator in indicators:
            try:
                el = await page.query_selector(indicator)
                if el:
                    await page.wait_for_selector(indicator, state="hidden", timeout=timeout * 1000)
                    await asyncio.sleep(2)
                    return True
            except Exception:
                continue

        # fallback: 等待固定时间
        await asyncio.sleep(min(timeout, 15))
        return True

    async def _extract_response(self, page, selectors: list[str], min_length: int = 50) -> str:
        """通用响应提取，带多选择器fallback"""
        for sel in selectors:
            try:
                els = await page.query_selector_all(sel)
                if els:
                    text = await els[-1].inner_text()
                    if len(text) >= min_length:
                        return text
            except Exception:
                continue

        # JS fallback
        for sel in selectors:
            try:
                text = await page.evaluate(
                    f"() => {{ const els = document.querySelectorAll('{sel}'); "
                    f"return els.length ? els[els.length - 1].innerText : ''; }}"
                )
                if text and len(text) >= min_length:
                    return text
            except Exception:
                continue

        return "[内容提取失败]"

    async def _extract_gpt_response(self, page) -> str:
        return await self._extract_response(page, self.GPT_RESPONSE_SELECTORS)

    async def _extract_gemini_response(self, page) -> str:
        return await self._extract_response(page, self.GEMINI_RESPONSE_SELECTORS)

    def _build_gemini_prompt(self, round_num: int, gpt_content: str) -> str:
        return (
            "以下是第" + str(round_num + 1) + "轮辩论任务。"
            "请对以下内容进行创新性扩展和跨界思考：\n\n"
            + gpt_content + "\n\n"
            + "【要求】提出创新点时，兼顾：1)创新性 2)可实现性 3)专利保护潜力"
        )

    def _build_gpt_prompt(self, round_num: int, gemini_content: str) -> str:
        return (
            "第" + str(round_num + 1) + "轮。Gemini提出了以下观点，请从学术审稿角度进行评判：\n\n"
            + gemini_content + "\n\n"
            + "【要求】1)指出逻辑漏洞 2)验证实验可行性 3)给出学术合规建议"
        )

    async def run_debate(self, task_id: str, initial_task: str) -> dict:
        """运行完整的GPT-Gemini网页辩论流程"""
        if not HAS_PLAYWRIGHT:
            return {"error": "Playwright not installed. Run: pip install playwright && playwright install chrome"}

        now = time.time()
        if now - self._last_call_time < self._rate_limit_delay:
            await asyncio.sleep(self._rate_limit_delay - (now - self._last_call_time))
        self._last_call_time = time.time()

        results = {
            "task_id": task_id,
            "rounds": [],
            "status": "running",
            "started_at": datetime.now().isoformat()
        }

        try:
            async with async_playwright() as p:
                browser_args = ["--no-sandbox"]
                if self.config.headless:
                    browser_args.append("--headless=new")

                context = await p.chromium.launch_persistent_context(
                    user_data_dir=self.config.user_data_dir,
                    headless=self.config.headless,
                    args=browser_args,
                    viewport={"width": 1280, "height": 800}
                )

                # Open GPT
                if not context.pages:
                    await context.new_page()
                page_gpt = context.pages[0]
                await page_gpt.goto(self.config.gpt_url, wait_until="networkidle", timeout=30000)
                await self._random_delay()

                # Find input box with retry
                gpt_sel = await self._find_input_selector(page_gpt, self.GPT_SELECTORS)

                # Type initial task
                await page_gpt.locator(gpt_sel).click()
                await asyncio.sleep(0.5)
                await page_gpt.keyboard.type(initial_task, delay=random.uniform(30, 80))
                await asyncio.sleep(0.5)
                await page_gpt.keyboard.press("Enter")
                await self._wait_for_response(page_gpt, platform="gpt")
                gpt_round0 = await self._extract_gpt_response(page_gpt)

                # Open Gemini
                page_gemini = await context.new_page()
                await page_gemini.goto(self.config.gemini_url, wait_until="networkidle", timeout=30000)
                await self._random_delay()

                # Multi-round debate
                for round_num in range(self.config.max_rounds):
                    print(f"[WebDebate] Round {round_num + 1}/{self.config.max_rounds}")

                    # Gemini responds to GPT
                    gemini_sel = await self._find_input_selector(page_gemini, self.GEMINI_SELECTORS)

                    gemini_prompt = self._build_gemini_prompt(round_num, gpt_round0)
                    await page_gemini.locator(gemini_sel).click()
                    await asyncio.sleep(0.5)
                    await page_gemini.keyboard.type(gemini_prompt, delay=random.uniform(30, 80))
                    await asyncio.sleep(0.5)
                    await page_gemini.keyboard.press("Enter")
                    await self._wait_for_response(page_gemini, platform="gemini")
                    gemini_round = await self._extract_gemini_response(page_gemini)

                    # GPT responds to Gemini
                    await page_gpt.bring_to_front()
                    await self._random_delay()

                    gpt_prompt = self._build_gpt_prompt(round_num, gemini_round)
                    gpt_sel = await self._find_input_selector(page_gpt, self.GPT_SELECTORS)
                    await page_gpt.locator(gpt_sel).click()
                    await asyncio.sleep(0.5)
                    await page_gpt.keyboard.type(gpt_prompt, delay=random.uniform(30, 80))
                    await asyncio.sleep(0.5)
                    await page_gpt.keyboard.press("Enter")
                    await self._wait_for_response(page_gpt, platform="gpt")
                    gpt_round_next = await self._extract_gpt_response(page_gpt)

                    # Save to MemoryPalace
                    self.palace.add_round(
                        task_id=task_id,
                        gpt_view=gpt_round_next,
                        gemini_view=gemini_round,
                        consistency_score=0.0
                    )

                    results["rounds"].append({
                        "round": round_num + 1,
                        "gpt": gpt_round_next[:200],
                        "gemini": gemini_round[:200]
                    })

                    gpt_round0 = gpt_round_next

                await context.close()
                results["status"] = "completed"
                results["completed_at"] = datetime.now().isoformat()
                return results

        except asyncio.TimeoutError as e:
            results["status"] = "timeout"
            results["error"] = "等待回复超时: " + str(e)
            return results
        except Exception as e:
            results["status"] = "error"
            results["error"] = str(e)
            return results
