# 社内AI工具API

> 通过浏览器自动化，将企业内部AI工具封装为与OpenAI兼容的API接口。
> 即使企业AI工具需要SSO登录认证，也可以像调用OpenAI API一样方便地调用。

---

## 目录

- [它是做什么的？](#它是做什么的)
- [前提条件](#前提条件)
- [快速上手（一步步跟着做）](#快速上手一步步跟着做)
- [验证服务是否正常](#验证服务是否正常)
- [使用方法](#使用方法)
  - [用Python调用](#用python调用)
  - [用cURL调用](#用curl调用)
  - [用LangChain调用](#用langchain调用)
- [文件对话工具（Streamlit UI）](#文件对话工具streamlit-ui)
- [LangChain高级示例](#langchain高级示例)
  - [Agent示例（自动调用工具）](#agent示例自动调用工具)
  - [RAG示例（知识库问答）](#rag示例知识库问答)
- [API接口列表](#api接口列表)
- [配置说明](#配置说明)
- [系统架构（了解原理）](#系统架构了解原理)
- [项目文件结构](#项目文件结构)
- [常见问题与解决方法](#常见问题与解决方法)

---

## 它是做什么的？

### 遇到的问题

企业内部AI工具需要通过浏览器登录（SSO认证），每次关闭浏览器后都要重新登录。这意味着我们无法像调用OpenAI API那样，在代码中直接使用它。

### 这个工具如何解决

本工具采用"两个进程"配合工作的方式：

1. **Edge浏览器进程**：打开Edge浏览器并登录一次，然后保持浏览器不关闭
2. **API服务进程**：通过浏览器调试协议（CDP）连接到已登录的Edge，帮你自动操作网页

这样一来，你的代码只需要调用 `http://localhost:8000/v1/chat/completions`，就像调用OpenAI API一样：

```
你的代码 → API服务 → Edge浏览器（已登录）→ AI工具网页
```

---

## 前提条件

在开始之前，请确保你的电脑上已安装以下软件：

| 软件 | 说明 | 安装方法 |
|------|------|----------|
| **Python 3.9+** | 编程语言 | 从 [python.org](https://www.python.org/downloads/) 下载安装 |
| **pip** | Python包管理器 | Python安装时会自动附带 |
| **Microsoft Edge** | 浏览器 | Windows系统自带，[下载地址](https://www.microsoft.com/edge) |
| **Git**（可选） | 版本管理工具 | 从 [git-scm.com](https://git-scm.com/) 下载安装 |

> **如何验证Python已安装？** 打开命令行/终端，输入 `python --version`，如果显示版本号（如 `Python 3.11.5`）就说明已安装。

---

## 快速上手（一步步跟着做）

### 第1步：下载项目代码

```bash
# 方法一：用Git克隆（推荐）
git clone <仓库地址>
cd internal-llm-api

# 方法二：直接下载ZIP解压，然后进入项目目录
cd internal-llm-api
```

### 第2步：安装依赖

**Windows用户：**
```bash
start.bat install
```

**Mac/Linux用户：**
```bash
chmod +x start.sh
./start.sh install
```

**或者手动安装：**
```bash
pip install -r requirements.txt
playwright install chromium
```

> **安装遇到问题？** 确认你的网络能正常访问pip源。如果下载慢，可以使用国内镜像：
> ```bash
> pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

### 第3步：配置环境变量（可选但推荐）

复制示例配置文件：
```bash
# Windows
copy .env.example .env

# Mac/Linux
cp .env.example .env
```

打开 `.env` 文件，根据实际情况修改：
```
# AI工具的网址
AI_TOOL_URL=https://taa.xxx.co.jp
```

> 如果不创建 `.env` 文件，程序会使用默认配置。

### 第4步：启动服务

你有**两种启动方式**可以选择：

#### 方式一：一键启动（推荐，只需一个终端窗口）

```bash
# Windows
start.bat all

# Mac/Linux（需在start.sh中添加all命令）
```

执行后会自动打开Edge浏览器。请在Edge中完成登录，**登录完成后回到终端按Enter键**，API服务就会自动启动。

#### 方式二：分步启动（需要两个终端窗口）

**终端窗口1 - 启动Edge浏览器：**
```bash
# Windows
start.bat edge

# Mac/Linux
./start.sh edge
```
等Edge打开后，在浏览器中完成登录。**登录后不要关闭Edge，保持它运行。**

**终端窗口2 - 启动API服务（新开一个终端）：**
```bash
# Windows
start.bat api

# Mac/Linux
./start.sh api
```

### 第5步：验证一切正常

打开一个新的终端窗口，执行：
```bash
curl http://localhost:8000/health
```

如果看到类似以下的输出，说明服务已正常运行：
```json
{"status": "ok", "edge_connected": true, "sessions": {"active": 0, "max": 3}}
```

**恭喜！API服务已经启动成功了！** 🎉

---

## 验证服务是否正常

```bash
# 检查服务状态
start.bat status

# 或直接访问
curl http://localhost:8000/health

# 手动检查Edge调试端口
curl http://127.0.0.1:9222/json/version
```

---

## 使用方法

### 用Python调用

首先安装OpenAI SDK（如果还没装的话）：
```bash
pip install openai
```

#### 基本调用（等待完整响应）

```python
from openai import OpenAI

# 创建客户端，指向本地API
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"  # 不需要API Key
)

# 发送消息
response = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "你好，请介绍一下你自己"}]
)

# 打印回复
print(response.choices[0].message.content)
```

#### 流式调用（逐字输出，像打字一样）

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

stream = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "写一首关于春天的诗"}],
    stream=True  # 开启流式输出
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # 输出完毕换行
```

#### 多轮对话

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

# 通过 extra_body 使用会话管理
response = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "你好"}],
    extra_body={"new_conversation": True}  # 开始新对话
)
print(response.choices[0].message.content)

# 获取 conversation_id 用于后续对话
conv_id = response.conversation_id  # 或从 model_extra 中获取
```

### 用cURL调用

```bash
# 基本调用
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5","messages":[{"role":"user","content":"你好"}]}'

# 流式调用
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5","messages":[{"role":"user","content":"你好"}],"stream":true}'
```

### 用LangChain调用

```python
from langchain_openai import ChatOpenAI

# 创建LLM实例
llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
    model="gpt-5"
)

# 调用
response = llm.invoke("你好，请介绍一下你自己")
print(response.content)
```

> 需要先安装LangChain依赖：`pip install langchain langchain-openai`

---

## 文件对话工具（Streamlit UI）

项目自带了一个图形界面的文件对话工具，可以上传文件（PDF、Word、Excel、TXT等），然后与AI针对文件内容进行对话。

### 安装额外依赖

```bash
pip install -r tools/requirements.txt
```

这会安装以下组件：
- `streamlit` - Web界面框架
- `PyMuPDF` - PDF文件读取
- `python-docx` - Word文件读取
- `openpyxl` - Excel文件读取

### 启动文件对话工具

```bash
streamlit run tools/file_chat.py
```

浏览器会自动打开（默认地址 `http://localhost:8501`），你会看到一个可视化界面：

1. **左侧栏**：上传文件、选择模型、设置系统提示词
2. **主界面**：与AI对话，提问关于文件的问题

### 支持的文件格式

| 格式 | 说明 |
|------|------|
| `.txt`, `.md`, `.log` | 纯文本文件 |
| `.json` | JSON文件（自动格式化显示） |
| `.pdf` | PDF文档 |
| `.docx` | Word文档 |
| `.xlsx`, `.xls` | Excel表格 |
| `.csv` | CSV表格 |
| `.xml`, `.html` | 标记语言文件 |
| `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg` | 配置文件 |
| `.py`, `.js`, `.ts`, `.java`, `.sql`, `.sh`, `.bat` | 源代码文件 |

---

## LangChain高级示例

### Agent示例（自动调用工具）

Agent可以根据你的问题自动选择合适的工具来回答。例如问"现在几点？"它会调用时间工具，问"125 * 0.8 + 50等于多少？"它会调用计算器工具。

#### 安装依赖

```bash
pip install langchain langchain-openai langchainhub
```

#### 运行

```bash
# 交互模式（对话式）
python examples/agent_example.py

# 演示模式（自动运行预设问题）
python examples/agent_example.py --demo
```

#### Agent工作原理

```
用户问题："帮我计算 125 * 0.8 + 50"
    ↓
Agent思考：用户需要计算，应该使用计算器工具
    ↓
调用工具：calculator("125 * 0.8 + 50")
    ↓
获取结果：150.0
    ↓
生成回答："125 * 0.8 + 50 的计算结果是 150"
```

### RAG示例（知识库问答）

RAG（检索增强生成）可以让AI基于你提供的文档来回答问题，而不是凭"记忆"。适用于企业知识库、内部文档问答等场景。

#### 安装依赖

```bash
pip install langchain langchain-openai langchain-community
pip install chromadb sentence-transformers
pip install pypdf  # 可选，用于PDF支持
```

> 首次运行时会自动下载Embedding模型（约500MB），请耐心等待。

#### 运行

```bash
# 交互模式（首次会自动创建示例索引）
python examples/rag_example.py

# 演示模式（自动运行预设问题）
python examples/rag_example.py --demo

# 索引自己的文档
python examples/rag_example.py --index ./my_documents

# 向已有索引追加文档
python examples/rag_example.py --add ./new_document.txt
```

#### RAG工作原理

```
第一阶段：建立索引
  你的文档 → 切分成小段 → 转成向量 → 存入向量数据库

第二阶段：问答
  用户提问 → 在向量数据库中搜索相关段落 → 将问题+相关段落一起发给AI → AI生成回答
```

---

## API接口列表

| 接口地址 | HTTP方法 | 说明 |
|---------|----------|------|
| `/` | GET | 查看服务基本信息 |
| `/health` | GET | 健康检查，查看Edge连接状态和会话数 |
| `/v1/chat/completions` | POST | **核心接口** - OpenAI兼容的聊天接口 |
| `/v1/models` | GET | 查看可用模型列表 |
| `/v1/conversations` | GET | 查看当前活跃的对话会话 |
| `/v1/debug/selectors` | GET | 调试用 - 检查页面CSS选择器匹配情况 |

### /v1/chat/completions 请求格式

```json
{
    "model": "gpt-5",
    "messages": [
        {"role": "system", "content": "你是一个有用的助手"},
        {"role": "user", "content": "你好"}
    ],
    "stream": false,
    "new_conversation": true,
    "conversation_id": "可选-用于继续之前的对话"
}
```

可选字段：
- `stream`：设为 `true` 启用流式输出（默认 `false`）
- `new_conversation`：设为 `true` 开始新对话
- `conversation_id`：指定对话ID以继续之前的对话

---

## 配置说明

通过项目根目录下的 `.env` 文件配置（复制 `.env.example` 然后修改）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `AI_TOOL_URL` | `https://taa.xxx.co.jp` | 你们公司AI工具的网址 |
| `EDGE_DEBUG_PORT` | `9222` | Edge浏览器的调试端口 |
| `MAX_SESSIONS` | `3` | 最大同时会话数（一般不需要改） |
| `RESPONSE_TIMEOUT` | `120` | AI回复超时时间（秒） |
| `MAX_INPUT_CHARS` | `50000` | 单次输入最大字符数 |
| `CHUNK_SIZE` | `45000` | 超长文本分块大小 |
| `API_HOST` | `0.0.0.0` | API服务监听地址 |
| `API_PORT` | `8000` | API服务端口号 |
| `SELECTOR_INPUT` | `textarea, ...` | 输入框的CSS选择器 |
| `SELECTOR_SEND_BUTTON` | `button[type='submit'], ...` | 发送按钮的CSS选择器 |
| `SELECTOR_RESPONSE` | `div[class*='response'], ...` | 回复区域的CSS选择器 |
| `SELECTOR_LOADING` | `div[class*='loading'], ...` | 加载中状态的CSS选择器 |

---

## 系统架构（了解原理）

### 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                        系统架构                               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  你的代码                              Edge浏览器             │
│  (OpenAI SDK/cURL/LangChain)          (已登录的状态)          │
│       │                                    ▲                 │
│       │ HTTP请求                           │ 自动操作网页     │
│       ▼                                    │                 │
│  ┌──────────────┐                    ┌──────────────┐       │
│  │  FastAPI     │  获取浏览器会话    │ EdgeManager  │       │
│  │  API服务     │◄──────────────────►│ (会话池管理) │       │
│  └──────┬───────┘                    └──────────────┘       │
│         │                                                    │
│         │ 调用                                               │
│         ▼                                                    │
│  ┌──────────────┐     Playwright     ┌──────────────┐       │
│  │  AIClient    │────────────────────►│  AI网页工具  │       │
│  │  (网页交互)  │    浏览器自动化     │  (内部工具)  │       │
│  └──────────────┘                    └──────────────┘       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 核心模块说明

| 模块 | 文件 | 作用 |
|------|------|------|
| **EdgeManager** | `app/edge_manager.py` | 管理Edge浏览器进程，处理CDP连接和会话池 |
| **AIClient** | `app/ai_client.py` | 与AI网页交互：发送消息、接收回复、处理超长文本分块 |
| **API Router** | `app/routers/chat.py` | 提供OpenAI兼容的API接口 |
| **Models** | `app/models.py` | 数据模型定义（请求/响应格式） |
| **Config** | `app/config.py` | 从 `.env` 文件读取配置 |
| **Main** | `app/main.py` | FastAPI应用入口 |
| **File Reader** | `tools/file_reader.py` | 多格式文件内容提取（PDF、Word、Excel等） |
| **File Chat** | `tools/file_chat.py` | Streamlit图形界面的文件对话工具 |

### 请求处理流程

```
1. 你的代码发送请求 → POST /v1/chat/completions

2. API服务收到请求
     ↓
3. 从EdgeManager获取一个空闲的浏览器会话
     ↓
4. AIClient在浏览器中操作：
   a. 找到输入框
   b. 输入消息（短文本直接输入，长文本用JS注入）
   c. 按Ctrl+Enter发送
   d. 等待AI回复（轮询检查直到回复稳定）
     ↓
5. 返回回复给你的代码
```

### 超长文本处理

当输入超过50,000字符时，系统会自动分块发送：

```
超长文本 → 分成多块 → 逐块发送，每块等AI确认"已收到" → 最后一块附带你的问题
```

---

## 项目文件结构

```
internal-llm-api/
│
├── app/                          # 核心应用代码
│   ├── __init__.py
│   ├── main.py                   # FastAPI应用入口
│   ├── edge_manager.py           # Edge浏览器进程管理（核心）
│   ├── ai_client.py              # AI网页交互逻辑（核心）
│   ├── config.py                 # 配置管理
│   ├── models.py                 # 数据模型
│   └── routers/
│       ├── __init__.py
│       └── chat.py               # 聊天API路由
│
├── examples/                     # 使用示例
│   ├── demo.py                   # 基础使用示例
│   ├── agent_example.py          # LangChain Agent示例
│   └── rag_example.py            # LangChain RAG示例
│
├── tools/                        # 附加工具
│   ├── file_reader.py            # 多格式文件读取工具
│   ├── file_chat.py              # 文件对话Streamlit界面
│   └── requirements.txt          # 工具的额外依赖
│
├── edge_data/                    # Edge用户数据（自动创建）
├── chroma_db/                    # 向量数据库（RAG示例创建）
├── debug/                        # 调试截图（出错时自动保存）
├── logs/                         # 日志文件
│
├── start.bat                     # Windows启动脚本
├── start.sh                      # Mac/Linux启动脚本
├── requirements.txt              # Python依赖清单
├── .env.example                  # 环境变量配置模板
├── .env                          # 实际环境变量配置（需自行创建）
└── README.md                     # 本文档
```

---

## 常见问题与解决方法

### Q: Edge连接失败怎么办？

**排查步骤：**
1. 检查Edge是否正在运行
   ```bash
   start.bat status
   ```
2. 检查CDP端口是否正常
   ```bash
   curl http://127.0.0.1:9222/json/version
   ```
3. 确认端口9222没有被其他程序占用
4. 确认防火墙没有阻止9222端口

### Q: 登录过期了怎么办？

直接在Edge浏览器中重新登录即可。API服务会自动使用新的会话，**不需要重启API服务**。

### Q: AI回复超时怎么办？

1. 在 `.env` 中增大 `RESPONSE_TIMEOUT` 的值（默认120秒）
2. 检查 `SELECTOR_RESPONSE` 是否能匹配到页面上的回复元素
3. 访问 `http://localhost:8000/v1/debug/selectors` 查看选择器匹配情况

### Q: 发送长文本失败怎么办？

1. 检查 `.env` 中的 `MAX_INPUT_CHARS` 和 `CHUNK_SIZE` 配置
2. 确认AI工具能正确理解分块发送的提示词（系统会自动提示AI逐块接收）

### Q: 启动时报 "端口已被占用"？

说明已经有一个Edge或API服务在运行了。你可以：
```bash
# 查找占用端口的进程（Windows）
netstat -ano | findstr :9222
netstat -ano | findstr :8000

# 结束进程
taskkill /F /PID <进程ID>
```

### Q: Streamlit文件对话工具打不开？

确保已安装额外依赖：
```bash
pip install -r tools/requirements.txt
```

### Q: 出错了如何调试？

- 错误时系统会自动在 `./debug/` 目录保存浏览器截图，查看截图可以了解出错时的页面状态
- 查看终端输出的日志信息
- 访问 `http://localhost:8000/v1/debug/selectors` 检查选择器是否正确匹配

---

## 可用模型

本API通过 `/v1/models` 接口列出可用模型。默认支持以下模型名称：

- `gpt-5`
- `gpt-5-thinking`
- `gpt-4.1-mini`
- `gpt-4o`

> 注意：实际使用的是企业内部部署的AI模型，模型名称仅用于兼容OpenAI SDK的调用格式。
