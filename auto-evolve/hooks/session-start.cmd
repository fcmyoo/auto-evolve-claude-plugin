: << 'CMDBLOCK'
@echo off
set "SCRIPT_DIR=%~dp0"
"C:\Program Files\Git\bin\bash.exe" -l -c "cd \"$(cygpath -u \"%CLAUDE_PROJECT_DIR%\")\" && CLAUDE_PLUGIN_ROOT=\"$(cygpath -u \"%SCRIPT_DIR%..\")\" bash \"$(cygpath -u \"%SCRIPT_DIR%\")session-start.sh\""
exit /b
CMDBLOCK

# Unix shell runs from here
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
"${SCRIPT_DIR}/session-start.sh"
