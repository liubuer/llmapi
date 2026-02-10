"""使用例デモ"""
import openai

# 設定
client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

# 基本的な会話
def basic_chat():
    response = client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "こんにちは、自己紹介をしてください"}]
    )
    print(response.choices[0].message.content)

# ストリーミング出力
def streaming_chat():
    stream = client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "短いジョークを一つ教えてください"}],
        stream=True
    )
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()

# LangChain使用例
def langchain_example():
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
        model="gpt-5"
    )

    response = llm.invoke("機械学習とは何ですか？")
    print(response.content)


if __name__ == "__main__":
    print("=== 基本的な会話 ===")
    basic_chat()

    print("\n=== ストリーミング出力 ===")
    streaming_chat()
