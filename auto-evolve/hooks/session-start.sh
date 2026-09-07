#!/bin/bash
# auto-evolve SessionStart hook：运行项目快速检查清单
# 规范：项目未初始化时静默退出，绝不报错打扰
set +e

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

QUICK_CHECK=""
for p in backend/scripts/validation/quick_check.sh scripts/validation/quick_check.sh .claude/quick_check.sh; do
    if [ -f "${PROJECT_ROOT}/$p" ]; then QUICK_CHECK="$p"; break; fi
done

# 项目未初始化检查清单 → 静默退出
[ -z "${QUICK_CHECK}" ] && exit 0

echo ""
echo "========================================="
echo "  auto-evolve 会话启动检查"
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
    echo "发现阻断性问题，建议先修复（或运行 /auto-evolve:init 重新初始化）"
fi
echo "========================================="
echo ""
exit 0
