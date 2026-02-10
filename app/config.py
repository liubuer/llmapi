"""設定管理"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # AIツール設定
    ai_tool_url: str = Field(default="https://taa.xxx.co.jp")

    # Edgeデバッグポート（稼働中のEdgeへの接続用）
    edge_debug_port: int = Field(default=9222)

    # ブラウザ設定
    browser_slow_mo: int = Field(default=100)

    # セッション設定
    max_sessions: int = Field(default=3)

    # タイムアウト設定
    response_timeout: int = Field(default=120)
    max_input_chars: int = Field(default=50000)

    # API設定
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    # ページセレクター
    selector_input: str = Field(
        default="textarea, [contenteditable='true'], input[type='text']"
    )
    selector_send_button: str = Field(
        default="button[type='submit'], button:has-text('発送'), button:has-text('Send'), button:has-text('送信')"
    )
    selector_response: str = Field(
        default="div[class*='response'], div[class*='message'], div[class*='answer'], div.markdown"
    )
    selector_loading: str = Field(
        default="div[class*='loading'], div[class*='typing'], span[class*='cursor']"
    )
    selector_new_chat: str = Field(
        default="button:has-text('新規チャット'), button:has-text('New'), a[href*='new']"
    )

    # モデルセレクター
    selector_model_button: str = Field(
        default="button[id^='mantine-'][id$='-target'][aria-haspopup='menu']"
    )
    selector_model_item: str = Field(
        default="div.mantine-Menu-itemLabel"
    )

    # デフォルトモデル
    default_model: str = Field(default="GPT-5")

    # 長文テキスト分割設定
    chunk_size: int = Field(default=45000)  # チャンクサイズ（プロンプト用に5000文字の余裕を確保）
    chunk_overlap: int = Field(default=200)  # オーバーラップ文字数、コンテキストの一貫性を確保

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

def get_settings() -> Settings:
    return settings
