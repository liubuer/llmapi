"""
AI网页交互客户端
负责与公司内部AI工具网页进行交互
"""
import asyncio
from typing import Optional, AsyncGenerator, List
from datetime import datetime

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from loguru import logger

from .config import get_settings
from .models import ChatMessage
from .browser_manager import browser_manager, get_browser_manager, BrowserSession


class AIClientError(Exception):
    """AI客户端错误"""
    pass


class AIClient:
    """AI网页交互客户端"""
    
    def __init__(self):
        self.settings = get_settings()
        
    async def _ensure_logged_in(self, page: Page) -> bool:
        """确保已登录"""
        try:
            # 检查是否在登录页面
            current_url = page.url
            
            # 如果URL包含login或者auth相关关键字，可能需要重新登录
            if "login" in current_url.lower() or "auth" in current_url.lower():
                logger.warning("检测到登录页面，可能需要重新认证")
                return False
            
            # 检查页面上是否有输入框（表示已成功进入AI工具）
            try:
                await page.wait_for_selector(
                    self.settings.selector_input,
                    timeout=5000
                )
                return True
            except PlaywrightTimeoutError:
                return False
                
        except Exception as e:
            logger.error(f"检查登录状态时出错: {e}")
            return False
    
    async def _navigate_to_ai_tool(self, page: Page):
        """导航到AI工具页面"""
        current_url = page.url
        target_url = self.settings.ai_tool_url
        
        # 如果不在目标页面，则导航
        if not current_url.startswith(target_url):
            logger.info(f"导航到AI工具: {target_url}")
            await page.goto(target_url, wait_until="networkidle")
            await asyncio.sleep(2)  # 等待页面完全加载
    
    async def _start_new_conversation(self, page: Page):
        """开始新对话"""
        try:
            # 尝试点击新对话按钮
            new_chat_btn = page.locator(self.settings.selector_new_chat).first
            if await new_chat_btn.is_visible():
                await new_chat_btn.click()
                await asyncio.sleep(1)
                logger.info("已开始新对话")
        except Exception as e:
            logger.warning(f"开始新对话时出错（可能页面已是新对话状态）: {e}")
    
    async def _select_model(self, page: Page, model: str):
        """选择模型"""
        try:
            model_selector = page.locator(self.settings.selector_model_select).first
            if await model_selector.is_visible():
                await model_selector.click()
                await asyncio.sleep(0.5)
                
                # 尝试选择指定模型
                model_option = page.locator(f"text={model}").first
                if await model_option.is_visible():
                    await model_option.click()
                    logger.info(f"已选择模型: {model}")
                    await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"选择模型时出错（使用默认模型）: {e}")
    
    async def _wait_for_response_complete(self, page: Page) -> str:
        """等待响应完成并获取内容"""
        timeout = self.settings.response_timeout * 1000  # 转换为毫秒
        start_time = datetime.now()
        
        last_content = ""
        stable_count = 0
        
        while (datetime.now() - start_time).total_seconds() < self.settings.response_timeout:
            try:
                # 检查是否还在加载
                loading = page.locator(self.settings.selector_loading)
                is_loading = await loading.count() > 0 and await loading.first.is_visible()
                
                # 获取最新的响应内容
                responses = page.locator(self.settings.selector_response)
                count = await responses.count()
                
                if count > 0:
                    # 获取最后一个响应
                    latest_response = responses.nth(count - 1)
                    current_content = await latest_response.inner_text()
                    
                    # 检查内容是否稳定（不再变化）
                    if current_content == last_content and not is_loading:
                        stable_count += 1
                        if stable_count >= 3:  # 连续3次相同，认为完成
                            return current_content.strip()
                    else:
                        stable_count = 0
                        last_content = current_content
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.debug(f"检查响应时出错: {e}")
                await asyncio.sleep(0.5)
        
        # 超时，返回已获取的内容
        if last_content:
            logger.warning("响应超时，返回部分内容")
            return last_content.strip()
        
        raise AIClientError("等待AI响应超时")
    
    async def _send_message(self, page: Page, message: str) -> str:
        """发送消息并获取响应"""
        # 检查消息长度
        if len(message) > self.settings.max_input_chars:
            raise AIClientError(
                f"消息长度超过限制: {len(message)} > {self.settings.max_input_chars}"
            )
        
        try:
            # 定位输入框
            input_box = page.locator(self.settings.selector_input).first
            await input_box.wait_for(state="visible", timeout=10000)
            
            # 清空并输入消息
            await input_box.click()
            await input_box.fill("")
            await asyncio.sleep(0.2)
            
            # 对于长文本，使用分段输入
            if len(message) > 1000:
                # 使用JavaScript直接设置值，更快
                await page.evaluate(
                    """(selector, text) => {
                        const el = document.querySelector(selector);
                        if (el) {
                            el.value = text;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    }""",
                    self.settings.selector_input.split(",")[0].strip(),
                    message
                )
            else:
                await input_box.fill(message)
            
            await asyncio.sleep(0.3)
            
            # 点击发送按钮或按Enter
            try:
                send_btn = page.locator(self.settings.selector_send_button).first
                if await send_btn.is_visible() and await send_btn.is_enabled():
                    await send_btn.click()
                else:
                    await input_box.press("Enter")
            except:
                await input_box.press("Enter")
            
            logger.info("消息已发送，等待响应...")
            
            # 等待响应完成
            response = await self._wait_for_response_complete(page)
            
            return response
            
        except PlaywrightTimeoutError:
            raise AIClientError("操作超时：无法找到输入框或发送按钮")
        except Exception as e:
            raise AIClientError(f"发送消息时出错: {e}")
    
    async def _stream_response(self, page: Page) -> AsyncGenerator[str, None]:
        """流式获取响应"""
        timeout = self.settings.response_timeout
        start_time = datetime.now()
        
        last_content = ""
        stable_count = 0
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            try:
                responses = page.locator(self.settings.selector_response)
                count = await responses.count()
                
                if count > 0:
                    latest_response = responses.nth(count - 1)
                    current_content = await latest_response.inner_text()
                    
                    # 如果有新内容，返回增量部分
                    if len(current_content) > len(last_content):
                        delta = current_content[len(last_content):]
                        last_content = current_content
                        stable_count = 0
                        yield delta
                    else:
                        # 检查是否还在加载
                        loading = page.locator(self.settings.selector_loading)
                        is_loading = await loading.count() > 0 and await loading.first.is_visible()
                        
                        if not is_loading:
                            stable_count += 1
                            if stable_count >= 5:
                                break
                
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.debug(f"流式获取响应时出错: {e}")
                await asyncio.sleep(0.2)
    
    def _format_messages(self, messages: List[ChatMessage]) -> str:
        """格式化消息列表为单个提示文本"""
        formatted_parts = []
        
        for msg in messages:
            if msg.role == "system":
                formatted_parts.append(f"[系统指令]\n{msg.content}\n")
            elif msg.role == "user":
                formatted_parts.append(f"[用户]\n{msg.content}\n")
            elif msg.role == "assistant":
                formatted_parts.append(f"[助手]\n{msg.content}\n")
        
        # 如果只有一条用户消息，直接返回内容
        if len(messages) == 1 and messages[0].role == "user":
            return messages[0].content
        
        return "\n".join(formatted_parts)
    
    async def chat(
        self,
        messages: List[ChatMessage],
        model: str = "gpt-5",
        new_conversation: bool = False,
        stream: bool = False
    ) -> str | AsyncGenerator[str, None]:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            model: 模型名称
            new_conversation: 是否开始新对话
            stream: 是否流式输出
            
        Returns:
            响应文本或流式生成器
        """
        manager = await get_browser_manager()
        
        async with manager.acquire_session() as session:
            page = session.page
            
            # 导航到AI工具
            await self._navigate_to_ai_tool(page)
            
            # 检查登录状态
            if not await self._ensure_logged_in(page):
                raise AIClientError(
                    "未登录或登录已过期，请运行 'python -m app.browser_manager --login' 重新登录"
                )
            
            # 如果需要，开始新对话
            if new_conversation:
                await self._start_new_conversation(page)
            
            # 选择模型
            await self._select_model(page, model)
            
            # 格式化消息
            prompt = self._format_messages(messages)
            
            # 发送消息
            if stream:
                # 先发送消息
                input_box = page.locator(self.settings.selector_input).first
                await input_box.wait_for(state="visible", timeout=10000)
                await input_box.click()
                
                if len(prompt) > 1000:
                    await page.evaluate(
                        """(selector, text) => {
                            const el = document.querySelector(selector);
                            if (el) {
                                el.value = text;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                            }
                        }""",
                        self.settings.selector_input.split(",")[0].strip(),
                        prompt
                    )
                else:
                    await input_box.fill(prompt)
                
                await asyncio.sleep(0.3)
                
                try:
                    send_btn = page.locator(self.settings.selector_send_button).first
                    if await send_btn.is_visible() and await send_btn.is_enabled():
                        await send_btn.click()
                    else:
                        await input_box.press("Enter")
                except:
                    await input_box.press("Enter")
                
                # 返回流式生成器
                return self._stream_response(page)
            else:
                return await self._send_message(page, prompt)


# 全局客户端实例
ai_client = AIClient()


async def get_ai_client() -> AIClient:
    """获取AI客户端实例"""
    return ai_client
