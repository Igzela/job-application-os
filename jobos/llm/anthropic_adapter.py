import json
import httpx


class AnthropicAdapter:
    """Anthropic Claude API适配器"""

    def __init__(self, api_key: str, base_url: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.Client(timeout=120.0)

    @classmethod
    def create(cls, api_key: str, base_url: str, model: str | None = None) -> "AnthropicAdapter":
        if not api_key:
            raise ValueError("API key is required")
        if not base_url:
            raise ValueError("Base URL is required")
        return cls(api_key=api_key, base_url=base_url, model=model or "claude-sonnet-4-20250514")

    def chat(self, messages: list[dict], system: str = "", temperature: float = 0.7) -> str:
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            payload["system"] = system

        for attempt in range(3):
            try:
                resp = self.client.post(url, headers=headers, json=payload)
                if resp.status_code == 429:
                    import time
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data["content"][0]["text"]
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (500, 503) and attempt < 2:
                    import time
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise RuntimeError("Max retries exceeded")

    def summarize_jd(self, jd_text: str) -> dict:
        system = "你是职位分析专家。分析JD并返回JSON格式的关键信息。"
        messages = [{"role": "user", "content": f"""分析以下职位描述，返回JSON：
{{
  "title": "职位名称",
  "company": "公司名称",
  "skills": ["技能1", "技能2"],
  "experience": "经验要求",
  "education": "学历要求",
  "salary": "薪资范围",
  "location": "工作地点",
  "key_responsibilities": ["职责1", "职责2"],
  "nice_to_haves": ["加分项1"]
}}

职位描述：
{jd_text}"""}]
        result = self.chat(messages, system=system, temperature=0.3)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"summary": jd_text[:200], "skills": [], "experience": "unknown"}

    def improve_greeting(self, greeting: str, context: dict) -> str:
        system = "你是招聘沟通专家。优化招呼语使其更专业、更有吸引力。"
        messages = [{"role": "user", "content": f"""优化以下招呼语：

原始招呼语：
{greeting}

职位信息：
{json.dumps(context, ensure_ascii=False, indent=2)}

要求：
1. 保持简洁（100字以内）
2. 突出匹配度
3. 语气专业但不过于正式
4. 包含具体的技术关键词"""}]
        return self.chat(messages, system=system, temperature=0.7)

    def improve_cover_letter(self, cover_letter: str, context: dict) -> str:
        system = "你是求职文书专家。优化求职信使其更有说服力。"
        messages = [{"role": "user", "content": f"""优化以下求职信：

{cover_letter}

职位信息：
{json.dumps(context, ensure_ascii=False, indent=2)}

要求：
1. 突出与职位的匹配点
2. 用具体数据和案例支撑
3. 语气真诚自信
4. 控制在300字以内"""}]
        return self.chat(messages, system=system, temperature=0.7)

    def rewrite_resume_bullet(self, bullet: str, context: dict) -> str:
        system = "你是简历优化专家。用STAR法则重写简历要点。"
        messages = [{"role": "user", "content": f"""重写以下简历要点：

{bullet}

职位关键词：{', '.join(context.get('keywords', []))}

要求：
1. 用STAR法则（情境-任务-行动-结果）
2. 量化成果
3. 匹配职位关键词"""}]
        return self.chat(messages, system=system, temperature=0.5)

    def explain_score(self, scores: dict, job_data: dict) -> str:
        system = "你是职业顾问。解释评分结果并给出建议。"
        messages = [{"role": "user", "content": f"""解释以下评分结果：

评分：{json.dumps(scores, indent=2)}
职位：{json.dumps(job_data, ensure_ascii=False, indent=2)}

请：
1. 解释每个维度的含义
2. 指出优势和劣势
3. 给出具体改进建议"""}]
        return self.chat(messages, system=system, temperature=0.5)
