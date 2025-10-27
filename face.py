#!/usr/bin/env python3
import sys, time, platform, random, signal, os, socket
from PySide6.QtCore import Qt, QTimer, QPointF, QRect
from PySide6.QtGui import (
    QGuiApplication, QPainter, QBrush, QPen, QColor, QScreen, QFont,
    QKeyEvent, QMouseEvent
)
from PySide6.QtWidgets import QApplication, QWidget, QLineEdit, QStyle

# =========================
#     DEBUG CONTROL
# =========================
DEBUG = os.environ.get("PHOTON_DEBUG", "0") == "1"

def dprint(msg: str, prefix="[face]"):
    """Unified debug print with timestamp"""
    if DEBUG:
        timestamp = time.strftime("%H:%M:%S")
        print(f"{timestamp} {prefix} {msg}", flush=True)

dprint(f"Process started (PID {os.getpid()})")
dprint(f"Python: {sys.executable}")
dprint(f"Debug mode: {DEBUG}")

# ---------- CONFIG ----------
BLINK_DURATION_SEC = 0.20
LINE_W = 3
FACE_COLOR   = QColor("#FDFD96")
SCLERA_COLOR = QColor("white")
PUPIL_COLOR  = QColor("black")
NOSE_COLOR   = QColor("black")
MOUTH_COLOR  = QColor("black")

TARGET_SIZE_INCH = 1.25
MARGIN_RATIO = 0.02

# Layout ratios
EYE_H_OFFSET   = 0.42
EYE_X_OFFSET   = 0.40
SCLERA_W_R     = 0.26
SCLERA_H_R     = 0.33
PUPIL_R_R      = 0.09
NOSE_SIZE_R    = 0.06
MOUTH_Y_OFFSET = 0.32
MOUTH_WIDTH_R  = 0.50

# Positioning options
USE_WORKAREA   = True
REPIN_EVERY_MS = 1000
DEBUG_POS      = False

# Input layout knobs
INPUT_WIDTH_SCALE  = 2.20
INPUT_MIN_WIDTH    = 200
INPUT_HEIGHT_SCALE = 0.28
INPUT_MIN_HEIGHT   = 46
INPUT_SHIFT_PX     = 0

WINDOW_SIDE_PADDING = 16

# =========================
#   IMPROVED IPC SYSTEM
# =========================
PHOTON_IPC_ENV = "PHOTON_IPC"
_IPC_KIND = None
_IPC_ADDR = None
_IPC_SEND_COUNT = 0

def _parse_ipc_env():
    """Parse PHOTON_IPC environment variable with validation"""
    spec = os.environ.get(PHOTON_IPC_ENV, "").strip()
    dprint(f"Reading {PHOTON_IPC_ENV}='{spec}'", "[ipc]")
    
    if not spec:
        error = f"{PHOTON_IPC_ENV} environment variable not set"
        dprint(f"✗ {error}", "[ipc]")
        raise RuntimeError(error)
    
    if spec.startswith("unix://"):
        path = spec[len("unix://"):]
        if not path:
            raise RuntimeError("Empty UNIX socket path")
        dprint(f"✓ Using UNIX socket: {path}", "[ipc]")
        # Check if path exists
        if not os.path.exists(path):
            dprint(f"⚠ Warning: Socket path doesn't exist yet: {path}", "[ipc]")
        return "unix", path
        
    if spec.startswith("udp://"):
        host_port = spec[len("udp://"):]
        try:
            host, port_s = host_port.rsplit(":", 1)
            port = int(port_s)
            if port <= 0 or port > 65535:
                raise ValueError("Port out of range")
            dprint(f"✓ Using UDP socket: {host}:{port}", "[ipc]")
            return "udp", (host, port)
        except Exception as e:
            raise RuntimeError(f"Invalid UDP address '{host_port}': {e}")
    
    error = f"Invalid {PHOTON_IPC_ENV} format: '{spec}' (expected unix://path or udp://host:port)"
    dprint(f"✗ {error}", "[ipc]")
    raise RuntimeError(error)

def _ensure_ipc_parsed():
    """Lazy initialization with error handling"""
    global _IPC_KIND, _IPC_ADDR
    if _IPC_KIND is None:
        try:
            _IPC_KIND, _IPC_ADDR = _parse_ipc_env()
            dprint(f"IPC initialized: type={_IPC_KIND}", "[ipc]")
        except Exception as e:
            dprint(f"✗ IPC initialization failed: {e}", "[ipc]")
            raise

def send_ipc(msg: str):
    """Send message to today2.py with comprehensive error handling and retry"""
    global _IPC_SEND_COUNT
    _IPC_SEND_COUNT += 1
    
    dprint(f"→ Sending #{_IPC_SEND_COUNT}: {msg[:80]}", "[ipc]")
    
    try:
        _ensure_ipc_parsed()
    except Exception as e:
        dprint(f"✗ IPC not initialized: {e}", "[ipc]")
        return
    
    # Encode message
    try:
        data = msg.encode("utf-8")
        dprint(f"Encoded {len(data)} bytes", "[ipc]")
    except Exception as e:
        dprint(f"✗ Encoding failed: {e}", "[ipc]")
        return
    
    # Send with retries
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if _IPC_KIND == "unix":
                dprint(f"Attempt {attempt+1}/{max_retries}: UNIX socket", "[ipc]")
                s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                s.settimeout(1.0)
                s.connect(_IPC_ADDR)
                s.send(data)
                s.close()
                dprint(f"✓ Sent via UNIX (attempt {attempt+1})", "[ipc]")
                return
                
            else:  # UDP
                dprint(f"Attempt {attempt+1}/{max_retries}: UDP socket", "[ipc]")
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(1.0)
                sent_bytes = s.sendto(data, _IPC_ADDR)
                s.close()
                dprint(f"✓ Sent {sent_bytes} bytes via UDP (attempt {attempt+1})", "[ipc]")
                return
                
        except socket.timeout:
            dprint(f"⚠ Attempt {attempt+1} timeout", "[ipc]")
            if attempt < max_retries - 1:
                time.sleep(0.1)
            else:
                dprint(f"✗ All {max_retries} attempts timed out", "[ipc]")
                
        except Exception as e:
            dprint(f"⚠ Attempt {attempt+1} failed: {e}", "[ipc]")
            if attempt < max_retries - 1:
                time.sleep(0.1)
            else:
                dprint(f"✗ All {max_retries} attempts failed: {e}", "[ipc]")

# =========================
#    TEXT INPUT WIDGET
# =========================
class SubmitLine(QLineEdit):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        dprint("Initializing text input widget", "[input]")
        
        self.setFocusPolicy(Qt.StrongFocus)
        self.setPlaceholderText("type then press Enter")

        self.setLayoutDirection(Qt.LeftToRight)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setClearButtonEnabled(False)

        # Text margins
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

        # Connect signals
        self.returnPressed.connect(self._on_enter)
        self.textChanged.connect(self._maybe_scroll_tail)
        
        self._last_text = ""
        self._key_count = 0
        
        dprint("✓ Text input widget initialized", "[input]")

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
        
        # Log text changes
        current_text = self.text()
        if current_text != self._last_text:
            dprint(f"Text changed: '{current_text}' (length={len(current_text)})", "[input]")
            self._last_text = current_text

    def showEvent(self, e):
        dprint("Widget show event", "[input]")
        super().showEvent(e)
        QTimer.singleShot(0, self._maybe_scroll_tail)

    def resizeEvent(self, e):
        dprint(f"Widget resize: {e.size().width()}x{e.size().height()}", "[input]")
        super().resizeEvent(e)
        self._maybe_scroll_tail()

    def mousePressEvent(self, e: QMouseEvent):
        dprint(f"Mouse click at ({e.x()}, {e.y()})", "[input]")
        
        # Raise window
        win = self.window()
        if win:
            try:
                win.raise_()
                win.activateWindow()
                dprint("Window raised and activated", "[input]")
            except Exception as ex:
                dprint(f"Failed to raise window: {ex}", "[input]")
        
        # Set focus if needed
        if not self.hasFocus():
            dprint("Setting focus → TYPING=1", "[input]")
            self.setFocus(Qt.MouseFocusReason)
            send_ipc("TYPING\t1")
        else:
            dprint("Already has focus", "[input]")
        
        super().mousePressEvent(e)
        QTimer.singleShot(0, self._maybe_scroll_tail)

    def focusInEvent(self, e):
        dprint(f"Focus in (reason={e.reason()})", "[input]")
        send_ipc("TYPING\t1")
        super().focusInEvent(e)
        self._maybe_scroll_tail()

    def focusOutEvent(self, e):
        dprint(f"Focus out (reason={e.reason()})", "[input]")
        send_ipc("TYPING\t0")
        super().focusOutEvent(e)

    def keyPressEvent(self, e: QKeyEvent):
        self._key_count += 1
        key_name = e.text() if e.text() else f"<{e.key()}>"
        dprint(f"Key #{self._key_count}: {key_name}", "[input]")
        
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            dprint("ENTER key pressed → submitting", "[input]")
            self._on_enter()
            return
            
        if e.key() == Qt.Key_Escape:
            dprint("ESCAPE key pressed → clearing", "[input]")
            self.clear()
            self.clearFocus()
            send_ipc("TYPING\t0")
            return
        
        super().keyPressEvent(e)
        self._maybe_scroll_tail()

    def _on_enter(self):
        text = self.text().strip()
        dprint("=" * 50, "[input]")
        dprint(f"SUBMIT triggered!", "[input]")
        dprint(f"Text: '{text}'", "[input]")
        dprint(f"Length: {len(text)}", "[input]")
        dprint("=" * 50, "[input]")
        
        # Always send TYPING=0 first
        send_ipc("TYPING\t0")
        
        if text:
            # Send the actual text
            send_ipc(f"SUBMIT\t{text}")
            dprint(f"✓ Submitted: '{text}'", "[input]")
            self.clear()
        else:
            dprint("⚠ Empty text, not submitting", "[input]")
        
        self.clearFocus()
        dprint("Focus cleared", "[input]")

# =========================
#    FACE OVERLAY
# =========================
class FaceOverlay(QWidget):
    def __init__(self):
        super().__init__()
        dprint("Initializing face overlay window", "[overlay]")

        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        dprint(f"Window flags set: {flags}", "[overlay]")

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)

        # Blink timing
        t0 = time.perf_counter()
        self._last_blink_reset = t0
        self._next_blink_period = self._new_blink_period()

        # Frame timer (~60 FPS)
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._tick_frame)
        self._frame_timer.start(1000 // 60)
        dprint("Frame timer started (60 FPS)", "[overlay]")

        # Repin timer
        if REPIN_EVERY_MS > 0:
            self._repin_timer = QTimer(self)
            self._repin_timer.timeout.connect(self._pin_top_right)
            self._repin_timer.start(REPIN_EVERY_MS)
            dprint(f"Repin timer started ({REPIN_EVERY_MS}ms)", "[overlay]")
        else:
            self._repin_timer = None

        self._screen: QScreen | None = None
        self._frame_count = 0

        # Create text input
        self.input = SubmitLine(self)
        self._resize_to_screen()
        
        dprint("✓ Face overlay initialized", "[overlay]")

    def _new_blink_period(self) -> float:
        return random.uniform(2.0, 6.0)

    def _eye_scale(self, t_now: float) -> float:
        elapsed = t_now - self._last_blink_reset
        if elapsed > self._next_blink_period:
            self._last_blink_reset = t_now
            self._next_blink_period = self._new_blink_period()
            elapsed = 0.0
        if elapsed > BLINK_DURATION_SEC:
            return 1.0
        prog = elapsed / BLINK_DURATION_SEC
        s = 1.0 - 2.0*prog if prog <= 0.5 else 2.0*(prog - 0.5)
        return max(s, 0.06)

    def _tick_frame(self):
        self._frame_count += 1
        self.raise_()
        self.update()
        
        # Log every 300 frames (~5 seconds)
        if DEBUG and self._frame_count % 300 == 0:
            dprint(f"Frame {self._frame_count}, input focus={self.input.hasFocus()}", "[overlay]")

    def _current_screen(self) -> QScreen:
        h = self.windowHandle()
        return (h.screen() if h and h.screen() else QGuiApplication.primaryScreen())

    def _logical_dpi(self) -> float:
        s = self._current_screen()
        dpi = (s.logicalDotsPerInch() if s else 96.0) or 96.0
        return dpi

    def _pixel_margin(self) -> int:
        s = self._current_screen()
        geo = (s.availableGeometry() if s else None) if USE_WORKAREA else (s.geometry() if s else None)
        base = min(geo.width(), geo.height()) if geo else 1000
        return max(int(MARGIN_RATIO * base), 8)

    def _resize_to_screen(self):
        """Calculate window size"""
        px = int(round(TARGET_SIZE_INCH * self._logical_dpi()))
        face_size = px

        input_w = max(INPUT_MIN_WIDTH, int(face_size * INPUT_WIDTH_SCALE))
        win_w = max(face_size, input_w + 2 * WINDOW_SIDE_PADDING)
        win_h = face_size + max(int(face_size * 0.52), 56)

        old_size = (self.width(), self.height())
        self.resize(win_w, win_h)
        dprint(f"Window resized: {old_size} → ({win_w}, {win_h})", "[overlay]")

    def _layout_rects(self):
        """Calculate face and input rectangles"""
        w, h = self.width(), self.height()

        face_size = min(w, int(h * 0.70))
        face_x = (w - face_size) // 2
        face_rect = QRect(face_x, 0, face_size, face_size)

        input_h = max(INPUT_MIN_HEIGHT, int(face_size * INPUT_HEIGHT_SCALE))
        input_w = max(INPUT_MIN_WIDTH, int(face_size * INPUT_WIDTH_SCALE))

        x = (w - input_w) // 2 + INPUT_SHIFT_PX
        y = face_rect.bottom() + 8

        s = self._current_screen()
        geo = (s.availableGeometry() if s else None) if USE_WORKAREA else (s.geometry() if s else None)
        if geo:
            x = min(x, geo.x() + geo.width() - input_w - self._pixel_margin())

        input_rect = QRect(x, y, input_w, input_h)
        return face_rect, input_rect

    def _pin_top_right(self):
        """Pin window to top-right corner"""
        s = self._current_screen()
        geo = (s.availableGeometry() if s else None) if USE_WORKAREA else (s.geometry() if s else None)
        if not geo:
            return
        
        m = self._pixel_margin()
        w, h = self.width(), self.height()
        x = geo.x() + geo.width() - w - m
        y = geo.y() + m
        x = max(geo.x(), min(x, geo.x() + geo.width()  - w))
        y = max(geo.y(), min(y, geo.y() + geo.height() - h))
        
        if (self.x(), self.y()) != (x, y):
            if DEBUG_POS or (DEBUG and self._frame_count < 10):
                dprint(f"Moving window: ({self.x()}, {self.y()}) → ({x}, {y})", "[overlay]")
            self.move(x, y)
        
        _, input_rect = self._layout_rects()
        if self.input.geometry() != input_rect:
            self.input.setGeometry(input_rect)

    def _hook_screen_signals(self, s: QScreen | None):
        """Connect screen geometry change signals"""
        if hasattr(self, "_screen") and self._screen is not None:
            for sig in ("geometryChanged", "availableGeometryChanged"):
                try:
                    getattr(self._screen, sig).disconnect(self._on_screen_geo_changed)
                except Exception:
                    pass
        self._screen = s
        if s is not None:
            try:
                s.geometryChanged.connect(self._on_screen_geo_changed)
            except Exception:
                pass
            try:
                s.availableGeometryChanged.connect(self._on_screen_geo_changed)
            except Exception:
                pass

    def _on_screen_geo_changed(self, *args):
        dprint("Screen geometry changed", "[overlay]")
        self._resize_to_screen()
        self._pin_top_right()

    def showEvent(self, e):
        dprint("Window show event", "[overlay]")
        super().showEvent(e)
        h = self.windowHandle()
        if h:
            h.screenChanged.connect(self._on_screen_changed)
            self._hook_screen_signals(h.screen())
            screen = h.screen()
            if screen:
                geo = screen.geometry()
                dprint(f"Screen: {geo.width()}x{geo.height()}", "[overlay]")
        QTimer.singleShot(0, self._after_show_pin)

    def _after_show_pin(self):
        self._resize_to_screen()
        self._pin_top_right()
        dprint(f"✓ Window visible at ({self.x()}, {self.y()})", "[overlay]")
        dprint(f"Window size: {self.width()}x{self.height()}", "[overlay]")
        dprint(f"Input geometry: {self.input.geometry()}", "[overlay]")

    def _on_screen_changed(self, screen):
        dprint(f"Screen changed: {screen}", "[overlay]")
        self._hook_screen_signals(screen)
        self._resize_to_screen()
        self._pin_top_right()

    def paintEvent(self, event):
        """Draw the face"""
        face_rect, _ = self._layout_rects()
        w = face_rect.width()
        h = face_rect.height()
        t_now = time.perf_counter()
        blink_s = self._eye_scale(t_now)

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
        sclera_h = max(sclera_h_open * blink_s, 1.0)

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(SCLERA_COLOR))
        p.drawEllipse(QPointF(cx - eye_dx, eye_y), sclera_w, sclera_h)
        p.drawEllipse(QPointF(cx + eye_dx, eye_y), sclera_w, sclera_h)

        base_pupil_r = radius * PUPIL_R_R
        pupil_r = min(base_pupil_r, max(sclera_h * 0.8, 0.5))
        p.setBrush(QBrush(PUPIL_COLOR))
        p.drawEllipse(QPointF(cx - eye_dx, eye_y), pupil_r, pupil_r)
        p.drawEllipse(QPointF(cx + eye_dx, eye_y), pupil_r, pupil_r)

        # Highlights
        highlight_r = max(pupil_r * 0.35, 0.6)
        p.setBrush(QBrush(QColor(255, 255, 255, 180)))
        offset = pupil_r * 0.45
        p.drawEllipse(QPointF(cx - eye_dx - offset, eye_y - offset), highlight_r, highlight_r)
        p.drawEllipse(QPointF(cx + eye_dx - offset, eye_y - offset), highlight_r, highlight_r)

        # Nose
        nose_size = radius * NOSE_SIZE_R
        p.setBrush(QBrush(NOSE_COLOR))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), nose_size, nose_size)

        # Mouth
        mouth_w = radius * MOUTH_WIDTH_R
        mouth_y = cy + radius * MOUTH_Y_OFFSET
        p.setPen(QPen(MOUTH_COLOR, LINE_W))
        p.setBrush(Qt.NoBrush)
        p.drawLine(cx - mouth_w / 2, mouth_y, cx + mouth_w / 2, mouth_y)

# =========================
#        MAIN
# =========================
def main():
    dprint("=" * 60)
    dprint("Creating QApplication", "[main]")
    
    # Log Qt environment
    dprint(f"QT_QPA_PLATFORM: {os.environ.get('QT_QPA_PLATFORM', 'default')}", "[main]")
    dprint(f"XDG_SESSION_TYPE: {os.environ.get('XDG_SESSION_TYPE', 'unknown')}", "[main]")
    dprint(f"DISPLAY: {os.environ.get('DISPLAY', 'not set')}", "[main]")
    dprint(f"WAYLAND_DISPLAY: {os.environ.get('WAYLAND_DISPLAY', 'not set')}", "[main]")
    
    app = QApplication(sys.argv)
    dprint("✓ QApplication created", "[main]")
    
    def _quit(*_):
        dprint("Signal received, quitting", "[main]")
        app.quit()
    
    signal.signal(signal.SIGINT, _quit)
    signal.signal(signal.SIGTERM, _quit)
    dprint("Signal handlers installed", "[main]")

    w = FaceOverlay()
    dprint("FaceOverlay instance created", "[main]")
    
    w.show()
    dprint("✓ Window shown, entering event loop", "[main]")
    dprint("=" * 60)
    
    exit_code = app.exec()
    dprint(f"Event loop exited with code {exit_code}", "[main]")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()