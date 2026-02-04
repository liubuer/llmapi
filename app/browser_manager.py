"""
企业环境专用浏览器管理器
解决企业版Edge/组策略环境下的限制问题

核心策略：
1. 不使用Edge的User Data目录（会被锁定/检测）
2. 使用Playwright自带的Chromium浏览器
3. 创建独立的用户数据目录，首次手动登录后保存状态
4. 之后自动复用登录状态
"""
import asyncio
import os
import platform
from typing import Optional, Dict, List
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import uuid

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from loguru import logger

from .config import get_settings


@dataclass
class BrowserSession:
    """浏览器会话"""
    session_id: str
    context: BrowserContext
    page: Page
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    is_busy: bool = False
    message_count: int = 0
    
    def mark_used(self):
        self.last_used = datetime.now()
        self.message_count += 1


class BrowserManager:
    """
    浏览器管理器 - 企业环境优化版
    
    使用独立的浏览器数据目录，避免与企业Edge冲突
    """
    
    _instance: Optional["BrowserManager"] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.settings = get_settings()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._persistent_context: Optional[BrowserContext] = None
        self._sessions: Dict[str, BrowserSession] = {}
        self._session_lock = asyncio.Lock()
        self._initialized = True
        self._started = False
        self._use_persistent = False
        
    def _get_browser_data_dir(self) -> Path:
        """
        获取独立的浏览器数据目录
        这个目录完全由我们控制，不会触发企业策略
        """
        # 使用项目目录下的 browser_data 文件夹
        return Path(self.settings.auth_state_path).parent / "browser_data"
    
    def _get_auth_state_file(self) -> Path:
        """获取认证状态文件路径"""
        return self.settings.auth_state_path / "state.json"
    
    async def start(self, use_persistent_context: bool = True):
        """
        启动浏览器管理器
        
        Args:
            use_persistent_context: 是否使用持久化上下文（推荐True，可保持登录状态）
        """
        if self._started:
            return
            
        async with self._lock:
            if self._started:
                return
            
            logger.info("正在启动浏览器管理器（企业环境模式）...")
            
            # 确保目录存在
            self.settings.auth_state_path.mkdir(parents=True, exist_ok=True)
            browser_data_dir = self._get_browser_data_dir()
            browser_data_dir.mkdir(parents=True, exist_ok=True)
            
            # 启动Playwright
            self._playwright = await async_playwright().start()
            
            # 检查环境变量配置
            use_persistent_context = os.environ.get(
                "USE_PERSISTENT_CONTEXT", "true"
            ).lower() == "true"
            
            if use_persistent_context:
                await self._start_persistent_mode(browser_data_dir)
            else:
                await self._start_normal_mode()
            
            self._started = True
            logger.info("浏览器管理器启动完成")
    
    async def _start_persistent_mode(self, browser_data_dir: Path):
        """
        持久化模式启动（推荐）
        
        使用独立的浏览器数据目录，登录状态会自动保存在这个目录中
        """
        logger.info(f"使用持久化模式，数据目录: {browser_data_dir}")
        self._use_persistent = True
        
        # 使用Playwright自带的Chromium，不使用系统Edge
        self._persistent_context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(browser_data_dir),
            headless=self.settings.browser_headless,
            slow_mo=self.settings.browser_slow_mo,
            # 不指定channel，使用Playwright自带的Chromium
            # 这样就不会触发企业Edge的策略
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-web-security",  # 某些企业环境需要
                "--disable-features=IsolateOrigins,site-per-process",
            ],
            ignore_default_args=["--enable-automation"],
        )
        
        logger.info("持久化上下文启动成功")
    
    async def _start_normal_mode(self):
        """普通模式启动（使用state.json）"""
        logger.info("使用普通模式启动")
        self._use_persistent = False
        
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.browser_headless,
            slow_mo=self.settings.browser_slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ]
        )
    
    async def stop(self):
        """停止浏览器管理器"""
        if not self._started:
            return
            
        async with self._lock:
            logger.info("正在停止浏览器管理器...")
            
            # 关闭所有会话
            for session in list(self._sessions.values()):
                await self._close_session(session)
            
            if self._use_persistent:
                if self._persistent_context:
                    await self._persistent_context.close()
                    self._persistent_context = None
            else:
                if self._browser:
                    await self._browser.close()
                    self._browser = None
            
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            
            self._started = False
            logger.info("浏览器管理器已停止")
    
    async def _create_context(self) -> BrowserContext:
        """创建浏览器上下文"""
        if self._use_persistent and self._persistent_context:
            return self._persistent_context
        
        auth_file = self._get_auth_state_file()
        
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "locale": "ja-JP",
            "timezone_id": "Asia/Tokyo",
        }
        
        if auth_file.exists():
            logger.info("加载已保存的认证状态")
            context_options["storage_state"] = str(auth_file)
        
        return await self._browser.new_context(**context_options)
    
    async def _create_session(self) -> BrowserSession:
        """创建新的浏览器会话"""
        session_id = str(uuid.uuid4())[:8]
        logger.info(f"创建新会话: {session_id}")
        
        if self._use_persistent and self._persistent_context:
            context = self._persistent_context
            page = await context.new_page()
        else:
            context = await self._create_context()
            page = await context.new_page()
        
        await page.set_extra_http_headers({
            "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7"
        })
        
        session = BrowserSession(
            session_id=session_id,
            context=context,
            page=page
        )
        
        self._sessions[session_id] = session
        return session
    
    async def _close_session(self, session: BrowserSession):
        """关闭会话"""
        logger.info(f"关闭会话: {session.session_id}")
        try:
            await session.page.close()
            if not self._use_persistent:
                await session.context.close()
        except Exception as e:
            logger.warning(f"关闭会话时出错: {e}")
        finally:
            self._sessions.pop(session.session_id, None)
    
    @asynccontextmanager
    async def acquire_session(self):
        """获取一个可用的会话"""
        session = None
        
        async with self._session_lock:
            for s in self._sessions.values():
                if not s.is_busy:
                    session = s
                    session.is_busy = True
                    logger.debug(f"复用现有会话: {session.session_id}")
                    break
            
            if session is None:
                if len(self._sessions) < self.settings.max_sessions:
                    session = await self._create_session()
                    session.is_busy = True
                else:
                    logger.warning("所有会话都在使用中，等待...")
        
        if session is None:
            retry_count = 0
            while session is None and retry_count < 30:
                await asyncio.sleep(1)
                retry_count += 1
                async with self._session_lock:
                    for s in self._sessions.values():
                        if not s.is_busy:
                            session = s
                            session.is_busy = True
                            break
            
            if session is None:
                raise TimeoutError("无法获取可用的浏览器会话")
        
        try:
            session.mark_used()
            yield session
        finally:
            session.is_busy = False
    
    async def manual_login(self, target_url: str = None):
        """
        手动登录流程
        
        会打开一个可见的浏览器窗口，用户手动完成登录后，
        登录状态会自动保存在独立的浏览器数据目录中
        """
        if target_url is None:
            target_url = self.settings.ai_tool_url
        
        logger.info("开始手动登录流程...")
        
        browser_data_dir = self._get_browser_data_dir()
        browser_data_dir.mkdir(parents=True, exist_ok=True)
        
        playwright = await async_playwright().start()
        
        try:
            print("\n" + "=" * 60)
            print("    企业环境登录向导")
            print("=" * 60)
            print()
            print("即将打开浏览器，请完成以下操作：")
            print()
            print("  1. 在浏览器中完成登录（包括企业SSO认证）")
            print("  2. 确认可以正常访问AI工具页面")
            print("  3. 回到此窗口按 Enter 键保存登录状态")
            print()
            print(f"目标URL: {target_url}")
            print(f"数据目录: {browser_data_dir}")
            print("=" * 60)
            print()
            input("按 Enter 键打开浏览器...")
            
            # 使用持久化上下文，登录状态会自动保存
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(browser_data_dir),
                headless=False,  # 必须可见才能手动登录
                slow_mo=100,
                viewport={"width": 1920, "height": 1080},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
                ignore_default_args=["--enable-automation"],
            )
            
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(target_url)
            
            print("\n" + "=" * 60)
            print("浏览器已打开！")
            print()
            print("请在浏览器中完成登录操作...")
            print("登录成功后，请回到此窗口")
            print("=" * 60)
            
            input("\n登录完成后，按 Enter 键保存状态并关闭浏览器...")
            
            # 关闭上下文会自动保存状态到 browser_data_dir
            await context.close()
            await playwright.stop()
            
            print("\n" + "=" * 60)
            print("✓ 登录状态已保存！")
            print()
            print(f"数据保存位置: {browser_data_dir}")
            print()
            print("现在可以启动API服务了：")
            print("  uvicorn app.main:app --host 0.0.0.0 --port 8000")
            print("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"登录失败: {e}")
            await playwright.stop()
            return False
    
    async def check_login_status(self, target_url: str = None) -> bool:
        """检查当前登录状态"""
        if target_url is None:
            target_url = self.settings.ai_tool_url
        
        browser_data_dir = self._get_browser_data_dir()
        
        if not browser_data_dir.exists():
            logger.warning("浏览器数据目录不存在，需要先登录")
            return False
        
        # 检查是否有登录数据
        cookies_file = browser_data_dir / "Default" / "Cookies"
        local_storage = browser_data_dir / "Default" / "Local Storage"
        
        has_data = cookies_file.exists() or local_storage.exists()
        
        if has_data:
            logger.info("检测到已保存的登录数据")
            return True
        else:
            logger.warning("未检测到登录数据，需要先登录")
            return False
    
    def get_session_info(self) -> List[dict]:
        """获取所有会话信息"""
        return [
            {
                "session_id": s.session_id,
                "created_at": s.created_at.isoformat(),
                "last_used": s.last_used.isoformat(),
                "is_busy": s.is_busy,
                "message_count": s.message_count
            }
            for s in self._sessions.values()
        ]
    
    @property
    def session_count(self) -> int:
        return len(self._sessions)
    
    @property
    def available_session_count(self) -> int:
        return sum(1 for s in self._sessions.values() if not s.is_busy)


# 全局实例
browser_manager = BrowserManager()


async def get_browser_manager() -> BrowserManager:
    """获取浏览器管理器实例"""
    if not browser_manager._started:
        await browser_manager.start()
    return browser_manager


# CLI支持
if __name__ == "__main__":
    import sys
    
    async def main():
        manager = BrowserManager()
        
        if len(sys.argv) < 2:
            print_help()
            return
        
        cmd = sys.argv[1]
        
        if cmd == "--login":
            url = sys.argv[2] if len(sys.argv) > 2 else None
            await manager.manual_login(url)
            
        elif cmd == "--check":
            has_login = await manager.check_login_status()
            if has_login:
                print("✓ 已检测到登录状态")
            else:
                print("✗ 未检测到登录状态，请先运行 --login")
                
        elif cmd == "--test":
            print("测试浏览器启动...")
            await manager.start()
            
            async with manager.acquire_session() as session:
                url = sys.argv[2] if len(sys.argv) > 2 else "https://www.google.com"
                print(f"导航到: {url}")
                await session.page.goto(url)
                print("页面标题:", await session.page.title())
                
                if manager.settings.browser_headless:
                    print("（无头模式，3秒后关闭）")
                    await asyncio.sleep(3)
                else:
                    input("按 Enter 关闭...")
            
            await manager.stop()
            
        elif cmd == "--clean":
            browser_data_dir = manager._get_browser_data_dir()
            if browser_data_dir.exists():
                import shutil
                shutil.rmtree(browser_data_dir)
                print(f"已清理浏览器数据: {browser_data_dir}")
            else:
                print("浏览器数据目录不存在")
                
        else:
            print(f"未知命令: {cmd}")
            print_help()
    
    def print_help():
        print("""
企业环境浏览器管理器

用法:
  python -m app.browser_manager <命令>

命令:
  --login [url]   手动登录并保存状态（首次使用必须执行）
  --check         检查登录状态
  --test [url]    测试浏览器启动
  --clean         清理浏览器数据（需要重新登录）

示例:
  python -m app.browser_manager --login
  python -m app.browser_manager --login https://taa.xxx.co.jp
  python -m app.browser_manager --check
  python -m app.browser_manager --test
""")
    
    asyncio.run(main())
