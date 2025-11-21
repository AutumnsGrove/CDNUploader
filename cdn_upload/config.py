"""Configuration and secrets management for CDN Upload CLI.

Handles loading secrets.json, validating configuration, and managing
R2 credentials and AI API keys.
"""

import json
import os
from pathlib import Path
from typing import Any

from .models import R2Config, AIConfig


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


def load_secrets(secrets_path: Path | None = None) -> dict[str, Any]:
    """Load and validate secrets.json.

    Args:
        secrets_path: Optional path to secrets.json. Defaults to ./secrets.json

    Returns:
        Dictionary containing all secrets

    Raises:
        ConfigError: If secrets.json is missing or invalid
    """
    if secrets_path is None:
        secrets_path = Path("secrets.json")

    if not secrets_path.exists():
        raise ConfigError(
            f"secrets.json not found at {secrets_path}. "
            "Copy from secrets.json.template and fill in your credentials."
        )

    try:
        with open(secrets_path) as f:
            secrets = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in secrets.json: {e}")

    return secrets


def validate_config(secrets: dict[str, Any]) -> None:
    """Validate that all required configuration fields are present.

    Args:
        secrets: Dictionary loaded from secrets.json

    Raises:
        ConfigError: If required fields are missing
    """
    required_fields = [
        ("r2", "account_id"),
        ("r2", "access_key_id"),
        ("r2", "secret_access_key"),
        ("r2", "bucket_name"),
        ("r2", "custom_domain"),
    ]

    for section, field in required_fields:
        if section not in secrets:
            raise ConfigError(f"Missing required section: {section}")
        if field not in secrets[section] or not secrets[section][field]:
            raise ConfigError(f"Missing required field: {section}.{field}")


def get_r2_config(secrets: dict[str, Any]) -> R2Config:
    """Extract R2 configuration from secrets.

    Args:
        secrets: Dictionary loaded from secrets.json

    Returns:
        R2Config dataclass with credentials
    """
    r2 = secrets["r2"]
    return R2Config(
        account_id=r2["account_id"],
        access_key_id=r2["access_key_id"],
        secret_access_key=r2["secret_access_key"],
        bucket_name=r2["bucket_name"],
        custom_domain=r2["custom_domain"],
    )


def get_ai_config(secrets: dict[str, Any]) -> AIConfig:
    """Extract AI provider configuration from secrets.

    Args:
        secrets: Dictionary loaded from secrets.json

    Returns:
        AIConfig dataclass with API keys
    """
    ai = secrets.get("ai", {})
    return AIConfig(
        anthropic_api_key=ai.get("anthropic_api_key"),
        openrouter_api_key=ai.get("openrouter_api_key"),
    )


def get_cache_dir() -> Path:
    """Get or create the cache directory for analysis results.

    Returns:
        Path to cache directory (~/.cache/cdn-cli/)
    """
    cache_dir = Path.home() / ".cache" / "cdn-cli"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir
