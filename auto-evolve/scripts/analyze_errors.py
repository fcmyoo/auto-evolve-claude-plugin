#!/usr/bin/env python3
"""
错误模式分析器
分析 .claude/error-logs/ 中的错误日志，识别高频错误模式
"""

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path


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

    def load_logs(self):
        """加载错误日志"""
        cutoff_date = datetime.now() - timedelta(days=self.days)

        for log_file in self.log_dir.glob("errors-*.jsonl"):
            # 从文件名提取日期
            date_str = log_file.stem.replace("errors-", "")
            try:
                log_date = datetime.strptime(date_str, "%Y-%m-%d")
                if log_date < cutoff_date:
                    continue
            except ValueError:
                continue

            # 读取日志
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self.errors.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

    def extract_error_type(self, error: dict) -> str:
        """从错误信息中提取错误类型"""
        error_msg = error.get('error', '')

        # 常见错误模式
        patterns = {
            'UnicodeEncodeError': 'unicode-encoding',
            'Illegal mix of collations': 'charset-collation',
            'Unknown column': 'column-not-found',
            'Table.*doesn\'t exist': 'table-not-found',
            'AttributeError': 'attribute-error',
            'File does not exist': 'file-not-found',
            'Exit code 1': 'general-failure',
        }

        for pattern, error_type in patterns.items():
            if pattern.lower() in error_msg.lower():
                return error_type

        # 新格式日志（全局 hook 只有 exit_code，无错误文本）无法分类
        if not error_msg:
            return 'exit-code-only'

        return 'unknown'

    def analyze(self):
        """分析错误模式"""
        if not self.errors:
            return None

        # 按错误类型统计
        error_types = Counter()
        error_details = defaultdict(list)

        for error in self.errors:
            error_type = self.extract_error_type(error)
            error_types[error_type] += 1
            # 兼容新旧日志格式：新全局日志无 command/error 字段（hook 只拿到 exit_code）
            error_details[error_type].append({
                'timestamp': error.get('timestamp', 'unknown'),
                'tool': error.get('tool', 'unknown'),
                'command': str(error.get('command', ''))[:100],
                'error': str(error.get('error', f"exit_code={error.get('exit_code', '?')}"))[:200],
            })

        return {
            'period': f'最近 {self.days} 天',
            'total_errors': len(self.errors),
            'error_types': dict(error_types),
            'top_errors': error_types.most_common(5),
            'details': dict(error_details),
        }

    def generate_report(self) -> str:
        """生成分析报告"""
        analysis = self.analyze()

        if not analysis:
            return "未发现错误日志"

        report = []
        report.append("=" * 60)
        report.append(f"错误模式分析报告 - {analysis['period']}")
        report.append("=" * 60)
        report.append("")
        report.append(f"总错误数: {analysis['total_errors']}")
        report.append("")
        report.append("高频错误 TOP 5:")
        report.append("")

        for i, (error_type, count) in enumerate(analysis['top_errors'], 1):
            percentage = (count / analysis['total_errors']) * 100
            report.append(f"{i}. {error_type}: {count} 次 ({percentage:.1f}%)")

        report.append("")
        report.append("详细信息:")
        report.append("")

        for error_type, count in analysis['top_errors']:
            report.append(f"## {error_type} ({count} 次)")
            report.append("")

            # 显示最近 3 个示例
            examples = analysis['details'][error_type][:3]
            for example in examples:
                report.append(f"  时间: {example['timestamp']}")
                report.append(f"  工具: {example['tool']}")
                report.append(f"  命令: {example['command']}")
                report.append(f"  错误: {example['error']}")
                report.append("")

        report.append("=" * 60)

        return "\n".join(report)

    def should_create_rule(self, error_type: str, count: int) -> bool:
        """判断是否应该为此错误创建检查规则"""
        # 高频错误（≥3次）且不是已知错误类型
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
    parser.add_argument('--output', default='docs/规范/错误分析报告.md',
                        help='输出报告路径')

    args = parser.parse_args()

    analyzer = ErrorPatternAnalyzer(args.log_dir, args.days)
    analyzer.load_logs()

    report = analyzer.generate_report()

    # 输出到终端
    print(report)

    # 保存到文件
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n报告已保存到: {args.output}")


if __name__ == '__main__':
    main()
