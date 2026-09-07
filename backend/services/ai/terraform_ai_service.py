import logging
import time

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

logger = logging.getLogger(__name__)


class TerraformAIService:

    def __init__(self):

        self.client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            timeout=settings.AI_TIMEOUT_SECONDS,
            max_retries=settings.AI_MAX_RETRIES
        )

    def generate(self, prompt: str):

        started_at = time.monotonic()

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
                max_tokens=settings.AI_MAX_TOKENS,
                extra_body={"reasoning_effort": "low"}
            )

        except APITimeoutError:
            logger.warning("Groq timed out after %.1fs", time.monotonic() - started_at)
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
            logger.exception("Unexpected error while calling Groq")
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

        # A truncated answer is not an error for the SDK: it arrives as a normal
        # completion. Left undetected, it produced half a main.tf that looked
        # perfectly well-formed.
        if getattr(choice, "finish_reason", None) == "length":
            logger.warning(
                "Groq hit the %d token ceiling: the answer is truncated",
                settings.AI_MAX_TOKENS
            )

        content = choice.message.content

        if not content or not content.strip():
            raise ApiException(
                message="The AI service (Groq) returned an empty response.",
                status_code=502
            )

        logger.info(
            "Groq responded in %.1fs (model=%s, %d chars)",
            time.monotonic() - started_at, settings.MODEL, len(content)
        )

        return content