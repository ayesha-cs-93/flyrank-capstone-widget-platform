from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://widget_user:widget_pass@localhost:5432/widget_platform"

    geo_provider_a_url: str = "http://ip-api.com/json"
    geo_provider_b_url: str = "https://ipapi.co"

    rate_limit_per_minute: int = 10

    allowed_origins: str = "*"

    # manual toggles used to prove fallback / degrade-gracefully behavior in the demo
    disable_geo_provider_a: bool = False
    disable_geo_provider_b: bool = False
    disable_email_side_effect: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
