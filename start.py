#!/usr/bin/env python3
# start.py – Simple GUI controller for Photon
import os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import time, signal, subprocess, threading
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtGui import QPalette, QColor

# ---------- paths ----------
ENGINE_LOCAL = HERE / "today2.py"
PYTHON = str(Path(sys.executable))

# state + logs
CACHE_DIR = Path.home() / ".cache" / "photon"
PIDFILE = CACHE_DIR / "photon.pid"
LOGFILE = CACHE_DIR / "engine.log"
AUTOSTART_FLAG = CACHE_DIR / ".autostart_done"

# Detect if we're in Flatpak
IN_FLATPAK = Path("/app").exists() or "FLATPAK_ID" in os.environ

# ---------- helpers ----------
def is_running() -> bool:
    """Check if Photon engine is currently running."""
    if not PIDFILE.exists():
        return False
    try:
        pid = int(PIDFILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        try: 
            PIDFILE.unlink()
        except Exception: 
            pass
        return False

def start_engine():
    """Start the voice engine."""
    if is_running():
        print("[engine] Already running")
        return
    
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    LOGFILE.parent.mkdir(parents=True, exist_ok=True)

    # Build command
    if not ENGINE_LOCAL.exists():
        print(f"[engine] Error: {ENGINE_LOCAL} not found")
        return
    
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "xcb")
    env["PHOTON_DEBUG"] = "1"
    
    cmd = [sys.executable, str(ENGINE_LOCAL)]
    
    print(f"[engine] Starting: {' '.join(cmd)}")
    
    # Open log file in append mode
    log = open(LOGFILE, "a", buffering=1)
    
    proc = subprocess.Popen(
        cmd,
        cwd=str(HERE),
        stdout=log,
        stderr=log,
        close_fds=True,
        start_new_session=True,
        env=env,
    )
    
    PIDFILE.write_text(str(proc.pid))
    time.sleep(0.3)

    if proc.poll() is not None:
        print(f"[engine] Error: exited instantly (code {proc.returncode})")
        try: 
            PIDFILE.unlink()
        except Exception: 
            pass
    else:
        print(f"[engine] Started with PID {proc.pid}")

def stop_engine():
    """Stop the voice engine COMPLETELY."""
    print("[engine] Stopping Photon...")
    
    # 1. Kill by PID file
    if PIDFILE.exists():
        try:
            pid = int(PIDFILE.read_text().strip())
            print(f"[engine] Killing process group {pid}")
            
            # Kill entire process group
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
                print(f"[engine] Sent SIGTERM to process group {pgid}")
            except Exception:
                # Fallback to single process
                try:
                    os.kill(pid, signal.SIGTERM)
                    print(f"[engine] Sent SIGTERM to PID {pid}")
                except Exception:
                    pass

            # Wait for graceful shutdown
            for _ in range(20):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.1)
                except ProcessLookupError:
                    break
            else:
                # Force kill
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[engine] Error with PID: {e}")
        finally:
            try: 
                PIDFILE.unlink()
            except Exception: 
                pass

    # 2. Cleanup any remaining processes
    time.sleep(0.2)
    subprocess.run(["pkill", "-TERM", "-f", "today2.py"], 
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.2)
    subprocess.run(["pkill", "-TERM", "-f", "face.py"], 
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.2)
    
    # 3. Force kill any stubborn processes
    subprocess.run(["pkill", "-KILL", "-f", "today2.py"], 
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-KILL", "-f", "face.py"], 
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    time.sleep(0.3)
    
    print("[engine] Stopped")

# ---------- UI ----------
def set_button_style(btn, on: bool):
    pal = btn.palette()
    pal.setColor(QPalette.Button, QColor(70, 200, 70) if on else QColor(220, 60, 60))
    btn.setAutoFillBackground(True)
    btn.setPalette(pal)
    btn.update()

class Control(QWidget):
    def __init__(self):
        super().__init__()
        mode = "Flatpak" if IN_FLATPAK else "Host"
        self.setWindowTitle(f"Photon Control ({mode})")
        self.resize(300, 120)
        
        self.status = QLabel("")
        self.btn = QPushButton("")
        self.btn.clicked.connect(self.toggle)
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.btn)

        # AUTO-START on first run
        if not AUTOSTART_FLAG.exists():
            AUTOSTART_FLAG.parent.mkdir(parents=True, exist_ok=True)
            AUTOSTART_FLAG.touch()
            print("[engine] First run - auto-starting")
            start_engine()
            time.sleep(0.5)

        self.refresh()

    def refresh(self):
        on = is_running()
        self.status.setText(f"Engine Status: {'RUNNING' if on else 'STOPPED'}")
        self.btn.setText("Stop Photon" if on else "Start Photon")
        set_button_style(self.btn, on)

    def toggle(self):
        if is_running():
            stop_engine()
        else:
            start_engine()
        time.sleep(0.5)
        self.refresh()

# ---------- CLI ----------
def main():
    # Handle --enable flag (start engine)
    if "--enable" in sys.argv:
        start_engine()
        print("[cli] Photon started")
        return
    
    # Handle --disable flag (stop engine)
    if "--disable" in sys.argv:
        stop_engine()
        print("[cli] Photon stopped")
        return
    
    # Default: show GUI
    app = QApplication(sys.argv)
    w = Control()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()