#!/bin/bash
# auto-evolve SessionEnd hook：分析今日错误日志，自动生成检查规则
# 规范：无日志/无生成器时静默退出；生成规则后不自动 git commit（由用户决定）
set +e

PROJECT_DIR="${CLAUDE_PROJECT_DIR}"
[ -z "${PROJECT_DIR}" ] && exit 0

LOG_DIR="${PROJECT_DIR}/.claude/error-logs"
LOG_FILE="${LOG_DIR}/errors-$(date +%Y-%m-%d).jsonl"

[ -f "${LOG_FILE}" ] || exit 0
ERROR_COUNT=$(grep -c . "${LOG_FILE}" 2>/dev/null || echo 0)
[ "${ERROR_COUNT}" -ge 1 ] || exit 0

# 定位生成器：项目内 → 插件内（CLAUDE_PLUGIN_ROOT）
GENERATOR=""
[ -f "${PROJECT_DIR}/backend/scripts/validation/simple_rule_generator.py" ] && \
    GENERATOR="${PROJECT_DIR}/backend/scripts/validation/simple_rule_generator.py"
if [ -z "${GENERATOR}" ] && [ -n "${CLAUDE_PLUGIN_ROOT}" ] && [ -f "${CLAUDE_PLUGIN_ROOT}/scripts/simple_rule_generator.py" ]; then
    GENERATOR="${CLAUDE_PLUGIN_ROOT}/scripts/simple_rule_generator.py"
fi
[ -z "${GENERATOR}" ] && [ -f "${HOME}/.claude/validation-toolkit/simple_rule_generator.py" ] && \
    GENERATOR="${HOME}/.claude/validation-toolkit/simple_rule_generator.py"
[ -z "${GENERATOR}" ] && { echo "[auto-evolve] 未找到规则生成器，跳过（日志已保留）"; exit 0; }

# 定位宿主 quick_check.sh（可能不存在，生成器会优雅跳过）
QUICK_CHECK=""
for p in backend/scripts/validation/quick_check.sh scripts/validation/quick_check.sh .claude/quick_check.sh; do
    [ -f "${PROJECT_DIR}/$p" ] && { QUICK_CHECK="$p"; break; }
done

echo ""
echo "========================================="
echo "  [auto-evolve] 会话结束 - 检测到 ${ERROR_COUNT} 个错误，分析中..."
echo "========================================="

cd "${PROJECT_DIR}"
ARGS=(--log-dir "${LOG_DIR}" --days 1 --threshold 1)
[ -n "${QUICK_CHECK}" ] && ARGS+=(--quick-check "${QUICK_CHECK}")
python "${GENERATOR}" "${ARGS[@]}" 2>&1

echo "========================================="
echo ""
exit 0
