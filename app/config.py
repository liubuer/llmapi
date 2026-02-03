"""
配置管理模块
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """应用配置"""
    
    # AI工具配置
    ai_tool_url: str = Field(
        default="https://taa.xxx.co.jp",
        description="公司内部AI工具URL"
    )
    
    # 浏览器配置
    browser_headless: bool = Field(
        default=True,
        description="是否使用无头浏览器模式"
    )
    browser_slow_mo: int = Field(
        default=100,
        description="浏览器操作延迟(ms)，用于稳定性"
    )
    
    # 会话池配置
    max_sessions: int = Field(
        default=3,
        description="最大并发会话数"
    )
    session_timeout: int = Field(
        default=300,
        description="会话超时时间(秒)"
    )
    
    # 认证配置
    auth_state_path: Path = Field(
        default=Path("./auth_state"),
        description="浏览器认证状态保存路径"
    )
    
    # API配置
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    
    # 输入限制
    max_input_chars: int = Field(
        default=50000,
        description="最大输入字符数"
    )
    
    # 超时配置
    response_timeout: int = Field(
        default=120,
        description="等待AI响应的超时时间(秒)"
    )
    
    # 页面元素选择器（需要根据实际页面调整）
    # 这些选择器需要根据实际的AI工具页面结构来配置
    selector_input: str = Field(
        default="textarea[data-testid='chat-input'], textarea.chat-input, textarea[placeholder*='消息'], textarea[placeholder*='输入'], #prompt-textarea, textarea",
        description="输入框选择器"
    )
    selector_send_button: str = Field(
        default="button[data-testid='send-button'], button.send-button, button[aria-label*='发送'], button[aria-label*='Send'], button:has(svg)",
        description="发送按钮选择器"
    )
    selector_response: str = Field(
        default="div[data-testid='response'], div.response-content, div.markdown, div.message-content, div[class*='response'], div[class*='answer']",
        description="响应内容选择器"
    )
    selector_loading: str = Field(
        default="div.loading, div[class*='loading'], div[class*='typing'], span[class*='cursor']",
        description="加载状态选择器"
    )
    selector_new_chat: str = Field(
        default="button[data-testid='new-chat'], button.new-chat, button[aria-label*='新对话'], button[aria-label*='New'], a[href*='new']",
        description="新对话按钮选择器"
    )
    selector_model_select: str = Field(
        default="select[data-testid='model-select'], div[class*='model-selector'], button[class*='model']",
        description="模型选择器"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# 全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings
