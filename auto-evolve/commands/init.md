---
description: 为当前项目初始化 auto-evolve 检查体系（模板选择式生成，强规范防发散）。首次在项目中使用本插件时运行。
---

按以下步骤为当前项目初始化 auto-evolve 检查体系：

1. 运行 dry-run 查看生成计划（必须先展示给用户，经同意后再写文件）：
   `python "${CLAUDE_PLUGIN_ROOT}/scripts/init_project_validation.py" --root "$(pwd)"`

2. 向用户展示 [检测报告] 和 [生成计划]，说明将写入的文件清单和强规范声明

3. 用户同意后执行：
   `python "${CLAUDE_PLUGIN_ROOT}/scripts/init_project_validation.py" --root "$(pwd)" --apply`

4. 验证 bash -n 语法校验全部通过，报告生成结果

强规范（必须遵守）：
- 检查项只能来自脚本内置的 CHECK_TEMPLATES 注册表，禁止即兴发明项目专属检查逻辑
- 项目专属检查只写在生成的占位段，需用户明确要求后按统一格式手工添加
- 禁止修改生成的 hook 脚本逻辑
