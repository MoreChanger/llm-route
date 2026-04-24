# Home

欢迎来到 LLM-ROUTE Wiki！

## 简介

LLM-ROUTE 是一个轻量级 LLM API 路由工具，主要解决大模型厂商超售导致请求频繁超时或出错的问题。

## 版本历史

### v1.3.0 (2026-04-24)

**Responses API 工具调用支持：**
- ✅ 完整的流式响应 SSE 事件转换
- ✅ Function Calling 支持
- ✅ 多轮对话 (`previous_response_id`)
- ✅ Cherry Studio 兼容测试通过

### v1.2.0

- Responses API 基础转换功能

### v1.1.0

- 智能重试机制优化

### v1.0.0

- 初始版本

## 主要功能

- **反向代理** - 支持 Anthropic 和 OpenAI 协议
- **智能重试** - 自动重试失败的请求
- **Responses API 转换** - 兼容更多模型服务
- **系统托盘** - 便捷的图形界面

## 文档

- [Responses API 转换](Responses-API-转换) - 详细了解转换功能，包括：
  - 配置方式
  - 支持功能列表
  - 使用示例（工具调用、多轮对话）
  - 技术细节
  - 故障排除

## 快速链接

- [GitHub 仓库](https://github.com/MoreChanger/llm-route)
- [最新发布](https://github.com/MoreChanger/llm-route/releases/latest)
- [问题反馈](https://github.com/MoreChanger/llm-route/issues)
