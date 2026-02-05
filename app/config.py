"""配置管理"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # AI工具配置
    ai_tool_url: str = Field(default="https://taa.xxx.co.jp")
    
    # Edge调试端口（用于连接已运行的Edge）
    edge_debug_port: int = Field(default=9222)
    
    # 浏览器配置
    browser_slow_mo: int = Field(default=100)
    
    # 会话配置
    max_sessions: int = Field(default=3)
    
    # 超时配置
    response_timeout: int = Field(default=120)
    max_input_chars: int = Field(default=50000)
    
    # API配置
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    
    # 页面选择器
    selector_input: str = Field(
        default="textarea, [contenteditable='true'], input[type='text']"
    )
    selector_send_button: str = Field(
        default="button[type='submit'], button:has-text('发送'), button:has-text('Send'), button:has-text('送信')"
    )
    selector_response: str = Field(
        default="div[class*='response'], div[class*='message'], div[class*='answer'], div.markdown"
    )
    selector_loading: str = Field(
        default="div[class*='loading'], div[class*='typing'], span[class*='cursor']"
    )
    selector_new_chat: str = Field(
        default="button:has-text('新对话'), button:has-text('New'), a[href*='new']"
    )

    # 模型选择器
    selector_model_button: str = Field(
        default="button.mantine-Button-root[aria-haspopup='menu']"
    )
    selector_model_dropdown: str = Field(
        default="div[role='menu'], div[class*='mantine-Menu-dropdown']"
    )

    # 默认模型
    default_model: str = Field(default="GPT-5")
    
    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

def get_settings() -> Settings:
    return settings
