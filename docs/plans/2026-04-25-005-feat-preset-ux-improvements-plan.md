---
title: feat: 预设功能用户体验改进
type: feat
status: active
date: 2026-04-25
origin: docs/brainstorms/2026-04-25-preset-ux-improvements-requirements.md
---

# feat: 预设功能用户体验改进

## Overview

改进预设功能的可观测性和用户反馈：在配置文件中存储当前激活的预设标记，并在 WebUI 中添加预设预览功能。

## Problem Frame

当前预设功能存在两个主要问题：

1. **当前预设检测不可靠** — 托盘和 WebUI 显示的"当前预设"仅比较 upstreams 的 url 和 protocol 字段（忽略了 convert_responses 等），当用户手动修改配置后标记就丢失，或者匹配到错误的预设。

2. **预设内容不可见** — 用户点击应用预设前无法预览具体会改什么，应用后也不知道改了什么，只能看到一个"预设已应用"的提示。

用户场景：用户在 WebUI 点击 jdcloud 预设后重启容器，发现密码恢复为默认值，完全不知道是预设覆盖了配置。

## Requirements Trace

- R1. 配置文件中应存储当前激活的预设标记（预设名称），而非通过模糊匹配推断
- R2. 应用预设时自动更新预设标记
- R3. 用户手动修改配置后，预设标记应自动清除
- R4. WebUI 中应用预设前应显示预设内容预览
- R5. 预览应包含：上游服务列表、路由规则、重试规则
- R6. 应用预设后应显示变更摘要（显示"已切换到预设 X"）

## Scope Boundaries

- 不改变预设文件的格式和存储位置
- 不实现预设叠加或组合功能
- 不实现预设的导入导出功能
- 不实现预设版本管理

## Context & Research

### Relevant Code and Patterns

- `src/config.py` — Config dataclass 和 load/save/apply_preset 函数
- `src/web_admin.py` — WebUI 处理器，使用 inline HTML/JS
- `src/tray.py` — 托盘菜单，包含 `_detect_current_preset()` 函数
- `tests/test_config.py` — 配置相关测试模式

### Key Technical Decisions

- **预设标记字段名**: 使用 `_active_preset` 作为配置文件中的字段名，下划线前缀表示系统管理字段
- **预览触发时机**: 点击"应用"按钮时弹窗预览，而非 hover 或单独的"预览"按钮
- **变更摘要范围**: 第一版仅显示"已切换到预设 X"，不显示详细的配置差异
- **手动修改检测**: 在 WebUI 的 `handle_config_save()` 中清除预设标记（显式检测用户行为）

## Open Questions

### Resolved

- [Affects R3][Technical] 如何检测"用户手动修改配置"？ — 通过 WebUI `handle_config_save()` 触发时清除标记，这是显式且可靠的检测方式。托盘端口修改和直接编辑 config.yaml 不清除标记。

### Deferred to Implementation

- [Affects R4][UI/UX] 预览弹窗的交互状态：loading/error/empty 状态如何显示？取消按钮如何工作？ — 使用现有 `.loading-overlay` 样式，错误在弹窗内显示，取消按钮复用 `.btn-secondary` 样式

## Implementation Units

- [x] **Unit 1: 添加 _active_preset 字段到 Config**

**Goal:** 配置文件中存储当前激活的预设标记

**Requirements:** R1

**Dependencies:** None

**Files:**
- Modify: `src/config.py` — Add `_active_preset` field to Config dataclass, update `load_config()` and `save_config()`
- Test: `tests/test_config.py`

**Approach:**
- 在 `Config` dataclass 添加 `_active_preset: Optional[str] = None` 字段
- 修改 `load_config()` 读取 `_active_preset` 字段
- 修改 `save_config()` 写入 `_active_preset` 字段（仅当非 None 时）

**Patterns to follow:**
- 现有字段如 `admin_password_hash` 的处理方式

**Test scenarios:**
- Happy path: 配置文件包含 `_active_preset: jdcloud`，加载后字段正确
- Happy path: 配置文件无 `_active_preset` 字段，加载后为 None
- Happy path: 保存配置时 `_active_preset` 有值，写入 YAML
- Happy path: 保存配置时 `_active_preset` 为 None，不写入该字段

**Verification:**
- 运行测试确保配置加载/保存正确处理 `_active_preset` 字段

---

- [x] **Unit 2: apply_preset 设置预设标记**

**Goal:** 应用预设时自动更新预设标记

**Requirements:** R2

**Dependencies:** Unit 1

**Files:**
- Modify: `src/config.py` — Add `preset_name` parameter to `apply_preset()`
- Modify: `src/web_admin.py` — Pass preset_name to `apply_preset()`, reload config after apply
- Modify: `src/tray.py` — Refresh `_current_preset` when config changes
- Test: `tests/test_config.py`

**Approach:**
- 修改 `apply_preset()` 函数签名，接受 `preset_name` 参数
- 在写入配置时设置 `_active_preset = preset_name`
- 修改 `handle_preset_apply()` 传递 preset_name
- 在 `handle_preset_apply()` 成功后重新加载配置（`self.proxy_server.config = load_config(...)`）
- 修改托盘在预设应用后刷新 `_current_preset`

**Patterns to follow:**
- `apply_preset()` 现有的配置合并逻辑

**Test scenarios:**
- Happy path: 应用预设后，`_active_preset` 被设置为预设名称
- Edge case: 预设名称包含特殊字符，正确存储
- Error path: 预设文件不存在，返回 False 且不修改配置

**Verification:**
- 应用预设后重新加载配置，确认 `_active_preset` 正确

---

- [x] **Unit 3: 手动修改配置时清除预设标记**

**Goal:** 用户通过 WebUI 修改配置后，预设标记自动清除

**Requirements:** R3

**Dependencies:** Unit 1

**Files:**
- Modify: `src/web_admin.py`
- Test: `tests/test_web_admin.py`

**Approach:**
- 在 `handle_config_save()` 中，保存前将 `config._active_preset = None`
- 这覆盖用户修改 port、log_level 等设置的场景

**Patterns to follow:**
- 现有 `handle_config_save()` 的配置更新逻辑

**Test scenarios:**
- Happy path: 用户修改端口后保存，`_active_preset` 被清除
- Happy path: 用户修改日志等级后保存，`_active_preset` 被清除
- Edge case: 当前无预设标记，保存后仍为 None

**Verification:**
- 通过 WebUI 修改配置后，重新加载配置确认 `_active_preset` 为 None

---

- [x] **Unit 4: 托盘使用 _active_preset 显示当前预设**

**Goal:** 托盘菜单准确显示当前预设名称

**Requirements:** R1

**Dependencies:** Unit 1, Unit 2

**Files:**
- Modify: `src/tray.py`

**Approach:**
- 修改 `_detect_current_preset()` 直接读取 `config._active_preset`
- 移除现有的模糊匹配逻辑
- 如果 `_active_preset` 为 None，返回 None 表示无预设

**Patterns to follow:**
- 现有托盘配置访问模式（通过 `self.proxy_server.config`）

**Test scenarios:**
- Happy path: `_active_preset` 有值，返回该值
- Happy path: `_active_preset` 为 None，返回 None
- Integration: 应用预设后托盘显示更新

**Verification:**
- 应用预设后托盘菜单显示正确的预设名称

---

- [x] **Unit 5: WebUI 预设列表显示当前预设标记**

**Goal:** WebUI 预设列表准确显示当前激活的预设名称

**Requirements:** R1

**Dependencies:** Unit 1, Unit 2

**Files:**
- Modify: `src/web_admin.py`

**Approach:**
- 修改 `handle_presets()` API 返回当前预设名称（`current_preset: config._active_preset`）
- 修改前端预设列表渲染，对当前预设添加视觉标记（如高亮边框、"当前"标签）

**Patterns to follow:**
- 现有 `handle_presets()` 的 API 模式

**Test scenarios:**
- Happy path: 有激活预设时，列表正确标记
- Happy path: 无激活预设时，无标记
- Integration: 应用预设后刷新列表，标记更新

**Verification:**
- WebUI 预设列表正确显示当前预设标记

---

- [x] **Unit 6: WebUI 预设预览 API**

**Goal:** 提供获取预设内容的 API 端点

**Requirements:** R4, R5

**Dependencies:** None

**Files:**
- Modify: `src/web_admin.py`
- Test: `tests/test_web_admin.py`

**Approach:**
- 添加 `GET /_admin/api/presets/preview?name=<preset_name>` 端点
- 读取预设文件，返回结构化内容：`{name, upstreams, routes, retry_rules}`
- 复用现有的 `list_presets()` 和 YAML 读取模式

**Patterns to follow:**
- 现有 `handle_presets()` 的 API 模式

**Test scenarios:**
- Happy path: 有效预设名称，返回预设内容
- Error path: 预设不存在，返回 404
- Error path: 预设文件损坏，返回 500

**Verification:**
- API 返回正确的预设内容结构

---

- [x] **Unit 7: WebUI 预设预览弹窗**

**Goal:** 点击"应用"按钮时显示预设内容预览弹窗

**Requirements:** R4, R5

**Dependencies:** Unit 6

**Files:**
- Modify: `src/web_admin.py` — 修改前端 HTML/JS

**Approach:**
- 修改 `applyPreset()` 函数：先调用预览 API，显示弹窗，确认后再应用
- 弹窗内容：显示上游服务列表、路由规则、重试规则
- 使用现有 CSS 样式（`.loading-overlay`, `.btn-*`）
- 取消按钮使用 `.btn-secondary`，确认按钮使用 `.btn-primary`
- 实现加载状态过渡：点击应用 → 显示 loading → 预览数据返回 → 显示内容

**Patterns to follow:**
- 现有 `confirm()` 和 `alert()` 的交互模式，升级为自定义弹窗

**Test scenarios:**
- Happy path: 点击应用，显示预览弹窗，确认后应用预设
- Happy path: 点击应用，显示预览弹窗，取消后不应用
- Error path: 预览加载失败，显示错误信息
- UI: 弹窗正确显示上游、路由、重试规则
- Empty state: 预设无 upstreams/routes/retry_rules 时显示空状态提示

**Verification:**
- 手动测试 WebUI 预览流程

---

- [x] **Unit 8: 应用预设后显示变更摘要**

**Goal:** 应用预设后显示"已切换到预设 X"摘要

**Requirements:** R6

**Dependencies:** Unit 2, Unit 7

**Files:**
- Modify: `src/web_admin.py`

**Approach:**
- 修改 `handle_preset_apply()` 返回 `{success: true, preset: name, message: "已切换到预设 xxx"}`
- 修改前端 `applyPreset()` 在应用成功后显示 message

**Patterns to follow:**
- 现有 API 响应格式

**Test scenarios:**
- Happy path: 应用成功，返回摘要消息
- Error path: 应用失败，返回错误消息

**Verification:**
- 应用预设后 WebUI 显示正确的摘要消息

## System-Wide Impact

- **Interaction graph:**
  - `apply_preset()` 调用链：WebUI → API → config.py → YAML 文件
  - 托盘启动时读取 `config._active_preset` 显示当前预设
- **Error propagation:** 配置文件读写失败时，现有错误处理机制适用
- **Unchanged invariants:** 预设文件格式不变，现有 `list_presets()` 函数不变

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| 配置文件损坏导致 `_active_preset` 丢失 | 设为 None 即可，不阻塞启动 |
| 预设名称变更后标记失效 | 用户重新应用预设即可修复 |
| 预览 API 性能 | 预设文件很小，读取开销可忽略 |

## Sources & References

- **Origin document:** docs/brainstorms/2026-04-25-preset-ux-improvements-requirements.md
- Related code: `src/config.py` — `Config`, `load_config`, `save_config`, `apply_preset`
- Related code: `src/web_admin.py` — `handle_presets`, `handle_preset_apply`
- Related code: `src/tray.py` — `_detect_current_preset`
