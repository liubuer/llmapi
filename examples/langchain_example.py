"""
LangChain 集成示例
展示如何使用包装后的API与LangChain框架集成
"""
import os

# 设置API基础URL（在实际使用中，可以通过环境变量设置）
os.environ["OPENAI_API_BASE"] = "http://localhost:8000/v1"
os.environ["OPENAI_API_KEY"] = "not-needed"  # 内部服务不需要真实的API key


# ============ 示例1: 基础聊天 ============
def example_basic_chat():
    """基础聊天示例"""
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    
    # 创建LLM实例
    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
        model="gpt-5",
        temperature=0.7,
    )
    
    # 简单对话
    messages = [
        SystemMessage(content="你是一个有帮助的助手。"),
        HumanMessage(content="请用简单的语言解释什么是机器学习。")
    ]
    
    response = llm.invoke(messages)
    print("基础聊天响应:")
    print(response.content)
    print("-" * 50)


# ============ 示例2: 流式输出 ============
def example_streaming():
    """流式输出示例"""
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage
    
    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
        model="gpt-5",
        streaming=True,
    )
    
    print("流式输出:")
    for chunk in llm.stream([HumanMessage(content="讲一个短笑话")]):
        print(chunk.content, end="", flush=True)
    print("\n" + "-" * 50)


# ============ 示例3: 使用链(Chain) ============
def example_chain():
    """使用LangChain链示例"""
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    
    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
        model="gpt-5",
    )
    
    # 创建提示模板
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个{role}。请用{style}的方式回答问题。"),
        ("human", "{question}")
    ])
    
    # 创建链
    chain = prompt | llm | StrOutputParser()
    
    # 执行链
    result = chain.invoke({
        "role": "历史老师",
        "style": "生动有趣",
        "question": "简要介绍一下日本的明治维新"
    })
    
    print("链式调用响应:")
    print(result)
    print("-" * 50)


# ============ 示例4: 带记忆的对话 ============
def example_with_memory():
    """带记忆的对话示例"""
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.messages import HumanMessage, AIMessage
    from langchain_core.runnables.history import RunnableWithMessageHistory
    from langchain_community.chat_message_histories import ChatMessageHistory
    
    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
        model="gpt-5",
    )
    
    # 创建带历史记录的提示
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个友好的助手。"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}")
    ])
    
    chain = prompt | llm
    
    # 消息历史存储
    store = {}
    
    def get_session_history(session_id: str):
        if session_id not in store:
            store[session_id] = ChatMessageHistory()
        return store[session_id]
    
    # 带历史的可运行对象
    with_history = RunnableWithMessageHistory(
        chain,
        get_session_history,
        input_messages_key="input",
        history_messages_key="history",
    )
    
    # 模拟多轮对话
    config = {"configurable": {"session_id": "user123"}}
    
    print("带记忆的对话:")
    
    response1 = with_history.invoke(
        {"input": "我叫小明，我喜欢编程"},
        config=config
    )
    print(f"用户: 我叫小明，我喜欢编程")
    print(f"AI: {response1.content}\n")
    
    response2 = with_history.invoke(
        {"input": "你还记得我叫什么名字吗？"},
        config=config
    )
    print(f"用户: 你还记得我叫什么名字吗？")
    print(f"AI: {response2.content}")
    print("-" * 50)


# ============ 示例5: RAG (检索增强生成) ============
def example_rag():
    """RAG示例 - 使用文档问答"""
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.runnables import RunnablePassthrough
    
    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
        model="gpt-5",
    )
    
    # 模拟检索到的文档
    documents = """
    公司规定:
    1. 工作时间: 上午9点到下午6点
    2. 午休时间: 12点到13点
    3. 年假: 入职第一年10天，之后每年增加1天，最多20天
    4. 病假: 每年最多15天带薪病假
    5. 加班: 需要提前申请，每小时按1.5倍工资计算
    """
    
    # 创建RAG提示
    template = """基于以下上下文回答问题。如果上下文中没有相关信息，请说明无法回答。

上下文:
{context}

问题: {question}

回答:"""
    
    prompt = ChatPromptTemplate.from_template(template)
    
    # 创建RAG链
    chain = (
        {"context": lambda x: documents, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    
    # 提问
    questions = [
        "年假有多少天？",
        "加班费怎么算？",
        "工资是多少？"  # 这个问题在文档中没有答案
    ]
    
    print("RAG问答:")
    for q in questions:
        answer = chain.invoke(q)
        print(f"问: {q}")
        print(f"答: {answer}\n")
    print("-" * 50)


# ============ 示例6: 结构化输出 ============
def example_structured_output():
    """结构化输出示例"""
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser
    from pydantic import BaseModel, Field
    from typing import List
    
    # 定义输出结构
    class TaskAnalysis(BaseModel):
        task_name: str = Field(description="任务名称")
        priority: str = Field(description="优先级: high/medium/low")
        estimated_time: str = Field(description="预估时间")
        subtasks: List[str] = Field(description="子任务列表")
    
    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
        model="gpt-5",
    )
    
    parser = JsonOutputParser(pydantic_object=TaskAnalysis)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个项目管理助手。请分析用户的任务并以JSON格式输出。"),
        ("human", "请分析这个任务: {task}\n\n{format_instructions}")
    ])
    
    chain = prompt | llm | parser
    
    result = chain.invoke({
        "task": "开发一个用户登录功能",
        "format_instructions": parser.get_format_instructions()
    })
    
    print("结构化输出:")
    print(f"任务名称: {result.get('task_name')}")
    print(f"优先级: {result.get('priority')}")
    print(f"预估时间: {result.get('estimated_time')}")
    print(f"子任务: {result.get('subtasks')}")
    print("-" * 50)


# ============ 示例7: Agent (智能代理) ============
def example_agent():
    """Agent示例 - 使用工具"""
    from langchain_openai import ChatOpenAI
    from langchain.agents import create_react_agent, AgentExecutor
    from langchain_core.prompts import PromptTemplate
    from langchain_core.tools import tool
    
    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
        model="gpt-5",
    )
    
    # 定义工具
    @tool
    def calculator(expression: str) -> str:
        """计算数学表达式。输入应该是一个有效的数学表达式。"""
        try:
            result = eval(expression)
            return str(result)
        except:
            return "计算错误"
    
    @tool
    def get_current_weather(city: str) -> str:
        """获取城市天气。输入应该是城市名称。"""
        # 模拟天气数据
        weather_data = {
            "东京": "晴天，温度25°C",
            "大阪": "多云，温度23°C",
            "北京": "晴天，温度20°C",
        }
        return weather_data.get(city, f"{city}的天气数据暂不可用")
    
    tools = [calculator, get_current_weather]
    
    # Agent提示模板
    template = """你是一个有帮助的AI助手。你可以使用以下工具：

{tools}

使用以下格式:

Question: 用户的问题
Thought: 你需要做什么
Action: 要使用的工具名称，应该是以下之一: {tool_names}
Action Input: 工具的输入
Observation: 工具返回的结果
... (这个Thought/Action/Action Input/Observation可以重复多次)
Thought: 我现在知道最终答案了
Final Answer: 给用户的最终答案

开始!

Question: {input}
Thought: {agent_scratchpad}"""
    
    prompt = PromptTemplate.from_template(template)
    
    # 创建Agent
    agent = create_react_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    
    print("Agent示例:")
    result = agent_executor.invoke({
        "input": "东京现在天气怎么样？另外，123乘以456等于多少？"
    })
    print(f"最终答案: {result['output']}")
    print("-" * 50)


# ============ 主函数 ============
def main():
    """运行所有示例"""
    print("=" * 60)
    print("LangChain 集成示例")
    print("=" * 60)
    print()
    
    try:
        # 运行各个示例
        example_basic_chat()
        example_streaming()
        example_chain()
        example_with_memory()
        example_rag()
        example_structured_output()
        # example_agent()  # Agent示例比较复杂，可选运行
        
    except Exception as e:
        print(f"运行示例时出错: {e}")
        print("请确保API服务正在运行 (uvicorn app.main:app --port 8000)")


if __name__ == "__main__":
    main()
