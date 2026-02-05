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

    async def _select_model(self, page: Page, model: str):
        """选择LLM模型"""
        try:
            # 查找模型选择按钮
            model_button = page.locator(self.settings.selector_model_button).first

            if not await model_button.is_visible(timeout=3000):
                logger.warning("未找到模型选择按钮")
                return False

            # 检查当前选中的模型
            button_text = await model_button.inner_text()
            if model in button_text:
                logger.info(f"当前已选择模型: {model}")
                return True

            logger.info(f"当前模型: {button_text.strip()}, 切换到: {model}")

            # 点击按钮打开下拉菜单
            await model_button.click()
            await asyncio.sleep(0.5)

            # 等待下拉菜单出现
            dropdown = page.locator(self.settings.selector_model_dropdown)
            await dropdown.wait_for(state="visible", timeout=3000)

            # 在下拉菜单中查找目标模型选项
            # 尝试多种选择器
            model_option = page.locator(f"text='{model}'").first
            if not await model_option.is_visible(timeout=1000):
                # 尝试包含模型名的按钮或菜单项
                model_option = page.locator(f"button:has-text('{model}'), [role='menuitem']:has-text('{model}'), div:has-text('{model}')").first

            if await model_option.is_visible(timeout=2000):
                await model_option.click()
                logger.info(f"已选择模型: {model}")
                await asyncio.sleep(0.5)
                return True
            else:
                logger.warning(f"未找到模型选项: {model}")
                # 点击空白处关闭下拉菜单
                await page.keyboard.press("Escape")
                return False

        except Exception as e:
            logger.warning(f"选择模型失败: {e}")
            try:
                await page.keyboard.press("Escape")
            except:
                pass
            return False
    
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
    
    async def _wait_for_response(self, page: Page, sent_message: str = "", initial_count: int = 0) -> str:
        """等待响应"""
        start = datetime.now()
        last_content = ""
        stable_count = 0

        # 加载中的提示文字（需要过滤）
        loading_texts = ["が回答を生成中", "生成中", "Loading", "Thinking", "..."]

        logger.debug(f"等待响应，选择器: {self.settings.selector_response}, 初始元素数: {initial_count}")

        # 记录初始内容（用于检测内容变化，即使元素数量不变）
        initial_content = ""
        if initial_count > 0:
            try:
                responses_init = page.locator(self.settings.selector_response)
                initial_content = await responses_init.nth(initial_count - 1).inner_text()
                initial_content = initial_content.strip()
                logger.debug(f"初始内容: {initial_content[:50]}...")
            except:
                pass

        wait_new_element_timeout = 5  # 等待新元素的超时时间（秒）

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
                elapsed = (datetime.now() - start).total_seconds()

                logger.debug(f"找到 {count} 个响应元素 (初始: {initial_count})，is_loading={is_loading}, elapsed={elapsed:.1f}s")

                # 等待新元素出现，但如果超时则检查内容变化
                if count <= initial_count and count > 0:
                    if elapsed < wait_new_element_timeout:
                        logger.debug("等待新响应元素出现...")
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        # 超时后检查最后一个元素的内容是否变化
                        current_content = await responses.nth(count - 1).inner_text()
                        current_content = current_content.strip()
                        if current_content == initial_content or current_content == sent_message.strip():
                            logger.debug("内容未变化，继续等待...")
                            await asyncio.sleep(0.5)
                            continue
                        logger.debug("检测到内容变化，继续处理")

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

        # 记录当前响应元素数量（用于检测新响应）
        responses = page.locator(self.settings.selector_response)
        initial_count = await responses.count()
        logger.debug(f"非流式模式: 当前响应元素数量 = {initial_count}")

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
        return await self._wait_for_response(page, sent_message=message, initial_count=initial_count)
    
    async def _stream_response(self, page: Page, sent_message: str = "", initial_count: int = 0) -> AsyncGenerator[str, None]:
        """流式响应"""
        start = datetime.now()
        last_content = ""
        stable_count = 0
        response_started = False

        # 加载中的提示文字（需要过滤）
        loading_texts = ["が回答を生成中", "生成中", "Loading", "Thinking", "..."]

        logger.debug(f"开始流式响应，选择器: {self.settings.selector_response}, 初始元素数: {initial_count}")

        # 记录初始内容（用于检测内容变化，即使元素数量不变）
        initial_content = ""
        if initial_count > 0:
            try:
                responses_init = page.locator(self.settings.selector_response)
                initial_content = await responses_init.nth(initial_count - 1).inner_text()
                initial_content = initial_content.strip()
                logger.debug(f"流式: 初始内容: {initial_content[:50]}...")
            except:
                pass

        wait_new_element_timeout = 5  # 等待新元素的超时时间（秒）

        # 先等待新响应元素出现
        while (datetime.now() - start).total_seconds() < self.settings.response_timeout:
            try:
                responses = page.locator(self.settings.selector_response)
                count = await responses.count()
                elapsed = (datetime.now() - start).total_seconds()

                logger.debug(f"流式: 找到 {count} 个响应元素 (初始: {initial_count}), elapsed={elapsed:.1f}s")

                # 等待新元素出现，但如果超时则检查内容变化
                if count <= initial_count and count > 0:
                    if elapsed < wait_new_element_timeout:
                        logger.debug("流式: 等待新响应元素出现...")
                        await asyncio.sleep(0.3)
                        continue
                    else:
                        # 超时后检查最后一个元素的内容是否变化
                        current_content = await responses.nth(count - 1).inner_text()
                        current_content = current_content.strip()
                        if current_content == initial_content or current_content == sent_message.strip():
                            logger.debug("流式: 内容未变化，继续等待...")
                            await asyncio.sleep(0.3)
                            continue
                        logger.debug("流式: 检测到内容变化，继续处理")

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
    
    def _map_model_name(self, model: str) -> str:
        """将API模型名称映射到网页上的模型名称"""
        model_lower = model.lower()

        # 模型名称映射
        model_mapping = {
            "gpt-5": "GPT-5",
            "gpt5": "GPT-5",
            "gpt-5-thinking": "GPT-5 thinking",
            "gpt5-thinking": "GPT-5 thinking",
            "gpt-4.1-mini": "GPT-4.1 mini",
            "gpt-4.1": "GPT-4.1 mini",
            "gpt4.1-mini": "GPT-4.1 mini",
        }

        # 查找映射
        if model_lower in model_mapping:
            return model_mapping[model_lower]

        # 如果没有映射，使用默认模型
        return self.settings.default_model

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

            # 选择模型（如果指定了模型名称）
            target_model = self._map_model_name(model)
            if target_model:
                await self._select_model(page, target_model)
            
            prompt = self._format_messages(messages)
            
            if stream:
                # 记录当前响应元素数量（用于检测新响应）
                responses = page.locator(self.settings.selector_response)
                initial_count = await responses.count()
                logger.debug(f"流式模式: 当前响应元素数量 = {initial_count}")

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

                return self._stream_response(page, sent_message=prompt, initial_count=initial_count)
            else:
                return await self._send_message(page, prompt)


ai_client = AIClient()

async def get_ai_client() -> AIClient:
    return ai_client
