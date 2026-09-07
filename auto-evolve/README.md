# auto-evolve

Session 自动进化系统插件。

## 功能

- **SessionStart**：会话启动时自动运行项目快速检查清单（项目未初始化时静默跳过）
- **SessionEnd**：会话结束时分析当日错误日志，自动生成/更新检查规则
- **全局错误捕获**：配合全局 PostToolUse hook（`~/.claude/hooks/log-error.sh`）记录所有工具调用错误
- **`/auto-evolve:init`**：为新项目初始化检查体系（模板选择式，强规范防发散）

## 新项目接入

1. 安装本插件后，在新项目里运行 `/auto-evolve:init`
2. 重启会话，SessionStart 检查自动生效

## 架构

```
全局层  PostToolUse 错误捕获（独立配置，见 README 安装说明）
项目层  SessionStart 检查 + SessionEnd 进化（本插件 hooks）
模板库  CHECK_TEMPLATES 注册表（唯一合法检查项来源）
```
