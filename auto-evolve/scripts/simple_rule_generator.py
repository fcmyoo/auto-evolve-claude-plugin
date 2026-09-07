#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版规则生成器 - 不依赖 API，生成规则模板由用户确认
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# 修复 Windows GBK 编码问题
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from analyze_errors import ErrorPatternAnalyzer


class SimpleRuleGenerator:
    """简化版规则生成器 - 生成规则建议，由 Claude Code 会话中的 AI 来完善"""

    def __init__(self):
        # scope: universal=任何项目适用 / project=仅本项目适用（依赖本项目路径）
        # project 级模板必须满足其 requires 路径存在才启用，避免在别的项目里"假检查"
        self.rule_templates = {
            'unicode-encoding': {
                'check_name': 'check_unicode_encoding',
                'scope': 'universal',
                'requires': [],
                'check_code': '''
if [ "$OS" = "Windows_NT" ] || [[ "$OSTYPE" == "msys" ]]; then
    if [ -z "$PYTHONIOENCODING" ]; then
        exit 1
    fi
fi
exit 0
''',
                'error_message': '未设置 Python 编码环境变量（Windows）',
                'fix_command': 'export PYTHONIOENCODING=utf-8',
                'severity': 'warning'
            },
            'charset-collation': {
                'check_name': 'check_charset_collation',
                'scope': 'project',
                'requires': ['backend/app'],
                'check_code': '''
grep -rn "JOIN.*ON.*=" backend/app --include="*.py" | grep -v "COLLATE" | head -1 > /dev/null
if [ $? -eq 0 ]; then
    exit 1
fi
exit 0
''',
                'error_message': '发现未加 COLLATE 的数据库 JOIN',
                'fix_command': '手动添加 COLLATE utf8mb4_unicode_ci 到 JOIN 语句',
                'severity': 'warning'
            },
            'column-not-found': {
                'check_name': 'check_config_columns',
                'scope': 'project',
                'requires': ['backend/scripts/validation/check_config_consistency.py'],
                'check_code': '''
python backend/scripts/validation/check_config_consistency.py > /dev/null 2>&1
if [ $? -ne 0 ]; then
    exit 1
fi
exit 0
''',
                'error_message': '配置列名与数据库不一致',
                'fix_command': 'python backend/scripts/validation/check_config_consistency.py',
                'severity': 'error'
            }
        }

    def generate_rule_from_template(self, error_type: str) -> dict | None:
        """从模板生成规则；project 级模板先验证依赖路径存在，不存在则视为不适用"""
        rule = self.rule_templates.get(error_type, None)
        if rule is None:
            return None
        if rule.get('scope') == 'project':
            for path in rule.get('requires', []):
                if not Path(path).exists():
                    return None
        return rule

    def integrate_rule_to_quick_check(self, rule: dict, quick_check_path: str):
        """将规则集成到 quick_check.sh（自动使用已修复的格式）"""
        with open(quick_check_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查规则是否已存在
        if rule['check_name'] in content:
            return False, "规则已存在"

        # severity: warning 计入 WARNINGS，error 计入 FAILED
        severity = rule.get('severity', 'warning')
        if severity == 'error':
            fail_block = f'''echo -e "${{RED}}FAIL${{NC}}"
        echo "   [ERROR] {rule['error_message']}"
        echo "   修复: {rule['fix_command']}"
        FAILED=$((FAILED + 1))'''
        else:
            fail_block = f'''echo -e "${{YELLOW}}WARNING${{NC}}"
        echo "   [WARNING] {rule['error_message']}"
        echo "   修复: {rule['fix_command']}"
        WARNINGS=$((WARNINGS + 1))'''

        # 计算下一个检查编号
        import re
        numbers = [int(m) for m in re.findall(r'^echo -n "(\d+)\. ', content, re.MULTILINE)]
        next_number = max(numbers) + 1 if numbers else 7

        # 构建新检查代码（与主脚本统一的计数器体系）
        new_check = f'''
# {rule['check_name']}（自动生成，模板见 simple_rule_generator.py）
echo -n "{next_number}. {rule['check_name'].replace('check_', '').replace('_', ' ').title()}... "
{rule['check_code']}
if [ $? -ne 0 ]; then
    {fail_block}
else
    echo -e "${{GREEN}}OK${{NC}}"
    PASSED=$((PASSED + 1))
fi
'''

        # 找到插入位置（最后一个检查之后）
        marker = "# ========================================="
        pos = content.rfind(marker)

        if pos > 0:
            new_content = content[:pos] + new_check + "\n" + content[pos:]

            # 备份（并确保备份文件不进 git）
            backup_path = f"{quick_check_path}.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self._ensure_backup_ignored()

            # 写入
            with open(quick_check_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return True, f"规则已添加（备份：{backup_path}）"

        return False, "找不到插入位置"

    def _ensure_backup_ignored(self):
        """元反馈#3：生成 .backup.* 时确保 gitignore 覆盖，避免备份文件混入工作区"""
        gitignore = Path('.gitignore')
        try:
            existing = gitignore.read_text(encoding='utf-8') if gitignore.exists() else ''
            if '*.backup.*' not in existing:
                with open(gitignore, 'a', encoding='utf-8') as f:
                    f.write('\n# 自动生成的备份文件\n*.backup.*\n')
        except Exception:
            pass


def main():
    import argparse

    parser = argparse.ArgumentParser(description='简化版规则生成器')
    parser.add_argument('--log-dir', default='.claude/error-logs')
    parser.add_argument('--days', type=int, default=1)
    parser.add_argument('--threshold', type=int, default=1)
    parser.add_argument('--quick-check', default='backend/scripts/validation/quick_check.sh')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--auto-commit', action='store_true')

    args = parser.parse_args()

    print("=" * 60)
    print("步骤1: 分析错误日志")
    print("=" * 60)

    analyzer = ErrorPatternAnalyzer(args.log_dir, args.days)
    analyzer.load_logs()
    analysis = analyzer.analyze()

    if not analysis or analysis['total_errors'] == 0:
        print("未发现错误日志")
        return

    print(f"总错误数: {analysis['total_errors']}")
    print()

    # 过滤需要生成规则的错误
    generator = SimpleRuleGenerator()
    rules_to_add = []

    # 项目没有 quick_check.sh 时不报错——日志照常分析，无宿主可写规则
    has_quick_check = Path(args.quick_check).exists()

    for error_type, count in analysis['top_errors']:
        if count < args.threshold:
            continue

        # 检查是否有模板（含 scope 路径验证）
        rule = generator.generate_rule_from_template(error_type)
        if not rule:
            print(f"跳过 {error_type}: 无适用模板")
            continue

        if not has_quick_check:
            print(f"跳过 {error_type}: 本项目无 quick_check.sh（{error_type} 已记录，不生成规则）")
            continue

        # 检查是否已存在
        with open(args.quick_check, 'r', encoding='utf-8') as f:
            if rule['check_name'] in f.read():
                print(f"跳过 {error_type}: 规则已存在")
                continue

        print(f"✓ {error_type}: {count} 次 → 将添加规则")
        rules_to_add.append((error_type, rule))

    if not rules_to_add:
        print("\n所有错误都已有规则或无适用模板")
        return

    print()
    print("=" * 60)
    print(f"步骤2: 添加 {len(rules_to_add)} 个规则")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN] 将添加的规则:")
        for error_type, rule in rules_to_add:
            print(f"\n--- {rule['check_name']} ---")
            print(rule['check_code'])
    else:
        for error_type, rule in rules_to_add:
            success, message = generator.integrate_rule_to_quick_check(rule, args.quick_check)
            if success:
                print(f"✓ {rule['check_name']}: {message}")
            else:
                print(f"✗ {rule['check_name']}: {message}")

        if args.auto_commit:
            import subprocess
            commit_msg = f"自动生成: 添加 {len(rules_to_add)} 个错误检查规则\n\n"
            for _, rule in rules_to_add:
                commit_msg += f"- {rule['check_name']}\n"

            subprocess.run(['git', 'add', args.quick_check])
            subprocess.run(['git', 'commit', '-m', commit_msg])
            print("\n✓ Git commit 已创建")

    print("\n" + "=" * 60)
    print("完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
