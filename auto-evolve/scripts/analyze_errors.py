#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错误模式分析器 v1.1
分析 .claude/error-logs/ 中的错误日志，识别高频错误模式。

v1.1 变更：
- 三级分类：error_signature（hook 预提取）→ 错误文本关键词 → unknown
- 未知错误按签名相似度聚类，报告列出代表性样本供人工沉淀模板
- 兼容新旧日志格式（v1.0 无 error_signature 字段也能跑）
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# 关键词 → 语义错误类型（第二级分类：hook 没给 signature 时对错误文本匹配）
KEYWORD_MAP = [
    (r'UnicodeEncodeError|gbk codec', 'unicode-encoding'),
    (r'Illegal mix of collations', 'charset-collation'),
    (r'Unknown column', 'column-not-found'),
    (r"Table '[^']*' doesn't exist|doesn't exist", 'table-not-found'),
    (r'AttributeError', 'attribute-error'),
    (r'FileNotFoundError|No such file or directory', 'file-not-found'),
    (r'ImportError|ModuleNotFoundError', 'import-error'),
    (r'PermissionError|Access denied|EPERM', 'permission-error'),
    (r'TimeoutError|timed out|ETIMEDOUT', 'timeout'),
    (r'SyntaxError|IndentationError', 'syntax-error'),
    (r'TypeError', 'type-error'),
    (r'KeyError', 'key-error'),
    (r'ValueError', 'value-error'),
    (r'ConnectionError|Connection refused|Can\'t connect', 'connection-error'),
    (r'null值|NULL值|非空|NOT NULL constraint', 'null-constraint'),
    (r'npm ERR!|node_modules', 'npm-error'),
    (r'git .*failed|fatal: .*git', 'git-error'),
]


class ErrorPatternAnalyzer:
    def __init__(self, log_dir: str, days: int = 7):
        """
        Args:
            log_dir: 错误日志目录
            days: 分析最近几天的日志
        """
        self.log_dir = Path(log_dir)
        self.days = days
        self.errors = []
        self.skipped_invalid = 0  # v1.0 时代的损坏记录（exit_code":, 非法JSON）

    def load_logs(self):
        """加载错误日志"""
        cutoff_date = datetime.now() - timedelta(days=self.days)

        for log_file in self.log_dir.glob("errors-*.jsonl"):
            date_str = log_file.stem.replace("errors-", "")
            try:
                log_date = datetime.strptime(date_str, "%Y-%m-%d")
                if log_date < cutoff_date:
                    continue
            except ValueError:
                continue

            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        # 排除空壳记录（旧 bug 产物：全空字段）
                        if not d.get('tool') and not d.get('error'):
                            self.skipped_invalid += 1
                            continue
                        self.errors.append(d)
                    except json.JSONDecodeError:
                        self.skipped_invalid += 1

    def classify(self, error: dict) -> str:
        """三级分类：hook 预提取签名 → 关键词 → unknown"""
        # 第一级：v1.1 hook 预提取的 error_signature（已是语义化签名）
        sig = error.get('error_signature', '')
        if sig:
            return self._normalize_sig(sig)

        # 第二级：对错误文本做关键词匹配（兼容 v1.0 日志）
        error_msg = str(error.get('error', ''))
        if error_msg:
            for pattern, etype in KEYWORD_MAP:
                if re.search(pattern, error_msg, re.IGNORECASE):
                    return etype

        # 第三级：无法分类
        if not error_msg:
            return 'exit-code-only'
        return 'unknown'

    def _normalize_sig(self, sig: str) -> str:
        """把 hook 的 error_signature 归一化为语义类型名"""
        if sig.startswith('mysql-'):
            # mysql-1054=列不存在, 1146=表不存在, 1062=唯一键冲突
            return {'mysql-1054': 'column-not-found',
                    'mysql-1146': 'table-not-found',
                    'mysql-1062': 'duplicate-key'}.get(sig, sig)
        if sig.endswith('Error') or sig.endswith('Exception'):
            # KeyError→key-error, ValueError→value-error, mysql连接类→connection-error
            return {
                'UnicodeEncodeError': 'unicode-encoding',
                'AttributeError': 'attribute-error',
                'FileNotFoundError': 'file-not-found',
                'ModuleNotFoundError': 'import-error',
                'ImportError': 'import-error',
                'PermissionError': 'permission-error',
                'SyntaxError': 'syntax-error',
                'KeyError': 'key-error',
                'TypeError': 'type-error',
                'ValueError': 'value-error',
                'TimeoutError': 'timeout',
            }.get(sig, sig.lower().replace('error', '-error', 1) if 'Error' in sig else sig.lower())
        if sig.startswith('exit-'):
            return f'{sig}-generic'
        return sig.lower().replace('_', '-')

    def analyze(self):
        """分析错误模式"""
        if not self.errors:
            return None

        error_types = Counter()
        error_details = defaultdict(list)
        unknown_sigs = Counter()  # unknown 组按原始签名二次聚合

        for error in self.errors:
            error_type = self.classify(error)
            error_types[error_type] += 1

            raw_sig = error.get('error_signature') or str(error.get('error', ''))[:60]
            if error_type in ('unknown', 'exit-code-only') or error_type.endswith('-generic'):
                unknown_sigs[raw_sig] += 1

            error_details[error_type].append({
                'timestamp': error.get('timestamp', 'unknown'),
                'tool': error.get('tool', 'unknown'),
                'command': str(error.get('command', ''))[:100],
                'error': str(error.get('error', f"exit_code={error.get('exit_code', '?')}"))[:200],
                'signature': raw_sig,
                'project': error.get('project', ''),
            })

        return {
            'period': f'最近 {self.days} 天',
            'total_errors': len(self.errors),
            'skipped_invalid': self.skipped_invalid,
            'error_types': dict(error_types),
            'top_errors': error_types.most_common(10),
            'unknown_sigs': unknown_sigs.most_common(10),
            'details': dict(error_details),
        }

    def generate_report(self) -> str:
        """生成分析报告"""
        analysis = self.analyze()

        if not analysis or analysis['total_errors'] == 0:
            msg = "未发现错误日志"
            if analysis and analysis['skipped_invalid']:
                msg += f"（跳过 {analysis['skipped_invalid']} 条无效/损坏记录）"
            return msg

        total = analysis['total_errors']
        report = []
        report.append("=" * 64)
        report.append(f"错误模式分析报告 - {analysis['period']}")
        report.append("=" * 64)
        report.append(f"总错误数: {total}（另有 {analysis['skipped_invalid']} 条损坏记录已跳过）")
        report.append("")

        # 分类质量指标
        known = total - sum(n for t, n in analysis['top_errors']
                            if t in ('unknown', 'exit-code-only') or t.endswith('-generic'))
        report.append(f"分类质量: {known}/{total} 已识别语义类型"
                      f"（{known/total*100:.0f}%）")
        report.append("")
        report.append("高频错误 TOP 10:")
        report.append("")
        for i, (error_type, count) in enumerate(analysis['top_errors'], 1):
            pct = count / total * 100
            report.append(f"{i}. {error_type}: {count} 次 ({pct:.1f}%)")

        # unknown 聚类详情——人工沉淀模板的输入
        if analysis['unknown_sigs']:
            report.append("")
            report.append("⚠ 未分类错误聚类（供人工判断是否沉淀新模板）:")
            report.append("")
            for sig, count in analysis['unknown_sigs']:
                report.append(f"  {count:3d}x  [{sig}]")

        report.append("")
        report.append("详细示例（每类最近 3 条）:")
        report.append("")
        for error_type, count in analysis['top_errors']:
            report.append(f"## {error_type} ({count} 次)")
            for example in analysis['details'][error_type][:3]:
                proj = example.get('project', '')
                proj_part = f" @ {proj}" if proj else ""
                report.append(f"  {example['timestamp']}{proj_part}")
                report.append(f"    {example['tool']}: {example['error'][:120]}")
            report.append("")

        report.append("=" * 64)
        return "\n".join(report)

    def should_create_rule(self, error_type: str, count: int) -> bool:
        """判断是否应该为此错误创建检查规则（铁律：跨项目≥3次才收录）"""
        threshold = 3
        known_errors = {'unicode-encoding', 'charset-collation', 'column-not-found'}
        return count >= threshold and error_type not in known_errors


def main():
    import argparse

    parser = argparse.ArgumentParser(description='分析 Claude Code 错误日志')
    parser.add_argument('--log-dir', default='.claude/error-logs',
                        help='错误日志目录')
    parser.add_argument('--days', type=int, default=7,
                        help='分析最近几天的日志')
    parser.add_argument('--output', default='',
                        help='输出报告路径（默认只打印到终端）')

    args = parser.parse_args()

    analyzer = ErrorPatternAnalyzer(args.log_dir, args.days)
    analyzer.load_logs()

    report = analyzer.generate_report()
    print(report)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n报告已保存到: {args.output}")


if __name__ == '__main__':
    main()
