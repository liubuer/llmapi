"""AIウェブインタラクションクライアント"""
import asyncio
from typing import AsyncGenerator, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from loguru import logger

from .config import get_settings
from .models import ChatMessage
from .edge_manager import edge_manager, get_edge_manager


# 長文テキスト分割プロンプトテンプレート
CHUNK_TEMPLATE_FIRST = """これから約{total_chars}文字の資料を{total_parts}回に分けて入力します。
これは第1部（全{total_parts}部）、約{part_chars}文字です。
この内容を受け取って記憶してください。受信後、次の資料を入力します。
受信後、「第1部受信完了」と短く返信してください。他の内容は不要です。

---資料開始---
{content}
---資料終了---"""

CHUNK_TEMPLATE_MIDDLE = """これは第{part_num}部（全{total_parts}部）、約{part_chars}文字です。
この内容を受け取り、前の資料と統合して記憶してください。受信後、入力を続けます。
受信後、「第{part_num}部受信完了」と短く返信してください。他の内容は不要です。

---資料開始---
{content}
---資料終了---"""

CHUNK_TEMPLATE_LAST = """これは最後の資料（第{part_num}部、全{total_parts}部）、約{part_chars}文字です。
受信後、全{total_parts}部の資料を記憶の中で完全な一つに統合してください。

---資料開始---
{content}
---資料終了---

資料の受信が完了しました。上記の全資料に基づいて、以下の質問に回答してください：

{question}"""

CHUNK_TEMPLATE_LAST_NO_QUESTION = """これは最後の資料（第{part_num}部、全{total_parts}部）、約{part_chars}文字です。
受信後、全{total_parts}部の資料を記憶の中で完全な一つに統合してください。
統合完了後、これらの資料の主要な内容を簡潔にまとめてください。

---資料開始---
{content}
---資料終了---"""


class AIClientError(Exception):
    pass


class AIClient:
    def __init__(self):
        self.settings = get_settings()
        self._debug_dir = Path("./debug")
        self._debug_dir.mkdir(exist_ok=True)

    async def _save_screenshot(self, page: Page, name: str):
        """デバッグスクリーンショットを保存"""
        try:
            path = self._debug_dir / f"{name}_{datetime.now().strftime('%H%M%S')}.png"
            await page.screenshot(path=str(path))
            logger.info(f"スクリーンショット: {path}")
        except:
            pass

    async def _navigate_to_ai_tool(self, page: Page):
        """AIツールページへ遷移"""
        current_url = page.url
        target_url = self.settings.ai_tool_url

        if not current_url.startswith(target_url):
            logger.info(f"遷移先: {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

    async def _select_model(self, page: Page, model: str):
        """LLMモデルを選択"""
        try:
            # モデル選択ボタンを検索 (id: mantine-*-target)
            model_button = page.locator(self.settings.selector_model_button).first

            if not await model_button.is_visible(timeout=3000):
                logger.warning("モデル選択ボタンが見つかりません")
                return False

            # 現在選択されているモデルを確認
            button_text = await model_button.inner_text()
            if model in button_text:
                logger.info(f"現在のモデル: {model}")
                return True

            logger.info(f"現在のモデル: {button_text.strip()}, 切り替え先: {model}")

            # ドロップダウンメニューID取得 (aria-controls属性から)
            dropdown_id = await model_button.get_attribute("aria-controls")
            logger.debug(f"ドロップダウンメニューID: {dropdown_id}")

            # ボタンをクリックしてドロップダウンを開く
            await model_button.click()
            await asyncio.sleep(0.5)

            # ドロップダウンメニューの表示を待機
            if dropdown_id:
                dropdown = page.locator(f"#{dropdown_id}")
                await dropdown.wait_for(state="visible", timeout=3000)

            # ドロップダウンメニューから対象モデルを検索 (mantine-Menu-itemLabel使用)
            menu_items = page.locator(self.settings.selector_model_item)
            count = await menu_items.count()
            logger.debug(f"メニュー項目 {count} 件発見")

            for i in range(count):
                item = menu_items.nth(i)
                item_text = await item.inner_text()
                logger.debug(f"メニュー項目 {i}: {item_text}")

                if model in item_text:
                    await item.click()
                    logger.info(f"モデル選択完了: {model}")
                    await asyncio.sleep(0.5)
                    return True

            logger.warning(f"モデルオプションが見つかりません: {model}")
            await page.keyboard.press("Escape")
            return False

        except Exception as e:
            logger.warning(f"モデル選択失敗: {e}")
            try:
                await page.keyboard.press("Escape")
            except:
                pass
            return False

    async def _find_input(self, page: Page):
        """入力ボックスを検索"""
        selectors = self.settings.selector_input.split(",")

        for selector in selectors:
            selector = selector.strip()
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=2000):
                    return element
            except:
                continue

        # 汎用セレクター
        for selector in ["textarea", "[contenteditable='true']", "input[type='text']"]:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=1000):
                    return element
            except:
                continue

        return None

    async def _find_send_button(self, page: Page):
        """送信ボタンを検索"""
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
        """レスポンスを待機"""
        start = datetime.now()
        last_content = ""
        stable_count = 0

        # 読み込み中の表示テキスト（フィルタ対象）
        loading_texts = ["が回答を生成中", "生成中", "Loading", "Thinking", "..."]

        logger.debug(f"レスポンス待機、セレクター: {self.settings.selector_response}, 初期要素数: {initial_count}")

        # 初期コンテンツを記録（要素数が変わらなくても内容変化を検出するため）
        initial_content = ""
        if initial_count > 0:
            try:
                responses_init = page.locator(self.settings.selector_response)
                initial_content = await responses_init.nth(initial_count - 1).inner_text()
                initial_content = initial_content.strip()
                logger.debug(f"初期コンテンツ: {initial_content[:50]}...")
            except:
                pass

        wait_new_element_timeout = 5  # 新要素の待機タイムアウト（秒）

        while (datetime.now() - start).total_seconds() < self.settings.response_timeout:
            try:
                # 読み込み状態を確認
                loading = page.locator(self.settings.selector_loading)
                is_loading = await loading.count() > 0
                if is_loading:
                    try:
                        is_loading = await loading.first.is_visible(timeout=500)
                    except:
                        is_loading = False

                # レスポンスを取得
                responses = page.locator(self.settings.selector_response)
                count = await responses.count()
                elapsed = (datetime.now() - start).total_seconds()

                logger.debug(f"レスポンス要素 {count} 件発見 (初期: {initial_count})、is_loading={is_loading}, elapsed={elapsed:.1f}s")

                # 新要素の出現を待機、タイムアウト後はコンテンツ変化を確認
                if count <= initial_count and count > 0:
                    if elapsed < wait_new_element_timeout:
                        logger.debug("新しいレスポンス要素の出現を待機中...")
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        # タイムアウト後、最後の要素の内容変化を確認
                        current_content = await responses.nth(count - 1).inner_text()
                        current_content = current_content.strip()
                        if current_content == initial_content or current_content == sent_message.strip():
                            logger.debug("内容変化なし、待機継続...")
                            await asyncio.sleep(0.5)
                            continue
                        logger.debug("内容変化を検出、処理続行")

                if count > 0:
                    content = await responses.nth(count - 1).inner_text()
                    content = content.strip()

                    logger.debug(f"最後の要素の内容 ({len(content)} 文字): {content[:100]}...")

                    # 読み込み表示をフィルタ
                    is_loading_text = any(t in content for t in loading_texts)

                    # ユーザー送信メッセージをフィルタ（ユーザーメッセージをレスポンスと誤認しないため）
                    if sent_message and content == sent_message.strip():
                        logger.debug("ユーザーメッセージを検出、スキップ")
                        await asyncio.sleep(0.5)
                        continue

                    if is_loading_text or len(content) < 5:
                        await asyncio.sleep(0.5)
                        continue

                    if content == last_content and not is_loading:
                        stable_count += 1
                        if stable_count >= 3:
                            logger.info(f"レスポンス安定、{len(content)} 文字を返却")
                            return content
                    else:
                        stable_count = 0
                        last_content = content

                await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"レスポンス待機中にエラー: {e}")
                await asyncio.sleep(0.5)

        if last_content:
            logger.warning(f"レスポンスタイムアウト、最終コンテンツを返却: {len(last_content)} 文字")
            return last_content

        await self._save_screenshot(page, "response_timeout")
        raise AIClientError("レスポンスタイムアウト")

    async def _send_message(self, page: Page, message: str) -> str:
        """メッセージを送信"""
        if len(message) > self.settings.max_input_chars:
            raise AIClientError(f"メッセージが長すぎます: {len(message)} > {self.settings.max_input_chars}")

        # 入力ボックスを検索
        input_box = await self._find_input(page)
        if not input_box:
            await self._save_screenshot(page, "no_input")
            raise AIClientError("入力ボックスが見つかりません")

        # 現在のレスポンス要素数を記録（新しいレスポンスの検出用）
        responses = page.locator(self.settings.selector_response)
        initial_count = await responses.count()
        logger.debug(f"非ストリーミングモード: 現在のレスポンス要素数 = {initial_count}")

        # メッセージを入力
        await input_box.click()
        await asyncio.sleep(0.2)

        if len(message) > 500:
            # 長文テキストはJSで入力
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
        logger.info(f"メッセージ入力完了 ({len(message)} 文字)")

        # 送信 - Ctrl+Enterを使用
        await input_box.press("Control+Enter")
        logger.info("メッセージ送信完了 (Ctrl+Enter)、レスポンス待機中...")
        return await self._wait_for_response(page, sent_message=message, initial_count=initial_count)

    async def _stream_response(self, page: Page, sent_message: str = "", initial_count: int = 0) -> AsyncGenerator[str, None]:
        """ストリーミングレスポンス"""
        start = datetime.now()
        last_content = ""
        stable_count = 0
        response_started = False

        # 読み込み中の表示テキスト（フィルタ対象）
        loading_texts = ["が回答を生成中", "生成中", "Loading", "Thinking", "..."]

        logger.debug(f"ストリーミングレスポンス開始、セレクター: {self.settings.selector_response}, 初期要素数: {initial_count}")

        # 初期コンテンツを記録（要素数が変わらなくても内容変化を検出するため）
        initial_content = ""
        if initial_count > 0:
            try:
                responses_init = page.locator(self.settings.selector_response)
                initial_content = await responses_init.nth(initial_count - 1).inner_text()
                initial_content = initial_content.strip()
                logger.debug(f"ストリーミング: 初期コンテンツ: {initial_content[:50]}...")
            except:
                pass

        wait_new_element_timeout = 5  # 新要素の待機タイムアウト（秒）

        # まず新しいレスポンス要素の出現を待機
        while (datetime.now() - start).total_seconds() < self.settings.response_timeout:
            try:
                responses = page.locator(self.settings.selector_response)
                count = await responses.count()
                elapsed = (datetime.now() - start).total_seconds()

                logger.debug(f"ストリーミング: レスポンス要素 {count} 件発見 (初期: {initial_count}), elapsed={elapsed:.1f}s")

                # 新要素の出現を待機、タイムアウト後はコンテンツ変化を確認
                if count <= initial_count and count > 0:
                    if elapsed < wait_new_element_timeout:
                        logger.debug("ストリーミング: 新しいレスポンス要素の出現を待機中...")
                        await asyncio.sleep(0.3)
                        continue
                    else:
                        # タイムアウト後、最後の要素の内容変化を確認
                        current_content = await responses.nth(count - 1).inner_text()
                        current_content = current_content.strip()
                        if current_content == initial_content or current_content == sent_message.strip():
                            logger.debug("ストリーミング: 内容変化なし、待機継続...")
                            await asyncio.sleep(0.3)
                            continue
                        logger.debug("ストリーミング: 内容変化を検出、処理続行")

                if count > 0:
                    content = await responses.nth(count - 1).inner_text()
                    content = content.strip()

                    logger.debug(f"ストリーミング: コンテンツ ({len(content)} 文字): {content[:50]}...")

                    # 読み込み表示かどうかを確認
                    is_loading_text = any(t in content for t in loading_texts)

                    # ユーザー送信メッセージをフィルタ
                    if sent_message and content == sent_message.strip():
                        logger.debug("ストリーミング: ユーザーメッセージを検出、スキップ")
                        await asyncio.sleep(0.3)
                        continue

                    if is_loading_text or len(content) < 5:
                        # まだ読み込み中、待機継続
                        await asyncio.sleep(0.3)
                        continue

                    # 実際のレスポンスが開始
                    if not response_started:
                        response_started = True
                        last_content = ""  # リセット
                        logger.info("ストリーミングレスポンス開始")

                    if len(content) > len(last_content):
                        delta = content[len(last_content):]
                        last_content = content
                        stable_count = 0
                        yield delta
                    else:
                        # まだ読み込み中かどうかを確認
                        loading = page.locator(self.settings.selector_loading)
                        is_loading = await loading.count() > 0
                        if not is_loading:
                            stable_count += 1
                            if stable_count >= 5:
                                logger.info("ストリーミングレスポンス終了")
                                break

                await asyncio.sleep(0.2)
            except Exception as e:
                logger.debug(f"ストリーミングレスポンスエラー: {e}")
                await asyncio.sleep(0.2)

        if not response_started:
            logger.warning("ストリーミングレスポンスタイムアウト、レスポンス未検出")
            await self._save_screenshot(page, "stream_timeout")

    def _map_model_name(self, model: str) -> str:
        """APIモデル名をウェブ上のモデル名にマッピング"""
        model_lower = model.lower()

        # モデル名マッピング
        model_mapping = {
            "gpt-5": "GPT-5",
            "gpt5": "GPT-5",
            "gpt-5-thinking": "GPT-5 thinking",
            "gpt5-thinking": "GPT-5 thinking",
            "gpt-4.1-mini": "GPT-4.1 mini",
            "gpt-4.1": "GPT-4.1 mini",
            "gpt4.1-mini": "GPT-4.1 mini",
        }

        # マッピングを検索
        if model_lower in model_mapping:
            return model_mapping[model_lower]

        # マッピングがない場合、デフォルトモデルを使用
        return self.settings.default_model

    def _format_messages(self, messages: List[ChatMessage]) -> str:
        """メッセージをフォーマット"""
        if len(messages) == 1 and messages[0].role == "user":
            return messages[0].content

        parts = []
        for msg in messages:
            if msg.role == "system":
                parts.append(f"[システム指示]\n{msg.content}")
            elif msg.role == "user":
                parts.append(f"[ユーザー]\n{msg.content}")
            elif msg.role == "assistant":
                parts.append(f"[アシスタント]\n{msg.content}")

        return "\n\n".join(parts)

    def _split_long_text(self, text: str, question: str = "") -> List[str]:
        """
        長文テキストを複数のチャンクに分割し、プロンプトテンプレートを適用

        Args:
            text: 分割する長文テキスト（背景資料）
            question: ユーザーの質問（最後のチャンクで提示）

        Returns:
            分割後のプロンプトリスト
        """
        chunk_size = self.settings.chunk_size
        total_chars = len(text)

        # テキストの分割が不要な場合
        if total_chars <= self.settings.max_input_chars:
            return [text]

        # 分割するチャンク数を計算
        # テンプレート用のスペースを確保（約500-1000文字）
        effective_chunk_size = chunk_size - 500
        num_chunks = (total_chars + effective_chunk_size - 1) // effective_chunk_size

        logger.info(f"テキストが長すぎます ({total_chars} 文字)、{num_chunks} チャンクに分割します")

        chunks = []
        start = 0

        for i in range(num_chunks):
            # このチャンクの終了位置を決定
            if i == num_chunks - 1:
                # 最後のチャンク、残り全てを取得
                end = total_chars
            else:
                end = min(start + effective_chunk_size, total_chars)
                # 文境界で分割を試行
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

            # 位置に応じてテンプレートを選択
            if i == 0:
                # 最初のチャンク
                formatted = CHUNK_TEMPLATE_FIRST.format(
                    total_chars=total_chars,
                    total_parts=num_chunks,
                    part_chars=part_chars,
                    content=chunk_content
                )
            elif i == num_chunks - 1:
                # 最後のチャンク
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
                # 中間チャンク
                formatted = CHUNK_TEMPLATE_MIDDLE.format(
                    part_num=part_num,
                    total_parts=num_chunks,
                    part_chars=part_chars,
                    content=chunk_content
                )

            chunks.append(formatted)
            logger.debug(f"チャンク {part_num}/{num_chunks}: {part_chars} 文字 (位置 {start}-{end})")
            start = end

        return chunks

    def _extract_question_and_content(self, text: str) -> Tuple[str, str]:
        """
        テキストから質問と背景資料を抽出

        以下の一般的な質問マーカーを識別:
        - "質問：" / "質問:"
        - "回答してください："
        - "Question:" / "Q:"
        - テキストの最後の段落（短い場合）

        Returns:
            (背景資料, 質問)
        """
        # 質問マーカーを識別
        question_markers = [
            '質問：', '質問:', '問：', '問:',
            '回答してください：', '回答してください:',
            'Question:', 'question:', 'Q:', 'q:',
            'お聞きします', '分析してください', 'まとめてください', '概括してください'
        ]

        for marker in question_markers:
            if marker in text:
                pos = text.rfind(marker)
                # 質問部分がテキスト末尾にあるか確認（最後の20%の位置）
                if pos > len(text) * 0.8:
                    content = text[:pos].strip()
                    question = text[pos:].strip()
                    logger.info(f"質問マーカーを識別: {marker}")
                    return content, question

        # 明確な質問マーカーが見つからない場合、最後の段落を確認
        paragraphs = text.strip().split('\n\n')
        if len(paragraphs) > 1:
            last_paragraph = paragraphs[-1].strip()
            # 最後の段落が短く（500文字未満）、質問のように見える場合
            if len(last_paragraph) < 500 and ('?' in last_paragraph or '？' in last_paragraph or 'お' in last_paragraph):
                content = '\n\n'.join(paragraphs[:-1])
                return content, last_paragraph

        # 質問を識別できない場合、原文テキストを返却
        return text, ""

    async def _send_chunked_messages(self, page: Page, chunks: List[str], stream: bool = False):
        """
        長文テキストを分割送信

        Args:
            page: Playwrightページオブジェクト
            chunks: 分割後のプロンプトリスト
            stream: ストリーミングレスポンスを使用するか（最後のチャンクのみ適用）

        Returns:
            最後のチャンクのレスポンス（文字列または非同期ジェネレーター）
        """
        total_chunks = len(chunks)
        logger.info(f"分割送信開始、全 {total_chunks} チャンク")

        for i, chunk in enumerate(chunks):
            part_num = i + 1
            is_last = (i == total_chunks - 1)

            logger.info(f"第 {part_num}/{total_chunks} チャンクを送信 ({len(chunk)} 文字)")

            if is_last:
                # 最後のチャンク、streamパラメータに応じてレスポンス方式を決定
                if stream:
                    # ストリーミングレスポンス
                    responses = page.locator(self.settings.selector_response)
                    initial_count = await responses.count()

                    input_box = await self._find_input(page)
                    if not input_box:
                        raise AIClientError("入力ボックスが見つかりません")

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
                    # 非ストリーミングレスポンス
                    return await self._send_message(page, chunk)
            else:
                # 最後のチャンク以外、確認レスポンスを待機
                response = await self._send_message(page, chunk)

                # レスポンスが受信確認かどうかを確認
                confirmation_keywords = ['受信完了', '受信', '了解', 'received', '承知', '分かりました']
                is_confirmed = any(kw in response.lower() for kw in confirmation_keywords)

                if is_confirmed:
                    logger.info(f"第 {part_num} チャンク受信確認済み")
                else:
                    logger.warning(f"第 {part_num} チャンクのレスポンス: {response[:100]}...")

                # 短い待機、送信速度を制御
                await asyncio.sleep(1)

    async def _click_new_chat(self, page: Page):
        """新規チャットボタンをクリック"""
        selectors = self.settings.selector_new_chat.split(",")
        for selector in selectors:
            selector = selector.strip()
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=2000):
                    await element.click()
                    logger.info(f"新規チャットボタンをクリック: {selector}")
                    await asyncio.sleep(1)
                    return True
            except Exception:
                continue
        logger.warning("新規チャットボタンが見つかりません")
        return False

    async def chat(
        self,
        messages: List[ChatMessage],
        model: str = "gpt-5",
        stream: bool = False,
        conversation_id: Optional[str] = None,
        new_conversation: bool = False
    ):
        """チャットリクエストを送信、セッション管理対応"""
        manager = await get_edge_manager()

        if not manager.is_connected:
            connected = await manager.connect_to_edge()
            if not connected:
                raise AIClientError(
                    "Edgeブラウザに接続できません。\n"
                    "先に実行してください: python -m app.edge_manager start"
                )

        async with manager.acquire_conversation_session(
            conversation_id=conversation_id,
            new_conversation=new_conversation
        ) as (session, conv_id):
            page = session.page

            await self._navigate_to_ai_tool(page)

            # 新規セッションの場合、新規チャットボタンをクリック
            if new_conversation:
                await self._click_new_chat(page)

            # 入力ボックスの存在確認（ログイン状態の検証）
            input_box = await self._find_input(page)
            if not input_box:
                await self._save_screenshot(page, "not_logged_in")
                raise AIClientError(
                    "入力ボックスが見つかりません。未ログインの可能性があります。\n"
                    "Edgeブラウザでログインを完了してください。"
                )

            # モデル選択（一時的に無効化、セレクターの調整が必要）
            # target_model = self._map_model_name(model)
            # if target_model:
            #     await self._select_model(page, target_model)

            prompt = self._format_messages(messages)

            # 長文テキストの分割が必要かどうかを確認
            if len(prompt) > self.settings.max_input_chars:
                logger.info(f"長文テキストを検出 ({len(prompt)} 文字)、分割モードを有効化")

                # 質問と背景資料を抽出
                content, question = self._extract_question_and_content(prompt)

                # テキストを分割
                chunks = self._split_long_text(content, question)

                # 分割送信
                result = await self._send_chunked_messages(page, chunks, stream=stream)
                return result, conv_id

            # 通常送信（テキスト長が制限内）
            if stream:
                # 現在のレスポンス要素数を記録（新しいレスポンスの検出用）
                responses = page.locator(self.settings.selector_response)
                initial_count = await responses.count()
                logger.debug(f"ストリーミングモード: 現在のレスポンス要素数 = {initial_count}")

                # 入力して送信
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
                logger.info(f"メッセージ送信 ({len(prompt)} 文字): {prompt[:50]}...")

                # 送信 - Ctrl+Enterを使用
                await input_box.press("Control+Enter")

                return self._stream_response(page, sent_message=prompt, initial_count=initial_count), conv_id
            else:
                result = await self._send_message(page, prompt)
                return result, conv_id


ai_client = AIClient()

async def get_ai_client() -> AIClient:
    return ai_client
