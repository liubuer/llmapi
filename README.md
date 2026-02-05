# 内部AI工具API

通过浏览器自动化将企业内部AI工具封装为OpenAI兼容API，解决企业认证问题。

---

## 目录

- [核心概念](#核心概念)
- [系统架构](#系统架构)
- [程序流程详解](#程序流程详解)
- [快速开始](#快速开始)
- [API使用](#api使用)
  - [Python / cURL](#python-openai-sdk)
  - [LangChain集成](#langchain-集成)
    - [Agent示例](#示例1-agent-工具调用)
    - [RAG示例](#示例2-rag-检索增强生成)
- [配置说明](#配置说明)
- [文件结构](#文件结构)
- [故障排除](#故障排除)
- [示例运行](#示例运行)

---

## 核心概念

### 解决的问题
企业内部AI工具需要SSO登录，每次关闭浏览器后需要重新认证。传统API调用方式无法绕过这个限制。

### 解决方案
采用**双进程架构**：
1. **长驻Edge进程**：启动带调试端口的Edge，手动完成登录后保持运行
2. **API服务进程**：通过CDP(Chrome DevTools Protocol)连接到已登录的Edge，复用认证会话

```
┌────────────────────────────────────────────────────────────────────┐
│                         系统架构总览                                 │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────┐         CDP协议          ┌──────────────────┐   │
│  │   客户端      │◄──────────────────────►│  Edge浏览器       │   │
│  │  (OpenAI SDK) │                         │ (已登录状态)      │   │
│  └──────┬───────┘                         └────────┬─────────┘   │
│         │                                          │              │
│         │ HTTP                                     │ 页面操作     │
│         ▼                                          ▼              │
│  ┌──────────────┐    acquire_session()    ┌──────────────────┐   │
│  │  FastAPI     │◄───────────────────────►│  EdgeManager     │   │
│  │  API服务     │                          │  (会话池管理)    │   │
│  └──────┬───────┘                         └──────────────────┘   │
│         │                                                         │
│         │ 调用                                                    │
│         ▼                                                         │
│  ┌──────────────┐      Playwright          ┌──────────────────┐   │
│  │  AIClient    │─────────────────────────►│  AI Web Tool     │   │
│  │  (网页交互)  │      自动化操作           │  (内部AI工具)    │   │
│  └──────────────┘                          └──────────────────┘   │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 系统架构

### 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **EdgeManager** | `app/edge_manager.py` | Edge进程管理、CDP连接、会话池 |
| **AIClient** | `app/ai_client.py` | 网页交互、消息发送、响应捕获 |
| **API Router** | `app/routers/chat.py` | OpenAI兼容API端点 |
| **Models** | `app/models.py` | Pydantic数据模型定义 |
| **Config** | `app/config.py` | 环境变量配置管理 |
| **Main** | `app/main.py` | FastAPI应用入口 |

### 模块依赖关系

```
main.py
   │
   ├──► edge_manager.py (启动时连接Edge)
   │         │
   │         └──► config.py (读取配置)
   │
   └──► routers/chat.py (注册路由)
              │
              └──► ai_client.py (处理请求)
                        │
                        ├──► edge_manager.py (获取会话)
                        └──► config.py (读取选择器配置)
```

---

## 程序流程详解

### 1. Edge启动流程

```
start.bat edge
      │
      ▼
edge_manager.py: cmd_start_edge()
      │
      ├─► start_edge_with_debug()
      │       │
      │       ├─► 获取Edge可执行文件路径
      │       ├─► 创建独立用户数据目录 ./edge_data
      │       └─► 启动Edge进程，参数:
      │             --remote-debugging-port=9222
      │             --user-data-dir=./edge_data
      │             --no-first-run
      │
      ├─► connect_to_edge()
      │       │
      │       └─► Playwright通过CDP连接
      │           chromium.connect_over_cdp("http://127.0.0.1:9222")
      │
      ├─► acquire_session() → 创建新页面
      │       │
      │       └─► page.goto(ai_tool_url) 打开AI工具
      │
      └─► 进入等待循环，保持Edge运行
```

### 2. API服务启动流程

```
start.bat api
      │
      ▼
main.py: lifespan()
      │
      ├─► edge_manager.connect_to_edge()
      │       │
      │       ├─► 启动Playwright
      │       ├─► 通过CDP连接到已运行的Edge
      │       ├─► 获取已有的BrowserContext
      │       └─► 设置 _connected = True
      │
      └─► 注册路由: chat_router (/v1/chat/completions)
```

### 3. 请求处理流程 (非流式)

```
POST /v1/chat/completions
      │
      ▼
routers/chat.py: chat_completions()
      │
      ├─► 创建 AIClient 实例
      │
      └─► client.chat(messages, model, stream=False)
                │
                ▼
          ai_client.py: chat()
                │
                ├─► edge_manager.acquire_session()
                │       │
                │       ├─► 检查会话池是否有空闲会话
                │       ├─► 如无，创建新页面 (最多3个)
                │       └─► 返回 BrowserSession (包含page对象)
                │
                ├─► _navigate_to_ai_tool(page)
                │       │
                │       └─► 检查URL，必要时跳转到AI工具页面
                │
                ├─► _find_input(page)
                │       │
                │       └─► 用选择器查找输入框 (textarea等)
                │
                ├─► _format_messages(messages)
                │       │
                │       └─► 将ChatMessage数组转为文本
                │           单条消息直接返回content
                │           多条消息添加 [系统指令]/[用户]/[助手] 前缀
                │
                ├─► [长文本处理] 如果 len(prompt) > 50000
                │       │
                │       ├─► _extract_question_and_content() 分离问题和资料
                │       ├─► _split_long_text() 分割为多块
                │       └─► _send_chunked_messages() 逐块发送
                │
                └─► _send_message(page, prompt)
                        │
                        ├─► input_box.click()
                        ├─► [短文本] input_box.fill(message)
                        │   [长文本] page.evaluate() JS注入
                        ├─► input_box.press("Control+Enter") 发送
                        │
                        └─► _wait_for_response(page)
                                │
                                ├─► 轮询检查响应元素
                                ├─► 过滤加载中状态
                                ├─► 等待内容稳定 (3次检查无变化)
                                └─► 返回响应文本
```

### 4. 请求处理流程 (流式)

```
POST /v1/chat/completions (stream=true)
      │
      ▼
返回 EventSourceResponse
      │
      └─► stream_response() 生成器
              │
              └─► client.chat(stream=True)
                      │
                      └─► _stream_response() 异步生成器
                              │
                              ├─► 轮询检查响应元素
                              ├─► 检测内容增量
                              │       │
                              │       └─► content[len(last_content):]
                              │
                              └─► yield delta (增量内容)
                                      │
                                      ▼
                              转换为SSE格式:
                              data: {"choices":[{"delta":{"content":"xxx"}}]}
```

### 5. 会话池管理

```
EdgeManager
      │
      ├─► _sessions: Dict[str, BrowserSession]
      │       │
      │       └─► 最多 max_sessions(默认3) 个会话
      │
      └─► acquire_session() 上下文管理器
              │
              ├─► 加锁 _session_lock
              ├─► 查找空闲会话 (is_busy=False)
              │       │
              │       ├─► 找到: 标记为busy，返回
              │       └─► 未找到且未达上限: 创建新会话
              │
              ├─► 如所有会话都忙，等待最多30秒
              │
              └─► try/finally 确保释放时 is_busy=False
```

### 6. 长文本分块处理

```
文本长度 > max_input_chars(50000)
      │
      ▼
_extract_question_and_content()
      │
      ├─► 识别问题标记: "问题："、"请回答："等
      └─► 分离为 (背景资料, 问题)
              │
              ▼
      _split_long_text(content, question)
              │
              ├─► 计算块数: total_chars / (chunk_size - 500)
              ├─► 在句子边界分割 (。！？.\n)
              │
              └─► 生成带模板的块:
                    块1: CHUNK_TEMPLATE_FIRST
                         "下面将输入约N字资料，分M次输入..."
                    块2~N-1: CHUNK_TEMPLATE_MIDDLE
                         "这是第X份资料..."
                    块N: CHUNK_TEMPLATE_LAST
                         "这是最后一份...请回答以下问题..."
                            │
                            ▼
              _send_chunked_messages()
                    │
                    ├─► 逐块发送，等待"已接收"确认
                    └─► 最后一块返回实际响应
```

---

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 启动Edge (终端1)
```bash
# Windows
start.bat edge

# Linux/Mac
./start.sh edge
```

在弹出的Edge中完成登录，**保持Edge运行**。

### 3. 启动API (终端2)
```bash
# Windows
start.bat api

# Linux/Mac
./start.sh api
```

### 4. 验证
```bash
curl http://localhost:8000/health
```

---

## API使用

### Python (OpenAI SDK)

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

# 非流式
response = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "你好"}]
)
print(response.choices[0].message.content)

# 流式
stream = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "写一首诗"}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### cURL

```bash
# 非流式
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5","messages":[{"role":"user","content":"你好"}]}'

# 流式
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5","messages":[{"role":"user","content":"你好"}],"stream":true}'
```

### API端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 服务信息 |
| `/health` | GET | 健康检查，返回Edge连接状态 |
| `/v1/chat/completions` | POST | OpenAI兼容聊天接口 |
| `/v1/models` | GET | 可用模型列表 |
| `/v1/debug/selectors` | GET | 调试端点，检查页面选择器 |

### LangChain 集成

由于本API兼容OpenAI格式，可以无缝集成LangChain生态。

#### 基础使用

```python
from langchain_openai import ChatOpenAI

# 创建LLM实例，指向本地API
llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
    model="gpt-5"
)

# 简单调用
response = llm.invoke("你好，请介绍一下你自己")
print(response.content)
```

#### 示例1: Agent (工具调用)

Agent可以根据用户输入自动选择和调用工具，实现复杂任务。

```python
"""
LangChain Agent 示例
- 定义多个工具（搜索、计算器、天气查询）
- Agent根据用户问题自动选择合适的工具
- 支持多轮对话和工具链式调用
"""
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool, tool
from langchain import hub
import requests

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
        # 安全的数学计算
        allowed_chars = set('0123456789+-*/.() ')
        if not all(c in allowed_chars for c in expression):
            return "错误：表达式包含非法字符"
        result = eval(expression)
        return f"计算结果: {expression} = {result}"
    except Exception as e:
        return f"计算错误: {e}"

@tool
def search_web(query: str) -> str:
    """搜索网络获取信息。当需要查找最新信息、新闻、事实时使用此工具。"""
    # 这里模拟搜索结果，实际应用中可接入搜索API
    mock_results = {
        "天气": "今天北京天气晴朗，温度15-22度，适合外出。",
        "新闻": "今日热点：科技公司发布新产品，股市表现平稳。",
        "default": f"搜索 '{query}' 的结果：找到相关信息若干条。"
    }
    for key, value in mock_results.items():
        if key in query:
            return value
    return mock_results["default"]

@tool
def get_current_time() -> str:
    """获取当前时间。当用户询问现在几点或当前时间时使用。"""
    from datetime import datetime
    now = datetime.now()
    return f"当前时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')}"

@tool
def file_reader(filepath: str) -> str:
    """读取本地文件内容。输入文件路径，返回文件内容。"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if len(content) > 1000:
                content = content[:1000] + "...(内容已截断)"
            return content
    except FileNotFoundError:
        return f"文件不存在: {filepath}"
    except Exception as e:
        return f"读取文件错误: {e}"

# 工具列表
tools = [calculator, search_web, get_current_time, file_reader]

# ========== 3. 创建Agent ==========

# 使用ReAct提示模板（推理+行动）
prompt = hub.pull("hwchase17/react")

# 创建Agent
agent = create_react_agent(llm, tools, prompt)

# 创建执行器
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,      # 显示思考过程
    max_iterations=5,  # 最大迭代次数
    handle_parsing_errors=True
)

# ========== 4. 运行Agent ==========

if __name__ == "__main__":
    # 测试不同类型的问题
    questions = [
        "现在几点了？",
        "帮我计算一下 125 * 0.8 + 50 等于多少",
        "搜索一下今天的天气情况",
        "我想知道现在的时间，然后帮我计算 24 - 当前小时数"
    ]

    for q in questions:
        print(f"\n{'='*50}")
        print(f"问题: {q}")
        print('='*50)
        result = agent_executor.invoke({"input": q})
        print(f"\n答案: {result['output']}")
```

**Agent执行流程:**

```
用户问题: "帮我计算 125 * 0.8 + 50"
      │
      ▼
Agent思考 (Thought)
      │ "用户需要计算数学表达式，我应该使用calculator工具"
      ▼
选择工具 (Action): calculator
      │
      ▼
执行工具 (Action Input): "125 * 0.8 + 50"
      │
      ▼
获取结果 (Observation): "计算结果: 125 * 0.8 + 50 = 150.0"
      │
      ▼
生成回答 (Final Answer): "125 * 0.8 + 50 的计算结果是 150"
```

#### 示例2: RAG (检索增强生成)

RAG通过向量数据库存储文档，在回答问题时检索相关内容，提高回答准确性。

```python
"""
LangChain RAG 示例
- 使用Chroma向量数据库存储文档
- 文档切分和向量化
- 检索增强生成回答
"""
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from langchain_community.document_loaders import (
    TextLoader,
    DirectoryLoader,
    PyPDFLoader
)
import os

# ========== 1. 配置 ==========

# LLM配置
llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
    model="gpt-5",
    temperature=0
)

# Embedding模型配置
# 注意：本地API可能不支持embeddings，这里使用替代方案

# 方案A: 使用HuggingFace本地Embedding（推荐，无需外部API）
from langchain_community.embeddings import HuggingFaceEmbeddings
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)

# 方案B: 如果有OpenAI API Key，可以使用OpenAI Embedding
# embeddings = OpenAIEmbeddings(
#     api_key="your-openai-api-key",
#     model="text-embedding-3-small"
# )

# 向量数据库存储路径
CHROMA_PATH = "./chroma_db"

# ========== 2. 文档加载与处理 ==========

def load_documents(source_path: str):
    """加载文档"""
    documents = []

    if os.path.isfile(source_path):
        # 单个文件
        if source_path.endswith('.pdf'):
            loader = PyPDFLoader(source_path)
        else:
            loader = TextLoader(source_path, encoding='utf-8')
        documents = loader.load()
    elif os.path.isdir(source_path):
        # 目录下所有文件
        # 加载txt文件
        txt_loader = DirectoryLoader(
            source_path,
            glob="**/*.txt",
            loader_cls=TextLoader,
            loader_kwargs={'encoding': 'utf-8'}
        )
        documents.extend(txt_loader.load())

        # 加载pdf文件
        pdf_loader = DirectoryLoader(
            source_path,
            glob="**/*.pdf",
            loader_cls=PyPDFLoader
        )
        documents.extend(pdf_loader.load())

    return documents

def split_documents(documents, chunk_size=1000, chunk_overlap=200):
    """文档切分"""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", "。", "！", "？", ".", " ", ""]
    )
    return text_splitter.split_documents(documents)

# ========== 3. 向量数据库操作 ==========

def create_vectorstore(documents, persist_directory=CHROMA_PATH):
    """创建向量数据库"""
    # 切分文档
    chunks = split_documents(documents)
    print(f"文档切分完成，共 {len(chunks)} 个片段")

    # 创建向量数据库
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_directory
    )
    print(f"向量数据库已创建: {persist_directory}")
    return vectorstore

def load_vectorstore(persist_directory=CHROMA_PATH):
    """加载已有的向量数据库"""
    return Chroma(
        persist_directory=persist_directory,
        embedding_function=embeddings
    )

# ========== 4. RAG链构建 ==========

def create_rag_chain(vectorstore, k=3):
    """创建RAG问答链"""

    # 检索器配置
    retriever = vectorstore.as_retriever(
        search_type="similarity",  # 相似度搜索
        search_kwargs={"k": k}     # 返回top-k个结果
    )

    # 自定义提示模板
    prompt_template = """基于以下已知信息，简洁和专业地回答用户的问题。
如果无法从中得到答案，请说"根据已知信息无法回答该问题"，不要编造答案。

已知信息:
{context}

问题: {question}

回答:"""

    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["context", "question"]
    )

    # 创建问答链
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",  # 将所有检索到的文档放入一个prompt
        retriever=retriever,
        return_source_documents=True,  # 返回源文档
        chain_type_kwargs={"prompt": prompt}
    )

    return qa_chain

# ========== 5. 完整RAG应用 ==========

class RAGApplication:
    """RAG应用封装"""

    def __init__(self, persist_directory=CHROMA_PATH):
        self.persist_directory = persist_directory
        self.vectorstore = None
        self.qa_chain = None

    def index_documents(self, source_path: str):
        """索引文档"""
        print(f"正在加载文档: {source_path}")
        documents = load_documents(source_path)
        print(f"加载了 {len(documents)} 个文档")

        self.vectorstore = create_vectorstore(
            documents,
            self.persist_directory
        )
        self.qa_chain = create_rag_chain(self.vectorstore)
        print("索引完成!")

    def load_index(self):
        """加载已有索引"""
        if os.path.exists(self.persist_directory):
            self.vectorstore = load_vectorstore(self.persist_directory)
            self.qa_chain = create_rag_chain(self.vectorstore)
            print("已加载现有索引")
        else:
            print("索引不存在，请先调用 index_documents()")

    def query(self, question: str) -> dict:
        """查询"""
        if not self.qa_chain:
            raise ValueError("请先索引文档或加载索引")

        result = self.qa_chain.invoke({"query": question})

        return {
            "answer": result["result"],
            "sources": [
                {
                    "content": doc.page_content[:200] + "...",
                    "metadata": doc.metadata
                }
                for doc in result["source_documents"]
            ]
        }

    def add_documents(self, source_path: str):
        """追加文档到现有索引"""
        if not self.vectorstore:
            self.load_index()

        documents = load_documents(source_path)
        chunks = split_documents(documents)
        self.vectorstore.add_documents(chunks)
        print(f"已追加 {len(chunks)} 个文档片段")

# ========== 6. 使用示例 ==========

if __name__ == "__main__":
    # 初始化RAG应用
    rag = RAGApplication()

    # 示例1: 索引本地文档目录
    # rag.index_documents("./documents")

    # 示例2: 索引单个文件
    # rag.index_documents("./documents/manual.pdf")

    # 示例3: 使用示例文本创建索引
    from langchain.schema import Document

    sample_docs = [
        Document(
            page_content="""
            公司员工手册 - 第一章：考勤制度

            1. 工作时间：周一至周五，上午9:00-12:00，下午13:00-18:00
            2. 迟到定义：超过9:15到达视为迟到
            3. 请假流程：提前一天在OA系统提交申请，由直属上级审批
            4. 年假规定：入职满一年后享有5天年假，每增加一年工龄增加1天
            5. 加班规定：加班需提前申请，工作日加班按1.5倍计算，周末按2倍计算
            """,
            metadata={"source": "employee_handbook.txt", "chapter": "考勤制度"}
        ),
        Document(
            page_content="""
            公司员工手册 - 第二章：报销制度

            1. 差旅报销：需在出差结束后5个工作日内提交
            2. 交通费：市内交通每日上限100元，需保留发票
            3. 住宿费：一线城市每晚上限500元，其他城市300元
            4. 餐饮费：每日上限150元，需保留发票
            5. 报销流程：填写报销单 → 部门经理审批 → 财务审核 → 打款
            """,
            metadata={"source": "employee_handbook.txt", "chapter": "报销制度"}
        ),
        Document(
            page_content="""
            公司员工手册 - 第三章：福利制度

            1. 五险一金：按国家规定缴纳
            2. 补充医疗：公司为员工购买补充医疗保险
            3. 节日福利：春节、中秋等节日发放礼品或购物卡
            4. 生日福利：生日当月发放200元生日礼金
            5. 团建活动：每季度组织一次团队活动
            6. 培训机会：每年可申请外部培训，公司承担费用上限5000元
            """,
            metadata={"source": "employee_handbook.txt", "chapter": "福利制度"}
        )
    ]

    # 创建索引
    rag.vectorstore = Chroma.from_documents(
        documents=sample_docs,
        embedding=embeddings,
        persist_directory=CHROMA_PATH
    )
    rag.qa_chain = create_rag_chain(rag.vectorstore)
    print("示例文档索引完成!")

    # 查询测试
    questions = [
        "公司的工作时间是几点到几点？",
        "年假是怎么规定的？",
        "出差住宿费的标准是多少？",
        "公司有哪些福利？"
    ]

    for q in questions:
        print(f"\n{'='*50}")
        print(f"问题: {q}")
        print('='*50)
        result = rag.query(q)
        print(f"回答: {result['answer']}")
        print(f"\n参考来源:")
        for i, source in enumerate(result['sources'], 1):
            print(f"  {i}. [{source['metadata'].get('chapter', 'N/A')}] {source['content'][:50]}...")
```

**RAG工作流程:**

```
┌─────────────────────────────────────────────────────────────────┐
│                         文档索引阶段                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  文档 (PDF/TXT/...)                                            │
│       │                                                        │
│       ▼                                                        │
│  ┌─────────────┐                                               │
│  │ 文档加载器   │  TextLoader / PyPDFLoader                     │
│  └──────┬──────┘                                               │
│         │                                                      │
│         ▼                                                      │
│  ┌─────────────┐                                               │
│  │ 文档切分器   │  RecursiveCharacterTextSplitter              │
│  └──────┬──────┘  chunk_size=1000, overlap=200                 │
│         │                                                      │
│         ▼                                                      │
│  ┌─────────────┐                                               │
│  │ Embedding   │  HuggingFaceEmbeddings                        │
│  │ 向量化      │  文本 → 768维向量                              │
│  └──────┬──────┘                                               │
│         │                                                      │
│         ▼                                                      │
│  ┌─────────────┐                                               │
│  │ Chroma DB   │  向量数据库存储                                │
│  │ 向量存储    │  persist_directory="./chroma_db"              │
│  └─────────────┘                                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         查询阶段                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  用户问题: "年假是怎么规定的？"                                   │
│       │                                                        │
│       ▼                                                        │
│  ┌─────────────┐                                               │
│  │ Embedding   │  问题向量化                                    │
│  └──────┬──────┘                                               │
│         │                                                      │
│         ▼                                                      │
│  ┌─────────────┐      相似度搜索                               │
│  │ Retriever   │ ─────────────────►  Chroma DB                │
│  └──────┬──────┘      top-k=3                                 │
│         │                                                      │
│         │  检索到的相关文档片段                                 │
│         ▼                                                      │
│  ┌─────────────────────────────────────────────┐               │
│  │ Prompt Template                              │               │
│  │                                              │               │
│  │ 已知信息:                                    │               │
│  │ {检索到的文档内容}                            │               │
│  │                                              │               │
│  │ 问题: {用户问题}                              │               │
│  └──────────────────────┬──────────────────────┘               │
│                         │                                      │
│                         ▼                                      │
│                  ┌─────────────┐                               │
│                  │    LLM      │  本地API (gpt-5)              │
│                  └──────┬──────┘                               │
│                         │                                      │
│                         ▼                                      │
│                   生成回答 + 源文档引用                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### LangChain 依赖安装

```bash
# 基础依赖
pip install langchain langchain-openai langchain-community

# Agent相关
pip install langchainhub

# RAG相关 (向量数据库)
pip install chromadb sentence-transformers

# 文档加载器
pip install pypdf  # PDF支持
pip install unstructured  # 更多格式支持
```

---

## 配置说明

通过 `.env` 文件或环境变量配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AI_TOOL_URL` | `https://taa.xxx.co.jp` | 内部AI工具URL |
| `EDGE_DEBUG_PORT` | `9222` | Edge CDP调试端口 |
| `MAX_SESSIONS` | `3` | 最大并发会话数 |
| `RESPONSE_TIMEOUT` | `120` | 响应超时(秒) |
| `MAX_INPUT_CHARS` | `50000` | 单次输入最大字符数 |
| `CHUNK_SIZE` | `45000` | 长文本分块大小 |
| `API_HOST` | `0.0.0.0` | API监听地址 |
| `API_PORT` | `8000` | API监听端口 |
| `SELECTOR_INPUT` | `textarea, ...` | 输入框CSS选择器 |
| `SELECTOR_RESPONSE` | `div[class*='response'], ...` | 响应区域CSS选择器 |
| `SELECTOR_LOADING` | `div[class*='loading'], ...` | 加载状态CSS选择器 |

---

## 文件结构

```
internal-llm-api/
│
├── app/                          # 应用主目录
│   ├── __init__.py
│   ├── main.py                   # FastAPI应用入口
│   │                               - lifespan: 启动时连接Edge
│   │                               - /health, / 端点
│   │
│   ├── edge_manager.py           # Edge进程管理 (核心)
│   │                               - EdgeManager: 单例模式
│   │                               - start_edge_with_debug(): 启动Edge
│   │                               - connect_to_edge(): CDP连接
│   │                               - acquire_session(): 获取会话
│   │                               - BrowserSession: 会话数据类
│   │                               - CLI命令: start, status, all
│   │
│   ├── ai_client.py              # AI网页交互
│   │                               - AIClient: 网页操作封装
│   │                               - chat(): 主入口
│   │                               - _send_message(): 发送消息
│   │                               - _stream_response(): 流式响应
│   │                               - _split_long_text(): 长文本分割
│   │                               - CHUNK_TEMPLATE_*: 分块模板
│   │
│   ├── config.py                 # 配置管理
│   │                               - Settings: Pydantic配置类
│   │                               - 从.env加载配置
│   │
│   ├── models.py                 # 数据模型
│   │                               - ChatMessage, ChatCompletionRequest
│   │                               - ChatCompletionResponse, Usage
│   │                               - OpenAI API兼容格式
│   │
│   └── routers/                  # API路由
│       ├── __init__.py
│       └── chat.py               # 聊天API
│                                   - /v1/chat/completions
│                                   - /v1/models
│                                   - /v1/debug/selectors
│
├── examples/                     # 使用示例
│   ├── demo.py                   # 基础使用示例
│   ├── agent_example.py          # LangChain Agent示例
│   │                               - 多工具定义(计算器/搜索/时间等)
│   │                               - ReAct Agent自动选择工具
│   │                               - 交互式对话模式
│   │
│   └── rag_example.py            # LangChain RAG示例
│                                   - Chroma向量数据库
│                                   - 文档加载/切分/向量化
│                                   - 检索增强问答
│
├── edge_data/                    # Edge用户数据目录 (自动创建)
├── chroma_db/                    # 向量数据库目录 (RAG示例创建)
├── debug/                        # 调试截图目录
├── logs/                         # 日志目录
│
├── start.bat                     # Windows启动脚本
├── start.sh                      # Linux/Mac启动脚本
├── requirements.txt              # Python依赖
├── .env                          # 环境变量配置
└── README.md                     # 本文档
```

---

## 故障排除

### Edge连接失败

```bash
# 检查状态
start.bat status

# 手动检查CDP端口
curl http://127.0.0.1:9222/json/version
```

确认:
- Edge进程正在运行
- 端口9222未被占用
- 防火墙未阻止

### 登录过期

直接在Edge浏览器中重新登录，API服务会自动使用新会话，无需重启。

### 响应超时

1. 检查 `.env` 中 `RESPONSE_TIMEOUT` 设置
2. 检查 `SELECTOR_RESPONSE` 是否匹配页面元素
3. 使用 `/v1/debug/selectors` 端点调试选择器

### 长文本发送失败

1. 检查 `MAX_INPUT_CHARS` 和 `CHUNK_SIZE` 配置
2. 确认AI工具能正确处理分块提示词

### 调试模式

错误时会在 `./debug/` 目录保存截图，用于诊断页面状态。

---

## 示例运行

### 运行Agent示例

```bash
# 安装依赖
pip install langchain langchain-openai langchainhub

# 交互模式
python examples/agent_example.py

# 演示模式
python examples/agent_example.py --demo
```

### 运行RAG示例

```bash
# 安装依赖
pip install langchain langchain-openai langchain-community
pip install chromadb sentence-transformers

# 交互模式（首次运行会创建示例索引）
python examples/rag_example.py

# 演示模式
python examples/rag_example.py --demo

# 索引自己的文档
python examples/rag_example.py --index ./my_documents

# 追加文档到已有索引
python examples/rag_example.py --add ./new_document.txt
```
