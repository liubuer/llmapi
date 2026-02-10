"""
常駐Edgeプロセスマネージャー

コア戦略：
1. Edgeを起動し、手動で一度ログイン
2. Edgeプロセスを常時稼働（終了しない）
3. APIがCDPプロトコルでログイン済みEdgeに接続
4. 認証済みブラウザセッションを再利用
"""
import asyncio
import subprocess
import platform
import os
import sys
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import uuid

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from loguru import logger

from .config import get_settings


def get_edge_path() -> str:
    """Edgeブラウザの実行ファイルパスを取得"""
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

    return "msedge"  # PATH内のコマンドを試行


@dataclass
class BrowserSession:
    """ブラウザセッション"""
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
    常駐Edgeプロセスマネージャー

    使用方法：
    1. start_edge_with_debug() でEdgeを起動（デバッグポート付き）
    2. Edgeで手動ログイン
    3. Edgeを稼働したまま、APIサービスを起動
    4. APIがCDPでログイン済みEdgeに接続
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
        # conversation tracking: conversation_id -> session_id
        self._conversations: Dict[str, str] = {}
        # conversation last activity: conversation_id -> datetime
        self._conversation_timeouts: Dict[str, datetime] = {}
        self._conversation_timeout_seconds = 1800  # 30 minutes
        self._initialized = True

    def start_edge_with_debug(self, headless: bool = False) -> subprocess.Popen:
        """
        デバッグポート付きEdgeブラウザを起動

        このEdgeプロセスは手動で閉じるまで稼働し続けます
        """
        edge_path = get_edge_path()
        debug_port = self.settings.edge_debug_port

        # 独立したユーザーデータディレクトリを使用（通常のEdgeとの競合を回避）
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

        logger.info(f"Edgeブラウザを起動: {edge_path}")
        logger.info(f"デバッグポート: {debug_port}")
        logger.info(f"ユーザーデータディレクトリ: {user_data_dir}")

        # Edgeプロセスを起動
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
        """稼働中のEdgeブラウザに接続"""
        debug_port = self.settings.edge_debug_port
        cdp_url = f"http://127.0.0.1:{debug_port}"

        logger.info(f"Edgeへの接続を試行: {cdp_url}")

        for attempt in range(max_retries):
            try:
                if not self._playwright:
                    self._playwright = await async_playwright().start()

                self._browser = await self._playwright.chromium.connect_over_cdp(
                    cdp_url,
                    timeout=10000
                )

                # 既存のコンテキストを取得
                contexts = self._browser.contexts
                if contexts:
                    self._context = contexts[0]
                    logger.info(f"Edgeに接続完了、{len(contexts)} 個のコンテキストを発見")
                else:
                    self._context = await self._browser.new_context()
                    logger.info("Edgeに接続完了、新しいコンテキストを作成")

                self._connected = True
                return True

            except Exception as e:
                logger.warning(f"接続試行 {attempt + 1}/{max_retries} 失敗: {e}")
                await asyncio.sleep(1)

        logger.error("Edgeブラウザに接続できません")
        return False

    async def disconnect(self):
        """Edgeとの接続を切断（Edgeは終了しない）"""
        if self._browser:
            # 注意：接続を切断するだけで、ブラウザは閉じない
            try:
                # 作成したセッションページを閉じる
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
        logger.info("Edgeとの接続を切断しました")

    @asynccontextmanager
    async def acquire_session(self):
        """利用可能なブラウザセッションを取得"""
        if not self._connected:
            connected = await self.connect_to_edge()
            if not connected:
                raise RuntimeError("Edgeブラウザに接続できません。Edgeが起動していることを確認してください")

        session = None

        async with self._session_lock:
            # 空きセッションを検索
            for s in self._sessions.values():
                if not s.is_busy:
                    session = s
                    session.is_busy = True
                    break

            # 新しいセッションを作成
            if session is None and len(self._sessions) < self.settings.max_sessions:
                session = await self._create_session()
                session.is_busy = True

        # 利用可能なセッションを待機
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
            raise TimeoutError("利用可能なセッションを取得できません")

        try:
            session.mark_used()
            yield session
        finally:
            session.is_busy = False

    @asynccontextmanager
    async def acquire_conversation_session(
        self,
        conversation_id: Optional[str] = None,
        new_conversation: bool = False
    ):
        """
        会話IDに紐づくブラウザセッションを取得

        - new_conversation=True: 空きセッションを取得し、新しいconversation_idを生成して紐づけ
        - conversation_id指定: 紐づけられたセッションを返却（ビジーの場合は待機）
        - いずれもなし: 空きセッションを取得し、conversation_idを生成（後方互換）
        """
        # 期限切れセッションをクリーンアップ
        await self._cleanup_expired_conversations()

        if not self._connected:
            connected = await self.connect_to_edge()
            if not connected:
                raise RuntimeError("Edgeブラウザに接続できません。Edgeが起動していることを確認してください")

        session = None
        conv_id = conversation_id

        if new_conversation:
            # 新規セッションを強制
            conv_id = f"conv-{uuid.uuid4().hex[:12]}"
            session = await self._acquire_any_idle_session()
            async with self._session_lock:
                self._conversations[conv_id] = session.session_id
                self._conversation_timeouts[conv_id] = datetime.now()
            logger.info(f"新規セッション: {conv_id} -> session {session.session_id}")

        elif conv_id and conv_id in self._conversations:
            # 既存セッションを継続
            target_session_id = self._conversations[conv_id]
            session = await self._acquire_specific_session(target_session_id)
            async with self._session_lock:
                self._conversation_timeouts[conv_id] = datetime.now()
            logger.info(f"セッション継続: {conv_id} -> session {target_session_id}")

        else:
            # conversation_id未指定または無効、空きセッションを取得
            conv_id = f"conv-{uuid.uuid4().hex[:12]}"
            session = await self._acquire_any_idle_session()
            async with self._session_lock:
                self._conversations[conv_id] = session.session_id
                self._conversation_timeouts[conv_id] = datetime.now()
            logger.info(f"セッション割り当て: {conv_id} -> session {session.session_id}")

        try:
            session.mark_used()
            yield session, conv_id
        finally:
            session.is_busy = False

    async def _acquire_any_idle_session(self) -> BrowserSession:
        """任意の空きセッションを取得"""
        session = None
        async with self._session_lock:
            for s in self._sessions.values():
                if not s.is_busy:
                    session = s
                    session.is_busy = True
                    break
            if session is None and len(self._sessions) < self.settings.max_sessions:
                session = await self._create_session()
                session.is_busy = True

        if session is None:
            # 利用可能なセッションを待機
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
            raise TimeoutError("利用可能なセッションを取得できません")
        return session

    async def _acquire_specific_session(self, session_id: str) -> BrowserSession:
        """指定IDのセッションを取得（ビジーの場合は待機）"""
        for _ in range(30):
            async with self._session_lock:
                session = self._sessions.get(session_id)
                if session and not session.is_busy:
                    session.is_busy = True
                    return session
            await asyncio.sleep(1)

        raise TimeoutError(f"セッション {session_id} のタイムアウト待機")

    async def _cleanup_expired_conversations(self):
        """期限切れの会話バインディングをクリーンアップ"""
        now = datetime.now()
        expired = []
        async with self._session_lock:
            for conv_id, last_active in self._conversation_timeouts.items():
                if (now - last_active).total_seconds() > self._conversation_timeout_seconds:
                    expired.append(conv_id)
            for conv_id in expired:
                self._conversations.pop(conv_id, None)
                self._conversation_timeouts.pop(conv_id, None)
                logger.info(f"セッションタイムアウトクリーンアップ: {conv_id}")

    def list_conversations(self) -> List[Dict]:
        """アクティブな会話を一覧表示"""
        result = []
        for conv_id, session_id in self._conversations.items():
            last_active = self._conversation_timeouts.get(conv_id)
            result.append({
                "conversation_id": conv_id,
                "session_id": session_id,
                "last_active": last_active.isoformat() if last_active else None,
            })
        return result

    def remove_conversation(self, conversation_id: str) -> bool:
        """会話バインディングを削除"""
        if conversation_id in self._conversations:
            self._conversations.pop(conversation_id, None)
            self._conversation_timeouts.pop(conversation_id, None)
            logger.info(f"会話を削除: {conversation_id}")
            return True
        return False

    async def _create_session(self) -> BrowserSession:
        """新しいセッションを作成"""
        session_id = str(uuid.uuid4())[:8]

        # 既存のコンテキストに新しいページを作成
        page = await self._context.new_page()

        session = BrowserSession(
            session_id=session_id,
            page=page
        )
        self._sessions[session_id] = session

        logger.info(f"新しいセッションを作成: {session_id}")
        return session

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def session_count(self) -> int:
        return len(self._sessions)


# グローバルインスタンス
edge_manager = EdgeManager()


async def get_edge_manager() -> EdgeManager:
    return edge_manager


# ========== CLIコマンド ==========

async def cmd_start_edge():
    """Edgeを起動し、ユーザーのログインを待機"""
    manager = EdgeManager()
    settings = get_settings()

    print("\n" + "=" * 60)
    print("    常駐Edgeプロセス起動ツール")
    print("=" * 60)
    print()
    print(f"Edgeブラウザを起動します（デバッグポート: {settings.edge_debug_port}）")
    print()
    print("以下の手順を実行してください：")
    print("  1. Edgeブラウザの起動を待機")
    print("  2. EdgeでAIツールにアクセスしてログイン")
    print("  3. ログイン成功後、Edgeを稼働させたまま維持")
    print("  4. 別のターミナルでAPIサービスを起動")
    print()
    print("注意：このターミナルとEdgeブラウザを閉じないでください！")
    print("=" * 60)
    print()

    # Edgeを起動
    process = manager.start_edge_with_debug()

    # Edgeの起動を待機
    await asyncio.sleep(3)

    # 接続を試行
    connected = await manager.connect_to_edge()

    if connected:
        # AIツールページを開く
        async with manager.acquire_session() as session:
            await session.page.goto(settings.ai_tool_url)

        print()
        print("✓ Edgeが起動しました！")
        print(f"✓ 開きました: {settings.ai_tool_url}")
        print()
        print("Edgeでログインを完了してください...")
        print("ログイン後、新しいターミナルで実行: uvicorn app.main:app --port 8000")
        print()
        print("Ctrl+C でEdgeを閉じて終了")

        try:
            # 稼働を維持
            while True:
                await asyncio.sleep(1)
                # Edgeプロセスがまだ稼働中か確認
                if process.poll() is not None:
                    print("\nEdgeが閉じられました")
                    break
        except KeyboardInterrupt:
            print("\n終了中...")
    else:
        print("✗ Edgeに接続できません")
        process.terminate()


async def cmd_check_status():
    """Edge接続状態を確認"""
    manager = EdgeManager()

    print("Edge接続状態を確認中...")

    connected = await manager.connect_to_edge(max_retries=3)

    if connected:
        print("✓ Edge接続済み")
        print(f"  セッション数: {manager.session_count}")

        # ページへのアクセスを試行
        try:
            async with manager.acquire_session() as session:
                url = session.page.url
                title = await session.page.title()
                print(f"  現在のURL: {url}")
                print(f"  ページタイトル: {title}")
        except Exception as e:
            print(f"  ページ情報取得失敗: {e}")

        await manager.disconnect()
    else:
        print("✗ Edge未接続")
        print()
        print("先に実行してください: python -m app.edge_manager start")


def cmd_start_all_sync():
    """一括起動：Edge + APIサービス（同期版）"""
    import uvicorn
    import time

    settings = get_settings()

    print("\n" + "=" * 60)
    print("    社内AIツールAPI - 一括起動")
    print("=" * 60)
    print()
    print(f"Edgeブラウザを起動します（デバッグポート: {settings.edge_debug_port}）")
    print()

    # Edgeを起動（シングルトンを使用せず、イベントループの競合を回避）
    manager = EdgeManager()
    process = manager.start_edge_with_debug()

    # Edgeの起動を待機
    print("Edgeの起動を待機中...")
    time.sleep(3)

    # Edgeプロセスが稼働しているか確認
    if process.poll() is not None:
        print("✗ Edgeの起動に失敗しました")
        return

    # 簡易HTTPリクエストでCDPポートの準備を確認
    import urllib.request
    cdp_url = f"http://127.0.0.1:{settings.edge_debug_port}/json/version"
    for i in range(10):
        try:
            urllib.request.urlopen(cdp_url, timeout=2)
            print("✓ Edge CDPポート準備完了")
            break
        except:
            time.sleep(1)
    else:
        print("✗ Edge CDPポートに接続できません")
        process.terminate()
        return

    print()
    print("✓ Edgeが起動しました！")
    print(f"  Edgeで以下にアクセスしてください: {settings.ai_tool_url}")
    print()
    print("=" * 60)
    print("  Edgeでログインを完了してください")
    print("  ログイン完了後、Enterキーを押してAPIサービスを起動...")
    print("=" * 60)
    print()

    # ユーザーのEnterキーを待機
    try:
        input(">>> Enterキーを押して続行...")
    except EOFError:
        pass

    # Edgeがまだ稼働しているか確認
    if process.poll() is not None:
        print("\n✗ Edgeが閉じられました。APIサービスを起動できません")
        return

    # シングルトン状態をリセット、APIサービスの再初期化を許可
    EdgeManager._instance = None

    print()
    print("=" * 60)
    print("  APIサービスを起動中...")
    print(f"  APIアドレス: http://{settings.api_host}:{settings.api_port}")
    print("  Ctrl+C でサービスを停止")
    print("=" * 60)
    print()

    # APIサービスを起動（ブロッキング）
    try:
        uvicorn.run(
            "app.main:app",
            host=settings.api_host,
            port=settings.api_port,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n終了中...")
    finally:
        # Edgeプロセスを終了
        if process.poll() is None:
            print("Edgeブラウザを終了中...")
            process.terminate()
            try:
                process.wait(timeout=5)
            except:
                process.kill()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("""
使用方法: python -m app.edge_manager <コマンド>

コマンド:
  start    Edgeブラウザを起動（デバッグポート付き）
  status   Edge接続状態を確認
  all      一括起動（Edge + APIサービス）
""")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "start":
        asyncio.run(cmd_start_edge())
    elif cmd == "status":
        asyncio.run(cmd_check_status())
    elif cmd == "all":
        cmd_start_all_sync()
    else:
        print(f"不明なコマンド: {cmd}")
