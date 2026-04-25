# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-04-26

### Added

- 预设功能用户体验改进
  - 配置文件中存储当前激活的预设标记 (`_active_preset`)
  - WebUI 预设预览功能，应用前可查看预设内容（上游服务、路由规则、重试规则）
  - 应用预设后显示变更摘要
  - 预设列表显示当前激活的预设标记
- Release workflow 动态读取 CHANGELOG.md 对应版本的更新日志

### Fixed

- 修复 Windows 桌面端线程安全问题，提升稳定性
- 优化平台检测性能，减少资源占用
- 改进注册表操作错误处理，便于问题排查
- 限制流式响应日志内存占用（最大 64KB）

### Changed

- 用户通过 WebUI 修改配置后自动清除预设标记，避免配置状态不一致

## [1.0.0] - 2025-01-15

### Added

- 初始版本发布
- 支持 OpenAI/Anthropic 协议转换
- Web 管理界面
- 系统托盘支持
- 预设配置功能

[1.4.0]: https://github.com/MoreChanger/llm-route/compare/v1.3.15...v1.4.0
[1.0.0]: https://github.com/MoreChanger/llm-route/releases/tag/v1.0.0
