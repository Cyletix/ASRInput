# config.py
import yaml
import os

DEFAULT_CONFIG = {
    "model_name": "large",
    "language": "zh",
    "device": "cuda",  # 或 "cpu" / None
    "buffer_seconds": 4,
    "step_seconds": 2
}

def load_config(config_path=None):
    if config_path is None:
        return DEFAULT_CONFIG

    if not os.path.exists(config_path):
        print(f"[Warning] config file not found: {config_path}, using defaults.")
        return DEFAULT_CONFIG

    with open(config_path, "r", encoding="utf-8") as f:
        file_config = yaml.safe_load(f)

    merged = dict(DEFAULT_CONFIG)
    merged.update(file_config or {})
    return merged
