# window.py
import os
import json
import time
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QMouseEvent, QGuiApplication
import keyboard  # 使用 keyboard 库

# 辅助函数：将文本插入当前活动窗口
# 本函数仅模拟键入，不改变当前应用焦点
def insert_text_into_active_window(text):
    try:
        keyboard.write(text)
    except Exception as e:
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        print("keyboard.write 失败，文本已复制到剪贴板，请手动粘贴。", e)

class ModernUIWindow(QMainWindow):
    def __init__(self, config_dict):
        super().__init__()
        self.config = config_dict
        self.setWindowTitle("语音识别悬浮窗口")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(300, 50)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)

        # 第一行：左侧为语音检测按钮，右侧为关闭按钮
        top_layout = QHBoxLayout()
        self.toggle_button = QPushButton("🎤")
        self.toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggle_button.setFixedSize(40, 20)
        self.toggle_button.setStyleSheet("background-color: lightgreen;")
        self.toggle_button.clicked.connect(self.toggle_recognition)
        top_layout.addWidget(self.toggle_button)
        top_layout.addStretch()
        self.close_button = QPushButton("X")
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setFixedSize(20, 20)
        self.close_button.clicked.connect(self.close)
        top_layout.addWidget(self.close_button)
        main_layout.addLayout(top_layout)

        # 第二行：文本框、反馈按钮、手动上屏按钮（反馈在左，上屏在右）
        bottom_layout = QHBoxLayout()
        self.recognition_edit = QLineEdit()
        self.recognition_edit.setPlaceholderText("等待识别...")
        self.recognition_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.recognition_edit.setFixedHeight(20)
        bottom_layout.addWidget(self.recognition_edit, stretch=1)
        self.feedback_button = QPushButton("反馈")
        self.feedback_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.feedback_button.setFixedSize(40, 20)
        self.feedback_button.clicked.connect(self.on_feedback_clicked)
        bottom_layout.addWidget(self.feedback_button)
        self.manual_send_button = QPushButton("上屏")
        self.manual_send_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.manual_send_button.setFixedSize(40, 20)
        self.manual_send_button.clicked.connect(self.on_manual_send)
        bottom_layout.addWidget(self.manual_send_button)
        main_layout.addLayout(bottom_layout)

        # 自动上屏定时器：5秒内无新语音则自动上屏
        self.auto_send_timer = QTimer(self)
        self.auto_send_timer.setInterval(5000)
        self.auto_send_timer.setSingleShot(True)
        self.auto_send_timer.timeout.connect(self.on_auto_send)

        self.last_recognized_text = ""
        self.last_audio_id = ""
        self.last_recognition_time = 0
        self.step_seconds = self.config.get("step_seconds", 2)

        from worker_thread import ASRWorkerThread
        self.worker = ASRWorkerThread(
            sample_rate=16000,
            chunk=2048,
            buffer_seconds=self.config.get("buffer_seconds", 8),
            device=self.config.get("device", "cpu"),
            config=self.config
        )
        self.worker.result_ready.connect(self.on_new_recognition)
        self.worker.start()
        self.recognition_active = True

        keyboard.add_hotkey('ctrl+shift+s', self.toggle_recognition)

        self._startPos = None

    def toggle_recognition(self):
        if self.recognition_active:
            self.worker.stop()
            self.worker.wait()
            self.recognition_active = False
            self.toggle_button.setText("🚫")
            self.toggle_button.setStyleSheet("background-color: lightcoral;")
            print("识别已停止")
        else:
            from worker_thread import ASRWorkerThread
            self.worker = ASRWorkerThread(
                sample_rate=16000,
                chunk=2048,
                buffer_seconds=self.config.get("buffer_seconds", 8),
                device=self.config.get("device", "cpu"),
                config=self.config
            )
            self.worker.result_ready.connect(self.on_new_recognition)
            self.worker.start()
            self.recognition_active = True
            self.toggle_button.setText("🎤")
            self.toggle_button.setStyleSheet("background-color: lightgreen;")
            print("识别已启动")

    def on_new_recognition(self, recognized_text, audio_id):
        now = time.time()
        self.auto_send_timer.start()
        if self.last_recognition_time and (now - self.last_recognition_time >= self.step_seconds) and self.last_recognized_text:
            insert_text_into_active_window(self.last_recognized_text)
            self.recognition_edit.clear()
            self.last_recognized_text = ""
        self.last_recognition_time = now
        self.last_recognized_text = recognized_text
        self.last_audio_id = audio_id
        self.recognition_edit.setText(recognized_text)

    def on_manual_send(self):
        current_text = self.recognition_edit.text().strip()
        if current_text:
            if self.auto_send_timer.isActive():
                self.auto_send_timer.stop()
            # 为避免重复上屏，清空内部记录
            self.last_recognized_text = ""
            # 隐藏窗口使目标应用获得焦点，再发送文本后恢复显示
            self.hide()
            QTimer.singleShot(300, lambda: self._send_text_and_clear(current_text))
        else:
            print("没有文本可上屏。")

    def _send_text_and_clear(self, text):
        insert_text_into_active_window(text)
        self.recognition_edit.clear()
        self.last_recognized_text = ""
        self.show()

    def on_auto_send(self):
        if not self.recognition_edit.hasFocus() and self.last_recognized_text:
            insert_text_into_active_window(self.last_recognized_text)
            self.recognition_edit.clear()
            self.last_recognized_text = ""

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
        with open("feedback.json", "a", encoding="utf-8") as f:
            json.dump(feedback, f, ensure_ascii=False)
            f.write("\n")
        print("反馈已保存：", feedback)
        self.recognition_edit.clear()
        self.last_recognized_text = ""

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
            self.worker.wait()
        QApplication.quit()
        super().closeEvent(event)
