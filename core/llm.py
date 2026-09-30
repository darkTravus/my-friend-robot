"""Le 'cerveau' : conversation avec mémoire courte."""
from openai import OpenAI


class Brain:
    def __init__(self, client: OpenAI, cfg: dict, model: str):
        self.client, self.model = client, model
        self.system_prompt = cfg["system_prompt"].strip()
        self.max_history = cfg["max_history_messages"]
        self.temperature = cfg["temperature"]
        self.max_tokens = cfg["max_tokens"]
        self.history = []

    def reply(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})
        self.history = self.history[-self.max_history:]
        messages = [{"role": "system", "content": self.system_prompt}] + self.history
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages,
            temperature=self.temperature, max_tokens=self.max_tokens,
        )
        answer = resp.choices[0].message.content.strip()
        self.history.append({"role": "assistant", "content": answer})
        return answer

    def reset(self):
        self.history.clear()
