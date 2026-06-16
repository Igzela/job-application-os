import json
from .base import LLMAdapter
from .prompts import JOB_MATCH_SYSTEM, GREETING_SYSTEM, SCAM_CHECK_SYSTEM, AUTO_REPLY_SYSTEM


def analyze_match(llm: LLMAdapter, job_data: dict, profile: dict) -> dict:
    """分析职位与求职者的匹配度"""
    messages = [{"role": "user", "content": f"""分析以下职位与求职者的匹配度：

职位信息：
{json.dumps(job_data, ensure_ascii=False, indent=2)}

求职者信息：
{json.dumps(profile, ensure_ascii=False, indent=2)}"""}]
    result = llm.chat(messages, system=JOB_MATCH_SYSTEM, temperature=0.3)
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"total_score": 50, "verdict": "未知", "reasoning": result}


def generate_greeting(llm: LLMAdapter, job_data: dict, profile: dict, evidence: str = "") -> str:
    """生成个性化招呼语"""
    messages = [{"role": "user", "content": f"""为以下职位生成BOSS直聘招呼语：

职位：{job_data.get('title', '未知')}
公司：{job_data.get('company', '未知')}
要求：{job_data.get('description', job_data.get('requirements', ''))}

求职者背景：
- 技能：{json.dumps(profile.get('skills', {}), ensure_ascii=False)}
- 经验：{profile.get('experience', '暂无')}

相关经历：
{evidence[:500] if evidence else '暂无'}"""}]
    return llm.chat(messages, system=GREETING_SYSTEM, temperature=0.8)


def check_scam(llm: LLMAdapter, job_description: str, company_info: str = "") -> dict:
    """LLM深度反诈分析"""
    messages = [{"role": "user", "content": f"""分析以下招聘信息是否存在诈骗风险：

职位描述：
{job_description}

公司信息：
{company_info or '未知'}"""}]
    result = llm.chat(messages, system=SCAM_CHECK_SYSTEM, temperature=0.3)
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"is_scam": False, "risk_level": "unknown", "reasoning": result}


def explain_scores(llm: LLMAdapter, scores: dict, job_data: dict, profile: dict) -> str:
    """解释评分结果"""
    system = "你是职业顾问，用中文解释评分结果并给出建议。"
    messages = [{"role": "user", "content": f"""解释以下匹配评分：

评分：{json.dumps(scores, indent=2)}
职位：{job_data.get('title', '未知')} - {job_data.get('company', '未知')}
求职者：{profile.get('name', '未知')}

请：
1. 指出最强匹配点
2. 指出最大短板
3. 给出1-2条可执行的改进建议"""}]
    return llm.chat(messages, system=system, temperature=0.5)


def generate_reply(llm: LLMAdapter, recruiter_message: str, job_context: dict, profile: dict, conversation_history: str = "") -> str:
    """Generate a reply to a recruiter's message on BOSS Zhipin."""
    messages = [{"role": "user", "content": f"""回复招聘者的消息：

招聘者最新消息：
{recruiter_message}

对话历史：
{conversation_history or '首次对话'}

职位/公司信息：
{json.dumps(job_context, ensure_ascii=False)}

我的背景：
{json.dumps(profile, ensure_ascii=False, indent=2)}

请生成一条简洁专业的回复。"""}]
    return llm.chat(messages, system=AUTO_REPLY_SYSTEM, temperature=0.7)
