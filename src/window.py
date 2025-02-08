# window.py
import os
import json
import time
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QMouseEvent, QGuiApplication
import keyboard  # 使用 keyboard 库

# 辅助函数：将文本插入当前活动窗口
def insert_text_into_active_window(text):
    try:
        import pyautogui
        pyautogui.write(text)
    except ImportError:
        # 若未安装 pyautogui，则将文本复制到剪贴板，并提示用户手动粘贴
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        print("pyautogui 未安装，文本已复制到剪贴板，请手动粘贴。")

class ModernUIWindow(QMainWindow):
    def __init__(self, config_dict):
        super().__init__()
        self.config = config_dict
        self.setWindowTitle("语音识别悬浮窗口")
        # 设置为工具窗口、无边框、始终置顶且不抢焦点
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # 窗口尺寸紧凑：宽 300，高 50
        self.resize(300, 50)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)

        # 第一行：语音检测开关和关闭按钮（右对齐）
        top_layout = QHBoxLayout()
        top_layout.addStretch()
        self.toggle_button = QPushButton("语音:开")
        self.toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggle_button.setFixedSize(40, 20)
        self.toggle_button.clicked.connect(self.toggle_recognition)
        top_layout.addWidget(self.toggle_button)

        self.close_button = QPushButton("X")
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setFixedSize(20, 20)
        self.close_button.clicked.connect(self.close)
        top_layout.addWidget(self.close_button)
        main_layout.addLayout(top_layout)

        # 第二行：文本框和反馈按钮（文本框占满剩余宽度）
        bottom_layout = QHBoxLayout()
        self.recognition_edit = QLineEdit()
        self.recognition_edit.setPlaceholderText("等待识别...")
        self.recognition_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.recognition_edit.setFixedHeight(20)
        bottom_layout.addWidget(self.recognition_edit, stretch=1)

        self.feedback_button = QPushButton("反馈")
        self.feedback_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.feedback_button.setFixedSize(40, 20)
        self.feedback_button.clicked.connect(self.on_feedback_clicked)
        bottom_layout.addWidget(self.feedback_button)
        main_layout.addLayout(bottom_layout)

        # 记录上一次识别的文本、音频ID及上次识别时间（用于判断间隔是否超过配置的 step_seconds）
        self.last_recognized_text = ""
        self.last_audio_id = ""
        self.last_recognition_time = 0
        self.step_seconds = self.config.get("step_seconds", 2)

        from worker_thread import ASRWorkerThread
        self.worker = ASRWorkerThread(
            sample_rate=16000,
            chunk=2048,
            buffer_seconds=self.config.get("buffer_seconds", 8),
            device=self.config.get("device", "cpu")
        )
        self.worker.result_ready.connect(self.on_new_recognition)
        self.worker.start()
        self.recognition_active = True

        # 全局热键（Ctrl+Shift+S）用于切换识别状态
        keyboard.add_hotkey('ctrl+shift+s', self.toggle_recognition)

        # 用于无边框窗口拖动
        self._startPos = None

    def toggle_recognition(self):
        if self.recognition_active:
            self.worker.stop()
            self.recognition_active = False
            self.toggle_button.setText("语音:关")
            print("识别已停止")
        else:
            from worker_thread import ASRWorkerThread
            self.worker = ASRWorkerThread(
                sample_rate=16000,
                chunk=2048,
                buffer_seconds=self.config.get("buffer_seconds", 8),
                device=self.config.get("device", "cpu")
            )
            self.worker.result_ready.connect(self.on_new_recognition)
            self.worker.start()
            self.recognition_active = True
            self.toggle_button.setText("语音:开")
            print("识别已启动")

    def on_new_recognition(self, recognized_text, audio_id):
        now = time.time()
        # 如果与上次识别间隔超过 step_seconds，则将上一次识别内容上屏
        if self.last_recognition_time and (now - self.last_recognition_time >= self.step_seconds) and self.last_recognized_text:
            insert_text_into_active_window(self.last_recognized_text)
        self.last_recognition_time = now
        self.last_recognized_text = recognized_text
        self.last_audio_id = audio_id
        self.recognition_edit.setText(recognized_text)

    def on_feedback_clicked(self):
        current_text = self.recognition_edit.text().strip()
        if not current_text or current_text == self.last_recognized_text:
            print("反馈：文本无修改，不反馈。")
            return
        audio_filename = self.worker.save_feedback_audio(self.last_audio_id)
        feedback = {
            "audio_filename": audio_filename,
            "original": self.last_recognized_text,
            "modified": current_text
        }
        with open("feedback_log.json", "a", encoding="utf-8") as f:
            json.dump(feedback, f, ensure_ascii=False)
            f.write("\n")
        print("反馈已保存：", feedback)
        self.recognition_edit.clear()
        self.last_recognized_text = ""

    # 重写鼠标事件，实现无边框窗口拖动
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._startPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._startPos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._startPos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._startPos = None
        event.accept()

    def closeEvent(self, event):
        if self.recognition_active:
            self.worker.stop()
            self.worker.wait()  # 确保线程完全停止
        super().closeEvent(event)
