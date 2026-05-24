# Claude Code 执行任务模板

## 输入信息
- 任务类型：{task_type}
- 执行方案：{plan}
- 具体需求：{requirements}

## 输出格式要求
执行完成后，输出JSON格式结果：

{
  "success": true/false,
  "files_created": ["文件路径列表"],
  "code": "主要代码内容",
  "data": "实验数据摘要",
  "charts": ["图表路径列表"],
  "summary": "执行摘要",
  "error": "错误信息（如有）"
}

## 工作目录
{output_dir}

请开始执行。
