# 内部AI工具API - 企业环境版

**解决方案：长驻Edge进程**

企业环境下，每次关闭Edge都需要重新登录。本方案通过保持Edge进程持续运行来解决此问题。

## 工作原理

```
┌─────────────────────────────────────────────────────────────┐
│  终端1: 启动Edge（带调试端口）                               │
│         ↓                                                   │
│  手动登录 → 保持Edge运行 → 不关闭                           │
└─────────────────────────────────────────────────────────────┘
                              ↓ CDP连接
┌─────────────────────────────────────────────────────────────┐
│  终端2: API服务                                              │
│         ↓                                                   │
│  通过CDP协议连接到已登录的Edge → 复用认证会话               │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 安装
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 启动Edge（终端1）
```bash
# Windows
start.bat edge

# Linux/Mac
./start.sh edge
```

在弹出的Edge中完成登录，**保持Edge运行，不要关闭**。

### 3. 启动API（终端2，新开）
```bash
# Windows
start.bat api

# Linux/Mac
./start.sh api
```

### 4. 测试
```bash
curl http://localhost:8000/health
```

## API使用

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "你好"}]
)
print(response.choices[0].message.content)
```

## 注意事项

1. **不要关闭Edge浏览器** - 关闭后需要重新登录
2. **不要关闭终端1** - Edge进程在其中运行
3. **登录过期时** - 在Edge中重新登录即可，无需重启服务
4. Edge使用独立的数据目录 `./edge_data`，不影响正常使用的Edge

## 文件结构

```
├── app/
│   ├── edge_manager.py   # 核心：长驻Edge进程管理
│   ├── ai_client.py      # AI网页交互
│   ├── main.py           # FastAPI入口
│   └── routers/          # API路由
├── edge_data/            # Edge用户数据（自动创建）
├── start.bat             # Windows启动脚本
└── start.sh              # Linux启动脚本
```

## 故障排除

### Edge连接失败
```bash
# 检查状态
start.bat status

# 确认Edge在运行且调试端口开放
# 默认端口: 9222
```

### 登录过期
直接在Edge浏览器中重新登录，API服务会自动使用新会话。
