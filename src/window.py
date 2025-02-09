import os
import json
import time
import re
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QLineEdit, QPushButton, QApplication, QSystemTrayIcon, QMenu, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QMouseEvent, QGuiApplication, QKeyEvent, QIcon, QAction
import keyboard  # 使用 keyboard 库
from asr_core import emo_set  # 用于提取表情

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
        # 无边框工具窗口、始终置顶且不抢焦点
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(0.85)
        # 整体尺寸 300x40，便于鼠标拖动
        self.resize(300, 40)

        self.setObjectName("MainWindow")
        self.setStyleSheet("""
        #MainWindow {
            background: transparent;
        }
        #CentralWidget {
            background-color: #000000;
            border: 1px solid #0060ff;
            border-radius: 8px;
        }
        """)
        central_widget = QWidget(self)
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # 初始化麦克风按钮部分
        self.toggle_button = QPushButton()
        self.toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggle_button.setFixedSize(20, 20)  # 按钮大小从 40x40 改为 20x20
        # 保持全黑的 SVG 图标
        self.toggle_button.setIcon(QIcon("ms_mic_inactive.svg"))
        self.toggle_button.setIconSize(QSize(12, 12))  # 图标尺寸从 24x24 改为 12x12
        # inactive 状态：背景色 #292929，圆形按钮（border-radius 为按钮宽度一半，即10px）
        self.toggle_button.setStyleSheet("border-radius: 10px; background-color: #292929; padding: 0px;")
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
        if not self.config.get("accept_feedback", False):
            self.feedback_button.hide()

        # 上屏按钮(Send)
        self.manual_send_button = QPushButton("Send")
        self.manual_send_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.manual_send_button.setFixedSize(50, 25)
        self.manual_send_button.clicked.connect(self.on_manual_send)
        layout.addWidget(self.manual_send_button)

        self.last_recognized_text = ""
        self.last_audio_id = ""
        self.last_sent_text = ""

        # 处理标点：根据配置删除结尾标点后追加自定义符号
        self.remove_trailing_period = self.config.get("remove_trailing_period", True)
        self.trailing_punctuation = self.config.get("trailing_punctuation", "")
        self.punctuation_mode = self.config.get("punctuation_mode", "half")

        # 自动上屏定时器（3秒后上屏）
        self.auto_send_timer = QTimer(self)
        self.auto_send_timer.setSingleShot(True)
        self.auto_send_timer.timeout.connect(self.auto_send)

        # 创建工作线程（稍后启动）
        from worker_thread import ASRWorkerThread
        self.worker = ASRWorkerThread(
            sample_rate=16000,
            chunk=self.config.get("chunk", 2048),
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
        # 屏幕底部居中
        screen = QGuiApplication.primaryScreen()
        if (screen):
            geometry = screen.availableGeometry()
            x = (geometry.width() - self.width()) // 2
            y = geometry.height() - self.height() - 10
            self.move(x, y)

        # 初始化系统托盘图标及菜单
        self.init_tray_icon()
        self.exiting = False

        # 麦克风加载时转圈动画
        self.loading = False
        self.spinner_index = 0
        self.spinner_icons = ["◐", "◓", "◑", "◒"]
        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self.update_spinner)

        # 初始化日志文件（写入到 log 目录，文件名带时间戳）
        os.makedirs("log", exist_ok=True)
        self.log_file_path = f"log/recognition_{time.strftime('%Y%m%d_%H%M%S')}.log"
        self.log_file = open(self.log_file_path, "a", encoding="utf-8")

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon.fromTheme("application-exit"))
        # 添加鼠标悬停提示文字
        self.tray_icon.setToolTip("ASRInput by Cyletix")
        self.tray_menu = QMenu()
    
        self.action_show = QAction("显示", self)
        self.action_show.triggered.connect(self.show_window_from_tray)
        self.tray_menu.addAction(self.action_show)

        # 配置：识别表情
        self.action_toggle_emoji = QAction("识别表情", self, checkable=True)
        self.action_toggle_emoji.setChecked(self.config.get("recognize_emoji", False))
        self.action_toggle_emoji.setToolTip("是否对识别结果进行表情处理")
        self.action_toggle_emoji.triggered.connect(lambda checked: self.config.update({"recognize_emoji": checked}) or print("识别表情设置:", checked))
        self.tray_menu.addAction(self.action_toggle_emoji)

        # 配置：识别说话人
        self.action_toggle_speaker = QAction("识别说话人", self, checkable=True)
        self.action_toggle_speaker.setChecked(self.config.get("recognize_speaker", False))
        self.action_toggle_speaker.setToolTip("是否锁定当前说话人")
        self.action_toggle_speaker.triggered.connect(lambda checked: self.config.update({"recognize_speaker": checked}) or print("识别说话人设置:", checked))
        self.tray_menu.addAction(self.action_toggle_speaker)

        # 配置：接受反馈
        self.action_toggle_feedback = QAction("接受反馈", self, checkable=True)
        self.action_toggle_feedback.setChecked(self.config.get("accept_feedback", False))
        self.action_toggle_feedback.setToolTip("仅在启用时记录反馈用音频")
        self.action_toggle_feedback.triggered.connect(lambda checked: self.config.update({"accept_feedback": checked}) or (self.feedback_button.setVisible(checked)) or print("接受反馈设置:", checked))
        self.tray_menu.addAction(self.action_toggle_feedback)

        # 子菜单：选择语言
        self.language_menu = QMenu("选择语言", self)
        for lang in ["zh", "en", "ja"]:
            action = QAction(lang, self, checkable=True)
            action.setData(lang)
            if lang == self.config.get("language", "zh"):
                action.setChecked(True)
            action.triggered.connect(lambda checked, a=action: self.set_language(a))
            self.language_menu.addAction(action)
        self.tray_menu.addMenu(self.language_menu)

        # 子菜单：VAD间隔设置
        self.vad_menu = QMenu("VAD间隔", self)
        for interval in [256, 512, 1024]:
            action = QAction(f"{interval} ms", self, checkable=True)
            action.setData(interval)
            if interval == self.config.get("vad_interval", 256):
                action.setChecked(True)
            action.triggered.connect(lambda checked, a=action: self.set_vad_interval(a))
            self.vad_menu.addAction(action)
        self.tray_menu.addMenu(self.vad_menu)

        # 新增子菜单：Chunk大小设置
        self.chunk_menu = QMenu("Chunk大小", self)
        for c in [512, 1024, 2048]:
            action = QAction(f"{c}", self, checkable=True)
            action.setData(c)
            if c == self.config.get("chunk", 2048):
                action.setChecked(True)
            action.triggered.connect(lambda checked, a=action: self.set_chunk(a))
            self.chunk_menu.addAction(action)
        self.tray_menu.addMenu(self.chunk_menu)

        # 退出选项
        self.action_exit = QAction("退出", self)
        self.action_exit.triggered.connect(self.exit_application)
        self.tray_menu.addAction(self.action_exit)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        from PyQt6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window_from_tray()

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

    def set_chunk(self, action):
        chunk_val = action.data()
        self.config["chunk"] = chunk_val
        for act in self.chunk_menu.actions():
            act.setChecked(act == action)
        print("Chunk 大小设置为:", chunk_val, "（需重启识别服务后生效）")

    def show_window_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def process_text(self, text):
        text = text.strip()
        if text:
            # 先删除末尾所有的半角或全角句号
            text = re.sub(r'[.。]+$', '', text)
            mode = self.punctuation_mode
            if mode in ["half", "full"]:
                text += self.trailing_punctuation
            elif mode == "space":
                text += " "
            # mode "none" 则不追加任何字符
        return text

    def toggle_recognition(self):
        if self.recognition_active:
            if self.loading:
                self.loading_timer.stop()
                self.loading = False
            self.worker.stop()
            self.worker.wait()
            self.recognition_active = False
            self.toggle_button.setIcon(QIcon("ms_mic_inactive.svg"))
            self.toggle_button.setIconSize(QSize(12, 12))  # 保持为 12x12
            self.toggle_button.setStyleSheet("border-radius: 10px; background-color: #292929; padding: 0px;")
            print("识别已停止")
        else:
            # 为确保加载动画能显示，延时启动工作线程
            self.loading = True
            self.spinner_index = 0
            self.toggle_button.setEnabled(False)
            self.loading_timer.start(200)
            QTimer.singleShot(200, self.start_worker)

    def start_worker(self):
        from worker_thread import ASRWorkerThread
        self.worker = ASRWorkerThread(
            sample_rate=16000,
            chunk=self.config.get("chunk", 2048),
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
        self.toggle_button.setIcon(QIcon("ms_mic_active.svg"))
        self.toggle_button.setIconSize(QSize(12, 12))  # 设置为 12x12
        # active 状态使用背景色 #A4C2E9，按钮尺寸仍为 20x20，圆角 10px
        self.toggle_button.setStyleSheet("border-radius: 10px; background-color: #A4C2E9; padding: 0px;")
        print("识别已启动")

    def update_spinner(self):
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_icons)
        self.toggle_button.setText(self.spinner_icons[self.spinner_index])

    def extract_emojis(self, text):
        return "".join(ch for ch in text if ch in emo_set)

    def log_recognition(self, text):
        record = {
            "时间": time.strftime("%Y-%m-%d %H:%M:%S"),
            "语言": self.config.get("language", "zh"),
            "表情": self.extract_emojis(text),
            "内容": text
        }
        self.log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.log_file.flush()

    def on_new_recognition(self, recognized_text, audio_id):
        processed = self.process_text(recognized_text)
        self.last_recognized_text = processed
        self.last_audio_id = audio_id
        self.recognition_edit.setText(processed)
        self.log_recognition(processed)
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
        if not self.config.get("accept_feedback", False):
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
            self.log_file.close()
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
