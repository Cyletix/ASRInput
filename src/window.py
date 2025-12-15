import os
import json
import time
import re
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QLineEdit, QPushButton,
    QApplication, QSystemTrayIcon, QMenu, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent
from PyQt6.QtGui import QMouseEvent, QGuiApplication, QIcon, QAction, QFocusEvent, QPixmap, QColor
import keyboard
from asr_core import emo_set

# === 图标配置 ===
ICON_APP = "audio-melody-music-38-svgrepo-com.svg"
ICON_ACTIVE = "ms_mic_active.svg"
ICON_INACTIVE = "ms_mic_inactive.svg"

def insert_text_into_active_window(text):
    try:
        keyboard.write(text)
    except Exception as e:
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        print("keyboard.write 失败，文本已复制到剪贴板。", e)

class ModernUIWindow(QMainWindow):
    def __init__(self, config_dict):
        super().__init__()
        self.config = config_dict
        self.setWindowTitle("语音识别悬浮窗口")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.worker = None
        self.exiting = False
        self.service_running = False  # 服务总开关状态
        self.mini_mode = False        # 极简模式状态

        # 默认配置兜底
        if "auto_send_delay" not in self.config:
            self.config["auto_send_delay"] = 3

        # === 界面构建 (默认完整模式) ===
        self.setFixedSize(400, 40)
        flags = (Qt.WindowType.Tool |
                 Qt.WindowType.FramelessWindowHint |
                 Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlags(flags)
        
        central_widget = QWidget(self)
        central_widget.setStyleSheet("border: 1px solid #1C1C1C; border-radius: 8px; background-color: rgba(0, 0, 0, 0.80);")
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        self.setCentralWidget(central_widget)
        
        # 1. 麦克风按钮
        self.toggle_button = QPushButton()
        self.setup_round_button(self.toggle_button, 30, 24, "#292929")
        self.toggle_button.clicked.connect(self.toggle_recognition)
        layout.addWidget(self.toggle_button)
        
        # 2. 输入框
        self.recognition_edit = QLineEdit()
        self.recognition_edit.setPlaceholderText("等待识别...")
        self.recognition_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.recognition_edit.setFixedHeight(25)
        self.recognition_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.recognition_edit.setStyleSheet("border: 1px solid #292929; border-bottom: 2px solid #7886C7; border-radius: 8px; padding: 0px; color: white; background: transparent;")
        self.recognition_edit.installEventFilter(self)
        layout.addWidget(self.recognition_edit, stretch=1)
        
        # 3. 上屏按钮
        self.manual_send_button = QPushButton("Send")
        self.manual_send_button.setFixedSize(50, 25)
        self.manual_send_button.setStyleSheet("border: 1px solid #292929; border-radius: 8px; color: white; background: #444;")
        self.manual_send_button.clicked.connect(self.on_manual_send)
        layout.addWidget(self.manual_send_button)

        # === 状态初始化 ===
        self.last_recognized_text = ""
        self.last_audio_id = ""
        self.last_sent_text = ""
        self.recognition_active = False
        
        self.remove_trailing_period = self.config.get("remove_trailing_period", True)
        self.trailing_punctuation = self.config.get("trailing_punctuation", " ")
        self.punctuation_mode = self.config.get("punctuation_mode", "half")
        
        # 自动上屏定时器
        self.auto_send_timer = QTimer(self)
        self.auto_send_timer.setSingleShot(True)
        self.auto_send_timer.timeout.connect(self.auto_send)
        
        # 日志
        os.makedirs("log", exist_ok=True)
        self.log_file_path = f"log/recognition_{time.strftime('%Y%m%d_%H%M%S')}.log"
        self.log_file = open(self.log_file_path, "a", encoding="utf-8")
        
        # 热键
        try:
            keyboard.add_hotkey('ctrl+shift+h', lambda: QTimer.singleShot(0, self.toggle_window_visibility))
            keyboard.add_hotkey('esc', lambda: QTimer.singleShot(100, self.on_esc_pressed))
        except:
            print("热键注册失败")
        
        # 托盘与位置
        self.init_tray_icon()
        self.reposition_window()
        
        # 默认启动并设置初始状态
        self.set_disabled_state()
        QTimer.singleShot(500, self.start_worker_service)

    def setup_round_button(self, button, btn_size, icon_size, bg_color, extra_border=""):
        button.setFixedSize(btn_size, btn_size)
        button.setIconSize(QSize(icon_size, icon_size))
        radius = btn_size // 2
        style = f"""
            QPushButton {{
                {extra_border}
                border-radius: {radius}px;
                background-color: {bg_color};
                padding: 2px;
                border: 1px solid transparent;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(255, 255, 255, 0.5);
            }}
            QPushButton:pressed {{
                background-color: black;
                border: 1px solid rgba(255, 255, 255, 0.3);
            }}
        """
        button.setStyleSheet(style)

    # === 图标状态控制 ===
    def set_active_state(self):
        if os.path.exists(ICON_ACTIVE):
            self.toggle_button.setIcon(QIcon(ICON_ACTIVE))
        else:
            self.toggle_button.setText("🎤")
        
        if self.mini_mode:
            # 极简模式：激活色 #A4C2E9，50x30, 边框保持
            self.setup_round_button(self.toggle_button, 50, 30, "#A4C2E9", extra_border="border: 2px solid #556070;")
        else:
            # 完整模式：激活色 #2196F3，正常大小
            self.setup_round_button(self.toggle_button, 30, 24, "#2196F3")

    def set_disabled_state(self):
        if os.path.exists(ICON_INACTIVE):
            self.toggle_button.setIcon(QIcon(ICON_INACTIVE))
        else:
            self.toggle_button.setText("⏸")
        
        if self.mini_mode:
            # 极简模式：灰色，50x30, 边框保持
            self.setup_round_button(self.toggle_button, 50, 30, "#292929", extra_border="border: 2px solid #556070;")
        else:
            # 完整模式：灰色，正常大小
            self.setup_round_button(self.toggle_button, 30, 24, "#292929")

    # === 托盘菜单 ===
    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(ICON_APP):
            self.tray_icon.setIcon(QIcon(ICON_APP))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(QApplication.style().StandardPixmap.SP_MediaPlay))
            
        self.tray_menu = QMenu()
        
        # 模式切换
        self.action_ui_mode = QAction("🔄 切换极简模式", self)
        self.action_ui_mode.triggered.connect(self.toggle_ui_mode)
        self.tray_menu.addAction(self.action_ui_mode)
        
        self.tray_menu.addSeparator()

        # 服务开关
        self.action_toggle_service = QAction("✅ 启用语音服务", self)
        self.action_toggle_service.setCheckable(True)
        self.action_toggle_service.setChecked(True)
        self.action_toggle_service.triggered.connect(self.handle_tray_toggle_service)
        self.tray_menu.addAction(self.action_toggle_service)
        
        self.tray_menu.addSeparator()

        # 缓冲设置
        buffer_menu = self.tray_menu.addMenu("🔧 缓冲时长 (断句)")
        self.action_group_buffer = []
        current_buf = self.config.get("buffer_seconds", 4)
        for sec in [2, 4, 8]:
            act = QAction(f"{sec} 秒", self)
            act.setCheckable(True)
            act.setChecked(current_buf == sec)
            act.triggered.connect(lambda checked, s=sec: self.update_config_buffer(s))
            buffer_menu.addAction(act)
            self.action_group_buffer.append(act)

        # 延迟设置
        delay_menu = self.tray_menu.addMenu("⏱️ 自动上屏延迟")
        self.action_group_delay = []
        current_delay = self.config.get("auto_send_delay", 3)
        for sec in [1, 3, 5, 999]:
            label = "不自动" if sec == 999 else f"{sec} 秒"
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(current_delay == sec)
            act.triggered.connect(lambda checked, s=sec: self.update_config_delay(s))
            delay_menu.addAction(act)
            self.action_group_delay.append(act)

        self.tray_menu.addSeparator()
        
        action_show = QAction("显示/隐藏", self)
        action_show.triggered.connect(self.toggle_window_visibility)
        self.tray_menu.addAction(action_show)
        
        action_quit = QAction("退出程序", self)
        action_quit.triggered.connect(self.exit_application)
        self.tray_menu.addAction(action_quit)
        
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(lambda r: self.toggle_window_visibility() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)

    # === [关键修改] 模式切换逻辑 ===
    def toggle_ui_mode(self):
        self.mini_mode = not self.mini_mode
        self.update_ui_layout()
    
    def update_ui_layout(self):
        if self.mini_mode:
            # === 极简模式 (参考你提供的样式) ===
            self.setFixedSize(150, 100) # 参考样式尺寸
            
            # 设置 Flags：不接受焦点，不激活窗口
            flags = (Qt.WindowType.Tool |
                     Qt.WindowType.FramelessWindowHint |
                     Qt.WindowType.WindowStaysOnTopHint |
                     Qt.WindowType.WindowDoesNotAcceptFocus)
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            
            # 样式：15px 圆角
            self.centralWidget().setStyleSheet("border: 1px solid #1C1C1C; border-radius: 15px; background-color: rgba(0, 0, 0, 0.80);")
            
            # 隐藏输入框和按钮
            self.recognition_edit.hide()
            self.manual_send_button.hide()
            
            # 按钮样式初始化 (50x30, 30 icon, 边框)
            self.setup_round_button(self.toggle_button, 50, 30, "#292929", extra_border="border: 2px solid #556070;")
            
        else:
            # === 完整模式 (恢复原样) ===
            self.setFixedSize(400, 40)
            
            # 恢复 Flags：允许焦点
            flags = (Qt.WindowType.Tool |
                     Qt.WindowType.FramelessWindowHint |
                     Qt.WindowType.WindowStaysOnTopHint)
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            
            # 样式：8px 圆角
            self.centralWidget().setStyleSheet("border: 1px solid #1C1C1C; border-radius: 8px; background-color: rgba(0, 0, 0, 0.80);")
            
            self.recognition_edit.show()
            self.manual_send_button.show()
            
            # 按钮样式恢复
            self.setup_round_button(self.toggle_button, 30, 24, "#292929")
            
        # 刷新状态颜色
        if self.worker and not self.worker.paused:
            self.set_active_state()
        else:
            self.set_disabled_state()
            
        # 必须调用 show 才能应用新的 Flags
        self.show()
        self.reposition_window()

    # === 配置更新 ===
    def update_config_buffer(self, seconds):
        self.config["buffer_seconds"] = seconds
        for act in self.action_group_buffer: act.setChecked(int(act.text().split()[0]) == seconds)
        if self.worker:
            self.stop_worker_service()
            self.start_worker_service()

    def update_config_delay(self, seconds):
        self.config["auto_send_delay"] = seconds
        for act in self.action_group_delay: 
            val = 999 if "不自动" in act.text() else int(act.text().split()[0])
            act.setChecked(val == seconds)

    # === 服务控制逻辑 ===
    def handle_tray_toggle_service(self):
        is_on = self.action_toggle_service.isChecked()
        if is_on:
            self.start_worker_service()
        else:
            self.stop_worker_service()

    def start_worker_service(self):
        if self.worker is not None: return
        from worker_thread import ASRWorkerThread
        self.worker = ASRWorkerThread(
            sample_rate=16000,
            chunk=self.config.get("chunk", 256),
            buffer_seconds=self.config.get("buffer_seconds", 4),
            device=self.config.get("device", "cuda"),
            config=self.config
        )
        self.worker.result_ready.connect(self.on_new_recognition)
        self.worker.initialized.connect(self.on_worker_initialized)
        self.worker.start()
        self.service_running = True
        print("识别服务启动中...")

    def stop_worker_service(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self.service_running = False
        self.recognition_active = False
        self.set_disabled_state()
        self.recognition_edit.setPlaceholderText("服务已停止")
        self.hide()

    def on_worker_initialized(self):
        self.recognition_active = True
        self.action_toggle_service.setChecked(True)
        self.set_active_state()
        print("识别服务已就绪")

    def toggle_recognition(self):
        if self.worker is None:
            self.start_worker_service()
        else:
            if self.worker.paused:
                self.worker.resume()
                self.set_active_state()
            else:
                self.worker.pause()
                self.set_disabled_state()

    def resume_recognition_state(self):
        if self.service_running and self.worker:
            self.worker.resume()
            self.set_active_state()
            print("<<< 恢复识别状态")

    # === 交互与事件 ===
    def eventFilter(self, obj, event):
        if obj == self.recognition_edit and event.type() == QEvent.Type.FocusIn:
            if self.worker and not self.worker.paused:
                self.worker.pause()
                self.set_disabled_state()
                self.auto_send_timer.stop()
                print(">>> 输入框获得焦点，暂停自动识别")
        return super().eventFilter(obj, event)

    def focusOutEvent(self, event: QFocusEvent):
        if self.worker and not self.worker.paused:
            self.worker.pause()
            self.set_disabled_state()
            print(">>> 窗口失去焦点，识别已暂停")
        super().focusOutEvent(event)

    def on_new_recognition(self, recognized_text, audio_id):
        processed = recognized_text.strip()
        self.last_recognized_text = processed
        self.last_audio_id = audio_id
        
        self.log_file.write(f"{time.strftime('%H:%M:%S')} - {processed}\n")
        self.log_file.flush()
        
        # === [关键修改] 极简模式逻辑 ===
        if self.mini_mode:
            # 极简模式：没有输入框缓冲，没有延迟，直接上屏
            insert_text_into_active_window(processed)
        else:
            # 完整模式：原有的带缓冲区的逻辑
            if not self.recognition_edit.hasFocus():
                current = self.recognition_edit.text()
                new_text = current + " " + processed if current else processed
                self.recognition_edit.setText(new_text)
                
                delay_sec = self.config.get("auto_send_delay", 3)
                if delay_sec < 900:
                    self.auto_send_timer.start(delay_sec * 1000)
                    print(f"收到内容，{delay_sec}秒后自动上屏...")

    def auto_send(self):
        if self.recognition_edit.hasFocus(): return
        current_text = self.recognition_edit.text().strip()
        if current_text and current_text != self.last_sent_text:
            insert_text_into_active_window(current_text)
            self.last_sent_text = current_text
            self.recognition_edit.clear()

    def on_manual_send(self):
        self.auto_send_timer.stop()
        current_text = self.recognition_edit.text().strip()
        if current_text:
            self.hide()
            QTimer.singleShot(100, lambda: (insert_text_into_active_window(current_text), self.show()))
            self.last_sent_text = current_text
            self.recognition_edit.clear()
        else:
            self.resume_recognition_state()

    # === 窗口行为 ===
    def toggle_window_visibility(self):
        if self.isVisible():
            self.hide()
            if self.worker and not self.worker.paused:
                self.worker.pause()
                self.set_disabled_state()
                print(">>> 窗口隐藏，自动暂停")
        else:
            self.show()
            self.activateWindow()
            if self.worker:
                self.worker.resume()
                self.set_active_state()
                print("<<< 窗口唤醒，自动开始")
            else:
                self.start_worker_service()

    def on_esc_pressed(self):
        if self.worker and not self.worker.paused:
            self.worker.pause()
            self.set_disabled_state()
        self.hide()

    def reposition_window(self):
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            # 贴着右下角
            x = geom.width() - self.width()
            y = geom.height() - self.height() 
            self.move(x, y)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._startPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, event):
        if hasattr(self, '_startPos') and self._startPos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._startPos)
    def mouseReleaseEvent(self, event):
        self._startPos = None

    def closeEvent(self, event):
        if self.exiting:
            if self.worker: self.worker.stop()
            self.log_file.close()
            event.accept()
        else:
            if self.worker and not self.worker.paused:
                self.worker.pause()
                self.set_disabled_state()
            self.hide()
            event.ignore()
            
    def exit_application(self):
        self.exiting = True
        self.close()
        QApplication.quit()