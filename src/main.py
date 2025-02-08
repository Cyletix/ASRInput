# main.py
import sys
import os
from PyQt6.QtWidgets import QApplication
from config import load_config
from window import ModernUIWindow

def main():
    app = QApplication(sys.argv)
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    config_dict = load_config(config_path)
    main_window = ModernUIWindow(config_dict)
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
