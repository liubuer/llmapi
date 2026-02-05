"""使用示例"""
import openai

# 配置
client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

# 基础对话
def basic_chat():
    response = client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "你好，请简单介绍一下你自己"}]
    )
    print(response.choices[0].message.content)

# 流式输出
def streaming_chat():
    stream = client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "讲一个简短的笑话"}],
        stream=True
    )
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()

# LangChain示例
def langchain_example():
    from langchain_openai import ChatOpenAI
    
    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
        model="gpt-5"
    )
    
    response = llm.invoke("什么是机器学习？")
    print(response.content)


if __name__ == "__main__":
    print("=== 基础对话 ===")
    basic_chat()
    
    print("\n=== 流式输出 ===")
    streaming_chat()
