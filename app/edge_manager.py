"""
长驻Edge进程管理器

核心策略：
1. 启动Edge并手动登录一次
2. 保持Edge进程持续运行（不关闭）
3. API通过CDP协议连接到已登录的Edge
4. 复用已认证的浏览器会话
"""
import asyncio
import subprocess
import platform
import os
import sys
from typing import Optional, Dict, List
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import uuid

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from loguru import logger

from .config import get_settings


def get_edge_path() -> str:
    """获取Edge浏览器可执行文件路径"""
    system = platform.system()
    
    if system == "Windows":
        paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        ]
    elif system == "Darwin":
        paths = ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    else:
        paths = ["/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable"]
    
    for path in paths:
        if os.path.exists(path):
            return path
    
    return "msedge"  # 尝试PATH中的命令


@dataclass
class BrowserSession:
    """浏览器会话"""
    session_id: str
    page: Page
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    is_busy: bool = False
    message_count: int = 0
    
    def mark_used(self):
        self.last_used = datetime.now()
        self.message_count += 1


class EdgeManager:
    """
    长驻Edge进程管理器
    
    使用方式：
    1. 运行 start_edge_with_debug() 启动Edge（带调试端口）
    2. 在Edge中手动登录
    3. 保持Edge运行，启动API服务
    4. API通过CDP连接到已登录的Edge
    """
    
    _instance: Optional["EdgeManager"] = None
    
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
        self._context: Optional[BrowserContext] = None
        self._sessions: Dict[str, BrowserSession] = {}
        self._session_lock = asyncio.Lock()
        self._connected = False
        self._edge_process: Optional[subprocess.Popen] = None
        self._initialized = True
    
    def start_edge_with_debug(self, headless: bool = False) -> subprocess.Popen:
        """
        启动带调试端口的Edge浏览器
        
        这个Edge进程会一直运行，直到手动关闭
        """
        edge_path = get_edge_path()
        debug_port = self.settings.edge_debug_port
        
        # 使用独立的用户数据目录（避免与正常Edge冲突）
        user_data_dir = Path("./edge_data").absolute()
        user_data_dir.mkdir(exist_ok=True)
        
        args = [
            edge_path,
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--disable-background-mode",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
        ]
        
        if headless:
            args.append("--headless=new")
        
        logger.info(f"启动Edge浏览器: {edge_path}")
        logger.info(f"调试端口: {debug_port}")
        logger.info(f"用户数据目录: {user_data_dir}")
        
        # 启动Edge进程
        if platform.system() == "Windows":
            self._edge_process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            self._edge_process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        
        return self._edge_process
    
    async def connect_to_edge(self, max_retries: int = 10) -> bool:
        """连接到已运行的Edge浏览器"""
        debug_port = self.settings.edge_debug_port
        cdp_url = f"http://127.0.0.1:{debug_port}"
        
        logger.info(f"尝试连接到Edge: {cdp_url}")
        
        for attempt in range(max_retries):
            try:
                if not self._playwright:
                    self._playwright = await async_playwright().start()
                
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    cdp_url,
                    timeout=10000
                )
                
                # 获取已有的上下文
                contexts = self._browser.contexts
                if contexts:
                    self._context = contexts[0]
                    logger.info(f"已连接到Edge，找到 {len(contexts)} 个上下文")
                else:
                    self._context = await self._browser.new_context()
                    logger.info("已连接到Edge，创建了新上下文")
                
                self._connected = True
                return True
                
            except Exception as e:
                logger.warning(f"连接尝试 {attempt + 1}/{max_retries} 失败: {e}")
                await asyncio.sleep(1)
        
        logger.error("无法连接到Edge浏览器")
        return False
    
    async def disconnect(self):
        """断开与Edge的连接（不关闭Edge）"""
        if self._browser:
            # 注意：只是断开连接，不关闭浏览器
            try:
                # 关闭我们创建的会话页面
                for session in list(self._sessions.values()):
                    try:
                        await session.page.close()
                    except:
                        pass
                self._sessions.clear()
            except:
                pass
            
            self._browser = None
            self._context = None
        
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        
        self._connected = False
        logger.info("已断开与Edge的连接")
    
    @asynccontextmanager
    async def acquire_session(self):
        """获取一个可用的浏览器会话"""
        if not self._connected:
            connected = await self.connect_to_edge()
            if not connected:
                raise RuntimeError("无法连接到Edge浏览器，请确保Edge已启动")
        
        session = None
        
        async with self._session_lock:
            # 查找空闲会话
            for s in self._sessions.values():
                if not s.is_busy:
                    session = s
                    session.is_busy = True
                    break
            
            # 创建新会话
            if session is None and len(self._sessions) < self.settings.max_sessions:
                session = await self._create_session()
                session.is_busy = True
        
        # 等待可用会话
        if session is None:
            for _ in range(30):
                await asyncio.sleep(1)
                async with self._session_lock:
                    for s in self._sessions.values():
                        if not s.is_busy:
                            session = s
                            session.is_busy = True
                            break
                if session:
                    break
        
        if session is None:
            raise TimeoutError("无法获取可用会话")
        
        try:
            session.mark_used()
            yield session
        finally:
            session.is_busy = False
    
    async def _create_session(self) -> BrowserSession:
        """创建新会话"""
        session_id = str(uuid.uuid4())[:8]
        
        # 在已有上下文中创建新页面
        page = await self._context.new_page()
        
        session = BrowserSession(
            session_id=session_id,
            page=page
        )
        self._sessions[session_id] = session
        
        logger.info(f"创建新会话: {session_id}")
        return session
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    @property
    def session_count(self) -> int:
        return len(self._sessions)


# 全局实例
edge_manager = EdgeManager()


async def get_edge_manager() -> EdgeManager:
    return edge_manager


# ========== CLI命令 ==========

async def cmd_start_edge():
    """启动Edge并等待用户登录"""
    manager = EdgeManager()
    settings = get_settings()
    
    print("\n" + "=" * 60)
    print("    长驻Edge进程启动器")
    print("=" * 60)
    print()
    print(f"即将启动Edge浏览器（调试端口: {settings.edge_debug_port}）")
    print()
    print("请完成以下步骤：")
    print("  1. 等待Edge浏览器启动")
    print("  2. 在Edge中访问AI工具并登录")
    print("  3. 登录成功后，保持Edge运行")
    print("  4. 在另一个终端启动API服务")
    print()
    print("注意：请勿关闭此终端或Edge浏览器！")
    print("=" * 60)
    print()
    
    # 启动Edge
    process = manager.start_edge_with_debug()
    
    # 等待Edge启动
    await asyncio.sleep(3)
    
    # 尝试连接
    connected = await manager.connect_to_edge()
    
    if connected:
        # 打开AI工具页面
        async with manager.acquire_session() as session:
            await session.page.goto(settings.ai_tool_url)
        
        print()
        print("✓ Edge已启动！")
        print(f"✓ 已打开: {settings.ai_tool_url}")
        print()
        print("请在Edge中完成登录...")
        print("登录后，请打开新终端运行: uvicorn app.main:app --port 8000")
        print()
        print("按 Ctrl+C 关闭Edge并退出")
        
        try:
            # 保持运行
            while True:
                await asyncio.sleep(1)
                # 检查Edge进程是否还在运行
                if process.poll() is not None:
                    print("\nEdge已关闭")
                    break
        except KeyboardInterrupt:
            print("\n正在关闭...")
    else:
        print("✗ 无法连接到Edge")
        process.terminate()


async def cmd_check_status():
    """检查Edge连接状态"""
    manager = EdgeManager()

    print("检查Edge连接状态...")

    connected = await manager.connect_to_edge(max_retries=3)

    if connected:
        print("✓ Edge已连接")
        print(f"  会话数: {manager.session_count}")

        # 尝试访问页面
        try:
            async with manager.acquire_session() as session:
                url = session.page.url
                title = await session.page.title()
                print(f"  当前URL: {url}")
                print(f"  页面标题: {title}")
        except Exception as e:
            print(f"  获取页面信息失败: {e}")

        await manager.disconnect()
    else:
        print("✗ Edge未连接")
        print()
        print("请先运行: python -m app.edge_manager start")


async def cmd_start_all():
    """一体化启动：Edge + API服务"""
    import uvicorn
    from threading import Thread

    manager = EdgeManager()
    settings = get_settings()

    print("\n" + "=" * 60)
    print("    内部AI工具API - 一体化启动")
    print("=" * 60)
    print()
    print(f"即将启动Edge浏览器（调试端口: {settings.edge_debug_port}）")
    print()

    # 启动Edge
    process = manager.start_edge_with_debug()

    # 等待Edge启动
    await asyncio.sleep(3)

    # 尝试连接
    connected = await manager.connect_to_edge()

    if not connected:
        print("✗ 无法连接到Edge")
        process.terminate()
        return

    # 打开AI工具页面
    async with manager.acquire_session() as session:
        await session.page.goto(settings.ai_tool_url)

    print()
    print("✓ Edge已启动！")
    print(f"✓ 已打开: {settings.ai_tool_url}")
    print()
    print("=" * 60)
    print("  请在Edge中完成登录")
    print("  登录完成后，按 Enter 键启动API服务...")
    print("=" * 60)
    print()

    # 等待用户按Enter
    try:
        input(">>> 按 Enter 键继续...")
    except EOFError:
        pass

    # 检查Edge是否还在运行
    if process.poll() is not None:
        print("\n✗ Edge已关闭，无法启动API服务")
        return

    # 断开当前连接（API服务会重新连接）
    await manager.disconnect()

    print()
    print("=" * 60)
    print("  正在启动API服务...")
    print(f"  API地址: http://{settings.api_host}:{settings.api_port}")
    print("  按 Ctrl+C 停止服务")
    print("=" * 60)
    print()

    # 启动API服务（阻塞）
    try:
        uvicorn.run(
            "app.main:app",
            host=settings.api_host,
            port=settings.api_port,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n正在关闭...")
    finally:
        # 关闭Edge进程
        if process.poll() is None:
            print("关闭Edge浏览器...")
            process.terminate()
            try:
                process.wait(timeout=5)
            except:
                process.kill()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("""
用法: python -m app.edge_manager <命令>

命令:
  start    启动Edge浏览器（带调试端口）
  status   检查Edge连接状态
  all      一体化启动（Edge + API服务）
""")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "start":
        asyncio.run(cmd_start_edge())
    elif cmd == "status":
        asyncio.run(cmd_check_status())
    elif cmd == "all":
        asyncio.run(cmd_start_all())
    else:
        print(f"未知命令: {cmd}")
