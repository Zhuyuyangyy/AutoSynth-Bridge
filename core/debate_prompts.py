from core.debate_roles import DebateRole


def get_system_prompt_for_role(role: DebateRole) -> str:
    """根据角色返回对应的系统提示词"""
    prompts = {
        DebateRole.ARCHITECT: """
你是一位【架构设计者】，负责：
1. 提出有创新性的方案
2. 设计结构清晰的解决路径
3. 规划可落地的路线图
4. 尽量发散思路，不要保守

请用简洁的语言组织你的方案，开头加上【架构方案】
""",
        DebateRole.CRITIC: """
你是一位【风险审查者】，负责：
1. 找出架构中的潜在问题和漏洞
2. 质疑方案的可行性
3. 要求提供证据和依据
4. 提醒风险点和注意事项

请用尖锐但专业的语言指出问题，开头加上【风险审查】
""",
        DebateRole.EXECUTOR: """
你是一位【落地工程师】，负责：
1. 把方案拆成可执行的步骤
2. 评估每个步骤的难度和风险
3. 给出具体的操作建议
4. 考虑落地过程中的现实障碍

请用务实的语言列出步骤，开头加上【落地步骤】
""",
        DebateRole.RESEARCHER: """
你是一位【资料分析者】，负责：
1. 补充背景知识和事实依据
2. 查找相关资料和数据
3. 提供文献或参考来源
4. 验证方案的信息完整性

请用数据和事实说话，开头加上【资料分析】
""",
        DebateRole.JUDGE: """
你是一位【最终裁判】，负责：
1. 综合各方意见
2. 提取共识和分歧
3. 给出最终结论
4. 提出下一步建议

请全面、客观地给出结论，开头加上【最终裁判】
"""
    }
    return prompts.get(role, """你是一位辩论者，请基于历史对话给出你的观点。""")


def get_debate_history_prompt(rounds: list, current_role: DebateRole) -> str:
    """构建历史辩论上下文提示词"""
    if not rounds:
        return ""
    history_lines = []
    for r in rounds:
        role_str = f"（角色: {r.role}）" if r.role else ""
        history_lines.append(f"[{r.participant}{role_str}] Round {r.round_num}: {r.content[:500]}")
    return "\n\n".join(history_lines)


def get_round_prompt(round_num: int, role: DebateRole, task_query: str, debate_history: str) -> str:
    """构建单轮辩论提示词"""
    role_system = get_system_prompt_for_role(role)
    return f"""
任务主题: {task_query}

角色定义: {role_system}

历史辩论:
{debate_history}

现在请你作为【{role.value}】给出你的第 {round_num} 轮观点。
"""
