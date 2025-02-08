# window.py
import os
import json
import time
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QMouseEvent, QGuiApplication
import keyboard  # 使用 keyboard 库

# 辅助函数：将文本插入当前活动窗口
def insert_text_into_active_window(text):
    try:
        # 尝试使用 keyboard 库模拟键入（需要管理员权限）
        keyboard.write(text)
    except Exception as e:
        # 若失败则复制到剪贴板，并提示用户手动粘贴
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        print("使用 keyboard.write 失败，文本已复制到剪贴板，请手动粘贴。", e)

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

        # 第一行：左侧为语音检测按钮，右侧为关闭按钮
        top_layout = QHBoxLayout()
        self.toggle_button = QPushButton("🎤")
        self.toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggle_button.setFixedSize(40, 20)
        # 初始状态：启用，背景绿色
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

        # 第二行：文本框、手动上屏按钮和反馈按钮
        bottom_layout = QHBoxLayout()
        self.recognition_edit = QLineEdit()
        self.recognition_edit.setPlaceholderText("等待识别...")
        # 允许编辑以检测激活状态
        self.recognition_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.recognition_edit.setFixedHeight(20)
        bottom_layout.addWidget(self.recognition_edit, stretch=1)
        # 手动上屏按钮
        self.manual_send_button = QPushButton("上屏")
        self.manual_send_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.manual_send_button.setFixedSize(40, 20)
        self.manual_send_button.clicked.connect(self.on_manual_send)
        bottom_layout.addWidget(self.manual_send_button)
        # 反馈按钮
        self.feedback_button = QPushButton("反馈")
        self.feedback_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.feedback_button.setFixedSize(40, 20)
        self.feedback_button.clicked.connect(self.on_feedback_clicked)
        bottom_layout.addWidget(self.feedback_button)
        main_layout.addLayout(bottom_layout)

        # 自动上屏定时器：5秒内无新语音则自动上屏
        self.auto_send_timer = QTimer(self)
        self.auto_send_timer.setInterval(5000)
        self.auto_send_timer.setSingleShot(True)
        self.auto_send_timer.timeout.connect(self.on_auto_send)

        # 记录上一次识别的文本、音频ID及上次识别时间
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

        # 全局热键（Ctrl+Shift+S）用于切换识别状态
        keyboard.add_hotkey('ctrl+shift+s', self.toggle_recognition)

        # 用于无边框窗口拖动
        self._startPos = None

    def toggle_recognition(self):
        if self.recognition_active:
            self.worker.stop()
            self.worker.wait()  # 等待线程结束
            self.recognition_active = False
            # 禁用状态：图标更改为禁用图标，背景红色
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
        # 每次有新识别结果时重启自动上屏定时器
        self.auto_send_timer.start()
        # 如果与上次识别间隔超过 step_seconds，则上屏上一次识别内容
        if self.last_recognition_time and (now - self.last_recognition_time >= self.step_seconds) and self.last_recognized_text:
            insert_text_into_active_window(self.last_recognized_text)
        self.last_recognition_time = now
        self.last_recognized_text = recognized_text
        self.last_audio_id = audio_id
        self.recognition_edit.setText(recognized_text)

    def on_manual_send(self):
        # 手动上屏：点击按钮时将当前文本发送到活动窗口
        current_text = self.recognition_edit.text().strip()
        if current_text:
            insert_text_into_active_window(current_text)
        else:
            print("没有文本可上屏。")

    def on_auto_send(self):
        # 自动上屏：如果5秒内未检测到新语音且文本框未激活，则上屏最后识别内容
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
            self.worker.wait()  # 确保线程完全结束
        QApplication.quit()
        super().closeEvent(event)
