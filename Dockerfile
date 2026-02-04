# 内部AI工具API - Docker镜像
# 企业环境优化版

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（Playwright需要）
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装Playwright Chromium
RUN playwright install chromium
RUN playwright install-deps chromium

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p logs auth_state browser_data

# 设置权限
RUN chmod +x start.sh

# 暴露端口
EXPOSE 8000

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV BROWSER_HEADLESS=true
ENV USE_PERSISTENT_CONTEXT=true

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
