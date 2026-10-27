"""
Configuration loader for the Server Monitoring Agent.
Reads a YAML config file and returns a typed namespace.
"""

import os
import logging
from pathlib import Path
from typing import Any
import yaml


log = logging.getLogger("agent.config")


class Config:
    """Simple attribute-access wrapper around the YAML config dict."""

    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        value = self._data.get(name)
        if isinstance(value, dict):
            return Config(value)
        if value is None:
            raise AttributeError(f"Config key '{name}' not found")
        return value

    def get(self, name: str, default: Any = None) -> Any:
        value = self._data.get(name, default)
        if isinstance(value, dict):
            return Config(value)
        return value

    def to_dict(self) -> dict:
        return self._data


def load_config(config_path: str = None) -> Config:
    """
    Load the YAML configuration file.

    Search order:
    1. Explicit path passed as argument
    2. config/config.yaml (relative to project root)
    3. config/config.example.yaml (fallback for quick testing)
    """
    # project_root is two levels up from src/modules/config_loader.py
    # -> src/modules -> src -> project_root
    project_root = Path(__file__).resolve().parent.parent.parent

    if config_path:
        path = Path(config_path)
    elif (project_root / "config" / "config.yaml").exists():
        path = project_root / "config" / "config.yaml"
    else:
        path = project_root / "config" / "config.example.yaml"
        log.warning("config.yaml not found, using config.example.yaml as fallback")

    log.info("Loading config from: %s", path)

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return Config(data)


def setup_logging(config: Config) -> None:
    """Configure root logging based on the agent_log section of config."""
    log_cfg = config.get("agent_log", {})
    level_name = log_cfg.get("level", "INFO") if isinstance(log_cfg, Config) else log_cfg.get("level", "INFO")
    log_file = log_cfg.get("file", "output/agent.log") if isinstance(log_cfg, Config) else log_cfg.get("file", "output/agent.log")

    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
