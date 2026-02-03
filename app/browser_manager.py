"""
Playwright 浏览器管理器
负责管理浏览器实例、会话池和认证状态
支持复用Edge浏览器的登录状态
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


def get_edge_user_data_path() -> Path:
    """获取Edge浏览器的用户数据目录路径"""
    system = platform.system()
    
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        return Path(local_app_data) / "Microsoft" / "Edge" / "User Data"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Microsoft Edge"
    else:
        return Path.home() / ".config" / "microsoft-edge"


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
        """标记会话被使用"""
        self.last_used = datetime.now()
        self.message_count += 1


class BrowserManager:
    """浏览器管理器 - 单例模式"""
    
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
        self._persistent_context: Optional[BrowserContext] = None  # 用于Edge配置文件模式
        self._sessions: Dict[str, BrowserSession] = {}
        self._session_lock = asyncio.Lock()
        self._initialized = True
        self._started = False
        self._use_edge_profile = False  # 是否使用Edge配置文件
        
    async def start(self, use_edge_profile: bool = False, edge_profile: str = "Default"):
        """
        启动浏览器管理器
        
        Args:
            use_edge_profile: 是否直接使用Edge的用户配置文件
            edge_profile: Edge配置文件名，默认"Default"
        """
        if self._started:
            return
            
        async with self._lock:
            if self._started:
                return
                
            logger.info("正在启动浏览器管理器...")
            
            # 确保认证状态目录存在
            self.settings.auth_state_path.mkdir(parents=True, exist_ok=True)
            
            # 启动Playwright
            self._playwright = await async_playwright().start()
            
            # 检查是否应该使用Edge配置文件
            # 优先使用环境变量配置
            use_edge_profile = use_edge_profile or os.environ.get("USE_EDGE_PROFILE", "").lower() == "true"
            edge_profile = os.environ.get("EDGE_PROFILE", edge_profile)
            
            if use_edge_profile:
                await self._start_with_edge_profile(edge_profile)
            else:
                await self._start_normal()
            
            self._started = True
            logger.info("浏览器管理器启动完成")
    
    async def _start_normal(self):
        """普通模式启动（使用保存的认证状态）"""
        self._use_edge_profile = False
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.browser_headless,
            slow_mo=self.settings.browser_slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ]
        )
        logger.info("使用普通模式启动")
    
    async def _start_with_edge_profile(self, profile: str = "Default"):
        """
        使用Edge配置文件启动（直接复用Edge登录状态）
        
        注意：此模式下需要先关闭Edge浏览器
        """
        edge_path = get_edge_user_data_path()
        
        if not edge_path.exists():
            logger.warning(f"Edge用户数据目录不存在: {edge_path}")
            logger.info("回退到普通模式")
            await self._start_normal()
            return
        
        profile_path = edge_path / profile
        if not profile_path.exists():
            logger.warning(f"Edge配置文件不存在: {profile_path}")
            logger.info("回退到普通模式")
            await self._start_normal()
            return
        
        try:
            logger.info(f"使用Edge配置文件: {profile}")
            self._use_edge_profile = True
            
            # 使用持久化上下文，这样可以共享Edge的登录状态
            self._persistent_context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(edge_path),
                channel="msedge",  # 使用系统安装的Edge
                headless=self.settings.browser_headless,
                slow_mo=self.settings.browser_slow_mo,
                args=[
                    f"--profile-directory={profile}",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            logger.info("成功使用Edge配置文件启动")
            
        except Exception as e:
            logger.error(f"使用Edge配置文件启动失败: {e}")
            logger.info("回退到普通模式")
            self._use_edge_profile = False
            await self._start_normal()
            
    async def stop(self):
        """停止浏览器管理器"""
        if not self._started:
            return
            
        async with self._lock:
            logger.info("正在停止浏览器管理器...")
            
            # 关闭所有会话
            for session in list(self._sessions.values()):
                await self._close_session(session)
            
            # 关闭浏览器（根据模式不同处理）
            if self._use_edge_profile:
                if self._persistent_context:
                    await self._persistent_context.close()
                    self._persistent_context = None
            else:
                if self._browser:
                    await self._browser.close()
                    self._browser = None
                
            # 关闭Playwright
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
                
            self._started = False
            logger.info("浏览器管理器已停止")
    
    def _get_auth_state_file(self) -> Path:
        """获取认证状态文件路径"""
        return self.settings.auth_state_path / "state.json"
    
    async def _create_context(self) -> BrowserContext:
        """创建浏览器上下文"""
        # 如果使用Edge配置文件模式，返回持久化上下文
        if self._use_edge_profile and self._persistent_context:
            return self._persistent_context
        
        auth_file = self._get_auth_state_file()
        
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "locale": "ja-JP",
            "timezone_id": "Asia/Tokyo",
        }
        
        # 如果存在认证状态，加载它
        if auth_file.exists():
            logger.info("加载已保存的认证状态")
            context_options["storage_state"] = str(auth_file)
        
        return await self._browser.new_context(**context_options)
    
    async def _create_session(self) -> BrowserSession:
        """创建新的浏览器会话"""
        session_id = str(uuid.uuid4())[:8]
        logger.info(f"创建新会话: {session_id}")
        
        if self._use_edge_profile and self._persistent_context:
            # Edge配置文件模式：在持久化上下文中创建新页面
            context = self._persistent_context
            page = await context.new_page()
        else:
            # 普通模式：创建新的上下文和页面
            context = await self._create_context()
            page = await context.new_page()
        
        # 设置额外的页面配置
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
            # 如果是Edge配置文件模式，不关闭上下文（因为是共享的）
            if not self._use_edge_profile:
                await session.context.close()
        except Exception as e:
            logger.warning(f"关闭会话时出错: {e}")
        finally:
            self._sessions.pop(session.session_id, None)
    
    @asynccontextmanager
    async def acquire_session(self):
        """获取一个可用的会话（上下文管理器）"""
        session = None
        
        async with self._session_lock:
            # 查找空闲会话
            for s in self._sessions.values():
                if not s.is_busy:
                    session = s
                    session.is_busy = True
                    logger.debug(f"复用现有会话: {session.session_id}")
                    break
            
            # 如果没有空闲会话且未达到上限，创建新会话
            if session is None:
                if len(self._sessions) < self.settings.max_sessions:
                    session = await self._create_session()
                    session.is_busy = True
                else:
                    # 等待会话可用
                    logger.warning("所有会话都在使用中，等待...")
        
        # 如果还是没有会话，等待重试
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
    
    async def manual_login(self):
        """手动登录流程 - 用于首次设置"""
        logger.info("开始手动登录流程...")
        
        # 使用非无头模式
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=False,
            slow_mo=100
        )
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        
        try:
            # 导航到AI工具页面
            await page.goto(self.settings.ai_tool_url)
            
            print("\n" + "="*60)
            print("请在浏览器中完成登录操作")
            print("登录完成后，请在此处按 Enter 键继续...")
            print("="*60 + "\n")
            
            # 等待用户手动登录
            input()
            
            # 保存认证状态
            auth_file = self._get_auth_state_file()
            auth_file.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(auth_file))
            
            logger.info(f"认证状态已保存到: {auth_file}")
            print(f"\n✓ 登录状态已保存！现在可以启动API服务了。\n")
            
        finally:
            await browser.close()
            await playwright.stop()
    
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
        """当前会话数"""
        return len(self._sessions)
    
    @property
    def available_session_count(self) -> int:
        """可用会话数"""
        return sum(1 for s in self._sessions.values() if not s.is_busy)


# 全局实例
browser_manager = BrowserManager()


async def get_browser_manager() -> BrowserManager:
    """获取浏览器管理器实例"""
    if not browser_manager._started:
        await browser_manager.start()
    return browser_manager


# CLI支持 - 用于手动登录
if __name__ == "__main__":
    import sys
    
    async def main():
        if len(sys.argv) > 1:
            cmd = sys.argv[1]
            
            if cmd == "--login":
                # 原始手动登录方式
                manager = BrowserManager()
                await manager.manual_login()
                
            elif cmd == "--import-edge":
                # 使用Edge配置文件导入
                print("从Edge导入登录状态...")
                print("请运行: python tools/import_edge_session.py")
                
            elif cmd == "--check-edge":
                # 检查Edge路径
                edge_path = get_edge_user_data_path()
                print(f"Edge用户数据目录: {edge_path}")
                print(f"目录存在: {edge_path.exists()}")
                
                if edge_path.exists():
                    print("\n可用的配置文件:")
                    for item in edge_path.iterdir():
                        if item.is_dir():
                            if item.name.startswith("Profile") or item.name == "Default":
                                print(f"  ✓ {item.name}")
                                
            elif cmd == "--test-edge":
                # 测试Edge配置文件模式
                profile = sys.argv[2] if len(sys.argv) > 2 else "Default"
                print(f"测试Edge配置文件模式: {profile}")
                print("⚠️  请先关闭所有Edge窗口！")
                input("按Enter继续...")
                
                manager = BrowserManager()
                await manager.start(use_edge_profile=True, edge_profile=profile)
                
                async with manager.acquire_session() as session:
                    await session.page.goto("https://taa.xxx.co.jp")
                    print("请检查浏览器是否已登录...")
                    input("按Enter关闭...")
                
                await manager.stop()
            else:
                print("未知命令")
                print("用法:")
                print("  python -m app.browser_manager --login       # 手动登录")
                print("  python -m app.browser_manager --import-edge # 从Edge导入")
                print("  python -m app.browser_manager --check-edge  # 检查Edge路径")
                print("  python -m app.browser_manager --test-edge [profile] # 测试Edge模式")
        else:
            print("用法:")
            print("  python -m app.browser_manager --login       # 手动登录并保存状态")
            print("  python -m app.browser_manager --import-edge # 从Edge导入登录状态")
            print("  python -m app.browser_manager --check-edge  # 检查Edge安装路径")
            print("  python -m app.browser_manager --test-edge   # 测试Edge配置文件模式")
    
    asyncio.run(main())
