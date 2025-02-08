import sys
import os
import yaml
from PyQt6.QtWidgets import QApplication
from window import ModernUIWindow

def load_config(config_path):
    if not os.path.exists(config_path):
        print("[Warning] config file not found, using defaults.")
        # 此处可以直接返回默认值字典
        return {
            "model_name": "large",
            "language": "zh",
            "device": "cuda",
            "buffer_seconds": 8,
            "step_seconds": 2,
            "remove_trailing_period": True,
            "trailing_punctuation": "",
            "punctuation_mode": "half",
            "model_cache_path": "models",
            "max_cache_count": 20,
            "cache_clear_interval": 10
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    app = QApplication(sys.argv)
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    config_dict = load_config(config_path)
    main_window = ModernUIWindow(config_dict)
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
