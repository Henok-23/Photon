#!/usr/bin/env python3
import os
if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
    os.environ["QT_QPA_PLATFORM"] = "xcb"

import sys, time, platform, random, signal, socket, subprocess, json, pathlib
from PySide6.QtCore import Qt, QTimer, QPointF, QRect, QSize
from PySide6.QtGui import (
    QGuiApplication, QPainter, QBrush, QPen, QColor, QScreen, QFont,
    QKeyEvent, QMouseEvent, QPixmap, QIcon
)
from PySide6.QtWidgets import QApplication, QWidget, QLineEdit, QStyle, QPushButton

# Default IPC socket
if "PHOTON_IPC" not in os.environ or not os.environ["PHOTON_IPC"].strip():
    os.environ["PHOTON_IPC"] = "unix:///tmp/photon"


# ---------- CONFIG ----------
BLINK_CLOSE_SEC = 1   # time to close eyes
BLINK_HOLD_SEC  = 6   # time eyes stay closed
BLINK_OPEN_SEC  = 1  # time to open eyes


BLINK_DURATION_SEC = 1
LINE_W = 3
FACE_COLOR   = QColor("#FDFD96")
SCLERA_COLOR = QColor("white")
PUPIL_COLOR  = QColor("black")
NOSE_COLOR   = QColor("black")
MOUTH_COLOR  = QColor("black")

TARGET_SIZE_INCH = .75
MARGIN_RATIO = 0.02

EYE_H_OFFSET   = 0.42
EYE_X_OFFSET   = 0.40
SCLERA_W_R     = 0.26
SCLERA_H_R     = 0.23
PUPIL_R_R      = 0.09
NOSE_SIZE_R    = 0.06
MOUTH_Y_OFFSET = 0.32
MOUTH_WIDTH_R  = 0.50

USE_WORKAREA   = True
REPIN_EVERY_MS = 5000

INPUT_WIDTH_SCALE  = 2.20
INPUT_MIN_WIDTH    = 270
INPUT_HEIGHT_SCALE = 0.28
INPUT_MIN_HEIGHT   = 35
INPUT_SHIFT_PX     = 0

WINDOW_SIDE_PADDING = 16

FACE_OPACITY_NORMAL = 1.0
FACE_OPACITY_HIDDEN = 0.35

EMAIL_APP_PATH = "em.py"

STATE_FILE = pathlib.Path.home() / ".photon_face_state.json"

IDLE_TIMEOUT_SEC = 30


def save_state(email_ever_opened: bool, position: tuple):
    try:
        state = {
            "email_ever_opened": email_ever_opened,
            "position": position
        }
        STATE_FILE.write_text(json.dumps(state))
    except:
        pass


def load_state():
    try:
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
            return state.get("email_ever_opened", False), state.get("position", None)
    except:
        pass
    return False, None


# ---------- IPC (STRICT) ----------
PHOTON_IPC_ENV = "PHOTON_IPC"
_IPC_KIND = None
_IPC_ADDR = None


def _parse_ipc_env():
    spec = os.environ.get(PHOTON_IPC_ENV, "").strip()
    if spec.startswith("unix://"):
        return "unix", spec[len("unix://"):]
    if spec.startswith("udp://"):
        host_port = spec[len("udp://"):]
        host, port_s = host_port.rsplit(":", 1)
        return "udp", (host, int(port_s))
    return None, None


def _ensure_ipc_parsed():
    global _IPC_KIND, _IPC_ADDR
    if _IPC_KIND is None:
        _IPC_KIND, _IPC_ADDR = _parse_ipc_env()


def send_ipc(msg: str):
    try:
        _ensure_ipc_parsed()
        if _IPC_KIND == "unix":
            s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            s.connect(_IPC_ADDR)
            s.send(msg.encode("utf-8"))
            s.close()
        elif _IPC_KIND == "udp":
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(msg.encode("utf-8"), _IPC_ADDR)
            s.close()
    except:
        pass


# ---------- Right-aligned input behavior ----------
class SubmitLine(QLineEdit):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setPlaceholderText("type then press Enter")

        self.setLayoutDirection(Qt.LeftToRight)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setClearButtonEnabled(False)

        INNER = 16
        self.setTextMargins(INNER, 0, INNER, 0)

        self.setStyleSheet("""
            QLineEdit {
                background: white;
                color: black;
                border: 1px solid rgba(0,0,0,0.25);
                border-radius: 10px;
            }
            QLineEdit:placeholder { color: rgba(0,0,0,0.45); }
        """)
        f = QFont()
        f.setPointSize(12)
        self.setFont(f)

        self.returnPressed.connect(self._on_enter)
        self.textChanged.connect(self._maybe_scroll_tail)

    def _visible_text_width_px(self) -> int:
        m = self.textMargins()
        l, r = m.left(), m.right()
        fw = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth, None, self)
        return max(0, self.width() - (l + r) - 2 * fw)

    def _text_width_px(self) -> int:
        return self.fontMetrics().horizontalAdvance(self.text())

    def _maybe_scroll_tail(self):
        if self._text_width_px() > self._visible_text_width_px() - 2:
            self.setCursorPosition(len(self.text()))
        else:
            self.setCursorPosition(self.cursorPosition())

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._maybe_scroll_tail)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._maybe_scroll_tail()

    def focusInEvent(self, e):
        send_ipc("TYPING\t1")
        win = self.window()
        if win and hasattr(win, '_mark_interaction'):
            win._mark_interaction()
        super().focusInEvent(e)
        self._maybe_scroll_tail()

    def focusOutEvent(self, e):
        send_ipc("TYPING\t0")
        super().focusOutEvent(e)

    def keyPressEvent(self, e: QKeyEvent):
        win = self.window()
        if win and hasattr(win, '_mark_interaction'):
            win._mark_interaction()

        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._on_enter()
            return  # ← Add return here so it doesn't continue
        if e.key() == Qt.Key_Escape:
            self.clear()
            self.clearFocus()
            send_ipc("TYPING\t0")
            return
        super().keyPressEvent(e)
        self._maybe_scroll_tail()

    def _on_enter(self):
        text = self.text().strip()
        send_ipc("TYPING\t0")

        if text.lower() == "email":
            win = self.window()
            if hasattr(win, '_handle_email_command'):
                win._handle_email_command()
            self.clear()
            self.clearFocus()
            return
                # Handle "install X" command
        text_lower = text.lower()
        if text_lower.startswith("install "):
            app_name = text[8:].strip()  # Get everything after "install "
            if app_name:
                try:
                    # Get the directory where face.py is located
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    install_script = os.path.join(script_dir, "install.py")
                    subprocess.Popen(
                        ["python3", install_script, app_name],
                        cwd=script_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )   
                except Exception as e:
                    print(f"[face] Install error: {e}")
                self.clear()
                self.clearFocus()
                return

        if text:
            send_ipc(f"SUBMIT\t{text}")
            self.clear()
        self.clearFocus()
    def mousePressEvent(self, e: QMouseEvent):
        win = self.window()
        
        # Wake up if sleeping
        if win and hasattr(win, 'is_sleeping') and win.is_sleeping:
            win.is_sleeping = False
            if hasattr(win, '_set_opacity'):
                win._set_opacity(FACE_OPACITY_NORMAL)
            if hasattr(win, '_mark_interaction'):
                win._mark_interaction()
            # Don't return here - let the click also focus the textbox
        
        # Mark interaction
        if win and hasattr(win, '_mark_interaction'):
            win._mark_interaction()
        
        # Raise window
        if win:
            try:
                win.raise_()
                win.activateWindow()
            except:
                pass
        
        # Always call parent FIRST to allow normal text input behavior
        super().mousePressEvent(e)
        
        # Then focus if needed
        if not self.hasFocus():
            self.setFocus(Qt.MouseFocusReason)
            send_ipc("TYPING\t1")
        
        QTimer.singleShot(0, self._maybe_scroll_tail)



# ---------- Gmail Button ----------
class GmailButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.PointingHandCursor)

        self.setText("📧")

        font = QFont()
        font.setPointSize(16)
        self.setFont(font)

        self.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid rgba(0,0,0,0.15);
                border-radius: 16px;
            }
            QPushButton:hover {
                background: rgba(220, 220, 220, 1);
                border: 1px solid rgba(0,0,0,0.3);
            }
            QPushButton:pressed {
                background: rgba(200, 200, 200, 1);
            }
        """)

        self.setToolTip("Open Email")


# ---------- Simple Email Input Widget ----------
class SimpleEmailInput(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        from PySide6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Type reply and press Enter")
        self.input_box.setFocusPolicy(Qt.StrongFocus)

        self.input_box.setStyleSheet("""
            QLineEdit {
                background: white;
                color: black;
                border: 2px solid #4CAF50;
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: 500;
            }
            QLineEdit:focus {
                border: 2px solid #2196F3;
                outline: none;
            }
        """)

        self.input_box.returnPressed.connect(self.on_submit)
        layout.addWidget(self.input_box)
        self.setLayout(layout)
        self.setFixedSize(400, 46)

    def on_submit(self):
        text = self.input_box.text().strip()
        if text:
            send_ipc(f"SUBMIT\t{text}")
            self.input_box.clear()

    def mousePressEvent(self, event):
        self.input_box.setFocus(Qt.MouseFocusReason)
        self.raise_()
        self.activateWindow()
        super().mousePressEvent(event)


# ---------- Overlay ----------
class FaceOverlay(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)

        # tracking for dragging
        self.drag_position = None

        # state vars
        self.move(9999, 50)
        self.email_app_process = None
        self.email_app_open = False

        saved_email_ever_opened, saved_position = load_state()
        self.email_ever_opened = saved_email_ever_opened

        self.email_input_window = None
        self.button_window = None

        self.is_sleeping = False
        self.target_opacity = FACE_OPACITY_NORMAL
        self.setWindowOpacity(self.target_opacity)

        self.idle_timeout_sec = IDLE_TIMEOUT_SEC
        self.last_interaction_time = time.perf_counter()

        self.idle_check_timer = QTimer(self)
        self.idle_check_timer.timeout.connect(self._check_idle)
        self.idle_check_timer.start(1000)

        self.original_pos = None
        self.original_y = None
        self.saved_email_position = saved_position

        t0 = time.perf_counter()
        self._last_blink_reset = t0
        self._next_blink_period = self._new_blink_period()

        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._tick_frame)
        self._frame_timer.start(1000 // 60)

        if REPIN_EVERY_MS > 0:
            self._repin_timer = QTimer(self)
            self._repin_timer.timeout.connect(self._pin_top_right)
            self._repin_timer.start(REPIN_EVERY_MS)
        else:
            self._repin_timer = None

        self._screen: QScreen | None = None

        self.input = SubmitLine(self)
        self.gmail_button = GmailButton(self)
        self.gmail_button.clicked.connect(self._handle_email_button_click)

        self._resize_to_screen()
        self._initial_position()

        self.email_check_timer = QTimer(self)
        self.email_check_timer.timeout.connect(self._check_email_app_status)
        self.email_check_timer.start(1000)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = None
            event.accept()
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_position is not None and not self.is_sleeping and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_position
            self.move(new_pos)
            self._update_layout()
            event.accept()
        super().mouseMoveEvent(event)


    def mousePressEvent(self, event):
        # Only allow drag when awake
        if event.button() == Qt.LeftButton:
            if not self.is_sleeping:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

        # Wake up if sleeping
        if not self.email_app_open:
            self._mark_interaction()

            if self.is_sleeping:
                self.is_sleeping = False
                self._set_opacity(FACE_OPACITY_NORMAL)

        super().mousePressEvent(event)

    def _initial_position(self):
        if self.email_ever_opened and self.saved_email_position:
            x, y = self.saved_email_position
            self.move(x, y)
            self.setGeometry(x, y, self.width(), self.height())
            self._restored_position = True
        else:
            self._pin_top_right()
        self._update_layout()

    def _mark_interaction(self):
        self.last_interaction_time = time.perf_counter()

        if self.is_sleeping:
            self.is_sleeping = False
            self._set_opacity(FACE_OPACITY_NORMAL)

    def _check_idle(self):
        if self.email_app_open:
            return

        elapsed = time.perf_counter() - self.last_interaction_time
        if elapsed >= self.idle_timeout_sec and not self.is_sleeping:
            self.is_sleeping = True
            self._set_opacity(FACE_OPACITY_HIDDEN)

    def _handle_email_command(self):
        self._mark_interaction()
        if self.is_sleeping:
            self.is_sleeping = False
            self._set_opacity(FACE_OPACITY_NORMAL)
        else:
            self._open_email_app()

    def _handle_email_button_click(self):
        self._mark_interaction()
        if self.is_sleeping:
            self.is_sleeping = False
            self._set_opacity(FACE_OPACITY_NORMAL)
        else:
            self._open_email_app()

    def _bring_face_front(self):
        try:
            self.raise_()
            self.activateWindow()
        except:
            pass

    def _open_email_app(self):
        self._mark_interaction()

        if self.email_app_process is None or self.email_app_process.poll() is not None:
            try:
                if self._repin_timer:
                    self._repin_timer.stop()
                    self._repin_timer = None

                if self.original_pos is None:
                    self.original_pos = self.pos()
                    self.original_y = self.y()

                s = self._current_screen()
                geo = s.availableGeometry() if s and USE_WORKAREA else (s.geometry() if s else None)
                if not geo:
                    return

                margin = self._pixel_margin()

                email_w = 700
                email_h = 800

                face_rect, _, _ = self._layout_rects()
                face_size = face_rect.width()
                face_offset_x = face_rect.x()

                start_y = geo.y() + margin + 50

                email_x = geo.x() + geo.width() - email_w - margin
                email_center_x = email_x + email_w // 2

                face_window_x = email_center_x - face_offset_x - face_size // 2
                face_y = start_y

                email_y = face_y + face_size - 55

                self.move(face_window_x, face_y)

                # ⛔ HIDE TEXTBOX + GMAIL BUTTON
                self.input.hide()
                self.gmail_button.hide()

                input_w = 400
                input_h = 46
                input_x = email_x + (email_w - input_w) // 2
                input_y = email_y + email_h 

                button_x = email_x + (email_w - 32) // 2
                button_y = input_y + input_h

                self._create_email_input_window(input_x, input_y, input_w, input_h)
                self._create_button_window(button_x, button_y)

                env = os.environ.copy()
                env["EM_WINDOW_X"] = str(email_x)
                env["EM_WINDOW_Y"] = str(email_y)
                env["PHOTON_IPC"] = os.environ.get("PHOTON_IPC", "")

                self.email_app_process = subprocess.Popen(
                    ["python3", EMAIL_APP_PATH],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                self.email_app_open = True
                self.email_ever_opened = True

                current_pos = (self.x(), self.y())
                save_state(self.email_ever_opened, current_pos)

                self._set_opacity(FACE_OPACITY_NORMAL)

                # keep face above em.py
                QTimer.singleShot(300, self._bring_face_front)
                QTimer.singleShot(800, self._bring_face_front)
                QTimer.singleShot(1500, self._bring_face_front)
            except Exception as e:
                print(f"Error opening email app: {e}")

    def _create_email_input_window(self, x, y, width, height):
        if self.email_input_window:
            self.email_input_window.close()

        self.email_input_window = SimpleEmailInput()
        self.email_input_window.move(x, y)
        self.email_input_window.show()

        def set_focus():
            if self.email_input_window:
                self.email_input_window.raise_()
                self.email_input_window.activateWindow()
                self.email_input_window.input_box.setFocus(Qt.MouseFocusReason)

        QTimer.singleShot(200, set_focus)
        QTimer.singleShot(500, set_focus)

    def _create_button_window(self, x, y):
        from PySide6.QtWidgets import QVBoxLayout

        self.button_window = QWidget()
        self.button_window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.button_window.setAttribute(Qt.WA_TranslucentBackground, True)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        button = GmailButton()
        layout.addWidget(button, alignment=Qt.AlignCenter)

        self.button_window.setLayout(layout)
        self.button_window.setGeometry(x, y, 32, 32)
        self.button_window.move(x, y)
        self.button_window.show()
        self.button_window.raise_()

    def _check_email_app_status(self):
        try:
            if self.email_app_process is not None:
                poll_result = self.email_app_process.poll()

                if poll_result is not None:
                    self.email_app_open = False
                    self.email_app_process = None

                    if self.email_input_window:
                        try: self.email_input_window.close()
                        except: pass
                        self.email_input_window = None

                    if self.button_window:
                        try: self.button_window.close()
                        except: pass
                        self.button_window = None

                    # SHOW TEXTBOX + BUTTON AGAIN
                    try:
                        self.input.show()
                        self.gmail_button.show()
                    except:
                        pass

                    self.is_sleeping = True
                    self._set_opacity(FACE_OPACITY_HIDDEN)

                    s = self._current_screen()
                    geo = s.availableGeometry() if s else None
                    if geo:
                        m = self._pixel_margin()
                        w, h = self.width(), self.height()
                        x = geo.x() + geo.width() - w - m
                        y = geo.y() + m + 50
                        x = max(geo.x(), min(x, geo.x() + geo.width() - w))
                        y = max(geo.y(), min(y, geo.y() + geo.height() - h))

                        self.move(x, y)
                        self.setGeometry(x, y, w, h)
                        self._update_layout()

                    current_pos = (self.x(), self.y())
                    save_state(self.email_ever_opened, current_pos)

                    self.last_interaction_time = time.perf_counter()

                else:
                    if not self.email_app_open:
                        self.email_app_open = True
                        self._set_opacity(FACE_OPACITY_NORMAL)
        except:import os

            self.email_app_open = False
            self.email_app_process = None

    def _set_opacity(self, opacity):
        self.setWindowOpacity(opacity)
        if hasattr(self, "input"):
            self.input.setWindowOpacity(opacity)
        if hasattr(self, "gmail_button"):
            self.gmail_button.setWindowOpacity(opacity)
        if self.email_input_window:
            self.email_input_window.setWindowOpacity(opacity)
        if self.button_window:
            self.button_window.setWindowOpacity(opacity)

    def _new_blink_period(self) -> float:
        return random.uniform(9.0, 13.0)

    def _eye_scale(self, t_now: float) -> float:
        elapsed = t_now - self._last_blink_reset

        # Start a new blink cycle
        total_blink_time = BLINK_CLOSE_SEC + BLINK_HOLD_SEC + BLINK_OPEN_SEC
        if elapsed > self._next_blink_period:
            self._last_blink_reset = t_now
            self._next_blink_period = self._new_blink_period()
            elapsed = 0.0

        # --- PHASE 1: CLOSING ---
        if elapsed < BLINK_CLOSE_SEC:
            prog = elapsed / BLINK_CLOSE_SEC
            return max(1.0 - prog, 0.0)  # Changed from 0.06

        # --- PHASE 2: HOLD CLOSED ---
        if elapsed < BLINK_CLOSE_SEC + BLINK_HOLD_SEC:
            return 0.0  # Changed from 0.06

        # --- PHASE 3: OPENING ---
        elapsed -= (BLINK_CLOSE_SEC + BLINK_HOLD_SEC)
        if elapsed < BLINK_OPEN_SEC:
            prog = elapsed / BLINK_OPEN_SEC
            return max(prog, 0.0)  # Changed from 0.06

        return 1.0



    def _tick_frame(self):
        self.update()

    def _current_screen(self) -> QScreen:
        h = self.windowHandle()
        return h.screen() if h else QGuiApplication.primaryScreen()

    def _logical_dpi(self) -> float:
        s = self._current_screen()
        return (s.logicalDotsPerInch() if s else 96.0) or 96.0

    def _pixel_margin(self) -> int:
        s = self._current_screen()
        geo = s.availableGeometry() if s else None
        base = min(geo.width(), geo.height()) if geo else 1000
        return max(int(MARGIN_RATIO * base), 8)

    def _resize_to_screen(self):
        px = int(round(TARGET_SIZE_INCH * self._logical_dpi()))
        face_size = px
        input_w = max(INPUT_MIN_WIDTH, int(face_size * INPUT_WIDTH_SCALE))
        win_w = max(face_size, input_w + 2 * WINDOW_SIDE_PADDING)
        win_h = face_size + max(int(face_size * 0.52), 56) + 100  # Changed 75 to 100
        self.resize(win_w, win_h)

    def _layout_rects(self):
        w, h = self.width(), self.height()
        face_size = min(w, int(h * 0.60))
        face_x = (w - face_size) // 2
        face_rect = QRect(face_x, 0, face_size, face_size)

        input_h = max(INPUT_MIN_HEIGHT, int(face_size * INPUT_HEIGHT_SCALE))
        input_w = max(INPUT_MIN_WIDTH, int(face_size * INPUT_WIDTH_SCALE))
        x = (w - input_w) // 2 + INPUT_SHIFT_PX
        y = face_rect.bottom() + 8
        input_rect = QRect(x, y, input_w, input_h)

        button_y = input_rect.bottom() + 6
        button_x = (w - 32) // 2
        button_rect = QRect(button_x, button_y, 32, 32)

        return face_rect, input_rect, button_rect

    def _update_layout(self):
        _, input_rect, button_rect = self._layout_rects()
        self.input.setGeometry(input_rect)
        self.gmail_button.setGeometry(button_rect)

    def _pin_top_right(self):
        s = self._current_screen()
        geo = s.availableGeometry() if s else None
        if not geo:
            return
        m = self._pixel_margin()
        w, h = self.width(), self.height()
        x = geo.x() + geo.width() - w - m
        y = geo.y() + m + 50

        if (self.x(), self.y()) != (x, y):
            self.move(x, y)
            self.setGeometry(x, y, w, h)
            if self.original_y is None:
                self.original_y = y

        self._update_layout()

    def showEvent(self, e):
        super().showEvent(e)
        self.raise_()
        self.activateWindow()

    def paintEvent(self, event):
        face_rect, _, _ = self._layout_rects()
        w = face_rect.width()
        h = face_rect.height()
        t_now = time.perf_counter()

        blink_s = self._eye_scale(t_now) if not self.is_sleeping else 0.01

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        size = min(w, h)
        cx = face_rect.x() + w / 2.0
        cy = face_rect.y() + h / 2.0
        radius = size * 0.48

        # Face
        p.setBrush(QBrush(FACE_COLOR))
        p.setPen(QPen(Qt.black, LINE_W))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Eyes
        eye_y = cy - radius * EYE_H_OFFSET
        eye_dx = radius * EYE_X_OFFSET
        sclera_w = radius * SCLERA_W_R
        sclera_h_open = radius * SCLERA_H_R
        sclera_h = sclera_h_open * blink_s

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(SCLERA_COLOR))
        p.drawEllipse(QPointF(cx - eye_dx, eye_y), sclera_w, sclera_h)
        p.drawEllipse(QPointF(cx + eye_dx, eye_y), sclera_w, sclera_h)

        base_pupil_r = radius * PUPIL_R_R
        pupil_r = min(base_pupil_r, max(sclera_h * 0.8, 0.5))
        p.setBrush(QBrush(PUPIL_COLOR))
        p.drawEllipse(QPointF(cx - eye_dx, eye_y), pupil_r, pupil_r)
        p.drawEllipse(QPointF(cx + eye_dx, eye_y), pupil_r, pupil_r)

        if sclera_h > 5:
            highlight_r = max(pupil_r * 0.35, 0.6)
            p.setBrush(QBrush(QColor(255, 255, 255, 180)))
            offset = pupil_r * 0.45
            p.drawEllipse(QPointF(cx - eye_dx - offset, eye_y - offset), highlight_r, highlight_r)
            p.drawEllipse(QPointF(cx + eye_dx - offset, eye_y - offset), highlight_r, highlight_r)

        # Nose
        nose_size = radius * NOSE_SIZE_R
        p.setBrush(QBrush(NOSE_COLOR))
        p.drawEllipse(QPointF(cx, cy), nose_size, nose_size)

        # Mouth
        mouth_w = radius * MOUTH_WIDTH_R
        mouth_y = cy + radius * MOUTH_Y_OFFSET
        p.setPen(QPen(MOUTH_COLOR, LINE_W))
        p.drawLine(cx - mouth_w / 2, mouth_y, cx + mouth_w / 2, mouth_y)


def main():
    try:
        app = QApplication(sys.argv)

        def _quit(*_):
            app.quit()

        signal.signal(signal.SIGINT, _quit)
        signal.signal(signal.SIGTERM, _quit)

        w = FaceOverlay()
        w.show()

        sys.exit(app.exec())
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
