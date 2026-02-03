"""
直接API调用示例
展示如何直接使用封装后的API，不依赖LangChain
"""
import httpx
import openai
from typing import Generator


API_BASE_URL = "http://localhost:8000"


# ============ 使用 httpx 直接调用 ============

def example_httpx_basic():
    """使用httpx直接调用API"""
    print("=== httpx 基础调用 ===")
    
    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            f"{API_BASE_URL}/v1/chat/completions",
            json={
                "model": "gpt-5",
                "messages": [
                    {"role": "system", "content": "你是一个有帮助的助手。"},
                    {"role": "user", "content": "用一句话介绍Python编程语言"}
                ],
                "temperature": 0.7
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"响应: {data['choices'][0]['message']['content']}")
        else:
            print(f"错误: {response.status_code} - {response.text}")
    
    print()


def example_httpx_streaming():
    """使用httpx进行流式调用"""
    print("=== httpx 流式调用 ===")
    
    with httpx.Client(timeout=120.0) as client:
        with client.stream(
            "POST",
            f"{API_BASE_URL}/v1/chat/completions",
            json={
                "model": "gpt-5",
                "messages": [
                    {"role": "user", "content": "数到10，每个数字用逗号分隔"}
                ],
                "stream": True
            }
        ) as response:
            print("流式响应: ", end="")
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(data)
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        print(content, end="", flush=True)
                    except:
                        pass
            print("\n")


# ============ 使用 OpenAI SDK ============

def example_openai_sdk():
    """使用OpenAI SDK调用"""
    print("=== OpenAI SDK 调用 ===")
    
    # 创建客户端
    client = openai.OpenAI(
        base_url=f"{API_BASE_URL}/v1",
        api_key="not-needed"  # 内部服务不需要API key
    )
    
    # 聊天补全
    response = client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": "你是一个专业的翻译。"},
            {"role": "user", "content": "请将以下内容翻译成英文：人工智能正在改变世界。"}
        ]
    )
    
    print(f"响应: {response.choices[0].message.content}")
    print(f"使用tokens: {response.usage}")
    print()


def example_openai_sdk_streaming():
    """使用OpenAI SDK进行流式调用"""
    print("=== OpenAI SDK 流式调用 ===")
    
    client = openai.OpenAI(
        base_url=f"{API_BASE_URL}/v1",
        api_key="not-needed"
    )
    
    print("流式响应: ", end="")
    stream = client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "user", "content": "写一首关于春天的俳句"}
        ],
        stream=True
    )
    
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print("\n")


def example_openai_multi_turn():
    """多轮对话示例"""
    print("=== 多轮对话 ===")
    
    client = openai.OpenAI(
        base_url=f"{API_BASE_URL}/v1",
        api_key="not-needed"
    )
    
    messages = [
        {"role": "system", "content": "你是一个友好的助手，记住用户告诉你的信息。"}
    ]
    
    # 第一轮
    messages.append({"role": "user", "content": "我叫田中，我是一名软件工程师。"})
    response1 = client.chat.completions.create(model="gpt-5", messages=messages)
    assistant_msg1 = response1.choices[0].message.content
    messages.append({"role": "assistant", "content": assistant_msg1})
    print(f"用户: 我叫田中，我是一名软件工程师。")
    print(f"AI: {assistant_msg1}\n")
    
    # 第二轮
    messages.append({"role": "user", "content": "你还记得我的名字和职业吗？"})
    response2 = client.chat.completions.create(model="gpt-5", messages=messages)
    assistant_msg2 = response2.choices[0].message.content
    print(f"用户: 你还记得我的名字和职业吗？")
    print(f"AI: {assistant_msg2}")
    print()


# ============ 异步调用 ============

async def example_async_call():
    """异步API调用"""
    print("=== 异步调用 ===")
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/v1/chat/completions",
            json={
                "model": "gpt-5",
                "messages": [
                    {"role": "user", "content": "简单介绍一下FastAPI框架"}
                ]
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"响应: {data['choices'][0]['message']['content']}")
        else:
            print(f"错误: {response.status_code}")
    
    print()


# ============ 检查API状态 ============

def check_api_health():
    """检查API健康状态"""
    print("=== API健康检查 ===")
    
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{API_BASE_URL}/health")
            if response.status_code == 200:
                data = response.json()
                print(f"状态: {data['status']}")
                print(f"浏览器会话数: {data['browser_sessions']}")
                print(f"可用会话数: {data['available_sessions']}")
                return True
            else:
                print(f"API不健康: {response.status_code}")
                return False
    except Exception as e:
        print(f"无法连接到API: {e}")
        return False


def list_models():
    """列出可用模型"""
    print("\n=== 可用模型 ===")
    
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{API_BASE_URL}/v1/models")
        if response.status_code == 200:
            data = response.json()
            for model in data['data']:
                print(f"- {model['id']} (owned by: {model['owned_by']})")


# ============ 主函数 ============

def main():
    """运行所有示例"""
    print("=" * 60)
    print("直接API调用示例")
    print("=" * 60)
    print()
    
    # 首先检查API状态
    if not check_api_health():
        print("\n请先启动API服务:")
        print("  uvicorn app.main:app --host 0.0.0.0 --port 8000")
        return
    
    list_models()
    print()
    
    # 运行示例
    example_httpx_basic()
    example_httpx_streaming()
    example_openai_sdk()
    example_openai_sdk_streaming()
    example_openai_multi_turn()
    
    # 异步示例
    import asyncio
    asyncio.run(example_async_call())


if __name__ == "__main__":
    main()
