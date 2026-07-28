from openai import OpenAI

from backend.config import settings


class TerraformAIService:

    def __init__(self):

        self.client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

    def generate(self, prompt: str):

        response = self.client.chat.completions.create(
            model=settings.MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )

        return response.choices[0].message.content