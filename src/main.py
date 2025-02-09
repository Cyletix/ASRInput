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
            "buffer_seconds": 5,
            "step_seconds": 2,
            "remove_trailing_period": True,
            "trailing_punctuation": "",
            "punctuation_mode": "half",
            "model_cache_path": "models",
            "max_cache_count": 20,
            "cache_clear_interval": 10,
            "enable_emoji": False,
            "enable_speaker": False,
            "enable_feedback": False,
            "vad_interval": 256,
            "noise_threshold": 0.01,
            "max_sentence_seconds": 4
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
