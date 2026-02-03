# 内部AI工具 API包装器

将公司内部网页版生成式AI工具包装成OpenAI兼容的API，供LangChain等框架使用。

## 项目结构

```
internal-llm-api/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI主入口
│   ├── config.py            # 配置管理
│   ├── models.py            # 数据模型
│   ├── browser_manager.py   # Playwright浏览器管理
│   ├── ai_client.py         # AI网页交互客户端
│   ├── langchain_adapter.py # 自定义LangChain适配器
│   └── routers/
│       └── chat.py          # 聊天API路由
├── tools/
│   ├── analyze_page.py      # 页面分析工具
│   └── import_edge_session.py # Edge登录状态导入工具
├── tests/
│   └── test_api.py
├── examples/
│   ├── langchain_example.py
│   └── direct_api_example.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── start.sh                 # 启动脚本
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 登录认证（三种方式任选其一）

#### 方式一：从Edge导入登录状态（推荐 ⭐）

如果你已经在Edge浏览器中登录了AI工具，可以直接导入登录状态：

```bash
python tools/import_edge_session.py
```

这会弹出一个交互式向导，选择导入方式。

#### 方式二：使用Edge配置文件模式启动

这种方式无需导入，直接复用Edge的登录状态，但每次启动前需要关闭Edge：

```bash
# 1. 关闭所有Edge浏览器窗口
# 2. 设置环境变量并启动
export USE_EDGE_PROFILE=true
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

或使用启动脚本：
```bash
./start.sh start-edge
```

#### 方式三：手动登录

```bash
python -m app.browser_manager --login
```

这会打开一个浏览器窗口，手动完成登录后按Enter保存状态。

### 3. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

或使用启动脚本：
```bash
./start.sh start
```

## API使用

### OpenAI兼容接口

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"  # 内部服务不需要API key
)

response = client.chat.completions.create(
    model="gpt-5",
    messages=[
        {"role": "user", "content": "你好"}
    ]
)
print(response.choices[0].message.content)
```

### LangChain集成

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
    model="gpt-5"
)

response = llm.invoke("你好")
print(response.content)
```

## 配置说明

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| AI_TOOL_URL | AI工具网址 | https://taa.xxx.co.jp |
| USE_EDGE_PROFILE | 是否使用Edge配置文件模式 | false |
| EDGE_PROFILE | Edge配置文件名 | Default |
| BROWSER_HEADLESS | 是否无头模式 | true |
| MAX_SESSIONS | 最大会话数 | 3 |
| SESSION_TIMEOUT | 会话超时(秒) | 300 |
| AUTH_STATE_PATH | 认证状态保存路径 | ./auth_state |

## 页面选择器配置

由于不同的AI工具页面结构不同，你可能需要调整CSS选择器。

使用页面分析工具：
```bash
python tools/analyze_page.py
```

然后根据分析结果在 `.env` 文件中配置选择器。

## 启动脚本命令

```bash
./start.sh help         # 显示帮助
./start.sh import-edge  # 从Edge导入登录状态
./start.sh check-edge   # 检查Edge配置
./start.sh login        # 手动登录
./start.sh start        # 启动服务（开发模式）
./start.sh start-edge   # 使用Edge配置文件模式启动
./start.sh production   # 启动服务（生产模式）
./start.sh analyze      # 分析页面结构
./start.sh test         # 运行测试
```

## 注意事项

1. **Edge配置文件模式**需要先关闭所有Edge窗口
2. 输入限制为50000字符
3. 建议在内网环境部署
4. 定期检查登录状态是否过期
5. 如果使用 `USE_EDGE_PROFILE=true`，每次启动前都需要关闭Edge


---

好的，我来详细梳理整个项目的工作流程：

## 整体架构流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              启动阶段                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   uvicorn app.main:app                                                      │
│         │                                                                   │
│         ▼                                                                   │
│   ┌─────────────┐    lifespan()    ┌──────────────────────┐                │
│   │  main.py    │ ───────────────► │  browser_manager.py  │                │
│   │  FastAPI    │                  │  BrowserManager      │                │
│   └─────────────┘                  │    .start()          │                │
│                                    └──────────┬───────────┘                │
│                                               │                            │
│                                               ▼                            │
│                                    ┌──────────────────────┐                │
│                                    │  启动 Playwright     │                │
│                                    │  启动 Chromium浏览器  │                │
│                                    │  加载认证状态         │                │
│                                    └──────────────────────┘                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              请求处理阶段                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   LangChain/OpenAI SDK                                                      │
│         │                                                                   │
│         │  POST /v1/chat/completions                                        │
│         ▼                                                                   │
│   ┌─────────────┐         ┌─────────────┐         ┌─────────────────┐      │
│   │  main.py    │────────►│  chat.py    │────────►│  ai_client.py   │      │
│   │  路由分发    │         │  API处理    │         │  AIClient       │      │
│   └─────────────┘         └─────────────┘         └────────┬────────┘      │
│                                                            │               │
│                                                            ▼               │
│                                    ┌───────────────────────────────────┐   │
│                                    │      browser_manager.py           │   │
│                                    │      acquire_session()            │   │
│                                    │      获取/创建浏览器会话            │   │
│                                    └───────────────┬───────────────────┘   │
│                                                    │                       │
│                                                    ▼                       │
│                                    ┌───────────────────────────────────┐   │
│                                    │      ai_client.py                 │   │
│                                    │      _navigate_to_ai_tool()       │   │
│                                    │      _send_message()              │   │
│                                    │      _wait_for_response()         │   │
│                                    └───────────────┬───────────────────┘   │
│                                                    │                       │
│                                                    ▼                       │
│                                    ┌───────────────────────────────────┐   │
│                                    │      Playwright Page              │   │
│                                    │      操作网页AI工具                 │   │
│                                    │      https://taa.xxx.co.jp        │   │
│                                    └───────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 详细流程说明

### 1️⃣ 启动阶段

```
入口文件: app/main.py
```

```python
# main.py 中的关键代码

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ===== 启动时执行 =====
    await browser_manager.start()  # 启动浏览器管理器
    yield
    # ===== 关闭时执行 =====
    await browser_manager.stop()   # 关闭浏览器

app = FastAPI(lifespan=lifespan)
app.include_router(chat_router)   # 注册API路由
```

**执行流程：**
```
uvicorn app.main:app
    │
    ├──► 加载 FastAPI 应用
    │
    ├──► 执行 lifespan() 启动逻辑
    │       │
    │       └──► browser_manager.start()
    │               │
    │               ├──► 启动 Playwright
    │               ├──► 启动 Chromium 浏览器
    │               └──► 加载认证状态 (auth_state/state.json)
    │
    └──► 开始监听 HTTP 请求 (端口 8000)
```

---

### 2️⃣ 浏览器管理器初始化

```
文件: app/browser_manager.py
类: BrowserManager
```

```python
async def start(self, use_edge_profile=False):
    # 1. 启动 Playwright
    self._playwright = await async_playwright().start()
    
    # 2. 根据模式选择启动方式
    if use_edge_profile:
        # 方式A: 直接使用Edge的用户数据
        self._persistent_context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=edge_path,
            channel="msedge"
        )
    else:
        # 方式B: 启动独立浏览器，加载保存的认证状态
        self._browser = await self._playwright.chromium.launch(headless=True)
```

**两种模式的区别：**

```
模式A: Edge配置文件模式 (USE_EDGE_PROFILE=true)
┌─────────────────────────────────────────┐
│  直接使用 Edge 浏览器的用户数据目录        │
│  C:\Users\xxx\AppData\Local\Microsoft\  │
│  Edge\User Data                         │
│                                         │
│  优点: 自动继承Edge的所有登录状态          │
│  缺点: 启动时必须关闭Edge                 │
└─────────────────────────────────────────┘

模式B: 独立浏览器模式 (默认)
┌─────────────────────────────────────────┐
│  启动独立的 Chromium 浏览器              │
│  从 auth_state/state.json 加载认证状态   │
│                                         │
│  优点: 不影响Edge使用                    │
│  缺点: 需要先导入或手动登录保存状态        │
└─────────────────────────────────────────┘
```

---

### 3️⃣ API请求处理流程

当用户发送请求时：

```python
# 用户代码 (LangChain 或 OpenAI SDK)
client = openai.OpenAI(base_url="http://localhost:8000/v1")
response = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "你好"}]
)
```

**请求流转：**

```
POST http://localhost:8000/v1/chat/completions
     │
     │  请求体:
     │  {
     │    "model": "gpt-5",
     │    "messages": [{"role": "user", "content": "你好"}],
     │    "stream": false
     │  }
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  app/routers/chat.py                                        │
│  @router.post("/chat/completions")                          │
│  async def chat_completions(request: ChatCompletionRequest) │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  app/ai_client.py                                           │
│  AIClient.chat(messages, model, stream)                     │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  app/browser_manager.py                                     │
│  async with manager.acquire_session() as session:           │
│      # 获取一个可用的浏览器会话                                │
└─────────────────────────────────────────────────────────────┘
```

---

### 4️⃣ 会话池管理

```
文件: app/browser_manager.py
方法: acquire_session()
```

```
会话池结构:
┌────────────────────────────────────────────────────┐
│                   BrowserManager                    │
│  ┌──────────────────────────────────────────────┐  │
│  │              _sessions (Dict)                 │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐        │  │
│  │  │Session 1│ │Session 2│ │Session 3│ (最多3个)│  │
│  │  │ Page    │ │ Page    │ │ Page    │        │  │
│  │  │ is_busy │ │ is_busy │ │ is_busy │        │  │
│  │  └─────────┘ └─────────┘ └─────────┘        │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘

获取会话流程:
┌─────────────┐     有空闲会话?      ┌─────────────┐
│ 请求到来    │ ──── Yes ──────────► │ 复用现有会话 │
└─────────────┘                      └─────────────┘
      │
      │ No
      ▼
┌─────────────────┐   未达上限?    ┌─────────────┐
│ 检查会话数量     │ ─── Yes ────► │ 创建新会话   │
└─────────────────┘                └─────────────┘
      │
      │ No (已达到 MAX_SESSIONS)
      ▼
┌─────────────────┐
│ 等待会话释放     │
│ (最多30秒)      │
└─────────────────┘
```

---

### 5️⃣ 网页交互核心逻辑

```
文件: app/ai_client.py
类: AIClient
```

**完整的消息发送流程：**

```python
async def chat(self, messages, model, new_conversation, stream):
    # 获取浏览器会话
    async with manager.acquire_session() as session:
        page = session.page
        
        # Step 1: 导航到AI工具页面
        await self._navigate_to_ai_tool(page)
        
        # Step 2: 检查登录状态
        if not await self._ensure_logged_in(page):
            raise AIClientError("未登录")
        
        # Step 3: 如果需要，开始新对话
        if new_conversation:
            await self._start_new_conversation(page)
        
        # Step 4: 选择模型
        await self._select_model(page, model)
        
        # Step 5: 格式化消息
        prompt = self._format_messages(messages)
        
        # Step 6: 发送消息并获取响应
        response = await self._send_message(page, prompt)
        
        return response
```

**详细的网页操作：**

```
┌────────────────────────────────────────────────────────────────┐
│                     _send_message(page, message)               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. 定位输入框                                                  │
│     input_box = page.locator(SELECTOR_INPUT)                   │
│     ┌──────────────────────────────────────┐                  │
│     │  textarea[placeholder*='消息']        │                  │
│     │  或 textarea.chat-input              │                  │
│     └──────────────────────────────────────┘                  │
│                           │                                    │
│                           ▼                                    │
│  2. 输入消息内容                                                │
│     await input_box.fill(message)                             │
│     ┌──────────────────────────────────────┐                  │
│     │  [输入框填入用户消息]                  │                  │
│     └──────────────────────────────────────┘                  │
│                           │                                    │
│                           ▼                                    │
│  3. 点击发送按钮                                                │
│     send_btn = page.locator(SELECTOR_SEND_BUTTON)             │
│     await send_btn.click()                                    │
│     ┌──────────────────────────────────────┐                  │
│     │  [发送] 按钮被点击                    │                  │
│     └──────────────────────────────────────┘                  │
│                           │                                    │
│                           ▼                                    │
│  4. 等待响应完成                                                │
│     await _wait_for_response_complete(page)                   │
│     ┌──────────────────────────────────────┐                  │
│     │  监控 SELECTOR_RESPONSE 元素          │                  │
│     │  检查 SELECTOR_LOADING 是否消失       │                  │
│     │  内容稳定后返回响应文本               │                  │
│     └──────────────────────────────────────┘                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**等待响应的逻辑：**

```python
async def _wait_for_response_complete(self, page):
    last_content = ""
    stable_count = 0
    
    while 未超时:
        # 检查是否还在加载
        is_loading = await page.locator(SELECTOR_LOADING).is_visible()
        
        # 获取最新响应内容
        responses = page.locator(SELECTOR_RESPONSE)
        current_content = await responses.last.inner_text()
        
        # 判断内容是否稳定
        if current_content == last_content and not is_loading:
            stable_count += 1
            if stable_count >= 3:  # 连续3次相同 = 完成
                return current_content
        else:
            stable_count = 0
            last_content = current_content
        
        await asyncio.sleep(0.5)
```

---

### 6️⃣ 响应返回

```
文件: app/routers/chat.py
```

```python
# 构建OpenAI兼容的响应格式
return ChatCompletionResponse(
    id="chatcmpl-xxx",
    model=request.model,
    choices=[
        ChatCompletionChoice(
            index=0,
            message=ChatMessage(
                role="assistant",
                content=response_text  # 从网页获取的AI回复
            ),
            finish_reason="stop"
        )
    ],
    usage=Usage(
        prompt_tokens=估算值,
        completion_tokens=估算值,
        total_tokens=估算值
    )
)
```

**返回给用户的JSON：**

```json
{
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "created": 1234567890,
    "model": "gpt-5",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "你好！有什么我可以帮助你的吗？"
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30
    }
}
```

---

### 7️⃣ 流式输出流程

如果 `stream=true`：

```
┌─────────────────────────────────────────────────────────────┐
│                     流式响应流程                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   客户端                    服务器                           │
│     │                         │                             │
│     │  POST /chat/completions │                             │
│     │  stream: true           │                             │
│     │ ──────────────────────► │                             │
│     │                         │                             │
│     │   SSE: data: {"delta": {"content": "你"}}             │
│     │ ◄────────────────────── │                             │
│     │                         │                             │
│     │   SSE: data: {"delta": {"content": "好"}}             │
│     │ ◄────────────────────── │                             │
│     │                         │                             │
│     │   SSE: data: {"delta": {"content": "！"}}             │
│     │ ◄────────────────────── │                             │
│     │                         │                             │
│     │   SSE: data: [DONE]     │                             │
│     │ ◄────────────────────── │                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**流式生成器：**

```python
async def _stream_response(self, page):
    last_content = ""
    
    while 未完成:
        current_content = await page.locator(SELECTOR_RESPONSE).last.inner_text()
        
        # 返回增量内容
        if len(current_content) > len(last_content):
            delta = current_content[len(last_content):]
            last_content = current_content
            yield delta  # 返回新增的部分
        
        await asyncio.sleep(0.2)
```

---

## 完整请求时序图

```
┌──────┐     ┌──────┐     ┌──────┐     ┌──────────┐     ┌──────────┐     ┌─────────┐
│Client│     │Main │     │ Chat │     │ AIClient │     │ Browser  │     │ AI网页  │
│      │     │ .py │     │ .py  │     │          │     │ Manager  │     │         │
└──┬───┘     └──┬───┘     └──┬───┘     └────┬─────┘     └────┬─────┘     └────┬────┘
   │            │            │              │                │                │
   │ POST /v1/chat/completions              │                │                │
   │───────────►│            │              │                │                │
   │            │            │              │                │                │
   │            │ 路由匹配    │              │                │                │
   │            │───────────►│              │                │                │
   │            │            │              │                │                │
   │            │            │ client.chat()│                │                │
   │            │            │─────────────►│                │                │
   │            │            │              │                │                │
   │            │            │              │ acquire_session()               │
   │            │            │              │───────────────►│                │
   │            │            │              │                │                │
   │            │            │              │ return session │                │
   │            │            │              │◄───────────────│                │
   │            │            │              │                │                │
   │            │            │              │ page.goto(AI_URL)               │
   │            │            │              │────────────────────────────────►│
   │            │            │              │                │                │
   │            │            │              │ page.fill(输入框, 消息)          │
   │            │            │              │────────────────────────────────►│
   │            │            │              │                │                │
   │            │            │              │ page.click(发送按钮)             │
   │            │            │              │────────────────────────────────►│
   │            │            │              │                │                │
   │            │            │              │            [AI处理中...]         │
   │            │            │              │                │                │
   │            │            │              │ 轮询获取响应内容                  │
   │            │            │              │◄───────────────────────────────►│
   │            │            │              │                │                │
   │            │            │ response_text│                │                │
   │            │            │◄─────────────│                │                │
   │            │            │              │                │                │
   │            │ JSON响应   │              │                │                │
   │◄───────────│◄───────────│              │                │                │
   │            │            │              │                │                │
```

---

## 关键文件职责总结

| 文件 | 职责 |
|------|------|
| `main.py` | FastAPI入口，生命周期管理，路由注册 |
| `config.py` | 配置管理，环境变量读取 |
| `models.py` | 请求/响应数据模型（OpenAI格式） |
| `browser_manager.py` | 浏览器实例管理，会话池，认证状态 |
| `ai_client.py` | 核心逻辑：网页交互，消息发送，响应获取 |
| `routers/chat.py` | API端点处理，格式转换 |
| `langchain_adapter.py` | 自定义LangChain适配器（可选） |
