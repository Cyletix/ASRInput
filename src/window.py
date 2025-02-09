import os
import json
import time
import re
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QLineEdit, QPushButton,
    QApplication, QSystemTrayIcon, QMenu, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent
from PyQt6.QtGui import QMouseEvent, QGuiApplication, QKeyEvent, QIcon, QAction, QFocusEvent, QPixmap, QColor, QPainter
import keyboard  # 使用 keyboard 库
from asr_core import emo_set  # 用于提取表情

def insert_text_into_active_window(text):
    try:
        keyboard.write(text)
    except Exception as e:
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        print("keyboard.write 失败，文本已复制到剪贴板，请手动粘贴。", e)

def tint_icon_white(icon, size):
    """
    将传入的 QIcon 转换为白色调图标，size为目标尺寸（宽度=高度）
    """
    # 获取固定尺寸的 pixmap
    pixmap = icon.pixmap(QSize(size, size))
    image = pixmap.toImage()
    for x in range(image.width()):
        for y in range(image.height()):
            color = image.pixelColor(x, y)
            if color.alpha() > 0:
                # 强制设为白色，保留透明度
                image.setPixelColor(x, y, QColor(255, 255, 255, color.alpha()))
    return QIcon(QPixmap.fromImage(image))

class ModernUIWindow(QMainWindow):
    def __init__(self, config_dict):
        super().__init__()
        self.config = config_dict
        self.setWindowTitle("语音识别悬浮窗口")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 根据是否接受反馈分别构建布局和设置窗口属性
        if self.config.get("accept_feedback", False):
            # ---------------- 接受反馈模式 ----------------
            self.setFixedSize(400, 40)
            flags = (Qt.WindowType.Tool |
                     Qt.WindowType.FramelessWindowHint |
                     Qt.WindowType.WindowStaysOnTopHint)
            self.setWindowFlags(flags)
            # 设置中央控件，背景黑色80%不透明，并加1px外边框
            central_widget = QWidget(self)
            central_widget.setStyleSheet("border: 1px solid #1C1C1C; border-radius: 8px; background-color: rgba(0, 0, 0, 0.80);")
            layout = QHBoxLayout(central_widget)
            layout.setContentsMargins(5, 5, 5, 5)
            self.setCentralWidget(central_widget)
            
            # 麦克风按钮：尺寸较大，无额外外圈
            self.toggle_button = QPushButton()
            self.setup_round_button(self.toggle_button, 60, 36, "#292929")
            self.toggle_button.setIcon(QIcon("ms_mic_inactive.svg"))
            self.toggle_button.clicked.connect(self.toggle_recognition)
            # 确保 QSS 生效
            self.toggle_button.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            layout.addWidget(self.toggle_button)
            
            # 添加识别输入框与反馈、Send按钮
            self.recognition_edit = QLineEdit()
            self.recognition_edit.setPlaceholderText("等待识别...")
            self.recognition_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.recognition_edit.setFixedHeight(25)
            self.recognition_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            # 设置2px圆角、蓝色底边及灰色边框
            self.recognition_edit.setStyleSheet("border: 1px solid #292929; border-bottom: 2px solid #7886C7; border-radius: 2px; padding: 0px;")
            layout.addWidget(self.recognition_edit, stretch=1)
            
            self.feedback_button = QPushButton("反馈")
            self.feedback_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.feedback_button.setFixedSize(50, 25)
            # 设置2px圆角
            self.feedback_button.setStyleSheet("border: 1px solid #292929; border-radius: 8px; padding: 0px;")
            self.feedback_button.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.feedback_button.clicked.connect(self.on_feedback_clicked)
            layout.addWidget(self.feedback_button)
            
            self.manual_send_button = QPushButton("Send")
            self.manual_send_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.manual_send_button.setFixedSize(50, 25)
            self.manual_send_button.setStyleSheet("border: 1px solid #292929; border-radius: 8px; padding: 0px;")
            self.manual_send_button.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.manual_send_button.clicked.connect(self.on_manual_send)
            layout.addWidget(self.manual_send_button)
        else:
            # ---------------- 不接受反馈模式 ----------------
            self.setFixedSize(150, 100)
            flags = (Qt.WindowType.Tool |
                     Qt.WindowType.FramelessWindowHint |
                     Qt.WindowType.WindowStaysOnTopHint |
                     Qt.WindowType.WindowDoesNotAcceptFocus)
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            
            # 构建仅显示麦克风按钮的界面，背景加1px外边框
            central_widget = QWidget(self)
            central_widget.setStyleSheet("border: 1px solid #1C1C1C; border-radius: 15px; background-color: rgba(0, 0, 0, 0.80);")
            layout = QHBoxLayout(central_widget)
            layout.setContentsMargins(5, 5, 5, 5)
            self.setCentralWidget(central_widget)
            
            self.toggle_button = QPushButton()
            self.toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # 设置圆形按钮并添加外圈2px的 #556070
            self.setup_round_button(self.toggle_button, 50, 30, "#292929", extra_border="border: 2px solid #556070;")
            # 使用 tint_icon_white() 将图标着色为白色
            base_icon = QIcon("ms_mic_inactive.svg")
            tinted_icon = tint_icon_white(base_icon, 30)
            self.toggle_button.setIcon(tinted_icon)
            self.toggle_button.clicked.connect(self.toggle_recognition)
            self.toggle_button.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            layout.addWidget(self.toggle_button)
            self.show()
        
        # 后续共用控件和逻辑初始化
        self.last_recognized_text = ""
        self.last_audio_id = ""
        self.last_sent_text = ""
        
        self.remove_trailing_period = self.config.get("remove_trailing_period", True)
        self.trailing_punctuation = self.config.get("trailing_punctuation", "")
        self.punctuation_mode = self.config.get("punctuation_mode", "half")
        
        self.auto_send_timer = QTimer(self)
        self.auto_send_timer.setSingleShot(True)
        self.auto_send_timer.timeout.connect(self.auto_send)
        
        # 初始状态：新状态下不立即启动识别
        self.recognition_active = False

        # 初始化日志
        os.makedirs("log", exist_ok=True)
        self.log_file_path = f"log/recognition_{time.strftime('%Y%m%d_%H%M%S')}.log"
        self.log_file = open(self.log_file_path, "a", encoding="utf-8")
        
        # 创建后台识别线程（保持原有逻辑）
        from worker_thread import ASRWorkerThread
        self.worker = ASRWorkerThread(
            sample_rate=16000,
            chunk=self.config.get("chunk", 256),
            buffer_seconds=self.config.get("buffer_seconds", 2),
            device=self.config.get("device", "cpu"),
            config=self.config
        )
        self.worker.result_ready.connect(self.on_new_recognition)
        self.worker.initialized.connect(self.on_worker_initialized)
        # 暂不调用 worker.start()，等待用户手动启动
        
        # 添加全局热键
        keyboard.add_hotkey('shift+alt+h', self.toggle_recognition)
        keyboard.add_hotkey('esc', lambda: (self.hide(), print("窗口已隐藏到系统托盘。")))
        
        # 初始化系统托盘图标与菜单
        self.init_tray_icon()

        # 调整浮窗默认位置：屏幕 availableGeometry() 底部中央，紧贴任务栏
        self.reposition_window()

    def reposition_window(self):
        """
        将窗口重新定位到屏幕 availableGeometry() 的底部中央（紧贴任务栏）
        """
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + (geom.width() - self.width()) // 2
            y = geom.y() + geom.height() - self.height()
            self.move(x, y)

    def event(self, e: QEvent):
        # 拦截窗口激活和焦点事件，非反馈模式下不转移焦点
        if e.type() in (QEvent.Type.WindowActivate, QEvent.Type.FocusIn) and not self.config.get("accept_feedback", False):
            return True
        return super().event(e)

    def focusInEvent(self, event: QFocusEvent):
        # 非反馈模式下不允许窗口获取焦点
        if not self.config.get("accept_feedback", False):
            self.clearFocus()
            event.ignore()
        else:
            super().focusInEvent(event)

    def focusNextPrevChild(self, next: bool) -> bool:
        # 非反馈模式下禁止焦点切换
        if not self.config.get("accept_feedback", False):
            return False
        return super().focusNextPrevChild(next)

    def setup_round_button(self, button, btn_size, icon_size, bg_color, extra_border=""):
        """
        设置按钮的固定尺寸和图标尺寸，并根据尺寸计算圆角。
        参数 extra_border 用于附加边框样式（例如非反馈模式下外圈）。
        """
        button.setFixedSize(btn_size, btn_size)
        button.setIconSize(QSize(icon_size, icon_size))
        radius = btn_size // 2
        style = f"{extra_border} border-radius: {radius}px; background-color: {bg_color}; padding: 4px;"
        button.setStyleSheet(style)

    def update_ui_mode(self):
        """
        根据 self.config["accept_feedback"] 动态构建 UI：
         - 反馈模式下：显示麦克风按钮、文本框、反馈及 Send 按钮（各部件均使用2px圆角），背景带1px #1C1C1C 外边框。
         - 非反馈模式下：仅显示麦克风按钮，且在圆形按钮外加4px的 #556070 外圈。
         切换模式时先停止识别，确保新状态下不立即识别，然后重新定位浮窗。
        """
        # 切换模式时先停止当前识别
        if self.recognition_active and self.worker is not None:
            self.worker.stop()
            self.worker.wait()
            self.recognition_active = False
            self.toggle_button.setIcon(QIcon("ms_mic_inactive.svg"))
        
        old_widget = self.centralWidget()
        if old_widget:
            old_widget.deleteLater()
        
        if self.config.get("accept_feedback", False):
            self.setFixedSize(400, 40)
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            central_widget = QWidget(self)
            central_widget.setStyleSheet("border: 1px solid #1C1C1C; border-radius: 15px; background-color: rgba(0, 0, 0, 0.80);")
            layout = QHBoxLayout(central_widget)
            layout.setContentsMargins(5, 5, 5, 5)
            self.setCentralWidget(central_widget)
            
            self.toggle_button = QPushButton()
            self.toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # 反馈模式下无需外圈
            self.setup_round_button(self.toggle_button, 30, 18, "#292929")
            self.toggle_button.setIcon(QIcon("ms_mic_inactive.svg"))
            self.toggle_button.clicked.connect(self.toggle_recognition)
            layout.addWidget(self.toggle_button)
            
            self.recognition_edit = QLineEdit()
            self.recognition_edit.setPlaceholderText("等待识别...")
            self.recognition_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.recognition_edit.setFixedHeight(25)
            self.recognition_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.recognition_edit.setStyleSheet("border: 1px solid #292929; border-bottom: 2px solid #A4C2E9; border-radius: 2px;")
            layout.addWidget(self.recognition_edit, stretch=1)
            
            self.feedback_button = QPushButton("反馈")
            self.feedback_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.feedback_button.setFixedSize(50, 25)
            self.feedback_button.setStyleSheet("border: 1px solid #292929; border-radius: 2px;")
            self.feedback_button.clicked.connect(self.on_feedback_clicked)
            layout.addWidget(self.feedback_button)
            
            self.manual_send_button = QPushButton("Send")
            self.manual_send_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.manual_send_button.setFixedSize(50, 25)
            self.manual_send_button.setStyleSheet("border: 1px solid #292929; border-radius: 2px;")
            self.manual_send_button.clicked.connect(self.on_manual_send)
            layout.addWidget(self.manual_send_button)
        else:
            self.setFixedSize(150, 100)
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            central_widget = QWidget(self)
            central_widget.setStyleSheet("border: 1px solid #1C1C1C; border-radius: 15px; background-color: rgba(0, 0, 0, 0.80);")
            layout = QHBoxLayout(central_widget)
            layout.setContentsMargins(5, 5, 5, 5)
            self.setCentralWidget(central_widget)
            
            self.toggle_button = QPushButton()
            self.toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # 正常模式下为圆形按钮添加外圈2px的 #556070
            self.setup_round_button(self.toggle_button, 50, 30, "#292929", extra_border="border: 2px solid #556070;")
            base_icon = QIcon("ms_mic_inactive.svg")
            # 将图标转换为白色线条图标
            tinted_icon = tint_icon_white(base_icon, 30)
            self.toggle_button.setIcon(tinted_icon)
            self.toggle_button.clicked.connect(self.toggle_recognition)
            layout.addWidget(self.toggle_button)
            self.show()
        # 重新定位浮窗到屏幕底部中央
        self.reposition_window()

    def focusNextPrevChild(self, next: bool) -> bool:
        # 非反馈模式下禁止焦点切换
        if not self.config.get("accept_feedback", False):
            return False
        return super().focusNextPrevChild(next)

    def closeEvent(self, event):
        if self.exiting:
            if self.recognition_active and self.worker is not None:
                self.worker.stop()
                self.worker.wait()
            self.log_file.close()
            event.accept()
        else:
            self.hide()
            event.ignore()
            
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

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon.fromTheme("application-exit"))
        self.tray_icon.setToolTip("ASRInput by Cyletix")
        self.tray_menu = QMenu()
        
        self.action_show = QAction("显示", self)
        self.action_show.triggered.connect(self.show_window_from_tray)
        self.tray_menu.addAction(self.action_show)
        
        self.action_toggle_emoji = QAction("识别表情", self, checkable=True)
        self.action_toggle_emoji.setChecked(self.config.get("recognize_emoji", False))
        self.action_toggle_emoji.setToolTip("是否对识别结果进行表情处理")
        self.action_toggle_emoji.triggered.connect(lambda checked: self.config.update({"recognize_emoji": checked}) or print("识别表情设置:", checked))
        self.tray_menu.addAction(self.action_toggle_emoji)
        
        self.action_toggle_speaker = QAction("识别说话人", self, checkable=True)
        self.action_toggle_speaker.setChecked(self.config.get("recognize_speaker", False))
        self.action_toggle_speaker.setToolTip("是否锁定当前说话人")
        self.action_toggle_speaker.triggered.connect(lambda checked: self.config.update({"recognize_speaker": checked}) or print("识别说话人设置:", checked))
        self.tray_menu.addAction(self.action_toggle_speaker)
        
        # “接受反馈”按钮：点击后更新界面并自动显示窗口
        self.action_toggle_feedback = QAction("接受反馈", self, checkable=True)
        self.action_toggle_feedback.setChecked(self.config.get("accept_feedback", False))
        self.action_toggle_feedback.setToolTip("启用后记录反馈音频，并切换为反馈模式")
        self.action_toggle_feedback.triggered.connect(lambda checked: (
            self.config.update({"accept_feedback": checked}),
            self.update_ui_mode(),
            self.show_window_from_tray(),
            print("接受反馈设置:", checked)
        ))
        self.tray_menu.addAction(self.action_toggle_feedback)
        
        self.language_menu = QMenu("选择语言", self)
        for lang in ["zh", "en", "ja"]:
            action = QAction(lang, self, checkable=True)
            action.setData(lang)
            if lang == self.config.get("language", "zh"):
                action.setChecked(True)
            action.triggered.connect(lambda checked, a=action: self.set_language(a))
            self.language_menu.addAction(action)
        self.tray_menu.addMenu(self.language_menu)
        
        self.vad_menu = QMenu("VAD间隔", self)
        for interval in [256, 512, 1024]:
            action = QAction(f"{interval} ms", self, checkable=True)
            action.setData(interval)
            if interval == self.config.get("vad_interval", 256):
                action.setChecked(True)
            action.triggered.connect(lambda checked, a=action: self.set_vad_interval(a))
            self.vad_menu.addAction(action)
        self.tray_menu.addMenu(self.vad_menu)
        
        self.chunk_menu = QMenu("Chunk大小", self)
        for c in [512, 1024, 2048]:
            action = QAction(f"{c}", self, checkable=True)
            action.setData(c)
            if c == self.config.get("chunk", 2048):
                action.setChecked(True)
            action.triggered.connect(lambda checked, a=action: self.set_chunk(a))
            self.chunk_menu.addAction(action)
        self.tray_menu.addMenu(self.chunk_menu)
        
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
        if self.worker is not None:
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
            text = re.sub(r'[.。]+$', '', text)
            mode = self.punctuation_mode
            if mode in ["half", "full"]:
                text += self.trailing_punctuation
            elif mode == "space":
                text += " "
        return text
        
    def toggle_recognition(self):
        if self.recognition_active:
            if self.worker is not None:
                self.worker.stop()
                self.worker.wait()
            self.recognition_active = False
            self.toggle_button.setIcon(QIcon("ms_mic_inactive.svg"))
            # 根据当前模式重置按钮样式
            if self.config.get("accept_feedback", False):
                self.setup_round_button(self.toggle_button, self.toggle_button.width(), 
                                          self.toggle_button.iconSize().width(), "#292929")
            else:
                self.setup_round_button(self.toggle_button, self.toggle_button.width(), 
                                          self.toggle_button.iconSize().width(), "#292929", extra_border="border: px solid #556070;")
            print("识别已停止")
        else:
            self.toggle_button.setEnabled(False)
            QTimer.singleShot(200, self.start_worker)
            
    def start_worker(self):
        from worker_thread import ASRWorkerThread
        self.worker = ASRWorkerThread(
            sample_rate=16000,
            chunk=self.config.get("chunk", 256),
            buffer_seconds=self.config.get("buffer_seconds", 2),
            device=self.config.get("device", "cpu"),
            config=self.config
        )
        self.worker.result_ready.connect(self.on_new_recognition)
        self.worker.initialized.connect(self.on_worker_initialized)
        self.worker.start()
        self.recognition_active = True
        print("识别启动中...")
        
    def on_worker_initialized(self):
        self.toggle_button.setEnabled(True)
        self.recognition_active = True
        self.toggle_button.setIcon(QIcon("ms_mic_active.svg"))
        if self.config.get("accept_feedback", False):
            self.setup_round_button(self.toggle_button, self.toggle_button.width(), 
                                      self.toggle_button.iconSize().width(), "#A4C2E9")
        else:
            self.setup_round_button(self.toggle_button, self.toggle_button.width(), 
                                      self.toggle_button.iconSize().width(), "#A4C2E9", extra_border="border: 2px solid #556070;")
        print("识别已启动")
        
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
        self.log_recognition(processed)
        if self.config.get("accept_feedback", False):
            self.recognition_edit.setText(processed)
            if self.auto_send_timer.isActive():
                self.auto_send_timer.stop()
            self.auto_send_timer.start(3000)
        else:
            insert_text_into_active_window(processed)
            
    def auto_send(self):
        if self.recognition_edit and self.recognition_edit.hasFocus():
            print("自动上屏已取消，因为文本框处于激活状态。")
            return
        if self.recognition_edit:
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
            if self.recognition_active and self.worker is not None:
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