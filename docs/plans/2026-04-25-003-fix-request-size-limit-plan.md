---
title: fix: 添加请求体大小限制防止内存耗尽攻击
type: fix
status: active
date: 2026-04-25
---

# fix: 添加请求体大小限制防止内存耗尽攻击

## Overview

为代理网关添加请求体大小限制，防止恶意超大请求导致内存耗尽和服务崩溃。

## Problem Frame

当前 `llm-route` 作为 LLM API 中转网关，`aiohttp` 默认不限制请求体大小。攻击者可发送超大请求体（如 10GB），导致：
- 内存耗尽（OOM）
- 服务崩溃
- 正常请求被拒绝

虽然上游 LLM API 有自己的限制，但攻击可能针对 `llm-route` 本身。

## Requirements Trace

- R1. 请求体大小应有限制，防止内存耗尽
- R2. 超过限制时返回 413 Payload Too Large 错误
- R3. 限制值应足够大，不影响正常 LLM 使用（含多模态）
- R4. 超大请求应记录日志，便于安全审计

## Scope Boundaries

- 仅限制入站请求体大小
- 不改变上游请求超时设置
- 不修改流式响应处理

## Key Technical Decisions

- **限制值 100MB**: 覆盖所有正常 LLM 使用场景（128K 上下文 + 多模态图片），同时有效防护恶意请求
- **使用 aiohttp client_max_size**: aiohttp 原生支持，配置简单

## Open Questions

### Resolved During Planning

- 限制值设为多少？→ 100MB，覆盖正常使用且足够防护

## Implementation Units

- [x] **Unit 1: 添加请求体大小限制**

**Goal:** 限制请求体最大 100MB，超过返回 413 错误

**Requirements:** R1, R2, R3, R4

**Dependencies:** None

**Files:**
- Modify: `src/proxy.py`

**Approach:**
- 在 `ProxyServer.__init__` 或 `start()` 中设置 `client_max_size`
- aiohttp 通过 `web.Application` 的 `client_max_size` 参数配置
- 超过限制时 aiohttp 自动返回 413
- 在 `handle_request` 中捕获 `HTTPRequestEntityTooLarge` 异常并记录日志

**Patterns to follow:**
- aiohttp 官方文档的 `client_max_size` 配置方式

**Test scenarios:**
- Happy path: 1MB 请求正常处理
- Happy path: 50MB 请求正常处理
- Edge case: 恰好 100MB 请求正常处理
- Error path: 超过 100MB 请求返回 413
- Error path: 超大请求记录日志（包含请求路径、大小信息）

**Verification:**
- 发送超过 100MB 的请求，确认返回 413 错误
- 正常 LLM 请求不受影响

## System-Wide Impact

- **Error propagation:** 超大请求返回 413，不影响其他请求
- **Unchanged invariants:** 现有路由、转发逻辑不变

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| 限制值过小影响正常使用 | 100MB 远大于正常 LLM 请求 |
| 客户端不处理 413 错误 | 标准 HTTP 错误码，客户端应正确处理 |

## Sources & References

- aiohttp 文档: `client_max_size` 参数
- 相关代码: `src/proxy.py` - `ProxyServer.start()`
