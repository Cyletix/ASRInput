import os
import json
import time
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QLineEdit, QPushButton, 
                             QApplication, QSystemTrayIcon, QMenu)
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QMouseEvent, QGuiApplication, QKeyEvent, QAction
import keyboard

def insert_text_into_active_window(text):
    try:
        keyboard.write(text)
    except Exception as e:
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)

class ModernUIWindow(QMainWindow):
    def __init__(self, config_dict):
        super().__init__()
        self.config = config_dict
        self.setWindowTitle("语音识别悬浮窗口")
        
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(0.85)
        self.resize(550, 45)

        self.setObjectName("MainWindow")
        self.setStyleSheet("""
        #MainWindow {
            border: 1px solid #555555;
            border-radius: 8px;
            background-color: #2b2b2b;
        }
        QLineEdit {
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 2px;
            background: #3b3b3b;
            color: #ffffff;
            selection-background-color: #505050;
        }
        QPushButton {
            background-color: #4b4b4b;
            border: 1px solid #555555;
            border-radius: 4px;
            color: #ffffff;
        }
        QPushButton:hover {
            background-color: #5b5b5b;
        }
        QPushButton:pressed {
            background-color: #3b3b3b;
        }
        """)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.toggle_button = QPushButton("🎤")
        self.toggle_button.setFixedSize(40, 30)
        self.toggle_button.setStyleSheet("background-color: #4CAF50; border: none; border-radius: 4px; color: white;")
        self.toggle_button.clicked.connect(self.toggle_recognition)
        layout.addWidget(self.toggle_button)

        self.recognition_edit = QLineEdit()
        self.recognition_edit.setPlaceholderText("等待识别...")
        self.recognition_edit.setFixedHeight(30)
        self.recognition_edit.installEventFilter(self)
        layout.addWidget(self.recognition_edit, stretch=1)

        self.feedback_button = QPushButton("反馈")
        self.feedback_button.setFixedSize(50, 30)
        self.feedback_button.clicked.connect(self.on_feedback_clicked)
        layout.addWidget(self.feedback_button)

        self.manual_send_button = QPushButton("上屏")
        self.manual_send_button.setFixedSize(50, 30)
        self.manual_send_button.clicked.connect(self.on_manual_send)
        layout.addWidget(self.manual_send_button)

        self.last_recognized_text = ""
        self.last_audio_id = ""
        self.last_sent_text = ""
        self.recognition_active = True
        self._startPos = None
        self.is_editing = False

        # === 自动上屏定时器 ===
        self.auto_send_timer = QTimer()
        self.auto_send_timer.setSingleShot(True)
        self.auto_send_timer.timeout.connect(self.trigger_auto_send)
        # 默认 3 秒
        self.auto_send_delay = self.config.get("auto_send_delay", 3) * 1000 

        self.init_tray_icon()

        from worker_thread import ASRWorkerThread
        self.worker = ASRWorkerThread(
            sample_rate=16000,
            config=self.config
        )
        self.worker.result_ready.connect(self.on_new_recognition)
        self.worker.start()

        try:
            keyboard.add_hotkey('ctrl+shift+h', self.toggle_recognition)
        except:
            print("Hotkey failed to register.")
        
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move((geo.width()-self.width())//2, geo.height()-self.height()-50)

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QApplication.style().StandardPixmap.SP_MediaPlay))
        menu = QMenu()
        show_action = QAction("显示/隐藏", self)
        show_action.triggered.connect(self.toggle_visibility)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_activated)

    def toggle_visibility(self):
        if self.isVisible(): self.hide()
        else: 
            self.show()
            self.activateWindow()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_visibility()

    def quit_app(self):
        self.worker.stop()
        QApplication.quit()

    # === 事件过滤器：检测是否进入编辑模式 ===
    def eventFilter(self, source, event):
        if source == self.recognition_edit:
            if event.type() == QEvent.Type.FocusIn:
                if self.recognition_active and not self.worker.paused:
                    print(">>> Focus detected: Entering edit mode, cancelling auto-send.")
                    self.is_editing = True
                    self.worker.pause()
                    self.auto_send_timer.stop() # 只要一点进去，立刻停止倒计时
                    self.recognition_edit.setStyleSheet("border: 2px solid orange; color: white; background: #3b3b3b;")
        return super().eventFilter(source, event)

    # === 收到新识别结果 ===
    def on_new_recognition(self, text, audio_id):
        # 如果正在编辑，别打扰用户
        if self.worker.paused or self.is_editing:
            return

        # 1. 先显示在框里
        self.recognition_edit.setText(text)
        self.last_recognized_text = text
        self.last_audio_id = audio_id
        
        # 2. 启动 3秒 倒计时
        if text.strip():
            print(f"Recognized: '{text}'. Waiting {self.auto_send_delay/1000}s...")
            # 如果用户一直在说话，重置计时器
            self.auto_send_timer.start(self.auto_send_delay) 

    # === 计时器结束：自动上屏 ===
    def trigger_auto_send(self):
        if not self.is_editing and not self.worker.paused:
            text = self.recognition_edit.text().strip()
            if text:
                print(">>> Timer expired: Auto-typing.")
                insert_text_into_active_window(text)
                self.last_sent_text = text
                
                # === 修正：自动上屏后清空文本框 ===
                self.recognition_edit.clear() 
                # ==============================

    # === 手动点击上屏按钮 ===
    def on_manual_send(self):
        self.auto_send_timer.stop() # 防止重复
        text = self.recognition_edit.text().strip()
        
        if text:
            self.hide() 
            QTimer.singleShot(100, lambda: self._do_paste_and_resume(text))
        else:
            self.resume_recognition_state()

    def _do_paste_and_resume(self, text):
        insert_text_into_active_window(text)
        self.last_sent_text = text
        self.show()
        # 手动上屏也要清空
        self.recognition_edit.clear()
        self.resume_recognition_state()

    def resume_recognition_state(self):
        print("<<< Resuming recognition.")
        self.is_editing = False
        self.worker.resume()
        self.recognition_edit.setStyleSheet("border: 1px solid #555555; color: white; background: #3b3b3b;")

    def on_feedback_clicked(self):
        self.auto_send_timer.stop()
        current_text = self.recognition_edit.text().strip()
        if not current_text: return
        
        filename = self.worker.save_feedback_audio(self.last_audio_id)
        if filename:
            feedback = {
                "audio_filename": filename,
                "original": self.last_recognized_text,
                "modified": current_text
            }
            with open("feedback.json", "a", encoding="utf-8") as f:
                json.dump(feedback, f, ensure_ascii=False)
                f.write("\n")
            print(f"Feedback saved: {filename}")
            
            self.recognition_edit.clear()
            self.resume_recognition_state()

    def toggle_recognition(self):
        if self.recognition_active:
            self.worker.stop()
            self.auto_send_timer.stop()
            self.recognition_active = False
            self.toggle_button.setText("🚫")
            self.toggle_button.setStyleSheet("background-color: #F44336; border: none; border-radius: 4px; color: white;")
        else:
            from worker_thread import ASRWorkerThread
            self.worker = ASRWorkerThread(sample_rate=16000, config=self.config)
            self.worker.result_ready.connect(self.on_new_recognition)
            self.worker.start()
            self.recognition_active = True
            self.toggle_button.setText("🎤")
            self.toggle_button.setStyleSheet("background-color: #4CAF50; border: none; border-radius: 4px; color: white;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._startPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, event):
        if self._startPos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._startPos)
    def mouseReleaseEvent(self, event):
        self._startPos = None

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage("提示", "已最小化到托盘", QSystemTrayIcon.MessageIcon.Information, 1000)