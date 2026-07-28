import os
from dotenv import load_dotenv

load_dotenv()


class Settings:

    PROJECT_NAME = "AI Terraform Landing Zone Generator"

    VERSION = "1.0.0"

    GENERATED_FOLDER = "generated"

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    MODEL = "llama-3.3-70b-versatile"


settings = Settings()