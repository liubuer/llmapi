"""
ファイル対話ツール - Streamlit UI

使用方法:
    streamlit run tools/file_chat.py
"""
import os
import sys
import json
import tempfile
from pathlib import Path

import streamlit as st
from openai import OpenAI

# プロジェクトルートディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent))
from file_reader import read_file

# ページ設定
st.set_page_config(
    page_title="File Chat - ファイル対話ツール",
    page_icon="📄",
    layout="wide"
)

# ==================== サイドバー設定 ====================
with st.sidebar:
    st.header("⚙️ 設定")

    # API設定
    api_base_url = st.text_input(
        "API Base URL",
        value=st.session_state.get("api_base_url", "http://localhost:8000/v1"),
        help="社内LLM APIのアドレス"
    )
    st.session_state.api_base_url = api_base_url

    model = st.selectbox(
        "モデル",
        ["gpt-5", "gpt-5-thinking", "gpt-4.1-mini", "gpt-4o"],
        index=0
    )

    st.divider()

    # ファイルアップロード
    st.header("📁 ファイルアップロード")
    uploaded_file = st.file_uploader(
        "ファイルを選択",
        type=["txt", "json", "pdf", "csv", "docx", "xlsx", "md", "xml",
              "html", "log", "yaml", "yml", "py", "js", "ts", "java",
              "sql", "sh", "bat", "ini", "cfg", "toml"],
        help="TXT, JSON, PDF, CSV, DOCX, XLSX, MD, XML 等の形式に対応"
    )

    # アップロードされたファイルの処理
    if uploaded_file is not None:
        # 一時ファイルに保存
        suffix = Path(uploaded_file.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        try:
            file_content = read_file(tmp_path)
            st.session_state.file_content = file_content
            st.session_state.file_name = uploaded_file.name
        except Exception as e:
            st.error(f"ファイル読み取り失敗: {e}")
            st.session_state.file_content = None
            st.session_state.file_name = None
        finally:
            os.unlink(tmp_path)

    # ファイルコンテンツプレビュー
    if st.session_state.get("file_content"):
        content = st.session_state.file_content
        char_count = len(content)
        st.info(f"📄 **{st.session_state.file_name}** ({char_count:,} 文字)")

        if char_count > 50000:
            st.warning(f"⚠️ ファイルが大きいです ({char_count:,} 文字)。50,000文字を超える場合は自動的にチャンク分割して送信されます")

        with st.expander("ファイルコンテンツプレビュー", expanded=False):
            preview = content[:2000]
            if len(content) > 2000:
                preview += f"\n\n... (残り {len(content) - 2000:,} 文字)"
            st.text(preview)

    st.divider()

    # システムプロンプト
    st.header("💬 システムプロンプト")
    system_prompt = st.text_area(
        "システムプロンプト (任意)",
        value=st.session_state.get("system_prompt", ""),
        height=100,
        placeholder="例: あなたはプロフェッショナルなドキュメント分析アシスタントです。日本語で回答してください。"
    )
    st.session_state.system_prompt = system_prompt

    st.divider()

    # セッション管理
    st.header("🔗 セッション管理")
    conv_id = st.session_state.get("conversation_id")
    if conv_id:
        st.success(f"セッションID: `{conv_id}`")
    else:
        st.info("セッション未確立")

    if st.button("🔄 新規セッション", use_container_width=True):
        st.session_state.conversation_id = None
        st.session_state.new_conversation = True
        st.session_state.chat_history = []
        st.rerun()


# ==================== 状態初期化 ====================
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "new_conversation" not in st.session_state:
    st.session_state.new_conversation = True
if "file_content" not in st.session_state:
    st.session_state.file_content = None
if "file_name" not in st.session_state:
    st.session_state.file_name = None

# ==================== メイン画面 ====================
st.title("📄 File Chat - ファイル対話ツール")
st.caption("ファイルをアップロードして、AIに質問し、スマートな分析を取得")

# 履歴メッセージを表示
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ユーザー入力
user_input = st.chat_input("質問を入力してください...")

if user_input:
    # メッセージを構築
    messages = []

    # システムプロンプト
    if st.session_state.system_prompt:
        messages.append({
            "role": "system",
            "content": st.session_state.system_prompt
        })

    # ファイルコンテンツがあり、最初のメッセージ（または新規セッション）の場合、ファイルコンテンツを含める
    file_content = st.session_state.get("file_content")
    is_first_message = len(st.session_state.chat_history) == 0

    if file_content and is_first_message:
        # 最初のメッセージにファイルコンテンツを含める
        combined = f"以下はファイル「{st.session_state.file_name}」の内容です:\n\n{file_content}\n\n---\n\n{user_input}"
        messages.append({"role": "user", "content": combined})
        display_text = user_input  # 画面には質問のみ表示
    else:
        messages.append({"role": "user", "content": user_input})
        display_text = user_input

    # ユーザーメッセージを表示
    with st.chat_message("user"):
        st.markdown(display_text)
    st.session_state.chat_history.append({"role": "user", "content": display_text})

    # APIを呼び出し
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        try:
            client = OpenAI(
                base_url=st.session_state.api_base_url,
                api_key="not-needed"
            )

            # 追加パラメータを構築
            extra_body = {}
            if st.session_state.get("new_conversation"):
                extra_body["new_conversation"] = True
                st.session_state.new_conversation = False
            elif st.session_state.get("conversation_id"):
                extra_body["conversation_id"] = st.session_state.conversation_id

            # ストリーミングリクエスト
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                extra_body=extra_body if extra_body else None
            )

            for chunk in stream:
                # conversation_idを抽出（カスタムフィールドから）
                if hasattr(chunk, "conversation_id") and chunk.conversation_id:
                    st.session_state.conversation_id = chunk.conversation_id
                # raw data内のconversation_idも確認
                if hasattr(chunk, "model_extra") and chunk.model_extra:
                    conv_id_from_extra = chunk.model_extra.get("conversation_id")
                    if conv_id_from_extra:
                        st.session_state.conversation_id = conv_id_from_extra

                if chunk.choices and chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response + "▌")

            message_placeholder.markdown(full_response)

        except Exception as e:
            error_msg = f"API呼び出し失敗: {e}"
            message_placeholder.error(error_msg)
            full_response = error_msg

        st.session_state.chat_history.append({"role": "assistant", "content": full_response})

    st.rerun()
