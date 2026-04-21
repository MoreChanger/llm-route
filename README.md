# LLM-ROUTE

轻量级 LLM API 路由工具，支持自动重试和系统托盘。

## 功能

- **反向代理** — 支持 Anthropic 和 OpenAI 协议，根据路径自动路由
- **智能重试** — 上游返回 400/429/500 等错误时自动重试
- **SSE 流式支持** — 支持流式请求，出错时自动重试
- **系统托盘** — 最小化到托盘，右键菜单控制
- **端口管理** — 自动检测端口占用，支持手动指定或随机分配

## 快速开始

### 1. 配置

编辑 `config.yaml`：

```yaml
host: 127.0.0.1
port: 8087

upstreams:
  anthropic:
    url: https://api.anthropic.com
    protocol: anthropic
  openai:
    url: https://api.openai.com
    protocol: openai

routes:
  - path: /v1/messages
    upstream: anthropic
  - path: /v1/chat/completions
    upstream: openai

retry_rules:
  - status: 429
    max_retries: 10
    delay: 2
    jitter: 1
```

### 2. 运行

双击 `llm-route.exe` 启动，服务自动运行。

或在命令行运行：

```bash
llm-route                    # 托盘模式
llm-route --headless         # 无头模式
llm-route --port 9000        # 指定端口
llm-route --config my.yaml   # 指定配置文件
```

### 3. 配置 AI 工具

**Claude Code:**

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8087
```

**Cursor:**

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8087
```

## 托盘菜单

- 复制代理地址
- 日志详情
- 启动/停止服务
- 更换端口
- 开机自启
- 退出

## 从源码运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python -m src.main
```

## 开发

```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试
pytest

# 打包
pyinstaller build.spec
```

## License

MIT
