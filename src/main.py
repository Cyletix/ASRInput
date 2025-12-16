import sys
import os
import yaml
from PyQt6.QtWidgets import QApplication
import logging

logging.getLogger().setLevel(logging.ERROR)

def load_config(config_path):
    if not os.path.exists(config_path):
        print(f"❌ 找不到配置文件: {config_path}")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# 读取配置
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
config_dict = load_config(config_path)

# === [重点] 把那段设置 os.environ 的代码全删了，这里什么都不要设 ===
# 只要确保 config_dict 被传给窗口就行了
# ==========================================================

from window import ModernUIWindow

def main():
    app = QApplication(sys.argv)
    main_window = ModernUIWindow(config_dict)
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    import sys
    print(f"当前 Python 版本：{sys.version}")
    import torch
    print(f"PyTorch 版本：{torch.__version__}")
    print(torch.cuda.is_available())

    print(f"当前工作目录：{os.getcwd()}")
    
    main()

    