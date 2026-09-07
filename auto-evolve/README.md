# auto-evolve

[![GitHub](https://img.shields.io/badge/GitHub-fcmyoo%2Fauto--evolve--claude--plugin-blue)](https://github.com/fcmyoo/auto-evolve-claude-plugin)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Plugin-purple)](https://docs.claude.com/en/docs/claude-code/plugins)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**让 Claude Code 从你的错误中学习。** 一个会话自动进化插件：启动时自动检查项目健康度，会话结束时自动分析错误日志、生成新的检查规则——下次启动时，昨天犯的错就再也犯不了了。

```
第 1 天：遇到 UnicodeEncodeError        → 自动记录
第 1 天：关闭会话                       → 自动分析，生成检查规则
第 2 天：打开会话                       → 自动检测环境缺陷，提示修复
第 3 天：这个错误消失了                  → 系统继续学习下一个错误
```

无需 API Key，无需外部服务，完全本地运行。

---

## 目录

- [为什么需要它](#为什么需要它)
- [工作原理](#工作原理)
- [安装](#安装)
- [快速开始](#快速开始)
- [三阶段进化闭环](#三阶段进化闭环)
- [强规范设计：为什么它不会失控](#强规范设计为什么它不会失控)
- [命令参考](#命令参考)
- [配置参考](#配置参考)
- [目录结构](#目录结构)
- [跨平台说明（Windows/macOS/Linux）](#跨平台说明windowsmacoslinux)
- [FAQ](#faq)
- [致谢](#致谢)
- [License](#license)

---

## 为什么需要它

使用 Claude Code 开发时，工具调用错误往往**重复发生**：

- Windows GBK 终端遇到 Unicode 字符 → `UnicodeEncodeError`
- MySQL 表排序规则不一致 → `Illegal mix of collations`
- 配置里的列名和数据库实际列名不一致 → `Unknown column`
- 改了方法名忘了改调用方 → `AttributeError`

每次都是：出错 → 排查 → 修复 → **下一个会话接着犯**。

人不会吸取教训可以理解，但工具不应该。auto-evolve 把这个循环变成自动的：

```
   ┌──────────────────────────────────────────────┐
   │                                              │
   ▼                                              │
 遇到错误 ──► 自动记录 ──► 会话结束自动分析 ──► 自动生成规则
                                                  │
   下次启动 ◄───────────── 规则写入检查清单 ◄──────┘
   提前拦截
```

## 工作原理

### 三层架构

```
┌─ 全局层（所有项目共享，安装一次）──────────────────┐
│  PostToolUse Hook：捕获所有工具调用错误              │
│  双写日志：全局日志（带项目标识）+ 项目本地日志        │
│  只记录，不判断 —— 数据积累层                        │
└──────────────────────────────────────────────────┘
                      ↓
┌─ 项目层（每个项目按需启用）────────────────────────┐
│  SessionStart Hook：运行 quick_check.sh 检查清单    │
│  SessionEnd Hook：分析当日错误 → 生成/更新检查规则   │
└──────────────────────────────────────────────────┘
                      ↓
┌─ 模板库（强规范核心）──────────────────────────────┐
│  CHECK_TEMPLATES 注册表：检查项的唯一合法来源        │
│  scope: universal → 任何项目适用                    │
│  scope: project  → 验证依赖路径存在才启用            │
└──────────────────────────────────────────────────┘
```

### 进化闭环

| 阶段 | 触发时机 | 做什么 |
|------|---------|--------|
| **捕获** | 每次工具调用失败（PostToolUse） | 写入 JSONL 日志：时间戳、工具名、退出码、错误摘要 |
| **进化** | 会话结束（SessionEnd） | 分析当日日志 → 识别高频错误 → 从模板库生成检查项 → 写入 quick_check.sh |
| **拦截** | 会话启动（SessionStart） | 运行检查清单 → 环境缺陷当场提示修复，错误还没发生就被拦住 |

## 安装

### 前置要求

- [Claude Code](https://docs.claude.com/en/docs/claude-code/overview)（CLI、桌面版或 VS Code 扩展均可）
- Python 3.10+（规则生成器用）
- Bash（Windows 用户：Git for Windows 自带的 Git Bash）

### 方式一：从 GitHub 安装（推荐）

```bash
# 1. 添加 marketplace
# 在 Claude Code 会话中输入：
/plugin marketplace add fcmyoo/auto-evolve-claude-plugin

# 2. 安装插件
/plugin install auto-evolve@lee-local

# 3. 重启 Claude Code 会话
```

### 方式二：本地克隆安装

```bash
git clone https://github.com/fcmyoo/auto-evolve-claude-plugin.git
cd auto-evolve-claude-plugin

# 在 Claude Code 会话中输入：
/plugin marketplace add /path/to/auto-evolve-claude-plugin
/plugin install auto-evolve@lee-local
```

### 安装全局错误捕获（可选但强烈推荐）

插件自带 SessionStart/SessionEnd hooks。错误捕获 PostToolUse hook 需单独配置一次（全局生效，所有项目共享）：

创建 `~/.claude/hooks/log-error.sh`（内容见 [scripts/](auto-evolve/scripts/) 说明），并在 `~/.claude/settings.json` 添加：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|Edit|Write|Read",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PROJECT_DIR:+~/.claude/hooks/log-error.sh}\""
          }
        ]
      }
    ]
  }
}
```

> 不配置这一步也能用——SessionStart 检查和 `/auto-evolve:init` 完全独立工作。配置后才有错误数据积累，进化闭环才完整。

## 快速开始

### 在已有项目中启用

```bash
# 在项目根目录的 Claude Code 会话中：
/auto-evolve:init
```

插件会：

1. **扫描项目**——检测 Python / Node / Git / 环境配置文件
2. **展示计划**——dry-run 输出将被生成的文件和选中的检查项，等你确认
3. **生成配置**——确认后写入 quick_check.sh + hooks 配置
4. **语法校验**——所有生成的 shell 脚本强制过 `bash -n`

生成后重启会话，每次启动自动检查。

### 在新项目中使用

什么都不用做。插件对未初始化的项目**静默跳过**——零打扰。等你写了一些代码，随时 `/auto-evolve:init`。

### 观察进化

```bash
# 查看错误统计
python <插件目录>/scripts/analyze_errors.py --log-dir .claude/error-logs --days 7

# 手动触发规则生成（预览模式）
python <插件目录>/scripts/simple_rule_generator.py --log-dir .claude/error-logs --dry-run

# 直接运行检查清单
bash backend/scripts/validation/quick_check.sh
```

## 三阶段进化闭环

### 1. 捕获（实时）

每次工具调用失败，PostToolUse hook 解析 stdin JSON，提取工具名、退出码和错误摘要，写入：

```
.claude/error-logs/errors-YYYY-MM-DD.jsonl     # 项目本地
~/.claude/error-logs/errors-YYYY-MM-DD.jsonl   # 全局（带项目标识）
```

成功调用（exit_code=0）直接忽略，日志只增不扰。

### 2. 进化（会话结束时）

SessionEnd hook 检查当日日志：

- 无错误 → 静默退出（毫秒级）
- 有错误 → 调用规则生成器 → 识别高频错误类型 → 从模板库匹配 → 自动追加检查项到 quick_check.sh

生成器内置防重复：已有规则不重加，无 quick_check.sh 的项目优雅跳过并保留日志。

### 3. 拦截（下次启动）

SessionStart hook 运行检查清单，典型输出：

```
=========================================================================
  快速检查清单
=========================================================================

1. Python 编码环境... WARNING
   [WARNING] Python 输出编码不是 UTF-8（当前: gbk）
   修复: export PYTHONIOENCODING=utf-8
2. Git 工作区状态... OK
3. 环境配置完整性... FAIL
   [ERROR] .env 缺少必需配置键
   修复: 对照 .env.example 补齐缺失键
4. Node 依赖安装... OK

=========================================================================
  通过: 2 | 失败: 1 | 警告: 1
=========================================================================
```

错误分级：`error` 计入失败（BLOCKED 提示），`warning` 计入警告（可继续开发）。

## 强规范设计：为什么它不会失控

自动生成代码的系统最大的风险是**发散**——生成的代码越来越随意，最终不可维护。auto-evolve 用机制而非约定来防发散：

| 规范 | 实现方式 |
|------|---------|
| 检查项只能来自注册表 | `CHECK_TEMPLATES` 是唯一合法来源，生成器无法即兴发明检查逻辑 |
| scope 分级 | `universal` 模板全局适用；`project` 模板必须验证依赖路径存在才启用——在别的项目里不会产生“假检查” |
| 生成的代码自包含 | 模板以 `exit 0` 结尾，不污染宿主脚本控制流 |
| 接入统一统计体系 | 生成的检查项使用宿主脚本的 `PASSED/FAILED/WARNINGS` 计数器，编号从宿主实测提取 |
| 默认 dry-run | 初始化器不带 `--apply` 只展示计划，不写文件 |
| 只写声明的文件 | 初始化器只触碰 5 个目标文件，绝不碰业务代码 |
| 生成即校验 | 每个生成的 .sh 强制 `bash -n`，失败即整体失败 |
| 配置只合并不覆盖 | `settings.local.json` 用合并语义，用户已有配置原样保留 |
| 项目专属检查留给人工 | 数据库连通性、业务规则等只在占位段留注释，生成器不碰 |

**自动化管共性，人管个性。**

## 命令参考

### 斜杠命令

| 命令 | 说明 |
|------|------|
| `/auto-evolve:init` | 为当前项目初始化检查体系（dry-run 展示计划 → 确认 → 写入 + 校验） |

### 初始化器

```bash
python scripts/init_project_validation.py --root <项目根> [--apply]
```

| 参数 | 说明 |
|------|------|
| `--root` | 项目根路径（默认当前目录） |
| `--apply` | 实际写入（默认 dry-run） |

自动检测：Git 仓库、Python 代码、`package.json`、`.env` / `.env.example` 及其必需键。

生成位置自动选择：有 `backend/` 目录 → `backend/scripts/validation/`，否则 → `.claude/`。

### 规则生成器

```bash
python scripts/simple_rule_generator.py --log-dir <日志目录> [选项]
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `--log-dir` | `.claude/error-logs` | 错误日志目录 |
| `--days` | `1` | 分析最近 N 天 |
| `--threshold` | `1` | 错误出现多少次才生成规则 |
| `--quick-check` | `backend/scripts/validation/quick_check.sh` | 规则宿主文件（不存在时优雅跳过） |
| `--dry-run` | — | 只预览不写入 |

### 错误分析器

```bash
python scripts/analyze_errors.py --log-dir <目录> --days <N> [--output <报告路径>]
```

输出高频错误 TOP 5 + 详细示例，兼容新旧两种日志格式。

## 配置参考

### 内置检查模板

| 模板 ID | scope | 检测条件 | 检查内容 | 默认级别 |
|--------|-------|---------|---------|---------|
| `python_encoding` | universal | 项目含 .py 文件 | stdout 编码是否 UTF-8 | warning |
| `git_status` | universal | 存在 .git | 工作区是否有未提交改动 | warning |
| `env_required_keys` | project | 存在 .env + .env.example | .env 是否包含示例文件声明的全部键 | error |
| `node_deps` | project | 存在 package.json | node_modules 是否已安装 | warning |

### 扩展模板

编辑 `scripts/init_project_validation.py` 的 `CHECK_TEMPLATES` 列表即可注册新模板。每个模板四个函数式字段：`detect`（是否适用）、`body`（检查命令，必须以裸测试结尾）、`fail_msg`、`fix`。

### SessionEnd 进化参数

编辑生成到项目的 `.claude/hooks/session-end.sh`：

```bash
ARGS=(--log-dir "${LOG_DIR}" --days 1 --threshold 1)
#                          ↑ 分析窗口   ↑ 生成阈值
```

## 目录结构

```
auto-evolve-claude-plugin/
├── .claude-plugin/
│   └── plugin.json              # 插件清单
├── hooks/
│   ├── hooks.json               # SessionStart / SessionEnd 注册
│   ├── session-start.sh / .cmd  # 启动检查（polyglot 跨平台）
│   └── session-end.sh / .cmd    # 结束进化
├── commands/
│   └── init.md                  # /auto-evolve:init 斜杠命令
├── scripts/
│   ├── init_project_validation.py   # 项目初始化器（模板选择式）
│   ├── simple_rule_generator.py     # 规则生成器
│   └── analyze_errors.py            # 错误分析器
└── README.md
```

运行时数据（每个项目独立）：

```
<项目>/.claude/
├── error-logs/errors-YYYY-MM-DD.jsonl   # 错误日志
└── settings.local.json                  # hooks 配置（初始化时合并）
<项目>/backend/scripts/validation/
└── quick_check.sh                       # 检查清单（进化的宿主）
```

## 跨平台说明（Windows/macOS/Linux）

| 平台 | hooks 执行方式 | 说明 |
|------|---------------|------|
| Windows | `.cmd` polyglot 包装 → Git Bash | 需安装 [Git for Windows](https://git-scm.com/download/win)，包装器自动定位 `bash.exe` 并用 `cygpath` 转换路径 |
| macOS / Linux | `.sh` 直接执行 | 无额外依赖 |

Windows 上 Claude Code 通过 CMD 执行 hook 命令，`.cmd` 文件同时是合法的 CMD 脚本和 Bash 脚本（polyglot 技术，同 [superpowers](https://github.com/obra/superpowers) 插件的方案），避免了 `.sh` 被 CMD 当文本打开的经典问题。

## FAQ

**Q：会和项目的 Claude 配置冲突吗？**
A：不会。初始化器对 `settings.local.json` 只做合并（`setdefault` 语义），已有 permissions 等配置原样保留；hooks 段已存在时跳过。

**Q：错误日志会无限增长吗？**
A：日志按天分文件（`errors-YYYY-MM-DD.jsonl`）。建议定期清理 30 天前的文件，或加个 cron。日志单条 ~200 字节，日常使用一年也就几 MB。

**Q：生成的规则错了怎么办？**
A：规则写入 quick_check.sh 前会自动备份原文件（时间戳后缀），直接恢复备份即可。也可以手动编辑 quick_check.sh——生成器只追加，不重写你手工添加的部分。

**Q：为什么不用 AI 生成检查规则？**
A：试过。AI 生成的好处是能处理未知错误，坏处是不可预测、不可审计。模板方案的规则 100% 可读、可预测、可版本控制。等规则库成熟后可以考虑 AI 辅助扩展模板本身。

**Q：SessionEnd hook 会在会话结束时拖慢退出吗？**
A：无错误时毫秒级退出（一次文件存在性检查）。有错误时运行 Python 分析，通常 2-5 秒。

**Q：支持哪些错误类型的自动规则？**
A：当前内置 3 个规则模板：`unicode-encoding`、`charset-collation`、`column-not-found`。其他错误类型会被记录和统计（analyze_errors.py 可查看），但需要人工沉淀为新模板——这是有意的设计，防止为一次性错误生成垃圾规则。

## 致谢

- [superpowers](https://github.com/obra/superpowers) by Jesse Vincent —— polyglot hooks 的 Windows 兼容方案和插件结构参考
- [Claude Code Plugins](https://docs.claude.com/en/docs/claude-code/plugins) 官方插件体系

## License

MIT
