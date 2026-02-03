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
