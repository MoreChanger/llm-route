# 代码质量修复与测试覆盖率提升 Spec

## Why
项目代码存在测试覆盖率不足的问题（整体覆盖率仅 46%），部分核心模块（proxy、responses_converter、log_file）测试覆盖不足，可能导致潜在 bug 未被发现。同时部分模块完全没有测试（log_window、main、single_instance、tray），增加了维护风险。

## What Changes
- 增加核心模块的单元测试，提升整体测试覆盖率至 70% 以上
- 为 responses_converter 模块增加 SSE 流式转换测试
- 为 proxy 模块增加边界条件和异常处理测试
- 为 log_file 模块增加日志滚动和压缩测试
- 优化依赖配置，减少不必要的依赖

## Impact
- Affected specs: 测试框架、代码覆盖率
- Affected code: 
  - tests/test_responses_converter.py
  - tests/test_proxy.py
  - tests/test_log_file.py
  - requirements.txt

## ADDED Requirements

### Requirement: 增加测试覆盖率
系统 SHALL 为核心模块提供至少 70% 的测试覆盖率。

#### Scenario: responses_converter 流式转换测试
- **WHEN** 调用 convert_stream 方法处理 SSE 流
- **THEN** 应正确转换并生成 Responses API 格式的事件流

#### Scenario: proxy 异常处理测试
- **WHEN** 上游服务返回错误或超时
- **THEN** 应正确处理异常并返回适当的错误响应

#### Scenario: log_file 日志滚动测试
- **WHEN** 日志文件超过大小限制
- **THEN** 应正确滚动日志文件并创建新文件

### Requirement: 优化项目依赖
系统 SHALL 仅包含必要的依赖项，避免引入未使用的重量级库。

#### Scenario: 依赖精简
- **WHEN** 检查 requirements.txt
- **THEN** 应只包含项目实际需要的依赖

## MODIFIED Requirements

### Requirement: 测试框架配置
测试框架 SHALL 支持异步测试和覆盖率报告，配置应保持最新。

## REMOVED Requirements
无
