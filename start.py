#!/usr/bin/env python3
# start.py – Photon controller with NUCLEAR stop
import os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import time, signal, subprocess
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtGui import QPalette, QColor

# ---------- paths ----------
ENGINE_LOCAL = HERE / "today2.py"

# state + logs
CACHE_DIR = Path.home() / ".cache" / "photon"
PIDFILE = CACHE_DIR / "photon.pid"
LOGFILE = CACHE_DIR / "engine.log"
FIRST_RUN_FLAG = CACHE_DIR / ".first_run_done"

# Detect if we're in Flatpak
IN_FLATPAK = Path("/app").exists() or "FLATPAK_ID" in os.environ

# ---------- helpers ----------
def is_running() -> bool:
    """Check if ANY Photon process is running."""
    # Check PID file first
    if PIDFILE.exists():
        try:
            pid = int(PIDFILE.read_text().strip())
            os.kill(pid, 0)
            return True
        except Exception:
            try: 
                PIDFILE.unlink()
            except Exception: 
                pass
    
    # Check if ANY photon process exists
    try:
        result = subprocess.run(
            ["pgrep", "-f", "today2.py"],
            capture_output=True,
            timeout=1
        )
        if result.returncode == 0:
            return True
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

    if not ENGINE_LOCAL.exists():
        print(f"[engine] Error: {ENGINE_LOCAL} not found")
        return
    
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "xcb")
    env["PHOTON_DEBUG"] = "1"
    
    cmd = [sys.executable, str(ENGINE_LOCAL)]
    
    print(f"[engine] Starting: {' '.join(cmd)}")
    
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
    time.sleep(0.5)

    if proc.poll() is not None:
        print(f"[engine] Error: exited instantly (code {proc.returncode})")
        try: 
            PIDFILE.unlink()
        except Exception: 
            pass
    else:
        print(f"[engine] ✓ Started with PID {proc.pid}")

def stop_engine():
    """NUCLEAR STOP - Kill EVERYTHING related to Photon and release audio."""
    print("[engine] ═══════════════════════════════════════")
    print("[engine] NUCLEAR STOP - Killing everything...")
    print("[engine] ═══════════════════════════════════════")
    
    # 1. Kill by PID file
    if PIDFILE.exists():
        try:
            pid = int(PIDFILE.read_text().strip())
            print(f"[engine] Killing process group {pid}")
            
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception as e:
                print(f"[engine] killpg failed: {e}")
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
        except Exception as e:
            print(f"[engine] Error with PID file: {e}")
        finally:
            try:
                PIDFILE.unlink()
            except Exception:
                pass
    
    # 2. Kill ALL Python processes running Photon scripts
    print("[engine] Killing all photon processes...")
    
    scripts_to_kill = [
        "today2.py",
        "face.py", 
        "wake.py",
        "launch.py",
        "activ.py",
    ]
    
    for script in scripts_to_kill:
        cmd = ["pkill", "-9", "-f", script]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[engine]   pkill -9 -f {script}")
    
    # 3. Kill any Python process using audio libraries
    audio_patterns = [
        "vosk",
        "pyaudio", 
        "sounddevice",
    ]
    
    for pattern in audio_patterns:
        cmd = ["pkill", "-9", "-f", pattern]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[engine]   pkill -9 -f {pattern}")
    
    time.sleep(0.3)
    
    # 4. Find and kill ANY process still holding /dev/snd (audio devices)
    print("[engine] Checking for processes holding audio devices...")
    try:
        # Find PIDs using audio devices
        result = subprocess.run(
            ["lsof", "/dev/snd/pcm*"],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines[1:]:  # Skip header
                if line.strip():
                    parts = line.split()
                    if len(parts) > 1:
                        try:
                            pid = int(parts[1])
                            # Check if it's a photon-related process
                            cmd_result = subprocess.run(
                                ["ps", "-p", str(pid), "-o", "comm="],
                                capture_output=True,
                                text=True
                            )
                            if "python" in cmd_result.stdout.lower():
                                print(f"[engine]   Killing audio-holding PID {pid}")
                                os.kill(pid, signal.SIGKILL)
                        except Exception:
                            pass
    except Exception as e:
        print(f"[engine] lsof check failed: {e}")
    
    # 5. Kill any remaining Python processes in our working directory
    print("[engine] Killing Python processes in photon directory...")
    try:
        result = subprocess.run(
            ["pgrep", "-f", str(HERE)],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid_str in pids:
                if pid_str.strip():
                    try:
                        pid = int(pid_str)
                        # Don't kill ourselves
                        if pid != os.getpid():
                            print(f"[engine]   Killing PID {pid}")
                            os.kill(pid, signal.SIGKILL)
                    except Exception:
                        pass
    except Exception:
        pass
    
    time.sleep(0.3)
    
    # 6. Force release audio - restart PulseAudio
    print("[engine] Restarting audio system...")
    
    # Try PulseAudio
    subprocess.run(
        ["pulseaudio", "--kill"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=2
    )
    time.sleep(0.3)
    subprocess.run(
        ["pulseaudio", "--start"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=2
    )
    
    # Try PipeWire (on newer systems)
    subprocess.run(
        ["systemctl", "--user", "restart", "pipewire"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=2
    )
    
    time.sleep(0.5)
    
    # 7. Final verification
    if is_running():
        print("[engine] ✗ Warning: Some processes may still be running")
    else:
        print("[engine] ✓ All processes stopped")
    
    print("[engine] ═══════════════════════════════════════")
    print("[engine] STOP COMPLETE")
    print("[engine] ═══════════════════════════════════════")

def auto_start_first_run():
    """Auto-start Photon on first run after install."""
    if FIRST_RUN_FLAG.exists():
        return False
    
    FIRST_RUN_FLAG.parent.mkdir(parents=True, exist_ok=True)
    FIRST_RUN_FLAG.touch()
    
    start_engine()
    return True

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
        self.resize(350, 180)
        
        self.status = QLabel("")
        self.btn = QPushButton("")
        self.btn.clicked.connect(self.toggle)
        
        self.info = QLabel("Tip: 'Stop' completely kills all processes and releases audio.")
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: gray; font-size: 10px;")
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.btn)
        layout.addWidget(self.info)

        # Auto-start on first run
        auto_start_first_run()
        
        self.refresh()

    def refresh(self):
        on = is_running()
        self.status.setText(f"Engine: {'RUNNING ✓' if on else 'STOPPED ✗'}")
        self.btn.setText("Stop Photon (Nuclear)" if on else "Start Photon")
        set_button_style(self.btn, on)

    def toggle(self):
        # Disable button during operation
        self.btn.setEnabled(False)
        
        if is_running():
            # Show that we're stopping
            self.status.setText("Engine: STOPPING...")
            self.btn.setText("Stopping...")
            set_button_style(self.btn, False)
            self.status.repaint()
            self.btn.repaint()
            QApplication.processEvents()
            
            stop_engine()
            
            # Wait a bit for cleanup
            time.sleep(1.0)
        else:
            # Show that we're starting
            self.status.setText("Engine: STARTING...")
            self.btn.setText("Starting...")
            set_button_style(self.btn, True)
            self.status.repaint()
            self.btn.repaint()
            QApplication.processEvents()
            
            start_engine()
            time.sleep(0.8)
        
        # Re-enable and refresh to actual state
        self.btn.setEnabled(True)
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
    
    # Handle --reset flag (clean first run flag)
    if "--reset" in sys.argv:
        try:
            FIRST_RUN_FLAG.unlink()
            print("[cli] First run flag reset")
        except Exception:
            pass
        return
    
    # Handle --status flag
    if "--status" in sys.argv:
        if is_running():
            print("[cli] Status: RUNNING")
        else:
            print("[cli] Status: STOPPED")
        return
    
    # Default: show GUI
    app = QApplication(sys.argv)
    w = Control()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()