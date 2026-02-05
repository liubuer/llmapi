"""
AI网页交互客户端
负责与公司内部AI工具网页进行交互

企业环境优化版 - 增强调试和登录检测
"""
import asyncio
import os
from typing import Optional, AsyncGenerator, List
from datetime import datetime
from pathlib import Path

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
        self._debug_dir = Path("./debug")
        self._debug_dir.mkdir(exist_ok=True)
        
    async def _save_debug_screenshot(self, page: Page, name: str):
        """保存调试截图"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self._debug_dir / f"{name}_{timestamp}.png"
            await page.screenshot(path=str(path))
            logger.info(f"调试截图已保存: {path}")
            return path
        except Exception as e:
            logger.warning(f"保存截图失败: {e}")
            return None
    
    async def _log_page_info(self, page: Page):
        """记录页面信息用于调试"""
        try:
            url = page.url
            title = await page.title()
            logger.info(f"当前页面 - URL: {url}")
            logger.info(f"当前页面 - 标题: {title}")
        except Exception as e:
            logger.warning(f"获取页面信息失败: {e}")
    
    async def _ensure_logged_in(self, page: Page) -> bool:
        """
        确保已登录
        
        检查逻辑：
        1. 等待页面完全加载
        2. 尝试查找输入框元素
        3. 如果找到输入框，说明已登录
        4. 如果找不到，保存截图用于调试
        """
        try:
            await self._log_page_info(page)
            
            # 等待页面加载完成
            logger.info("等待页面加载...")
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except PlaywrightTimeoutError:
                logger.warning("等待networkidle超时，继续尝试...")
            
            # 额外等待，确保动态内容加载
            await asyncio.sleep(3)
            
            # 再次记录页面信息
            await self._log_page_info(page)
            
            # 检查URL是否包含登录相关关键字
            current_url = page.url.lower()
            login_keywords = ["login", "auth", "signin", "sso", "oauth", "adfs"]
            
            for keyword in login_keywords:
                if keyword in current_url:
                    logger.warning(f"URL包含'{keyword}'，可能在登录页面")
                    await self._save_debug_screenshot(page, "login_page_detected")
                    # 不立即返回False，继续检查是否有输入框
                    break
            
            # 尝试查找输入框 - 使用多种选择器
            input_selectors = [
                self.settings.selector_input,
                "textarea",
                "input[type='text']",
                "[contenteditable='true']",
                "[role='textbox']",
            ]
            
            for selector in input_selectors:
                try:
                    logger.debug(f"尝试选择器: {selector}")
                    element = page.locator(selector).first
                    
                    # 等待元素出现
                    await element.wait_for(state="visible", timeout=5000)
                    
                    # 检查元素是否可见
                    if await element.is_visible():
                        logger.info(f"✓ 找到输入框 (选择器: {selector})")
                        return True
                        
                except PlaywrightTimeoutError:
                    logger.debug(f"选择器超时: {selector}")
                    continue
                except Exception as e:
                    logger.debug(f"选择器失败: {selector}, 错误: {e}")
                    continue
            
            # 所有选择器都失败
            logger.warning("未找到任何输入框元素")
            
            # 保存截图用于调试
            screenshot_path = await self._save_debug_screenshot(page, "no_input_found")
            
            # 保存页面HTML用于调试
            try:
                html_path = self._debug_dir / f"page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                content = await page.content()
                html_path.write_text(content, encoding="utf-8")
                logger.info(f"页面HTML已保存: {html_path}")
            except Exception as e:
                logger.warning(f"保存HTML失败: {e}")
            
            # 打印一些页面元素信息帮助调试
            try:
                # 查找所有textarea
                textareas = await page.locator("textarea").count()
                logger.info(f"页面中textarea数量: {textareas}")
                
                # 查找所有input
                inputs = await page.locator("input").count()
                logger.info(f"页面中input数量: {inputs}")
                
                # 查找所有button
                buttons = await page.locator("button").count()
                logger.info(f"页面中button数量: {buttons}")
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"检查登录状态时出错: {e}")
            await self._save_debug_screenshot(page, "login_check_error")
            return False
    
    async def _navigate_to_ai_tool(self, page: Page):
        """导航到AI工具页面"""
        current_url = page.url
        target_url = self.settings.ai_tool_url
        
        # 如果不在目标页面，则导航
        if not current_url.startswith(target_url):
            logger.info(f"导航到AI工具: {target_url}")
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            except PlaywrightTimeoutError:
                logger.warning("导航超时，尝试继续...")
            
            # 等待页面加载
            await asyncio.sleep(3)
        else:
            logger.info(f"已在目标页面: {current_url}")
    
    async def _start_new_conversation(self, page: Page):
        """开始新对话"""
        try:
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
                
                model_option = page.locator(f"text={model}").first
                if await model_option.is_visible():
                    await model_option.click()
                    logger.info(f"已选择模型: {model}")
                    await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"选择模型时出错（使用默认模型）: {e}")
    
    async def _wait_for_response_complete(self, page: Page) -> str:
        """等待响应完成并获取内容"""
        start_time = datetime.now()
        
        last_content = ""
        stable_count = 0
        
        logger.info("等待AI响应...")
        
        while (datetime.now() - start_time).total_seconds() < self.settings.response_timeout:
            try:
                # 检查是否还在加载
                loading = page.locator(self.settings.selector_loading)
                is_loading = await loading.count() > 0
                
                if is_loading:
                    try:
                        is_loading = await loading.first.is_visible()
                    except:
                        is_loading = False
                
                # 获取最新的响应内容
                responses = page.locator(self.settings.selector_response)
                count = await responses.count()
                
                if count > 0:
                    latest_response = responses.nth(count - 1)
                    current_content = await latest_response.inner_text()
                    
                    if current_content == last_content and not is_loading:
                        stable_count += 1
                        if stable_count >= 3:
                            logger.info(f"响应完成，内容长度: {len(current_content)}")
                            return current_content.strip()
                    else:
                        stable_count = 0
                        last_content = current_content
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.debug(f"检查响应时出错: {e}")
                await asyncio.sleep(0.5)
        
        if last_content:
            logger.warning("响应超时，返回部分内容")
            return last_content.strip()
        
        raise AIClientError("等待AI响应超时")
    
    async def _find_input_element(self, page: Page):
        """查找输入框元素"""
        # 尝试多种选择器
        selectors = [
            self.settings.selector_input,
            "textarea",
            "[contenteditable='true']",
            "input[type='text']",
        ]
        
        for selector in selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible():
                    logger.debug(f"使用输入框选择器: {selector}")
                    return element
            except:
                continue
        
        return None
    
    async def _find_send_button(self, page: Page):
        """查找发送按钮"""
        selectors = [
            self.settings.selector_send_button,
            "button[type='submit']",
            "button:has-text('发送')",
            "button:has-text('Send')",
            "button:has-text('送信')",
            "button svg",  # 通常发送按钮有图标
        ]
        
        for selector in selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible() and await element.is_enabled():
                    logger.debug(f"使用发送按钮选择器: {selector}")
                    return element
            except:
                continue
        
        return None
    
    async def _send_message(self, page: Page, message: str) -> str:
        """发送消息并获取响应"""
        if len(message) > self.settings.max_input_chars:
            raise AIClientError(
                f"消息长度超过限制: {len(message)} > {self.settings.max_input_chars}"
            )
        
        try:
            # 查找输入框
            input_box = await self._find_input_element(page)
            if not input_box:
                await self._save_debug_screenshot(page, "no_input_box")
                raise AIClientError("找不到输入框")
            
            await input_box.wait_for(state="visible", timeout=10000)
            
            # 清空并输入消息
            await input_box.click()
            await asyncio.sleep(0.2)
            
            # 对于长文本，使用JavaScript直接设置值
            if len(message) > 1000:
                await page.evaluate(
                    """(text) => {
                        const el = document.querySelector('textarea') || 
                                   document.querySelector('[contenteditable="true"]') ||
                                   document.querySelector('input[type="text"]');
                        if (el) {
                            if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                                el.value = text;
                            } else {
                                el.innerText = text;
                            }
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    }""",
                    message
                )
            else:
                await input_box.fill(message)
            
            await asyncio.sleep(0.3)
            logger.info(f"已输入消息，长度: {len(message)}")
            
            # 查找并点击发送按钮
            send_btn = await self._find_send_button(page)
            if send_btn:
                await send_btn.click()
                logger.info("已点击发送按钮")
            else:
                # 尝试按Enter发送
                await input_box.press("Enter")
                logger.info("已按Enter发送")
            
            # 等待响应完成
            response = await self._wait_for_response_complete(page)
            return response
            
        except PlaywrightTimeoutError:
            await self._save_debug_screenshot(page, "send_timeout")
            raise AIClientError("操作超时：无法找到输入框或发送按钮")
        except AIClientError:
            raise
        except Exception as e:
            await self._save_debug_screenshot(page, "send_error")
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
                    
                    if len(current_content) > len(last_content):
                        delta = current_content[len(last_content):]
                        last_content = current_content
                        stable_count = 0
                        yield delta
                    else:
                        loading = page.locator(self.settings.selector_loading)
                        is_loading = await loading.count() > 0
                        
                        if is_loading:
                            try:
                                is_loading = await loading.first.is_visible()
                            except:
                                is_loading = False
                        
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
        # 如果只有一条用户消息，直接返回内容
        if len(messages) == 1 and messages[0].role == "user":
            return messages[0].content
        
        formatted_parts = []
        
        for msg in messages:
            if msg.role == "system":
                formatted_parts.append(f"[系统指令]\n{msg.content}\n")
            elif msg.role == "user":
                formatted_parts.append(f"[用户]\n{msg.content}\n")
            elif msg.role == "assistant":
                formatted_parts.append(f"[助手]\n{msg.content}\n")
        
        return "\n".join(formatted_parts)
    
    async def chat(
        self,
        messages: List[ChatMessage],
        model: str = "gpt-5",
        new_conversation: bool = False,
        stream: bool = False,
        skip_login_check: bool = False  # 调试用：跳过登录检查
    ) -> str | AsyncGenerator[str, None]:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            model: 模型名称
            new_conversation: 是否开始新对话
            stream: 是否流式输出
            skip_login_check: 跳过登录检查（调试用）
            
        Returns:
            响应文本或流式生成器
        """
        # 检查环境变量
        skip_login_check = skip_login_check or os.environ.get("SKIP_LOGIN_CHECK", "").lower() == "true"
        
        manager = await get_browser_manager()
        
        async with manager.acquire_session() as session:
            page = session.page
            
            # 导航到AI工具
            await self._navigate_to_ai_tool(page)
            
            # 检查登录状态
            if not skip_login_check:
                if not await self._ensure_logged_in(page):
                    raise AIClientError(
                        "未登录或登录已过期，请运行 'python -m app.browser_manager --login' 重新登录"
                    )
            else:
                logger.warning("已跳过登录检查（调试模式）")
                await asyncio.sleep(2)  # 给页面一些加载时间
            
            # 如果需要，开始新对话
            if new_conversation:
                await self._start_new_conversation(page)
            
            # 选择模型
            await self._select_model(page, model)
            
            # 格式化消息
            prompt = self._format_messages(messages)
            
            # 发送消息
            if stream:
                input_box = await self._find_input_element(page)
                if not input_box:
                    raise AIClientError("找不到输入框")
                
                await input_box.wait_for(state="visible", timeout=10000)
                await input_box.click()
                
                if len(prompt) > 1000:
                    await page.evaluate(
                        """(text) => {
                            const el = document.querySelector('textarea') || 
                                       document.querySelector('[contenteditable="true"]');
                            if (el) {
                                if (el.tagName === 'TEXTAREA') {
                                    el.value = text;
                                } else {
                                    el.innerText = text;
                                }
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                            }
                        }""",
                        prompt
                    )
                else:
                    await input_box.fill(prompt)
                
                await asyncio.sleep(0.3)
                
                send_btn = await self._find_send_button(page)
                if send_btn:
                    await send_btn.click()
                else:
                    await input_box.press("Enter")
                
                return self._stream_response(page)
            else:
                return await self._send_message(page, prompt)


# 全局客户端实例
ai_client = AIClient()


async def get_ai_client() -> AIClient:
    """获取AI客户端实例"""
    return ai_client
