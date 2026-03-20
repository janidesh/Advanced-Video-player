import sys
import os
import json
import webbrowser
import ctypes
import re
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QSlider, QFileDialog, QFrame, QLabel, QSizeGrip, 
    QMenu, QGraphicsBlurEffect, QMessageBox
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtCore import Qt, QUrl, QTimer, QStandardPaths, QEvent
from PySide6.QtGui import QPixmap, QCursor, QIcon


class JanithPlayer(QMainWindow):
    """
    A custom, frameless media player built with PySide6.
    Features borderless dragging, a translucent 'liquid glass' control panel,
    SRT subtitle parsing, and global keyboard shortcuts. most of the codes wrote by me but some of the code inspired by previous open source projects and stackoverflow answers and also 
    took the help of AI to optimize some of the code and also to fix some of the bugs and also to add some of the features.
    """
    
    def __init__(self):
        super().__init__()
        
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1150, 750)
        
        self.setFocusPolicy(Qt.StrongFocus) 
        
        if getattr(sys, 'frozen', False):
            self.script_dir = os.path.dirname(sys.executable)
        else:
            self.script_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.assets_dir = os.path.join(self.script_dir, "Assets")
        self.logo_path = os.path.join(self.assets_dir, "logo.png")
        self.db_path = os.path.join(self.assets_dir, "playback_data.json")
        
        if not os.path.exists(self.assets_dir):
            os.makedirs(self.assets_dir)
            
        self.current_file = None
        self.playlist = []
        self.current_playlist_idx = -1
        self.subtitles = []
        self.is_muted = False
        self.is_looping = False
        self.is_always_on_top = False
        self.seek_step = 5.0 
       
        self._setup_multimedia()
        self._build_ui()
        self._connect_signals()
        self._setup_taskbar_icon()
        
        self.handle_state_change(QMediaPlayer.StoppedState)

    def _setup_multimedia(self):
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.video_surface = QVideoWidget()
        
        self.video_surface.setFocusPolicy(Qt.NoFocus)
        
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_surface)
        
        self.video_surface.setMouseTracking(True)
        self.video_surface.installEventFilter(self)
        
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.auto_hide_ui)

        self.sub_timer = QTimer()
        self.sub_timer.timeout.connect(self.sync_subtitles)
        self.sub_timer.start(100)

    def _build_ui(self):
        self.container = QWidget()
        self.container.setObjectName("MainContainer")
        self.setCentralWidget(self.container)
        
        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(45)
        self.title_bar.setObjectName("TitleBar")
        t_layout = QHBoxLayout(self.title_bar)
        
        t_layout.addWidget(self._create_dot("#ff5f57", self.safe_exit))
        t_layout.addWidget(self._create_dot("#ffbd2e", self.showMinimized))
        t_layout.addWidget(self._create_dot("#28c940", self.toggle_fullscreen))
        t_layout.addStretch()
        
        if os.path.exists(self.logo_path):
            self.title_logo = QLabel()
            pixmap = QPixmap(self.logo_path).scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.title_logo.setPixmap(pixmap)
            t_layout.addWidget(self.title_logo)
            
        t_layout.addWidget(QLabel("JANITH VIDEO PLAYER PRO"))
        t_layout.addStretch()
        self.main_layout.addWidget(self.title_bar)

        # -- Video Canvas & Overlays --
        self.video_layout = QVBoxLayout()
        self.video_layout.addWidget(self.video_surface)
        
        # Placeholder screen when video is stopped
        self.screen_logo = QLabel(self.video_surface)
        self.screen_logo.setAlignment(Qt.AlignCenter)
        self.screen_logo.setStyleSheet("background-color: #000;")
        
        # Subtitle engine UI
        self.subtitle_label = QLabel(self.video_surface)
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("""
            color: #ffffff;
            font-size: 26px;
            font-weight: bold;
            font-family: 'Iskoola Pota', 'Nirmala UI', sans-serif;
            background-color: rgba(0, 0, 0, 160);
            padding: 8px 15px;
            border-radius: 8px;
        """)
        self.subtitle_label.hide() 
        self.main_layout.addLayout(self.video_layout)

        self.controls_wrapper = QWidget()
        self.controls_wrapper.setFixedHeight(120)
        
        self.glass_bg = QFrame(self.controls_wrapper)
        self.glass_bg.setObjectName("LiquidGlassBg")
        self.blur_effect = QGraphicsBlurEffect()
        self.blur_effect.setBlurRadius(40)
        self.glass_bg.setGraphicsEffect(self.blur_effect)

        self.controls = QFrame(self.controls_wrapper)
        self.controls.setObjectName("ControlPanelUI")
        self.ctrl_layout = QVBoxLayout(self.controls)

        self.seeker = QSlider(Qt.Horizontal)
        self.seeker.setFocusPolicy(Qt.NoFocus) 
        self.ctrl_layout.addWidget(self.seeker)

        btn_row = QHBoxLayout()
        self.btn_browse = QPushButton("📁 Open Media")
        self.btn_subs = QPushButton("📝 Load Subs")
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setMinimumWidth(100)
       
        for btn in [self.btn_browse, self.btn_subs, self.btn_play]:
            btn.setFocusPolicy(Qt.NoFocus)
        
        self.branding_logo = QLabel()
        self.branding_logo.setCursor(QCursor(Qt.PointingHandCursor))
        self.branding_logo.mousePressEvent = lambda e: webbrowser.open("https://jdr.kesug.com")
        btn_row.addWidget(self.btn_browse)
        btn_row.addWidget(self.btn_subs)
        btn_row.addStretch()
        btn_row.addWidget(self.branding_logo)
        btn_row.addWidget(self.btn_play)
        btn_row.addStretch()
        
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.setValue(70)
        self.vol_slider.setFocusPolicy(Qt.NoFocus)
        self.audio.setVolume(0.7)
        
        btn_row.addWidget(QLabel("🔊"))
        btn_row.addWidget(self.vol_slider)
        btn_row.addWidget(QSizeGrip(self.controls))
        
        self.ctrl_layout.addLayout(btn_row)
        self.main_layout.addWidget(self.controls_wrapper)

        self._apply_stylesheet()
        self._load_images()
        
        self.setMouseTracking(True)
        self.container.setMouseTracking(True)

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #MainContainer { background: rgba(15, 15, 18, 220); border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.1); }
            #TitleBar { background: rgba(255, 255, 255, 0.05); }
            #LiquidGlassBg { background: rgba(45, 35, 60, 160); border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }
            #ControlPanelUI { background: transparent; }
            QPushButton { background: rgba(255, 255, 255, 0.12); color: white; border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; padding: 7px 15px; font-weight: bold; }
            QPushButton:hover { background: rgba(255, 255, 255, 0.25); border: 1px solid rgba(255, 255, 255, 0.4); }
            QSlider::handle:horizontal { background: #ff2a5f; width: 14px; height: 14px; border-radius: 7px; margin: -5px 0; }
            QSlider::groove:horizontal { background: rgba(255,255,255,0.2); height: 4px; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #ff2a5f; border-radius: 2px; }
            QMenu { background-color: rgba(30, 25, 35, 240); color: #eee; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 5px; }
            QMenu::item { padding: 8px 30px 8px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #ff2a5f; color: white; }
            QMenu::separator { height: 1px; background: rgba(255,255,255,0.1); margin: 5px 0; }
        """)

    def _load_images(self):
        if os.path.exists(self.logo_path):
            pix = QPixmap(self.logo_path)
            self.screen_logo.setPixmap(pix.scaled(500, 500, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.branding_logo.setPixmap(pix.scaled(35, 35, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _setup_taskbar_icon(self):
        if os.path.exists(self.logo_path):
            self.setWindowIcon(QIcon(self.logo_path))
        if os.name == 'nt':
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('janith.videoplayer.pro')
            except AttributeError:
                pass

    def _connect_signals(self):
        self.btn_browse.clicked.connect(self.browse_video)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_subs.clicked.connect(self.load_subtitles)
        self.vol_slider.valueChanged.connect(self.set_volume)
        
        self.player.positionChanged.connect(self.seeker.setValue)
        self.player.durationChanged.connect(lambda d: self.seeker.setRange(0, d))
        self.seeker.sliderMoved.connect(self.player.setPosition)
        
        self.player.playbackStateChanged.connect(self.handle_state_change)
        
        self.video_surface.setContextMenuPolicy(Qt.CustomContextMenu)
        self.video_surface.customContextMenuRequested.connect(self.show_context_menu)

    def browse_video(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Open Video(s)")
        if paths:
            self.save_current_position()
            self.playlist = paths
            self.current_playlist_idx = 0
            self.play_current_playlist_item()

    def play_current_playlist_item(self):
        if 0 <= self.current_playlist_idx < len(self.playlist):
            path = self.playlist[self.current_playlist_idx]
            self.current_file = path
            self.subtitles.clear()
            self.subtitle_label.hide()
            
            self.player.setSource(QUrl.fromLocalFile(path))
            
            potential_sub = os.path.splitext(path)[0] + ".srt"
            if os.path.exists(potential_sub):
                self.parse_srt(potential_sub)

            last_pos = self.get_saved_position(path)
            QTimer.singleShot(400, lambda: self.player.setPosition(last_pos))
            self.player.play()

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def set_volume(self, v):
        self.audio.setVolume(v / 100)
        self.is_muted = (v == 0)

    def toggle_mute(self):
        self.vol_slider.setValue(70 if self.is_muted else 0)

    def skip_video(self, seconds):
        """Skips the video forward or backward safely."""
        new_pos = max(0, min(self.player.position() + (seconds * 1000), self.player.duration()))
        self.player.setPosition(new_pos)

    def set_seek_step(self, val):
        self.seek_step = val

    def toggle_loop(self, checked):
        self.is_looping = checked

    def handle_state_change(self, state):
        """Updates UI based on playback status."""
        self.btn_play.setText("⏸ Pause" if state == QMediaPlayer.PlayingState else "▶ Play")
        
        if state == QMediaPlayer.PlayingState:
            self.screen_logo.hide()
        else:
            self.screen_logo.show()
            self.screen_logo.raise_()
            
        if state == QMediaPlayer.StoppedState and self.current_file:
            if self.player.position() >= self.player.duration() - 500: 
                if self.is_looping:
                    self.player.setPosition(0)
                    self.player.play()
                elif self.current_playlist_idx < len(self.playlist) - 1:
                    self.current_playlist_idx += 1
                    self.play_current_playlist_item()

    def load_subtitles(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Subtitle", "", "SubRip Subtitles (*.srt)")
        if path:
            self.parse_srt(path)

    def parse_srt(self, path):
        """Parses an SRT file via RegEx into memory for fast playback synchronization."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:(?!\n\n).)*)', re.DOTALL)
            matches = pattern.findall(content)
            
            self.subtitles.clear()
            for match in matches:
                start_ms = self._time_to_ms(match[1])
                end_ms = self._time_to_ms(match[2])
                text = match[3].replace('\n', '<br>')
                self.subtitles.append({'start': start_ms, 'end': end_ms, 'text': text})
            
            QMessageBox.information(self, "Subtitles Loaded", f"Successfully loaded {len(self.subtitles)} lines.")
            self.subtitle_label.show()
            self.subtitle_label.raise_()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to parse subtitle file:\n{str(e)}")

    def _time_to_ms(self, time_str):
        h, m, s = time_str.split(':')
        s, ms = s.split(',')
        return (int(h) * 3600000) + (int(m) * 60000) + (int(s) * 1000) + int(ms)

    def sync_subtitles(self):
        if not self.subtitles or self.player.playbackState() != QMediaPlayer.PlayingState:
            return
            
        current_time = self.player.position()
        active_text = ""
        
        for sub in self.subtitles:
            if sub['start'] <= current_time <= sub['end']:
                active_text = sub['text']
                break
                
        if active_text:
            self.subtitle_label.setText(active_text)
            if self.subtitle_label.isHidden(): self.subtitle_label.show()
        else:
            self.subtitle_label.setText("")

    def take_screenshot(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            pixmap = self.video_surface.grab()
            desktop = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(desktop, f"JanithPlayer_{timestamp}.png")
            
            pixmap.save(filename)
            QMessageBox.information(self, "Screenshot", f"Saved to Desktop:\n{filename}")

    def toggle_always_on_top(self, checked):
        self.is_always_on_top = checked
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowStaysOnTopHint)
        self.show()

    def show_context_menu(self, pos):
        """Builds a comprehensive right-click menu over the video surface."""
        menu = QMenu(self)
        
        play_menu = menu.addMenu("▶ Playback")
        play_menu.addAction("Play / Pause (Spacebar)", self.toggle_play)
        play_menu.addAction("Stop", self.player.stop)
        play_menu.addAction("Restart Video", lambda: self.player.setPosition(0))
        play_menu.addSeparator()
        
        seek_menu = play_menu.addMenu("⏭ Arrow Key Seek Amount")
        for s in [0.5, 1.0, 2.0, 5.0, 10.0]:
            action = seek_menu.addAction(f"{s} seconds")
            action.setCheckable(True)
            action.setChecked(self.seek_step == s)
            action.triggered.connect(lambda _, val=s: self.set_seek_step(val))
            
        play_menu.addSeparator()
        play_menu.addAction("⏩ Skip Forward", lambda: self.skip_video(self.seek_step))
        play_menu.addAction("⏪ Skip Backward", lambda: self.skip_video(-self.seek_step))
        
        speed_menu = play_menu.addMenu("⏱ Playback Speed")
        for s in [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
            speed_menu.addAction(f"{s}x").triggered.connect(lambda _, v=s: self.player.setPlaybackRate(v))

        audio_menu = menu.addMenu("🔊 Audio Settings")
        audio_menu.addAction("Volume Up", lambda: self.vol_slider.setValue(min(100, self.vol_slider.value() + 10)))
        audio_menu.addAction("Volume Down", lambda: self.vol_slider.setValue(max(0, self.vol_slider.value() - 10)))
        audio_menu.addAction("Unmute" if self.is_muted else "Mute", self.toggle_mute)

        size_menu = menu.addMenu("📐 Video Size")
        size_menu.addAction("Fit Screen", lambda: self.video_surface.setAspectRatioMode(Qt.KeepAspectRatio))
        size_menu.addAction("Fill Screen", lambda: self.video_surface.setAspectRatioMode(Qt.KeepAspectRatioByExpanding))
        size_menu.addAction("Stretch to Fill", lambda: self.video_surface.setAspectRatioMode(Qt.IgnoreAspectRatio))

        subs_menu = menu.addMenu("📝 Subtitles")
        subs_menu.addAction("Load .srt File...", self.load_subtitles)
        subs_menu.addAction("Hide Subtitles", self.subtitle_label.hide)

        menu.addSeparator()
        top_action = menu.addAction("📌 Always on Top")
        top_action.setCheckable(True)
        top_action.setChecked(self.is_always_on_top)
        top_action.triggered.connect(self.toggle_always_on_top)
        
        loop_action = menu.addAction("🔁 Loop Video")
        loop_action.setCheckable(True)
        loop_action.setChecked(self.is_looping)
        loop_action.triggered.connect(self.toggle_loop)
        
        menu.addAction("📸 Take Screenshot", self.take_screenshot)
        menu.addSeparator()
        menu.addAction("🔲 Toggle Fullscreen", self.toggle_fullscreen)
        menu.addAction("🗑 Clear History", self.clear_history)
        menu.addAction("❌ Exit Application", self.safe_exit)

        menu.exec_(self.video_surface.mapToGlobal(pos))

    def save_current_position(self):
        if self.current_file and self.player.duration() > 0:
            data = {}
            if os.path.exists(self.db_path):
                try:
                    with open(self.db_path, 'r') as f: data = json.load(f)
                except (json.JSONDecodeError, FileNotFoundError):
                    pass
            
            data[self.current_file] = self.player.position()
            with open(self.db_path, 'w') as f: json.dump(data, f)

    def get_saved_position(self, path):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r') as f:
                    return json.load(f).get(path, 0)
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        return 0

    def clear_history(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.title_bar.show()
            self.controls_wrapper.show()
        else:
            self.showFullScreen()
            self.title_bar.hide()
            self.ui_timer.start(3000)

    def auto_hide_ui(self):
        """Hides the mouse and UI elements after a period of inactivity in fullscreen."""
        if self.isFullScreen() and self.player.playbackState() == QMediaPlayer.PlayingState:
            self.controls_wrapper.hide()
            self.setCursor(Qt.BlankCursor)

    def safe_exit(self):
        self.save_current_position()
        self.close()

    def _create_dot(self, color, func):
        btn = QPushButton()
        btn.setFixedSize(14, 14)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(f"background: {color}; border-radius: 7px; border: none; padding: 0;")
        btn.clicked.connect(func)
        return btn

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.toggle_play()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.toggle_fullscreen()
        elif event.key() == Qt.Key_Right:   # Seek Forward
            self.skip_video(self.seek_step) 
        elif event.key() == Qt.Key_Left:    # Seek Backward
            self.skip_video(-self.seek_step)
        elif event.key() == Qt.Key_Up:      # Volume Up
            new_vol = min(100, self.vol_slider.value() + 5)
            self.vol_slider.setValue(new_vol)
        elif event.key() == Qt.Key_Down:    # Volume Down
            new_vol = max(0, self.vol_slider.value() - 5)
            self.vol_slider.setValue(new_vol)
        elif event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.toggle_fullscreen()
            else:
                self.safe_exit()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, source, event):
        """Wakes up the UI and cursor when the mouse moves over the video surface."""
        if source == self.video_surface and event.type() == QEvent.Type.MouseMove:
            if self.isFullScreen():
                self.setCursor(Qt.ArrowCursor)
               
                if event.pos().y() >= self.height() - 150:
                    self.controls_wrapper.show()
                self.ui_timer.start(3000)
        return super().eventFilter(source, event)

    def mousePressEvent(self, event):
        """Initializes drag for the borderless window ONLY from the title bar."""
        if event.button() == Qt.LeftButton: 
            # Check if the click is within the title bar's area (y <= 45)
            if event.pos().y() <= self.title_bar.height() and not self.isFullScreen():
                self.drag_pos = event.globalPosition().toPoint()
            else:
                self.drag_pos = None # Prevent dragging from the video area

    def mouseMoveEvent(self, event):
        """Handles frameless window dragging logic."""
        if not self.isFullScreen() and getattr(self, 'drag_pos', None):
            diff = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + diff)
            self.drag_pos = event.globalPosition().toPoint()
            
        if self.isFullScreen():
            self.setCursor(Qt.ArrowCursor)
            if getattr(event, 'pos', None) and event.pos().y() >= self.height() - 150:
                self.controls_wrapper.show()
            self.ui_timer.start(3000)

    def mouseReleaseEvent(self, event):
        """Clears the drag position when the mouse button is released."""
        if event.button() == Qt.LeftButton:
            self.drag_pos = None

    def resizeEvent(self, event):
        """Keeps overlays dynamically centered/scaled on window resize."""
        self.screen_logo.setGeometry(0, 0, self.video_surface.width(), self.video_surface.height())
        
        if hasattr(self, 'subtitle_label'):
            sub_w = self.video_surface.width() - 40
            self.subtitle_label.setGeometry(20, self.video_surface.height() - 150, sub_w, 100)

        if hasattr(self, 'glass_bg') and hasattr(self, 'controls'):
            self.glass_bg.setGeometry(0, 0, self.width(), 120)
            self.controls.setGeometry(0, 0, self.width(), 120)
            
        super().resizeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    player_app = JanithPlayer()
    player_app.show()
    sys.exit(app.exec())