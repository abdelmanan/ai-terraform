from openai import (
    OpenAI,
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    AuthenticationError,
    APIStatusError,
)

from backend.config import settings
from backend.exceptions.api_exception import ApiException

class TerraformAIService:

    def __init__(self):

        self.client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

    def generate(self, prompt: str):
        try:
            response = self.client.chat.completions.create(
                model=settings.MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,
                max_tokens=6000,
                extra_body={"reasoning_effort": "low"}
            )

        except APITimeoutError:
            raise ApiException(
                message="The AI service (Groq) did not respond in time. Please try again.",
                status_code=504
            )

        except RateLimitError:
            raise ApiException(
                message="The AI service (Groq) rate limit was reached. Please try again later.",
                status_code=429
            )

        except AuthenticationError:
            raise ApiException(
                message="Unable to authenticate with the AI service (Groq). Check the API key configuration.",
                status_code=500
            )

        except APIConnectionError:
            raise ApiException(
                message="Unable to reach the AI service (Groq). Please check your connection and try again.",
                status_code=502
            )

        except APIStatusError as e:
            raise ApiException(
                message=f"The AI service (Groq) returned an error: {e.message}",
                status_code=502
            )

        except Exception:
            raise ApiException(
                message="Unexpected error while generating the Terraform project using AI.",
                status_code=500
            )

        if not response.choices:
            raise ApiException(
                message="The AI service (Groq) returned no completion choices.",
                status_code=502
            )

        choice = response.choices[0]

        if choice.finish_reason == "length":
            raise ApiException(
                message=(
                    "The AI service (Groq) response was truncated because it hit "
                    "the token limit. Try a smaller project or simplify the request."
                ),
                status_code=502
            )

        content = choice.message.content

        if not content or not content.strip():
            raise ApiException(
                message="The AI service (Groq) returned an empty response.",
                status_code=502
            )

        return content