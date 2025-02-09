import os
import json
import time
import re
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QLineEdit, QPushButton, QApplication, QSystemTrayIcon, QMenu, QSizePolicy
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QMouseEvent, QGuiApplication, QKeyEvent, QIcon, QAction
import keyboard  # 使用 keyboard 库

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
        # 使用无边框工具窗口，始终置顶且不抢焦点
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(0.85)
        # 调整整体UI尺寸稍大一些（例如450x40），用于鼠标拖动空间
        self.resize(450, 40)

        # 设置纯黑背景和马卡龙风格边框（2px淡粉色边框）
        self.setObjectName("MainWindow")
        self.setStyleSheet("""
        #MainWindow {
            background-color: #000000;
            border: 2px solid #FFB6C1;
            border-radius: 8px;
        }
        """)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # 麦克风按钮
        self.toggle_button = QPushButton("🎤")
        self.toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggle_button.setFixedSize(30, 25)
        self.toggle_button.setStyleSheet("background-color: lightgreen; border-radius: 5px;")
        self.toggle_button.clicked.connect(self.toggle_recognition)
        layout.addWidget(self.toggle_button)

        # 文本框显示识别内容
        self.recognition_edit = QLineEdit()
        self.recognition_edit.setPlaceholderText("等待识别...")
        self.recognition_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.recognition_edit.setFixedHeight(25)
        self.recognition_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.recognition_edit, stretch=1)

        # 反馈按钮
        self.feedback_button = QPushButton("反馈")
        self.feedback_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.feedback_button.setFixedSize(50, 25)
        self.feedback_button.clicked.connect(self.on_feedback_clicked)
        layout.addWidget(self.feedback_button)

        # 如果配置中取消了接受反馈，则隐藏反馈按钮
        if not self.config.get("enable_feedback", True):
            self.feedback_button.hide()

        # 上屏按钮
        self.manual_send_button = QPushButton("上屏")
        self.manual_send_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.manual_send_button.setFixedSize(50, 25)
        self.manual_send_button.clicked.connect(self.on_manual_send)
        layout.addWidget(self.manual_send_button)

        self.last_recognized_text = ""
        self.last_audio_id = ""
        self.last_sent_text = ""

        self.remove_trailing_period = self.config.get("remove_trailing_period", True)
        self.trailing_punctuation = self.config.get("trailing_punctuation", "")
        self.punctuation_mode = self.config.get("punctuation_mode", "half")

        # 用于自动上屏的定时器（延迟3秒）
        self.auto_send_timer = QTimer(self)
        self.auto_send_timer.setSingleShot(True)
        self.auto_send_timer.timeout.connect(self.auto_send)

        from worker_thread import ASRWorkerThread
        self.worker = ASRWorkerThread(
            sample_rate=16000,
            chunk=2048,
            buffer_seconds=self.config.get("buffer_seconds", 8),
            device=self.config.get("device", "cpu"),
            config=self.config
        )
        self.worker.result_ready.connect(self.on_new_recognition)
        self.worker.initialized.connect(self.on_worker_initialized)
        self.worker.start()
        self.recognition_active = True

        keyboard.add_hotkey('ctrl+shift+h', self.toggle_recognition)

        self._startPos = None

        # 设置窗口位置为屏幕底部居中
        screen = QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            x = (geometry.width() - self.width()) // 2
            y = geometry.height() - self.height() - 10
            self.move(x, y)

        # 初始化系统托盘图标及菜单
        self.init_tray_icon()
        self.exiting = False  # 用于标识是否真的退出

        # 用于麦克风加载时的转圈动画控制
        self.loading = False
        self.spinner_index = 0
        self.spinner_icons = ["◐", "◓", "◑", "◒"]
        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self.update_spinner)

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        # 使用一个默认图标，可自行替换为合适的图标路径
        self.tray_icon.setIcon(QIcon.fromTheme("application-exit"))
        self.tray_menu = QMenu()

        self.action_show = QAction("显示", self)
        self.action_show.triggered.connect(self.show_window_from_tray)
        self.tray_menu.addAction(self.action_show)

        # 设置项：是否识别表情
        self.action_toggle_emoji = QAction("识别表情", self, checkable=True)
        self.action_toggle_emoji.setChecked(self.config.get("enable_emoji", True))
        self.action_toggle_emoji.triggered.connect(self.toggle_emoji)
        self.tray_menu.addAction(self.action_toggle_emoji)

        # 设置项：是否识别说话人
        self.action_toggle_speaker = QAction("识别说话人", self, checkable=True)
        self.action_toggle_speaker.setChecked(self.config.get("enable_speaker", True))
        self.action_toggle_speaker.triggered.connect(self.toggle_speaker)
        self.tray_menu.addAction(self.action_toggle_speaker)

        # 设置项：是否接受反馈
        self.action_toggle_feedback = QAction("接受反馈", self, checkable=True)
        self.action_toggle_feedback.setChecked(self.config.get("enable_feedback", True))
        self.action_toggle_feedback.triggered.connect(self.toggle_feedback)
        self.tray_menu.addAction(self.action_toggle_feedback)

        # 子菜单：选择语言
        self.language_menu = QMenu("选择语言", self)
        languages = ["zh", "en", "ja"]
        for lang in languages:
            action = QAction(lang, self, checkable=True)
            action.setData(lang)
            if lang == self.config.get("language", "zh"):
                action.setChecked(True)
            action.triggered.connect(lambda checked, a=action: self.set_language(a))
            self.language_menu.addAction(action)
        self.tray_menu.addMenu(self.language_menu)

        # 子菜单：VAD间隔设置
        self.vad_menu = QMenu("VAD间隔", self)
        vad_intervals = [256, 512, 1024]
        for interval in vad_intervals:
            action = QAction(f"{interval} ms", self, checkable=True)
            action.setData(interval)
            if interval == self.config.get("vad_interval", 256):
                action.setChecked(True)
            action.triggered.connect(lambda checked, a=action: self.set_vad_interval(a))
            self.vad_menu.addAction(action)
        self.tray_menu.addMenu(self.vad_menu)

        # 退出选项
        self.action_exit = QAction("退出", self)
        self.action_exit.triggered.connect(self.exit_application)
        self.tray_menu.addAction(self.action_exit)

        self.tray_icon.setContextMenu(self.tray_menu)
        # 支持双击托盘图标恢复窗口
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        from PyQt6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window_from_tray()

    def toggle_emoji(self, checked):
        self.config["enable_emoji"] = checked
        print("识别表情设置:", checked)

    def toggle_speaker(self, checked):
        self.config["enable_speaker"] = checked
        print("识别说话人设置:", checked)

    def toggle_feedback(self, checked):
        self.config["enable_feedback"] = checked
        print("接受反馈设置:", checked)
        if not checked:
            self.feedback_button.hide()
        else:
            self.feedback_button.show()

    def set_language(self, action):
        lang = action.data()
        self.config["language"] = lang
        for act in self.language_menu.actions():
            act.setChecked(act == action)
        print("语言设置为:", lang)

    def set_vad_interval(self, action):
        interval = action.data()
        self.config["vad_interval"] = interval
        if hasattr(self, "worker"):
            self.worker.vad_chunk_ms = interval
            self.worker.vad_chunk_samples = int(self.worker.sample_rate * interval / 1000)
        for act in self.vad_menu.actions():
            act.setChecked(act == action)
        print("VAD间隔设置为:", interval, "ms")

    def show_window_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

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
            if self.loading:
                self.loading_timer.stop()
                self.loading = False
            self.worker.stop()
            self.worker.wait()
            self.recognition_active = False
            self.toggle_button.setText("🚫")
            self.toggle_button.setStyleSheet("background-color: lightcoral; border-radius: 5px;")
            print("识别已停止")
        else:
            self.loading = True
            self.spinner_index = 0
            self.toggle_button.setEnabled(False)
            self.loading_timer.start(200)
            from worker_thread import ASRWorkerThread
            self.worker = ASRWorkerThread(
                sample_rate=16000,
                chunk=2048,
                buffer_seconds=self.config.get("buffer_seconds", 8),
                device=self.config.get("device", "cpu"),
                config=self.config
            )
            self.worker.result_ready.connect(self.on_new_recognition)
            self.worker.initialized.connect(self.on_worker_initialized)
            self.worker.start()
            self.recognition_active = True
            print("识别启动中...")

    def on_worker_initialized(self):
        self.loading_timer.stop()
        self.loading = False
        self.toggle_button.setEnabled(True)
        self.toggle_button.setText("🎤")
        self.toggle_button.setStyleSheet("background-color: lightgreen; border-radius: 5px;")
        print("识别已启动")

    def update_spinner(self):
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_icons)
        self.toggle_button.setText(self.spinner_icons[self.spinner_index])

    def on_new_recognition(self, recognized_text, audio_id):
        processed = self.process_text(recognized_text)
        self.last_recognized_text = processed
        self.last_audio_id = audio_id
        self.recognition_edit.setText(processed)
        if self.auto_send_timer.isActive():
            self.auto_send_timer.stop()
        self.auto_send_timer.start(3000)

    def auto_send(self):
        if self.recognition_edit.hasFocus():
            print("自动上屏已取消，因为文本框处于激活状态。")
            return
        current_text = self.recognition_edit.text().strip()
        if current_text and current_text != self.last_sent_text:
            insert_text_into_active_window(current_text)
            self.last_sent_text = current_text

    def on_manual_send(self):
        current_text = self.recognition_edit.text().strip()
        if current_text:
            if current_text != self.last_sent_text:
                self.hide()
                QTimer.singleShot(100, lambda: (insert_text_into_active_window(current_text), self.show()))
                self.last_sent_text = current_text
        else:
            print("没有文本可上屏。")

    def on_feedback_clicked(self):
        if not self.config.get("enable_feedback", True):
            print("反馈功能已禁用。")
            return
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
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            print("窗口已隐藏到系统托盘。")
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
        if self.exiting:
            if self.recognition_active:
                self.worker.stop()
                self.worker.wait()
            event.accept()
        else:
            self.hide()
            event.ignore()

    def exit_application(self):
        self.exiting = True
        self.tray_icon.hide()
        self.close()
        QApplication.quit()

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = ModernUIWindow({})
    window.show()
    sys.exit(app.exec())
