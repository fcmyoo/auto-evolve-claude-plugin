# auto-evolve

[![GitHub](https://img.shields.io/badge/Claude%20Code-Plugin-purple)](https://docs.claude.com/en/docs/claude-code/plugins)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](auto-evolve/LICENSE)

**让 Claude Code 从你的错误中学习。** 一个会话自动进化插件：启动时自动检查项目健康度，会话结束时自动分析错误日志、生成新的检查规则——下次启动时，昨天犯的错就再也犯不了了。

```
第 1 天：遇到 UnicodeEncodeError   → 自动记录
第 1 天：关闭会话                  → 自动分析，生成检查规则
第 2 天：打开会话                  → 自动检测环境缺陷，提示修复
第 3 天：这个错误消失了             → 系统继续学习下一个错误
```

无需 API Key，无需外部服务，完全本地运行。

## 安装

```bash
# 在 Claude Code 会话中：
/plugin marketplace add fcmyoo/auto-evolve-claude-plugin
/plugin install auto-evolve@lee-local
```

重启会话即生效。新项目接入：在项目根目录运行 `/auto-evolve:init`。

## 它做什么

| 时机 | 行为 |
|------|------|
| 会话启动（SessionStart） | 运行项目快速检查清单，环境缺陷当场提示（未初始化的项目静默跳过） |
| 工具调用失败（PostToolUse） | 记录错误签名到 JSONL 日志（双写：全局 + 项目本地） |
| 会话结束（SessionEnd） | 分析当日错误 → 高频错误自动生成检查项 → 写入检查清单 |
| 人工（`/auto-evolve:init`） | 模板选择式初始化项目检查体系（dry-run 展示计划，确认后写入 + 语法校验） |

## 核心设计：强规范防发散

自动生成代码的系统最大的风险是失控。auto-evolve 用机制而非约定约束：

- 检查项只能来自内置 `CHECK_TEMPLATES` 注册表，禁止即兴发明
- 模板分 `universal`（全局适用）/ `project`（验证依赖路径存在才启用）两级
- 生成的代码自包含、接入宿主统计体系、强制 `bash -n` 语法校验
- 错误分类失败的进 unknown 聚类供人工审——不为一次性错误生成垃圾规则

## 文档

📖 **完整文档见 [`auto-evolve/README.md`](auto-evolve/README.md)**，包含：

- 工作原理与三层架构详解
- 三阶段进化闭环（捕获 → 进化 → 拦截）
- 命令与配置参考（初始化器 / 规则生成器 / 错误分析器）
- 内置检查模板清单与扩展方法
- 跨平台说明（Windows polyglot hooks / macOS / Linux）
- FAQ

## 目录结构

```
auto-evolve-claude-plugin/
├── .claude-plugin/marketplace.json   # marketplace 清单（/plugin add 的入口）
└── auto-evolve/                      # 插件本体
    ├── .claude-plugin/plugin.json    # 插件清单
    ├── README.md                     # 完整文档 ⭐
    ├── hooks/                        # SessionStart / SessionEnd hooks
    ├── commands/init.md              # /auto-evolve:init 斜杠命令
    └── scripts/                      # 初始化器 / 规则生成器 / 错误分析器
```

## License

MIT — 见 [auto-evolve/LICENSE](auto-evolve/LICENSE)
