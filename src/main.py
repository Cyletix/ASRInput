import sys
import os
import yaml
from PyQt6.QtWidgets import QApplication

def load_config(config_path):
    if not os.path.exists(config_path):
        print("[Warning] config file not found, using defaults.")
        return {
            "model_name": "large",
            "language": "zh",
            "device": "cuda",
            "buffer_seconds": 1.5,
            "step_seconds": 0.5,
            "remove_trailing_period": True,
            "trailing_punctuation": "",  # 自定义结尾标点（可为空、半角、全角或空格）
            "punctuation_mode": "half",  # 可选 "half"、"full"、"space"、"none"
            "model_cache_path": "models",
            "max_cache_count": 20,
            "cache_clear_interval": 10,
            "recognize_emoji": False,
            "recognize_speaker": False,
            "accept_feedback": False,
            "vad_interval": 256,
            "noise_threshold": 0.01,
            "max_sentence_seconds": 4,
            "chunk": 1024  # 默认 chunk 大小
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# main.py 位于 src 文件夹中，模型文件夹在项目根目录下
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
config_dict = load_config(config_path)

# 设置 TRANSFORMERS_CACHE 为项目根目录下的 models（绝对路径）
models_abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", config_dict.get("model_cache_path", "models")))
os.environ["TRANSFORMERS_CACHE"] = models_abs_path
print("TRANSFORMERS_CACHE set to:", os.environ["TRANSFORMERS_CACHE"])

from window import ModernUIWindow

def main():
    app = QApplication(sys.argv)
    main_window = ModernUIWindow(config_dict)
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
