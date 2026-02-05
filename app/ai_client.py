"""AI网页交互客户端"""
import asyncio
from typing import AsyncGenerator, List, Tuple
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from loguru import logger

from .config import get_settings
from .models import ChatMessage
from .edge_manager import edge_manager, get_edge_manager


# 大文本分割提示词模板
CHUNK_TEMPLATE_FIRST = """下面将输入一份约{total_chars}字的资料，将分{total_parts}次输入。
这是第1份资料（共{total_parts}份），约{part_chars}字。
请你接收并记住这些内容，接收完后我将继续输入下一份资料。
收到后请简短回复"已接收第1份"即可，无需其他内容。

---资料开始---
{content}
---资料结束---"""

CHUNK_TEMPLATE_MIDDLE = """这是第{part_num}份资料（共{total_parts}份），约{part_chars}字。
请你接收并与之前的资料合并记忆，接收完后我将继续输入。
收到后请简短回复"已接收第{part_num}份"即可，无需其他内容。

---资料开始---
{content}
---资料结束---"""

CHUNK_TEMPLATE_LAST = """这是最后一份资料（第{part_num}份，共{total_parts}份），约{part_chars}字。
请你接收后，将所有{total_parts}份资料在记忆中合并成完整的一份。

---资料开始---
{content}
---资料结束---

资料接收完毕。现在请根据上述全部资料，回答以下问题：

{question}"""

CHUNK_TEMPLATE_LAST_NO_QUESTION = """这是最后一份资料（第{part_num}份，共{total_parts}份），约{part_chars}字。
请你接收后，将所有{total_parts}份资料在记忆中合并成完整的一份。
合并完成后，请简要概括这些资料的主要内容。

---资料开始---
{content}
---资料结束---"""


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
            # 查找模型选择按钮 (id 匹配 mantine-*-target)
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

            # 获取下拉菜单ID (从 aria-controls 属性)
            dropdown_id = await model_button.get_attribute("aria-controls")
            logger.debug(f"下拉菜单ID: {dropdown_id}")

            # 点击按钮打开下拉菜单
            await model_button.click()
            await asyncio.sleep(0.5)

            # 等待下拉菜单出现
            if dropdown_id:
                dropdown = page.locator(f"#{dropdown_id}")
                await dropdown.wait_for(state="visible", timeout=3000)

            # 在下拉菜单中查找目标模型选项 (使用 mantine-Menu-itemLabel)
            menu_items = page.locator(self.settings.selector_model_item)
            count = await menu_items.count()
            logger.debug(f"找到 {count} 个菜单项")

            for i in range(count):
                item = menu_items.nth(i)
                item_text = await item.inner_text()
                logger.debug(f"菜单项 {i}: {item_text}")

                if model in item_text:
                    await item.click()
                    logger.info(f"已选择模型: {model}")
                    await asyncio.sleep(0.5)
                    return True

            logger.warning(f"未找到模型选项: {model}")
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

    def _split_long_text(self, text: str, question: str = "") -> List[str]:
        """
        将长文本分割成多个块，并添加提示词模板

        Args:
            text: 要分割的长文本（背景资料）
            question: 用户的问题（将在最后一块中提出）

        Returns:
            分割后的提示词列表
        """
        chunk_size = self.settings.chunk_size
        total_chars = len(text)

        # 如果文本不需要分割
        if total_chars <= self.settings.max_input_chars:
            return [text]

        # 计算需要分割的块数
        # 为模板预留空间（约500-1000字符）
        effective_chunk_size = chunk_size - 500
        num_chunks = (total_chars + effective_chunk_size - 1) // effective_chunk_size

        logger.info(f"文本过长 ({total_chars} 字符)，将分割为 {num_chunks} 块")

        chunks = []
        start = 0

        for i in range(num_chunks):
            # 确定这一块的结束位置
            if i == num_chunks - 1:
                # 最后一块，取剩余所有内容
                end = total_chars
            else:
                end = min(start + effective_chunk_size, total_chars)
                # 尝试在句子边界处分割
                boundary_chars = ['。', '！', '？', '\n', '.', '!', '?']
                search_start = max(end - 200, start)
                best_boundary = end
                for bc in boundary_chars:
                    pos = text.rfind(bc, search_start, end)
                    if pos > search_start:
                        best_boundary = pos + 1
                        break
                end = best_boundary

            chunk_content = text[start:end]
            part_chars = len(chunk_content)
            part_num = i + 1

            # 根据位置选择模板
            if i == 0:
                # 第一块
                formatted = CHUNK_TEMPLATE_FIRST.format(
                    total_chars=total_chars,
                    total_parts=num_chunks,
                    part_chars=part_chars,
                    content=chunk_content
                )
            elif i == num_chunks - 1:
                # 最后一块
                if question:
                    formatted = CHUNK_TEMPLATE_LAST.format(
                        part_num=part_num,
                        total_parts=num_chunks,
                        part_chars=part_chars,
                        content=chunk_content,
                        question=question
                    )
                else:
                    formatted = CHUNK_TEMPLATE_LAST_NO_QUESTION.format(
                        part_num=part_num,
                        total_parts=num_chunks,
                        part_chars=part_chars,
                        content=chunk_content
                    )
            else:
                # 中间块
                formatted = CHUNK_TEMPLATE_MIDDLE.format(
                    part_num=part_num,
                    total_parts=num_chunks,
                    part_chars=part_chars,
                    content=chunk_content
                )

            chunks.append(formatted)
            logger.debug(f"块 {part_num}/{num_chunks}: {part_chars} 字符 (位置 {start}-{end})")
            start = end

        return chunks

    def _extract_question_and_content(self, text: str) -> Tuple[str, str]:
        """
        从文本中提取问题和背景资料

        尝试识别常见的问题标记，如：
        - "问题：" / "问："
        - "请回答："
        - "Question:" / "Q:"
        - 文本最后一段（如果较短）

        Returns:
            (背景资料, 问题)
        """
        # 尝试识别问题标记
        question_markers = [
            '问题：', '问题:', '问：', '问:',
            '请回答：', '请回答:',
            'Question:', 'question:', 'Q:', 'q:',
            '请问', '请分析', '请总结', '请概括'
        ]

        for marker in question_markers:
            if marker in text:
                pos = text.rfind(marker)
                # 检查问题部分是否在文本末尾（最后20%的位置）
                if pos > len(text) * 0.8:
                    content = text[:pos].strip()
                    question = text[pos:].strip()
                    logger.info(f"识别到问题标记: {marker}")
                    return content, question

        # 如果没有找到明确的问题标记，检查最后一段
        paragraphs = text.strip().split('\n\n')
        if len(paragraphs) > 1:
            last_paragraph = paragraphs[-1].strip()
            # 如果最后一段较短（小于500字符）且像是问题
            if len(last_paragraph) < 500 and ('?' in last_paragraph or '？' in last_paragraph or '请' in last_paragraph):
                content = '\n\n'.join(paragraphs[:-1])
                return content, last_paragraph

        # 无法识别问题，返回原文本
        return text, ""

    async def _send_chunked_messages(self, page: Page, chunks: List[str], stream: bool = False):
        """
        分批发送长文本

        Args:
            page: Playwright页面对象
            chunks: 分割后的提示词列表
            stream: 是否使用流式响应（仅最后一块使用）

        Returns:
            最后一块的响应（字符串或异步生成器）
        """
        total_chunks = len(chunks)
        logger.info(f"开始分批发送，共 {total_chunks} 块")

        for i, chunk in enumerate(chunks):
            part_num = i + 1
            is_last = (i == total_chunks - 1)

            logger.info(f"发送第 {part_num}/{total_chunks} 块 ({len(chunk)} 字符)")

            if is_last:
                # 最后一块，根据stream参数决定响应方式
                if stream:
                    # 流式响应
                    responses = page.locator(self.settings.selector_response)
                    initial_count = await responses.count()

                    input_box = await self._find_input(page)
                    if not input_box:
                        raise AIClientError("找不到输入框")

                    await input_box.click()
                    await page.evaluate("""(text) => {
                        const el = document.querySelector('textarea') ||
                                   document.querySelector('[contenteditable="true"]');
                        if (el) {
                            if (el.tagName === 'TEXTAREA') el.value = text;
                            else el.innerText = text;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    }""", chunk)
                    await asyncio.sleep(0.3)
                    await input_box.press("Control+Enter")

                    return self._stream_response(page, sent_message=chunk, initial_count=initial_count)
                else:
                    # 非流式响应
                    return await self._send_message(page, chunk)
            else:
                # 非最后一块，等待确认响应
                response = await self._send_message(page, chunk)

                # 检查响应是否表示已接收
                confirmation_keywords = ['已接收', '接收', '收到', 'received', '了解', '明白']
                is_confirmed = any(kw in response.lower() for kw in confirmation_keywords)

                if is_confirmed:
                    logger.info(f"第 {part_num} 块已确认接收")
                else:
                    logger.warning(f"第 {part_num} 块响应: {response[:100]}...")

                # 短暂等待，避免发送过快
                await asyncio.sleep(1)
    
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

            # 选择模型（暂时屏蔽，选择器需要调试）
            # target_model = self._map_model_name(model)
            # if target_model:
            #     await self._select_model(page, target_model)

            prompt = self._format_messages(messages)

            # 检查是否需要分割长文本
            if len(prompt) > self.settings.max_input_chars:
                logger.info(f"检测到长文本 ({len(prompt)} 字符)，启用分割模式")

                # 提取问题和背景资料
                content, question = self._extract_question_and_content(prompt)

                # 分割文本
                chunks = self._split_long_text(content, question)

                # 分批发送
                return await self._send_chunked_messages(page, chunks, stream=stream)

            # 正常发送（文本长度在限制内）
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
