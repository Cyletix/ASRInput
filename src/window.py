# window.py
import os
import json
import time
import re
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QMouseEvent, QGuiApplication, QKeyEvent
import keyboard  # 使用 keyboard 库

# 辅助函数：模拟键入文本到当前活动窗口（不改变当前焦点）
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
        # 工具窗口、无边框、始终置顶且不抢焦点；设透明度
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(0.85)
        self.resize(500, 40)

        # 主部件与一行布局：麦克风按钮、文本框、反馈按钮、上屏按钮
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # 麦克风按钮（左侧）：用于启用/禁用识别，背景色与图标切换
        self.toggle_button = QPushButton("🎤")
        self.toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggle_button.setFixedSize(40, 30)
        self.toggle_button.setStyleSheet("background-color: lightgreen; border-radius: 5px;")
        self.toggle_button.clicked.connect(self.toggle_recognition)
        layout.addWidget(self.toggle_button)

        # 文本框（中间）：显示识别结果，可编辑
        self.recognition_edit = QLineEdit()
        self.recognition_edit.setPlaceholderText("等待识别...")
        self.recognition_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.recognition_edit.setFixedHeight(30)
        layout.addWidget(self.recognition_edit, stretch=1)

        # 反馈按钮（右侧左边）：点击后提交反馈并清空窗口内容
        self.feedback_button = QPushButton("反馈")
        self.feedback_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.feedback_button.setFixedSize(60, 30)
        self.feedback_button.clicked.connect(self.on_feedback_clicked)
        layout.addWidget(self.feedback_button)

        # 上屏按钮（右侧最右）：点击后将当前识别结果发送到目标应用，但保留窗口内容
        self.manual_send_button = QPushButton("上屏")
        self.manual_send_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.manual_send_button.setFixedSize(60, 30)
        self.manual_send_button.clicked.connect(self.on_manual_send)
        layout.addWidget(self.manual_send_button)

        # 保存最新识别结果，用于反馈比较
        self.last_recognized_text = ""
        self.last_audio_id = ""
        self.last_sent_text = ""

        # 后处理配置：标点控制（使用正则删除末尾句号或全角句号）
        self.remove_trailing_period = self.config.get("remove_trailing_period", True)
        self.trailing_punctuation = self.config.get("trailing_punctuation", "")  # 留空表示删除
        self.punctuation_mode = self.config.get("punctuation_mode", "half")  # "half" 或 "full"

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

        # 设置窗口位置为屏幕下方居中
        screen = QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            x = (geometry.width() - self.width()) // 2
            y = geometry.height() - self.height() - 10
            self.move(x, y)

    def process_text(self, text):
        text = text.strip()
        if self.remove_trailing_period and text:
            if self.punctuation_mode == "half":
                text = re.sub(r'[.]+$', '', text)
            elif self.punctuation_mode == "full":
                text = re.sub(r'[。]+$', '', text)
        return text

    def toggle_recognition(self):
        if self.recognition_active:
            self.worker.stop()
            self.worker.wait()
            self.recognition_active = False
            self.toggle_button.setText("🚫")
            self.toggle_button.setStyleSheet("background-color: lightcoral; border-radius: 5px;")
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
            self.toggle_button.setStyleSheet("background-color: lightgreen; border-radius: 5px;")
            print("识别已启动")

    def on_new_recognition(self, recognized_text, audio_id):
        processed = self.process_text(recognized_text)
        # 只发送与上次不同的内容，防止重复上屏
        if processed and processed != self.last_sent_text:
            insert_text_into_active_window(processed)
            self.last_sent_text = processed
        self.last_recognized_text = processed
        self.last_audio_id = audio_id
        self.recognition_edit.setText(processed)

    def on_manual_send(self):
        current_text = self.recognition_edit.text().strip()
        if current_text:
            if current_text != self.last_sent_text:
                insert_text_into_active_window(current_text)
                self.last_sent_text = current_text
        else:
            print("没有文本可上屏。")

    def on_feedback_clicked(self):
        current_text = self.recognition_edit.text().strip()
        if not current_text:
            print("反馈：没有内容。")
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
        self.last_sent_text = ""

    def keyPressEvent(self, event: QKeyEvent):
        # PyQt6 中使用 Qt.Key.Key_Escape
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

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
