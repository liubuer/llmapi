"""
从Edge浏览器导入登录状态
支持三种方式：
1. 直接使用Edge的用户数据目录（推荐）
2. 从Edge导出cookies并导入
3. 连接到已打开的Edge浏览器
"""
import asyncio
import json
import shutil
import sqlite3
import os
from pathlib import Path
from typing import Optional, List, Dict
import platform

from playwright.async_api import async_playwright, Browser, BrowserContext
from loguru import logger


def get_edge_user_data_path() -> Path:
    """获取Edge浏览器的用户数据目录路径"""
    system = platform.system()
    
    if system == "Windows":
        # Windows路径
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        return Path(local_app_data) / "Microsoft" / "Edge" / "User Data"
    elif system == "Darwin":
        # macOS路径
        return Path.home() / "Library" / "Application Support" / "Microsoft Edge"
    else:
        # Linux路径
        return Path.home() / ".config" / "microsoft-edge"


def get_chrome_user_data_path() -> Path:
    """获取Chrome浏览器的用户数据目录路径（备选）"""
    system = platform.system()
    
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        return Path(local_app_data) / "Google" / "Chrome" / "User Data"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    else:
        return Path.home() / ".config" / "google-chrome"


class EdgeSessionImporter:
    """Edge浏览器会话导入器"""
    
    def __init__(self, auth_state_path: Path = Path("./auth_state")):
        self.auth_state_path = auth_state_path
        self.auth_state_path.mkdir(parents=True, exist_ok=True)
    
    async def method1_use_edge_profile(
        self, 
        profile: str = "Default",
        target_url: str = "https://taa.xxx.co.jp"
    ) -> bool:
        """
        方法1：直接使用Edge的用户配置文件（推荐）
        
        这种方式会启动一个使用Edge用户数据的Chromium实例，
        自动继承Edge中的所有登录状态。
        
        Args:
            profile: Edge配置文件名，默认"Default"，如果有多个配置可能是"Profile 1"等
            target_url: 目标AI工具URL
        
        Returns:
            是否成功
        """
        edge_path = get_edge_user_data_path()
        
        if not edge_path.exists():
            logger.error(f"Edge用户数据目录不存在: {edge_path}")
            return False
        
        profile_path = edge_path / profile
        if not profile_path.exists():
            logger.error(f"Edge配置文件不存在: {profile_path}")
            logger.info("可用的配置文件:")
            for item in edge_path.iterdir():
                if item.is_dir() and (item.name.startswith("Profile") or item.name == "Default"):
                    logger.info(f"  - {item.name}")
            return False
        
        logger.info(f"使用Edge配置文件: {profile_path}")
        
        playwright = await async_playwright().start()
        
        try:
            # 重要：需要先关闭Edge浏览器，否则无法访问用户数据
            print("\n" + "=" * 60)
            print("⚠️  重要：请先关闭所有Edge浏览器窗口！")
            print("=" * 60)
            input("关闭后按 Enter 继续...")
            
            # 使用Edge的用户数据目录启动
            # 注意：使用 channel="msedge" 可以直接使用系统安装的Edge
            browser = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(edge_path),
                channel="msedge",  # 使用系统Edge
                headless=False,
                args=[f"--profile-directory={profile}"]
            )
            
            # 打开目标页面
            page = browser.pages[0] if browser.pages else await browser.new_page()
            await page.goto(target_url, wait_until="networkidle")
            await asyncio.sleep(3)
            
            # 检查是否已登录
            print("\n" + "=" * 60)
            print("请确认页面是否已经登录成功")
            print("如果已登录，可以看到AI工具的主界面")
            print("=" * 60)
            
            confirmed = input("是否已成功登录？(y/n): ").lower().strip()
            
            if confirmed == 'y':
                # 保存状态
                state_file = self.auth_state_path / "state.json"
                await browser.storage_state(path=str(state_file))
                logger.info(f"✓ 登录状态已保存到: {state_file}")
                await browser.close()
                await playwright.stop()
                return True
            else:
                logger.warning("登录确认失败")
                await browser.close()
                await playwright.stop()
                return False
                
        except Exception as e:
            logger.error(f"导入失败: {e}")
            await playwright.stop()
            return False
    
    async def method2_copy_cookies(
        self,
        profile: str = "Default", 
        target_domain: str = "xxx.co.jp"
    ) -> bool:
        """
        方法2：从Edge复制cookies
        
        读取Edge的cookies数据库，提取目标域名的cookies，
        然后在Playwright中设置这些cookies。
        
        Args:
            profile: Edge配置文件名
            target_domain: 目标域名
            
        Returns:
            是否成功
        """
        edge_path = get_edge_user_data_path()
        cookies_path = edge_path / profile / "Network" / "Cookies"
        
        if not cookies_path.exists():
            # 旧版本Edge的cookies位置
            cookies_path = edge_path / profile / "Cookies"
        
        if not cookies_path.exists():
            logger.error(f"找不到Edge cookies文件: {cookies_path}")
            return False
        
        print("\n" + "=" * 60)
        print("⚠️  重要：请先关闭所有Edge浏览器窗口！")
        print("=" * 60)
        input("关闭后按 Enter 继续...")
        
        try:
            # 复制cookies数据库（因为Edge运行时会锁定文件）
            temp_cookies = self.auth_state_path / "temp_cookies.db"
            shutil.copy2(cookies_path, temp_cookies)
            
            # 读取cookies
            cookies = self._read_cookies_from_db(temp_cookies, target_domain)
            
            # 清理临时文件
            temp_cookies.unlink()
            
            if not cookies:
                logger.warning(f"未找到域名 {target_domain} 的cookies")
                return False
            
            logger.info(f"找到 {len(cookies)} 个相关cookies")
            
            # 使用Playwright设置cookies
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context()
            
            # 设置cookies
            await context.add_cookies(cookies)
            
            # 验证
            page = await context.new_page()
            await page.goto(f"https://{target_domain}", wait_until="networkidle")
            await asyncio.sleep(3)
            
            print("\n请确认是否已登录...")
            confirmed = input("是否已成功登录？(y/n): ").lower().strip()
            
            if confirmed == 'y':
                state_file = self.auth_state_path / "state.json"
                await context.storage_state(path=str(state_file))
                logger.info(f"✓ 登录状态已保存到: {state_file}")
                await browser.close()
                await playwright.stop()
                return True
            else:
                await browser.close()
                await playwright.stop()
                return False
                
        except Exception as e:
            logger.error(f"复制cookies失败: {e}")
            return False
    
    def _read_cookies_from_db(self, db_path: Path, domain: str) -> List[Dict]:
        """从SQLite数据库读取cookies"""
        cookies = []
        
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # 查询包含目标域名的cookies
            cursor.execute("""
                SELECT host_key, name, value, path, expires_utc, is_secure, is_httponly
                FROM cookies 
                WHERE host_key LIKE ?
            """, (f"%{domain}%",))
            
            for row in cursor.fetchall():
                host, name, value, path, expires, secure, httponly = row
                
                # Chromium的时间戳需要转换
                # Chromium使用的是从1601年1月1日开始的微秒数
                if expires:
                    # 转换为Unix时间戳
                    expires = (expires - 11644473600000000) / 1000000
                
                cookie = {
                    "name": name,
                    "value": value,
                    "domain": host,
                    "path": path or "/",
                    "secure": bool(secure),
                    "httpOnly": bool(httponly),
                }
                
                if expires and expires > 0:
                    cookie["expires"] = expires
                
                cookies.append(cookie)
            
            conn.close()
            
        except Exception as e:
            logger.error(f"读取cookies数据库失败: {e}")
        
        return cookies
    
    async def method3_connect_to_existing(
        self,
        target_url: str = "https://taa.xxx.co.jp",
        debug_port: int = 9222
    ) -> bool:
        """
        方法3：连接到已运行的Edge浏览器
        
        需要先以调试模式启动Edge：
        msedge.exe --remote-debugging-port=9222
        
        Args:
            target_url: 目标URL
            debug_port: 调试端口
            
        Returns:
            是否成功
        """
        print("\n" + "=" * 60)
        print("请按以下步骤操作：")
        print()
        print("1. 关闭所有Edge窗口")
        print()
        print("2. 以调试模式启动Edge（在命令行运行）：")
        print()
        if platform.system() == "Windows":
            print('   "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" --remote-debugging-port=9222')
        else:
            print(f'   msedge --remote-debugging-port={debug_port}')
        print()
        print("3. 在打开的Edge中登录AI工具")
        print()
        print("4. 登录成功后，回到这里按Enter")
        print("=" * 60)
        input("\n准备好后按 Enter 继续...")
        
        playwright = await async_playwright().start()
        
        try:
            # 连接到已运行的浏览器
            browser = await playwright.chromium.connect_over_cdp(f"http://localhost:{debug_port}")
            
            # 获取已有的上下文
            contexts = browser.contexts
            if not contexts:
                logger.error("没有找到浏览器上下文")
                return False
            
            context = contexts[0]
            
            # 查找目标页面
            target_page = None
            for page in context.pages:
                if target_url in page.url:
                    target_page = page
                    break
            
            if not target_page:
                logger.warning("未找到目标页面，创建新页面...")
                target_page = await context.new_page()
                await target_page.goto(target_url, wait_until="networkidle")
            
            # 保存状态
            state_file = self.auth_state_path / "state.json"
            await context.storage_state(path=str(state_file))
            
            logger.info(f"✓ 登录状态已保存到: {state_file}")
            
            # 注意：不要关闭通过CDP连接的浏览器
            await playwright.stop()
            return True
            
        except Exception as e:
            logger.error(f"连接失败: {e}")
            logger.info("请确保Edge以调试模式运行，且端口正确")
            await playwright.stop()
            return False


async def interactive_import():
    """交互式导入向导"""
    print("\n" + "=" * 60)
    print("    Edge浏览器登录状态导入工具")
    print("=" * 60)
    print()
    print("请选择导入方式：")
    print()
    print("  1. 使用Edge用户配置文件（推荐，最简单）")
    print("     - 直接复用Edge中的登录状态")
    print("     - 需要先关闭Edge浏览器")
    print()
    print("  2. 复制Edge的Cookies")
    print("     - 从Edge数据库提取cookies")
    print("     - 需要先关闭Edge浏览器")
    print()
    print("  3. 连接到调试模式的Edge")
    print("     - 适合Edge无法关闭的情况")
    print("     - 需要以调试模式重启Edge")
    print()
    print("  4. 手动登录（原始方式）")
    print("     - 打开新浏览器手动登录")
    print()
    
    choice = input("请选择 (1/2/3/4): ").strip()
    
    importer = EdgeSessionImporter()
    
    # 获取配置
    target_url = input("AI工具URL (默认 https://taa.xxx.co.jp): ").strip()
    if not target_url:
        target_url = "https://taa.xxx.co.jp"
    
    if choice == "1":
        profile = input("Edge配置文件名 (默认 Default): ").strip() or "Default"
        success = await importer.method1_use_edge_profile(profile, target_url)
    elif choice == "2":
        profile = input("Edge配置文件名 (默认 Default): ").strip() or "Default"
        # 从URL提取域名
        from urllib.parse import urlparse
        domain = urlparse(target_url).netloc
        success = await importer.method2_copy_cookies(profile, domain)
    elif choice == "3":
        success = await importer.method3_connect_to_existing(target_url)
    elif choice == "4":
        # 调用原来的手动登录
        from app.browser_manager import BrowserManager
        manager = BrowserManager()
        await manager.manual_login()
        return
    else:
        print("无效选择")
        return
    
    if success:
        print("\n" + "=" * 60)
        print("✓ 登录状态导入成功！")
        print("现在可以启动API服务了：")
        print("  uvicorn app.main:app --host 0.0.0.0 --port 8000")
        print("=" * 60)
    else:
        print("\n导入失败，请尝试其他方式或手动登录")


# CLI入口
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--check":
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
        else:
            print("用法:")
            print("  python import_edge_session.py         # 交互式导入")
            print("  python import_edge_session.py --check # 检查Edge路径")
    else:
        asyncio.run(interactive_import())
