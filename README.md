# 内部AI工具 API包装器

将公司内部网页版生成式AI工具包装成OpenAI兼容的API，供LangChain等框架使用。

**企业环境优化版** - 解决了企业版Edge/组策略环境下的限制问题。

## 核心原理

```
┌─────────────────────────────────────────────────────────────────┐
│  问题：企业环境限制                                              │
│  ├── Edge "User Data" 目录被组策略锁定                          │
│  ├── 后台安全代理持续占用文件                                    │
│  └── 检测到自动化访问时 Edge 会退出 (exitCode=21)                │
├─────────────────────────────────────────────────────────────────┤
│  解决方案：独立浏览器数据目录                                     │
│  ├── 使用 Playwright 自带的 Chromium（不使用系统Edge）           │
│  ├── 创建独立的 ./browser_data 目录存储登录状态                  │
│  ├── 首次手动登录后，状态自动保存                                │
│  └── 之后启动时自动复用登录状态                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 项目结构

```
internal-llm-api/
├── app/
│   ├── main.py              # FastAPI主入口
│   ├── config.py            # 配置管理
│   ├── models.py            # 数据模型(OpenAI兼容)
│   ├── browser_manager.py   # 浏览器管理器（企业环境优化）
│   ├── ai_client.py         # AI网页交互客户端
│   ├── langchain_adapter.py # 自定义LangChain适配器
│   └── routers/chat.py      # API路由
├── tools/
│   └── analyze_page.py      # 页面分析工具
├── examples/                 # 使用示例
├── browser_data/            # 浏览器数据目录（自动创建）
├── auth_state/              # 认证状态目录
├── start.sh                 # 启动脚本
└── requirements.txt
```

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 安装Playwright浏览器
playwright install chromium
```

### 2. 首次登录（重要！）

首次使用必须手动登录一次，以保存登录状态：

```bash
python -m app.browser_manager --login
```

这会：
1. 打开一个Chromium浏览器窗口
2. 自动导航到AI工具页面
3. 你需要手动完成登录（包括企业SSO认证）
4. 登录成功后，回到命令行按Enter保存状态

**登录状态会保存在 `./browser_data` 目录中，之后启动时会自动复用。**

### 3. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

或使用启动脚本：
```bash
./start.sh start
```

### 4. 测试

```bash
curl http://localhost:8000/health
```

## API使用

### OpenAI SDK

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

### LangChain

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

### 流式输出

```python
# OpenAI SDK
stream = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "讲个故事"}],
    stream=True
)
for chunk in stream:
    print(chunk.choices[0].delta.content, end="")

# LangChain
for chunk in llm.stream("讲个故事"):
    print(chunk.content, end="")
```

## 启动脚本命令

```bash
./start.sh login [url]    # 手动登录（首次必须）
./start.sh check          # 检查登录状态
./start.sh start          # 启动服务（开发模式）
./start.sh production     # 启动服务（生产模式）
./start.sh test [url]     # 测试浏览器（可见模式）
./start.sh analyze        # 分析页面结构
./start.sh clean          # 清理所有数据
./start.sh help           # 显示帮助
```

## 配置说明

复制 `.env.example` 为 `.env` 并根据需要修改：

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| AI_TOOL_URL | AI工具网址 | https://taa.xxx.co.jp |
| BROWSER_HEADLESS | 是否无头模式 | true |
| USE_PERSISTENT_CONTEXT | 是否使用持久化上下文 | true |
| MAX_SESSIONS | 最大并发会话数 | 3 |
| RESPONSE_TIMEOUT | 响应超时(秒) | 120 |

## 页面选择器配置

由于不同AI工具的页面结构不同，你可能需要调整CSS选择器。

使用页面分析工具：
```bash
python tools/analyze_page.py
```

然后在 `.env` 中配置：
- `SELECTOR_INPUT` - 输入框
- `SELECTOR_SEND_BUTTON` - 发送按钮
- `SELECTOR_RESPONSE` - 响应内容区域
- `SELECTOR_LOADING` - 加载状态指示器

## 企业环境注意事项

1. **不要使用Edge的用户数据目录** - 会被组策略锁定
2. **使用独立的browser_data目录** - 完全由本工具控制
3. **首次登录必须手动完成** - 包括企业SSO认证
4. **登录状态会自动保存** - 之后无需重复登录
5. **如果登录过期** - 重新运行 `./start.sh login`

## 故障排除

### 登录状态丢失
```bash
./start.sh login
```

### 浏览器启动失败
```bash
playwright install chromium --force
```

### 检查登录状态
```bash
./start.sh check
```

### 清理重新开始
```bash
./start.sh clean
./start.sh login
```

## 架构图

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   LangChain /    │     │    FastAPI       │     │   Playwright     │
│   OpenAI SDK     │────►│    API服务       │────►│   浏览器自动化    │
│                  │     │  (端口8000)      │     │                  │
└──────────────────┘     └──────────────────┘     └────────┬─────────┘
                                                           │
                                                           ▼
                                                  ┌──────────────────┐
                                                  │  ./browser_data  │
                                                  │  (独立数据目录)   │
                                                  │  保存登录状态     │
                                                  └────────┬─────────┘
                                                           │
                                                           ▼
                                                  ┌──────────────────┐
                                                  │   公司内部AI工具  │
                                                  │ taa.xxx.co.jp    │
                                                  └──────────────────┘
```
