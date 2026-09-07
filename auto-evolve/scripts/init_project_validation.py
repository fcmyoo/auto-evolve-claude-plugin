#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目验证体系初始化器（模板选择式生成，强规范）。

强规范（修改本脚本前必读，违反任何一条即为 bug）：
1. 检查项只能来自 CHECK_TEMPLATES 注册表；注册表之外的业务检查只留占位段
2. 默认 dry-run；写入必须 --apply；被覆盖文件自动备份
3. 只写 PLAN 声明的文件，不触碰任何业务代码
4. 生成的 .sh 必须通过 bash -n 语法校验
5. settings.local.json 只合并 hooks 段，其他键原样保留
6. 错误捕获由全局 PostToolUse hook 负责，此处绝不重复配置（避免双写日志）
"""

import io
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

SKIP_DIRS = {'venv', '.venv', 'env', 'node_modules', '.git', '.claude', '__pycache__'}

QUICK_CHECK_LOCATIONS = [
    'backend/scripts/validation/quick_check.sh',
    'scripts/validation/quick_check.sh',
    '.claude/quick_check.sh',
]


# ---------------------------------------------------------------- 项目检测（只读）

def detect(root: Path) -> dict:
    ctx = {'root': root}
    ctx['has_git'] = (root / '.git').is_dir()

    ctx['has_python'] = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if any(f.endswith('.py') for f in filenames):
            ctx['has_python'] = True
            break

    pkg = None
    for cand in (root / 'package.json', root / 'frontend' / 'package.json'):
        if cand.is_file():
            pkg = cand
            break
    ctx['package_json'] = pkg
    ctx['node_dir_rel'] = pkg.parent.relative_to(root).as_posix() if pkg else ''

    env_example = next((c for c in (root / '.env.example', root / 'backend' / '.env.example') if c.is_file()), None)
    env_file = next((c for c in (root / '.env', root / 'backend' / '.env') if c.is_file()), None)
    ctx['env_example'] = env_example
    ctx['env_file'] = env_file
    ctx['env_rel'] = env_file.relative_to(root).as_posix() if env_file else ''
    if env_example:
        ctx['env_example_rel'] = env_example.relative_to(root).as_posix()
        keys = []
        for line in env_example.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                keys.append(line.split('=', 1)[0].strip())
        ctx['env_keys'] = keys
    else:
        ctx['env_example_rel'] = ''
        ctx['env_keys'] = []
    return ctx


# ---------------------------------------------------------------- 检查模板注册表（唯一合法来源）
# body 必须以"裸测试命令"结尾（把退出码留给外层 if 判断），严禁在 body 内 exit

CHECK_TEMPLATES = [
    {
        'id': 'python_encoding',
        'title': 'Python 编码环境',
        'severity': 'warning',
        'detect': lambda c: c['has_python'],
        'body': lambda c: (
            'ENCODING=$(python -c "import sys; print(sys.stdout.encoding.lower())" 2>/dev/null || echo unknown)\n'
            '[ "$ENCODING" = "utf-8" ] || [ "$ENCODING" = "utf8" ]\n'
        ),
        'fail_msg': lambda c: 'Python 输出编码不是 UTF-8（当前: $ENCODING）',
        'fix': lambda c: 'export PYTHONIOENCODING=utf-8',
    },
    {
        'id': 'git_status',
        'title': 'Git 工作区状态',
        'severity': 'warning',
        'detect': lambda c: c['has_git'],
        'body': lambda c: (
            'if [ -d .git ]; then\n'
            '    [ -z "$(git status --porcelain 2>/dev/null | head -1)" ]\n'
            'fi\n'
        ),
        'fail_msg': lambda c: 'Git 工作区有未提交改动',
        'fix': lambda c: 'git add/commit 或 stash',
    },
    {
        'id': 'env_required_keys',
        'title': '环境配置完整性',
        'severity': 'error',
        'detect': lambda c: bool(c['env_file'] and c['env_keys']),
        'body': lambda c: (
            'MISSING=""\n'
            'for KEY in ' + ' '.join(c['env_keys']) + '; do\n'
            '    grep -q "^${KEY}=" "' + c['env_rel'] + '" 2>/dev/null || MISSING="${MISSING}${KEY} "\n'
            'done\n'
            '[ -z "$MISSING" ]\n'
        ),
        'fail_msg': lambda c: '.env 缺少必需配置键',
        'fix': lambda c: '对照 ' + c['env_example_rel'] + ' 补齐缺失键',
    },
    {
        'id': 'node_deps',
        'title': 'Node 依赖安装',
        'severity': 'warning',
        'detect': lambda c: c['package_json'] is not None,
        'body': lambda c: '[ -d "' + c['node_dir_rel'] + '/node_modules" ]\n',
        'fail_msg': lambda c: 'npm 依赖未安装',
        'fix': lambda c: 'cd ' + c['node_dir_rel'] + ' && npm install',
    },
]


# ---------------------------------------------------------------- 代码渲染（固定格式）

def render_check(num: int, tpl: dict, ctx: dict) -> str:
    if tpl['severity'] == 'error':
        fail = (
            '        echo -e "${RED}FAIL${NC}"\n'
            '        echo "   [ERROR] ' + tpl['fail_msg'](ctx) + '"\n'
            '        echo "   修复: ' + tpl['fix'](ctx) + '"\n'
            '        FAILED=$((FAILED + 1))\n'
        )
    else:
        fail = (
            '        echo -e "${YELLOW}WARNING${NC}"\n'
            '        echo "   [WARNING] ' + tpl['fail_msg'](ctx) + '"\n'
            '        echo "   修复: ' + tpl['fix'](ctx) + '"\n'
            '        WARNINGS=$((WARNINGS + 1))\n'
        )
    return (
        '\n# 检查 ' + str(num) + ': ' + tpl['title'] + '（模板: ' + tpl['id'] + '）\n'
        'echo -n "' + str(num) + '. ' + tpl['title'] + '... "\n'
        + tpl['body'](ctx) +
        'if [ $? -ne 0 ]; then\n' + fail +
        'else\n'
        '    echo -e "${GREEN}OK${NC}"\n'
        '    PASSED=$((PASSED + 1))\n'
        'fi\n'
    )


SCAFFOLD_HEADER = '''#!/bin/bash
# 快速检查清单（由 init_project_validation.py 生成于 {date}）
# 强规范：新增检查必须按统一格式（编号 echo -n、接入 PASSED/FAILED/WARNINGS 计数）
#        项目专属检查只写在[占位段]，生成器不会自动发明

RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m'

PASSED=0
FAILED=0
WARNINGS=0

echo "========================================================================="
echo "  快速检查清单"
echo "========================================================================="
echo ""
'''

SCAFFOLD_FOOTER = '''
# [项目专属检查占位] —— 数据库连通性、业务表、领域规则等由人工按上面格式添加
# 生成器强规范：不自动生成此段内容

echo ""
echo "========================================================================="
echo "  检查结果汇总"
echo "========================================================================="
echo -e "  ${GREEN}通过:${NC} $PASSED"
echo -e "  ${RED}失败:${NC} $FAILED"
echo -e "  ${YELLOW}警告:${NC} $WARNINGS"
echo "========================================================================="

if [ "$FAILED" -gt 0 ]; then
    echo -e "  ${RED}[BLOCKED] 发现阻断性问题，请先修复${NC}"
    exit 1
elif [ "$WARNINGS" -gt 0 ]; then
    echo -e "  ${YELLOW}[OK WITH WARNINGS] 可以继续开发，建议处理警告${NC}"
    exit 2
else
    echo -e "  ${GREEN}[ALL CLEAR] 所有检查通过${NC}"
    exit 0
fi
'''


SESSION_START_SH = '''#!/bin/bash
# Claude Code Session Start Hook（init_project_validation.py 生成）
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

QUICK_CHECK=""
for p in backend/scripts/validation/quick_check.sh scripts/validation/quick_check.sh .claude/quick_check.sh; do
    if [ -f "${PROJECT_ROOT}/$p" ]; then QUICK_CHECK="$p"; break; fi
done

[ -z "${QUICK_CHECK}" ] && exit 0

echo ""
echo "========================================="
echo "  Claude Code 会话启动检查"
echo "========================================="
echo ""
bash "${PROJECT_ROOT}/${QUICK_CHECK}"
EXIT_CODE=$?
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "所有检查通过，可以开始开发"
elif [ $EXIT_CODE -eq 2 ]; then
    echo "存在警告，可继续开发"
else
    echo "发现阻断性问题，建议先修复"
fi
echo "========================================="
echo ""
exit 0
'''

SESSION_END_SH = '''#!/bin/bash
# Session End Hook（init_project_validation.py 生成）- 会话结束时分析错误并生成规则
PROJECT_DIR="${CLAUDE_PROJECT_DIR}"
LOG_DIR="${PROJECT_DIR}/.claude/error-logs"
LOG_FILE="${LOG_DIR}/errors-$(date +%Y-%m-%d).jsonl"

[ -f "${LOG_FILE}" ] || exit 0
ERROR_COUNT=$(grep -c . "${LOG_FILE}" 2>/dev/null || echo 0)
[ "${ERROR_COUNT}" -ge 1 ] || exit 0

echo ""
echo "========================================="
echo "  会话结束 - 检测到 ${ERROR_COUNT} 个错误，分析中..."
echo "========================================="

GENERATOR=""
[ -f "${PROJECT_DIR}/backend/scripts/validation/simple_rule_generator.py" ] && \\
    GENERATOR="${PROJECT_DIR}/backend/scripts/validation/simple_rule_generator.py"
[ -z "${GENERATOR}" ] && [ -f "${HOME}/.claude/validation-toolkit/simple_rule_generator.py" ] && \\
    GENERATOR="${HOME}/.claude/validation-toolkit/simple_rule_generator.py"
[ -z "${GENERATOR}" ] && { echo "未找到规则生成器，跳过（日志已保留）"; exit 0; }

QUICK_CHECK=""
for p in backend/scripts/validation/quick_check.sh scripts/validation/quick_check.sh .claude/quick_check.sh; do
    [ -f "${PROJECT_DIR}/$p" ] && { QUICK_CHECK="$p"; break; }
done

cd "${PROJECT_DIR}"
ARGS=(--log-dir "${LOG_DIR}" --days 1 --threshold 1)
[ -n "${QUICK_CHECK}" ] && ARGS+=(--quick-check "${QUICK_CHECK}")
python "${GENERATOR}" "${ARGS[@]}" 2>&1

echo "========================================="
echo ""
exit 0
'''

CMD_WRAPPER = ''': << 'CMDBLOCK'
@echo off
"C:\\Program Files\\Git\\bin\\bash.exe" -l -c "cd \\"$(cygpath -u \\"%CLAUDE_PROJECT_DIR%\\")\\" && bash \\".claude/hooks/{script}.sh\\""
exit /b
CMDBLOCK

# Unix shell runs from here
"${{CLAUDE_PROJECT_DIR}}/.claude/hooks/{script}.sh"
'''

HOOK_BLOCKS = {
    'SessionStart': [{
        'matcher': 'startup|resume|clear',
        'hooks': [{'type': 'command',
                   'command': 'bash "${CLAUDE_PROJECT_DIR}/.claude/hooks/session-start.sh"'}],
    }],
    'SessionEnd': [{
        'matcher': 'exit',
        'hooks': [{'type': 'command',
                   'command': 'bash "${CLAUDE_PROJECT_DIR}/.claude/hooks/session-end.sh"'}],
    }],
}


def merge_settings(root: Path) -> str:
    p = root / '.claude' / 'settings.local.json'
    data = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            return 'settings.local.json 解析失败，跳过合并（未改动）'
    hooks = data.setdefault('hooks', {})
    changed = []
    for name, block in HOOK_BLOCKS.items():
        if name not in hooks:
            hooks[name] = block
            changed.append(name)
    if not changed:
        return 'settings.local.json: hooks 已存在，无需合并'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 'settings.local.json: 已合并 hooks 段（' + ', '.join(changed) + '），其他键未动'


# ---------------------------------------------------------------- 主流程

def main():
    import argparse
    ap = argparse.ArgumentParser(description='项目验证体系初始化器（模板选择式，强规范）')
    ap.add_argument('--root', default='.')
    ap.add_argument('--apply', action='store_true', help='实际写入（默认 dry-run）')
    args = ap.parse_args()

    root = Path(args.root).resolve()
    ctx = detect(root)

    print('=' * 64)
    print('  项目验证体系初始化（强规范：模板选择式生成，不发散）')
    print('=' * 64)

    print('\n[检测报告]')
    print('  项目根: ' + str(root))
    print('  Git 仓库: ' + ('是' if ctx['has_git'] else '否'))
    print('  Python 代码: ' + ('是' if ctx['has_python'] else '否'))
    print('  Node 前端: ' + ('是' if ctx['package_json'] else '否'))
    print('  环境配置: 实际=' + str(ctx['env_file'] or '未找到') + ' 示例=' + str(ctx['env_example'] or '未找到'))
    if ctx['env_keys']:
        shown = ', '.join(ctx['env_keys'][:8]) + (' ...' if len(ctx['env_keys']) > 8 else '')
        print('  必需配置键 (' + str(len(ctx['env_keys'])) + '): ' + shown)

    checks = [t for t in CHECK_TEMPLATES if t['detect'](ctx)]
    if not checks:
        print('\n未检测到可生成的检查项（项目结构过于简单或为空）')
        return

    target_dir = 'backend/scripts/validation' if (root / 'backend').is_dir() else '.claude'
    quick_target = target_dir + '/quick_check.sh'

    print('\n[生成计划]')
    print('  1. ' + quick_target + ' — 检查项: ' + ', '.join(t['id'] for t in checks))
    print('  2. .claude/hooks/session-start.sh + .cmd')
    print('  3. .claude/hooks/session-end.sh + .cmd')
    print('  4. .claude/settings.local.json — 仅合并 hooks 段')
    print('  5. .claude/error-logs/ 目录')

    print('\n[强规范声明]')
    print('  - 检查项全部来自模板注册表，未发明任何项目专属逻辑')
    print('  - 项目专属检查（数据库/业务规则）只在占位段留注释，需人工添加')
    print('  - 错误捕获由全局 PostToolUse hook 负责，此处不重复配置')
    print('  - 已存在文件自动备份后写入')

    if not args.apply:
        print('\n[DRY RUN] 未写入任何文件。确认后加 --apply 执行。')
        return

    stamps = datetime.now().strftime('%Y%m%d%H%M%S')
    results = []

    def write(path: Path, content: str):
        if path.exists():
            backup = path.with_name(path.name + '.backup.' + stamps)
            shutil.copy2(path, backup)
            results.append('  备份: ' + backup.relative_to(root).as_posix())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
        results.append('  写入: ' + path.relative_to(root).as_posix())

    checks_content = SCAFFOLD_HEADER.format(date=datetime.now().strftime('%Y-%m-%d %H:%M'))
    for i, t in enumerate(checks, 1):
        checks_content += render_check(i, t, ctx)
    checks_content += SCAFFOLD_FOOTER
    write(root / quick_target, checks_content)

    write(root / '.claude/hooks/session-start.sh', SESSION_START_SH)
    write(root / '.claude/hooks/session-end.sh', SESSION_END_SH)
    write(root / '.claude/hooks/session-start.cmd', CMD_WRAPPER.format(script='session-start'))
    write(root / '.claude/hooks/session-end.cmd', CMD_WRAPPER.format(script='session-end'))
    results.append('  ' + merge_settings(root))
    (root / '.claude' / 'error-logs').mkdir(parents=True, exist_ok=True)
    results.append('  创建: .claude/error-logs/')

    print('\n[写入结果]')
    for r in results:
        print(r)

    print('\n[语法校验]')
    ok = True
    git_bash = r'C:\Program Files\Git\bin\bash.exe'
    use_git_bash = Path(git_bash).exists()
    for rel in (quick_target, '.claude/hooks/session-start.sh', '.claude/hooks/session-end.sh'):
        # Windows 上裸 `bash` 可能命中 WSL 占位程序，优先用 Git Bash 完整路径
        cmd = ([git_bash] if use_git_bash else ['bash']) + ['-n', Path(rel).as_posix()]
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
        if proc.returncode == 0:
            print('  bash -n 通过: ' + rel)
        else:
            print('  bash -n 失败: ' + rel)
            print('    ' + (proc.stderr or proc.stdout or '').strip()[:200])
            ok = False
    if not ok:
        sys.exit(1)

    print('\n[完成] 重启 Claude Code 会话后生效。')


if __name__ == '__main__':
    main()
