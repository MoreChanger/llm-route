---
title: fix: 改进流式请求日志和超时处理
type: fix
status: active
date: 2026-04-25
---

# fix: 改进流式请求日志和超时处理

## Overview

改进流式请求的可观测性和超时处理，解决长时间请求卡住无法排查的问题。

## Problem Frame

当前问题：
1. **日志只在请求结束后记录** — 请求卡住时日志里完全看不到
2. **流式请求没有单独超时** — 可能无限等待
3. **无进度追踪** — 不知道请求处理到哪一步

用户场景：流式请求非常久，客户端没有反应，日志里看不到这条请求。

## Requirements Trace

- R1. 请求开始时立即记录日志，便于排查卡住的请求
- R2. 流式请求设置合理的超时时间
- R3. 长时间流式请求定期记录进度

## Scope Boundaries

- 仅修改日志记录时机和超时设置
- 不改变流式响应的核心转发逻辑

## Key Technical Decisions

- **请求开始日志**: 在 `handle_request` 入口记录请求开始
- **流式超时**: 设置 10 分钟总超时（足够长但不会无限）
- **进度日志**: 每 60 秒记录一次流式进度

## Implementation Units

- [x] **Unit 1: 添加请求开始日志**

**Goal:** 请求开始时立即记录，便于排查卡住的请求

**Requirements:** R1

**Dependencies:** None

**Files:**
- Modify: `src/proxy.py`

**Approach:**
- 在 `handle_request` 入口处记录请求开始日志
- 包含：method, path, 请求体大小

**Test scenarios:**
- Happy path: 请求正常完成，日志显示开始和结束
- Error path: 请求超时卡住，日志至少显示请求开始

**Verification:**
- 发送请求后立即能在日志中看到

---

- [x] **Unit 2: 设置流式请求超时**

**Goal:** 流式请求有合理的超时时间，不会无限等待

**Requirements:** R2

**Dependencies:** None

**Files:**
- Modify: `src/proxy.py`

**Approach:**
- 流式请求使用单独的 `ClientSession` 或覆盖超时设置
- 设置 `sock_read` 超时（每次读取 chunk 的超时）
- 总超时保持 120 秒，但 sock_read 设置较长（如 60 秒）

**Test scenarios:**
- Happy path: 正常流式请求完成
- Error path: 上游无响应，超时后正确断开

**Verification:**
- 流式请求不会无限卡住

---

- [x] **Unit 3: 添加流式进度日志**

**Goal:** 长时间流式请求定期记录进度

**Requirements:** R3

**Dependencies:** Unit 2

**Files:**
- Modify: `src/proxy.py`

**Approach:**
- 在流式循环中记录进度（每 60 秒或每 N 个 chunk）
- 记录：已接收字节数、已用时间

**Test scenarios:**
- Happy path: 长时间流式请求定期记录进度
- Happy path: 短请求不产生额外的进度日志

**Verification:**
- 长时间请求能看到进度日志

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| 日志量增加 | 请求开始日志精简，进度日志限制频率 |
| 超时过短影响正常请求 | 设置足够长的超时（10分钟总超时） |

## Sources & References

- 相关代码: `src/proxy.py` - `_forward_streaming`, `handle_request`
