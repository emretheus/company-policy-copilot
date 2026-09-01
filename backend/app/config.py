from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://copilot:copilot@localhost:5432/policy_copilot"
    ollama_base_url: str = "http://localhost:11434"
    ollama_generation_model: str = "llama3.1:8b"
    ollama_embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768
    jwt_secret: str = "dev-secret-change-me"

    class Config:
        env_file = ".env"


settings = Settings()
