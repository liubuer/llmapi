"""
自定义LangChain LLM适配器
提供与公司内部AI工具的原生集成
"""
from typing import Any, Dict, Iterator, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    AIMessageChunk,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field
import httpx


class InternalAILLM(LLM):
    """
    公司内部AI工具的LangChain LLM适配器
    
    用法:
        llm = InternalAILLM(base_url="http://localhost:8000")
        response = llm.invoke("你好")
    """
    
    base_url: str = Field(default="http://localhost:8000")
    model: str = Field(default="gpt-5")
    temperature: float = Field(default=0.7)
    timeout: int = Field(default=120)
    
    @property
    def _llm_type(self) -> str:
        return "internal-ai"
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "temperature": self.temperature,
        }
    
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """调用LLM"""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/completions",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "temperature": self.temperature,
                    "stop": stop,
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["text"]


class InternalAIChatModel(BaseChatModel):
    """
    公司内部AI工具的LangChain Chat Model适配器
    
    用法:
        chat = InternalAIChatModel(base_url="http://localhost:8000")
        response = chat.invoke([HumanMessage(content="你好")])
    """
    
    base_url: str = Field(default="http://localhost:8000")
    model: str = Field(default="gpt-5")
    temperature: float = Field(default=0.7)
    timeout: int = Field(default=120)
    streaming: bool = Field(default=False)
    
    @property
    def _llm_type(self) -> str:
        return "internal-ai-chat"
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "temperature": self.temperature,
        }
    
    def _convert_message_to_dict(self, message: BaseMessage) -> Dict[str, str]:
        """将LangChain消息转换为API格式"""
        if isinstance(message, HumanMessage):
            return {"role": "user", "content": message.content}
        elif isinstance(message, AIMessage):
            return {"role": "assistant", "content": message.content}
        elif isinstance(message, SystemMessage):
            return {"role": "system", "content": message.content}
        else:
            return {"role": "user", "content": str(message.content)}
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """生成响应"""
        message_dicts = [self._convert_message_to_dict(m) for m in messages]
        
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": message_dicts,
                    "temperature": self.temperature,
                    "stop": stop,
                    "stream": False,
                }
            )
            response.raise_for_status()
            data = response.json()
        
        content = data["choices"][0]["message"]["content"]
        message = AIMessage(content=content)
        generation = ChatGeneration(message=message)
        
        return ChatResult(generations=[generation])
    
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """流式生成响应"""
        message_dicts = [self._convert_message_to_dict(m) for m in messages]
        
        with httpx.Client(timeout=self.timeout) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": message_dicts,
                    "temperature": self.temperature,
                    "stop": stop,
                    "stream": True,
                }
            ) as response:
                import json
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                chunk = ChatGenerationChunk(
                                    message=AIMessageChunk(content=content)
                                )
                                if run_manager:
                                    run_manager.on_llm_new_token(content)
                                yield chunk
                        except json.JSONDecodeError:
                            pass


# 便捷函数
def get_internal_llm(
    base_url: str = "http://localhost:8000",
    model: str = "gpt-5",
    **kwargs
) -> InternalAILLM:
    """获取内部AI LLM实例"""
    return InternalAILLM(base_url=base_url, model=model, **kwargs)


def get_internal_chat_model(
    base_url: str = "http://localhost:8000",
    model: str = "gpt-5",
    **kwargs
) -> InternalAIChatModel:
    """获取内部AI Chat Model实例"""
    return InternalAIChatModel(base_url=base_url, model=model, **kwargs)


# 使用示例
if __name__ == "__main__":
    # 测试LLM
    print("=== 测试 InternalAILLM ===")
    llm = InternalAILLM()
    response = llm.invoke("用一句话介绍Python")
    print(f"响应: {response}")
    
    print("\n=== 测试 InternalAIChatModel ===")
    chat = InternalAIChatModel()
    messages = [
        SystemMessage(content="你是一个有帮助的助手"),
        HumanMessage(content="你好！")
    ]
    response = chat.invoke(messages)
    print(f"响应: {response.content}")
    
    print("\n=== 测试流式输出 ===")
    chat_stream = InternalAIChatModel(streaming=True)
    print("流式响应: ", end="")
    for chunk in chat_stream.stream([HumanMessage(content="数到5")]):
        print(chunk.content, end="", flush=True)
    print()
