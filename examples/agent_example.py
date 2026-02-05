"""
LangChain Agent 示例

功能：
- 定义多个工具（计算器、时间查询、文件读取等）
- Agent根据用户问题自动选择合适的工具
- 支持多轮对话和工具链式调用

依赖安装：
    pip install langchain langchain-openai langchainhub

运行前确保API服务已启动：
    start.bat api
"""
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import tool
from langchain import hub
from datetime import datetime


# ========== 1. 创建LLM ==========
llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
    model="gpt-5",
    temperature=0
)


# ========== 2. 定义工具 ==========

@tool
def calculator(expression: str) -> str:
    """计算数学表达式。输入应该是一个有效的数学表达式，如 '2 + 2' 或 '100 * 0.15'"""
    try:
        # 安全的数学计算（只允许数字和基本运算符）
        allowed_chars = set('0123456789+-*/.() ')
        if not all(c in allowed_chars for c in expression):
            return "错误：表达式包含非法字符"
        result = eval(expression)
        return f"计算结果: {expression} = {result}"
    except Exception as e:
        return f"计算错误: {e}"


@tool
def get_current_time() -> str:
    """获取当前时间。当用户询问现在几点或当前时间时使用。"""
    now = datetime.now()
    return f"当前时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')} (星期{['一','二','三','四','五','六','日'][now.weekday()]})"


@tool
def search_info(query: str) -> str:
    """搜索信息。当需要查找知识、新闻、天气等信息时使用此工具。"""
    # 模拟搜索结果（实际应用中可接入搜索API）
    mock_results = {
        "天气": "今天天气晴朗，温度15-22度，适合外出。空气质量良好。",
        "新闻": "今日热点新闻：1. 科技公司发布新产品 2. 股市表现平稳 3. 国际会议召开",
        "汇率": "今日汇率：1美元 = 7.2人民币，1欧元 = 7.8人民币，1日元 = 0.048人民币",
        "python": "Python是一种高级编程语言，以简洁易读著称，广泛用于Web开发、数据科学、AI等领域。",
    }

    query_lower = query.lower()
    for key, value in mock_results.items():
        if key in query_lower:
            return value
    return f"搜索 '{query}' 的结果：这是一个通用查询，建议参考官方文档或专业资料。"


@tool
def file_reader(filepath: str) -> str:
    """读取本地文件内容。输入文件的完整路径，返回文件内容。用于读取文本文件、配置文件等。"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if len(content) > 2000:
                content = content[:2000] + "\n...(内容过长，已截断)"
            return f"文件内容:\n{content}"
    except FileNotFoundError:
        return f"错误：文件不存在 - {filepath}"
    except PermissionError:
        return f"错误：没有权限读取文件 - {filepath}"
    except Exception as e:
        return f"读取文件错误: {e}"


@tool
def unit_converter(query: str) -> str:
    """单位转换工具。支持长度、重量、温度等单位转换。
    输入格式示例：'100 cm to m', '5 kg to g', '25 celsius to fahrenheit'"""
    try:
        parts = query.lower().replace('to', ' ').split()
        if len(parts) < 3:
            return "输入格式错误，请使用：'数值 原单位 to 目标单位'，如 '100 cm to m'"

        value = float(parts[0])
        from_unit = parts[1]
        to_unit = parts[-1]

        # 长度转换
        length_units = {
            'mm': 0.001, 'cm': 0.01, 'm': 1, 'km': 1000,
            'inch': 0.0254, 'ft': 0.3048, 'mile': 1609.34
        }

        # 重量转换
        weight_units = {
            'mg': 0.001, 'g': 1, 'kg': 1000,
            'oz': 28.3495, 'lb': 453.592
        }

        # 温度转换
        if from_unit in ['celsius', 'c'] and to_unit in ['fahrenheit', 'f']:
            result = value * 9/5 + 32
            return f"{value}°C = {result:.2f}°F"
        elif from_unit in ['fahrenheit', 'f'] and to_unit in ['celsius', 'c']:
            result = (value - 32) * 5/9
            return f"{value}°F = {result:.2f}°C"

        # 长度转换
        if from_unit in length_units and to_unit in length_units:
            meters = value * length_units[from_unit]
            result = meters / length_units[to_unit]
            return f"{value} {from_unit} = {result:.4f} {to_unit}"

        # 重量转换
        if from_unit in weight_units and to_unit in weight_units:
            grams = value * weight_units[from_unit]
            result = grams / weight_units[to_unit]
            return f"{value} {from_unit} = {result:.4f} {to_unit}"

        return f"不支持的单位转换: {from_unit} -> {to_unit}"

    except ValueError:
        return "数值格式错误，请输入有效的数字"
    except Exception as e:
        return f"转换错误: {e}"


# 工具列表
tools = [calculator, get_current_time, search_info, file_reader, unit_converter]


# ========== 3. 创建Agent ==========

def create_agent():
    """创建Agent执行器"""
    # 使用ReAct提示模板（推理+行动）
    # 这个模板会引导LLM进行思考、选择工具、执行、观察结果的循环
    prompt = hub.pull("hwchase17/react")

    # 创建Agent
    agent = create_react_agent(llm, tools, prompt)

    # 创建执行器
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,           # 显示详细的思考过程
        max_iterations=5,       # 最大迭代次数，防止无限循环
        handle_parsing_errors=True,  # 自动处理解析错误
        return_intermediate_steps=True  # 返回中间步骤
    )

    return agent_executor


# ========== 4. 交互式对话 ==========

def interactive_chat(agent_executor):
    """交互式对话"""
    print("\n" + "="*60)
    print("  LangChain Agent 交互模式")
    print("  - 可以询问时间、进行计算、搜索信息、读取文件等")
    print("  - 输入 'quit' 或 'exit' 退出")
    print("="*60 + "\n")

    while True:
        try:
            user_input = input("\n你: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("再见!")
                break

            print("\n" + "-"*40)
            result = agent_executor.invoke({"input": user_input})
            print("-"*40)
            print(f"\nAgent: {result['output']}")

        except KeyboardInterrupt:
            print("\n\n已中断")
            break
        except Exception as e:
            print(f"\n错误: {e}")


# ========== 5. 示例运行 ==========

def run_examples(agent_executor):
    """运行示例问题"""
    examples = [
        "现在几点了？",
        "帮我计算 (125 * 0.8 + 50) / 2 等于多少",
        "把 100 摄氏度转换成华氏度",
        "搜索一下今天的天气",
        "5公里等于多少英里？",
    ]

    print("\n" + "="*60)
    print("  Agent 示例演示")
    print("="*60)

    for question in examples:
        print(f"\n{'='*50}")
        print(f"问题: {question}")
        print('='*50)

        try:
            result = agent_executor.invoke({"input": question})
            print(f"\n答案: {result['output']}")
        except Exception as e:
            print(f"\n错误: {e}")

        print()


# ========== 主程序 ==========

if __name__ == "__main__":
    import sys

    print("正在初始化Agent...")
    agent_executor = create_agent()
    print("Agent初始化完成!")

    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        # 运行示例
        run_examples(agent_executor)
    else:
        # 交互模式
        interactive_chat(agent_executor)
