# LLM-ROUTE

轻量级 LLM API 路由工具，支持自动重试和系统托盘。

> 本项目旨在解决大模型厂商超售导致请求频繁超时或出错的问题，通过智能重试机制提高 API 调用的稳定性。

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
- 加载预设
- 开机自启
- 退出

## 预设

预设文件存放在 `presets/` 目录，切换预设后自动更新配置。

内置预设：
- `openai.yaml` — OpenAI 官方 API
- `anthropic.yaml` — Anthropic 官方 API
- `jdcloud.yaml` — JD Cloud 模型服务

添加新预设只需在 `presets/` 目录创建 `.yaml` 文件即可自动识别。

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
