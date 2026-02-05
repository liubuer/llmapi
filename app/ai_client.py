"""AI网页交互客户端"""
import asyncio
from typing import AsyncGenerator, List
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from loguru import logger

from .config import get_settings
from .models import ChatMessage
from .edge_manager import edge_manager, get_edge_manager


class AIClientError(Exception):
    pass


class AIClient:
    def __init__(self):
        self.settings = get_settings()
        self._debug_dir = Path("./debug")
        self._debug_dir.mkdir(exist_ok=True)
    
    async def _save_screenshot(self, page: Page, name: str):
        """保存调试截图"""
        try:
            path = self._debug_dir / f"{name}_{datetime.now().strftime('%H%M%S')}.png"
            await page.screenshot(path=str(path))
            logger.info(f"截图: {path}")
        except:
            pass
    
    async def _navigate_to_ai_tool(self, page: Page):
        """导航到AI工具页面"""
        current_url = page.url
        target_url = self.settings.ai_tool_url
        
        if not current_url.startswith(target_url):
            logger.info(f"导航到: {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
    
    async def _find_input(self, page: Page):
        """查找输入框"""
        selectors = self.settings.selector_input.split(",")
        
        for selector in selectors:
            selector = selector.strip()
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=2000):
                    return element
            except:
                continue
        
        # 通用选择器
        for selector in ["textarea", "[contenteditable='true']", "input[type='text']"]:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=1000):
                    return element
            except:
                continue
        
        return None
    
    async def _find_send_button(self, page: Page):
        """查找发送按钮"""
        selectors = [
            self.settings.selector_send_button,
            "button[type='submit']",
            "button:has(svg)",
        ]
        
        for selector in selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=1000):
                    if await element.is_enabled():
                        return element
            except:
                continue
        return None
    
    async def _wait_for_response(self, page: Page, sent_message: str = "") -> str:
        """等待响应"""
        start = datetime.now()
        last_content = ""
        stable_count = 0

        # 加载中的提示文字（需要过滤）
        loading_texts = ["が回答を生成中", "生成中", "Loading", "Thinking", "..."]

        logger.debug(f"等待响应，选择器: {self.settings.selector_response}")

        while (datetime.now() - start).total_seconds() < self.settings.response_timeout:
            try:
                # 检查加载状态
                loading = page.locator(self.settings.selector_loading)
                is_loading = await loading.count() > 0
                if is_loading:
                    try:
                        is_loading = await loading.first.is_visible(timeout=500)
                    except:
                        is_loading = False

                # 获取响应
                responses = page.locator(self.settings.selector_response)
                count = await responses.count()

                logger.debug(f"找到 {count} 个响应元素，is_loading={is_loading}")

                if count > 0:
                    content = await responses.nth(count - 1).inner_text()
                    content = content.strip()

                    logger.debug(f"最后一个元素内容 ({len(content)} 字符): {content[:100]}...")

                    # 过滤加载提示
                    is_loading_text = any(t in content for t in loading_texts)

                    # 过滤用户发送的消息（避免把用户消息当作响应）
                    if sent_message and content == sent_message.strip():
                        logger.debug("检测到用户消息，跳过")
                        await asyncio.sleep(0.5)
                        continue

                    if is_loading_text or len(content) < 5:
                        await asyncio.sleep(0.5)
                        continue

                    if content == last_content and not is_loading:
                        stable_count += 1
                        if stable_count >= 3:
                            logger.info(f"响应稳定，返回 {len(content)} 字符")
                            return content
                    else:
                        stable_count = 0
                        last_content = content

                await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"等待响应时出错: {e}")
                await asyncio.sleep(0.5)

        if last_content:
            logger.warning(f"响应超时，返回最后内容: {len(last_content)} 字符")
            return last_content

        await self._save_screenshot(page, "response_timeout")
        raise AIClientError("响应超时")
    
    async def _send_message(self, page: Page, message: str) -> str:
        """发送消息"""
        if len(message) > self.settings.max_input_chars:
            raise AIClientError(f"消息过长: {len(message)} > {self.settings.max_input_chars}")
        
        # 查找输入框
        input_box = await self._find_input(page)
        if not input_box:
            await self._save_screenshot(page, "no_input")
            raise AIClientError("找不到输入框")
        
        # 输入消息
        await input_box.click()
        await asyncio.sleep(0.2)
        
        if len(message) > 500:
            # 长文本用JS输入
            await page.evaluate("""(text) => {
                const el = document.querySelector('textarea') || 
                           document.querySelector('[contenteditable="true"]');
                if (el) {
                    if (el.tagName === 'TEXTAREA') el.value = text;
                    else el.innerText = text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }""", message)
        else:
            await input_box.fill(message)
        
        await asyncio.sleep(0.3)
        logger.info(f"已输入消息 ({len(message)} 字符)")
        
        # 发送 - 使用 Ctrl+Enter
        await input_box.press("Control+Enter")
        logger.info("消息已发送 (Ctrl+Enter)，等待响应...")
        return await self._wait_for_response(page, sent_message=message)
    
    async def _stream_response(self, page: Page, sent_message: str = "") -> AsyncGenerator[str, None]:
        """流式响应"""
        start = datetime.now()
        last_content = ""
        stable_count = 0
        response_started = False

        # 加载中的提示文字（需要过滤）
        loading_texts = ["が回答を生成中", "生成中", "Loading", "Thinking", "..."]

        logger.debug(f"开始流式响应，选择器: {self.settings.selector_response}")

        # 先等待响应开始（过滤加载提示）
        while (datetime.now() - start).total_seconds() < self.settings.response_timeout:
            try:
                responses = page.locator(self.settings.selector_response)
                count = await responses.count()

                logger.debug(f"流式: 找到 {count} 个响应元素")

                if count > 0:
                    content = await responses.nth(count - 1).inner_text()
                    content = content.strip()

                    logger.debug(f"流式: 内容 ({len(content)} 字符): {content[:50]}...")

                    # 检查是否是加载提示
                    is_loading_text = any(t in content for t in loading_texts)

                    # 过滤用户发送的消息
                    if sent_message and content == sent_message.strip():
                        logger.debug("流式: 检测到用户消息，跳过")
                        await asyncio.sleep(0.3)
                        continue

                    if is_loading_text or len(content) < 5:
                        # 还在加载中，继续等待
                        await asyncio.sleep(0.3)
                        continue

                    # 真正的响应开始了
                    if not response_started:
                        response_started = True
                        last_content = ""  # 重置
                        logger.info("流式响应开始")

                    if len(content) > len(last_content):
                        delta = content[len(last_content):]
                        last_content = content
                        stable_count = 0
                        yield delta
                    else:
                        # 检查是否还在加载
                        loading = page.locator(self.settings.selector_loading)
                        is_loading = await loading.count() > 0
                        if not is_loading:
                            stable_count += 1
                            if stable_count >= 5:
                                logger.info("流式响应结束")
                                break

                await asyncio.sleep(0.2)
            except Exception as e:
                logger.debug(f"流式响应出错: {e}")
                await asyncio.sleep(0.2)

        if not response_started:
            logger.warning("流式响应超时，未检测到响应内容")
            await self._save_screenshot(page, "stream_timeout")
    
    def _format_messages(self, messages: List[ChatMessage]) -> str:
        """格式化消息"""
        if len(messages) == 1 and messages[0].role == "user":
            return messages[0].content
        
        parts = []
        for msg in messages:
            if msg.role == "system":
                parts.append(f"[系统指令]\n{msg.content}")
            elif msg.role == "user":
                parts.append(f"[用户]\n{msg.content}")
            elif msg.role == "assistant":
                parts.append(f"[助手]\n{msg.content}")
        
        return "\n\n".join(parts)
    
    async def chat(
        self,
        messages: List[ChatMessage],
        model: str = "gpt-5",
        stream: bool = False
    ):
        """发送聊天请求"""
        manager = await get_edge_manager()
        
        if not manager.is_connected:
            connected = await manager.connect_to_edge()
            if not connected:
                raise AIClientError(
                    "无法连接到Edge浏览器。\n"
                    "请先运行: python -m app.edge_manager start"
                )
        
        async with manager.acquire_session() as session:
            page = session.page
            
            await self._navigate_to_ai_tool(page)
            
            # 检查是否有输入框（验证登录状态）
            input_box = await self._find_input(page)
            if not input_box:
                await self._save_screenshot(page, "not_logged_in")
                raise AIClientError(
                    "未找到输入框，可能未登录。\n"
                    "请在Edge浏览器中完成登录。"
                )
            
            prompt = self._format_messages(messages)
            
            if stream:
                # 输入并发送
                await input_box.click()
                if len(prompt) > 500:
                    await page.evaluate("""(text) => {
                        const el = document.querySelector('textarea') ||
                                   document.querySelector('[contenteditable="true"]');
                        if (el) {
                            if (el.tagName === 'TEXTAREA') el.value = text;
                            else el.innerText = text;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    }""", prompt)
                else:
                    await input_box.fill(prompt)

                await asyncio.sleep(0.3)
                logger.info(f"发送消息 ({len(prompt)} 字符): {prompt[:50]}...")

                # 发送 - 使用 Ctrl+Enter
                await input_box.press("Control+Enter")

                return self._stream_response(page, sent_message=prompt)
            else:
                return await self._send_message(page, prompt)


ai_client = AIClient()

async def get_ai_client() -> AIClient:
    return ai_client
