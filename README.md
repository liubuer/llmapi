# 内部AI工具API

通过浏览器自动化将企业内部AI工具封装为OpenAI兼容API，解决企业认证问题。

---

## 目录

- [核心概念](#核心概念)
- [系统架构](#系统架构)
- [程序流程详解](#程序流程详解)
- [快速开始](#快速开始)
- [API使用](#api使用)
- [配置说明](#配置说明)
- [文件结构](#文件结构)
- [故障排除](#故障排除)

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
├── edge_data/                    # Edge用户数据目录 (自动创建)
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
