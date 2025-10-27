#!/usr/bin/env python3
# today2.py — Production version

import os
os.environ["PHOTON_SKIP_WARM_START"] = "1"

import sys, time, queue, json, re, math, wave, difflib
from dataclasses import dataclass
from typing import Tuple, Optional, List
import threading, socket, tempfile, atexit, random, string
import subprocess

import numpy as np
import sounddevice as sd
import webrtcvad
from vosk import Model as VoskModel, KaldiRecognizer

from launch import launch_from_text
from activ import activate_async, refresh_apps_cache

# =========================
#        CONFIG
# =========================
TRIGGER_WORDS = {
    "photon","foeton","foe ton","fotoan","fo ton","photo","for don't","food on","who do"
}
FUZZY_THRESHOLD = 0.80
COOLDOWN_SEC = 1.2
POST_SESSION_REFRACTORY = 0.6

SAMPLE_RATE = 16000
BLOCK_MS = 30
BLOCK_SAMPLES = SAMPLE_RATE * BLOCK_MS // 1000
WAKE_DBFS_GATE = -50

def _find_vosk_model_dir():
    env = os.environ.get("VOSK_MODEL_DIR")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (
        os.path.join(here, "models", "vosk-model-small-en-us-0.15"),
        os.path.join(here, "vosk-model-small-en-us-0.15"),
        "/app/photon/models/vosk-model-small-en-us-0.15",
    ):
        if os.path.isdir(p):
            return p
    raise RuntimeError("Vosk model not found. Set VOSK_MODEL_DIR.")

VOSK_MODEL_DIR = _find_vosk_model_dir()
MIC_DEVICE = None

# =========================
# IMPROVED IPC SYSTEM
# =========================
PHOTON_IPC_ENV = "PHOTON_IPC"

_USER_TYPING = False
_SUBMITTED_TEXTS = queue.Queue()
_IPC_SOCK = None
_IPC_KIND = None
_IPC_ADDR = None
_IPC_THREAD_STARTED = False
_IPC_MSG_COUNT = 0

def _mk_rand(n=8):
    """Generate random string for socket names"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def _start_ipc_listener():
    """
    Start IPC listener with multiple fallback strategies:
    1. UNIX socket in XDG_RUNTIME_DIR (best)
    2. UNIX socket in /tmp (fallback)
    3. UDP on localhost (final fallback)
    """
    
    # Strategy 1: XDG_RUNTIME_DIR (preferred for Flatpak)
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir and os.path.isdir(runtime_dir):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            path = os.path.join(runtime_dir, f"photon-{os.getpid()}-{_mk_rand()}.sock")
            
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            
            s.bind(path)
            os.chmod(path, 0o600)

            def _cleanup():
                try: s.close()
                except Exception: pass
                try: os.unlink(path)
                except Exception: pass

            atexit.register(_cleanup)
            return "unix", path, s
            
        except Exception as e:
            pass
    
    # Strategy 2: /tmp fallback
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        path = os.path.join(tempfile.gettempdir(), f"photon-{os.getpid()}-{_mk_rand()}.sock")
        
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        
        s.bind(path)
        os.chmod(path, 0o600)

        def _cleanup():
            try: s.close()
            except Exception: pass
            try: os.unlink(path)
            except Exception: pass

        atexit.register(_cleanup)
        return "unix", path, s
        
    except Exception as e:
        pass
    
    # Strategy 3: UDP fallback (most compatible)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        addr = s.getsockname()

        def _cleanup():
            try: s.close()
            except Exception: pass

        atexit.register(_cleanup)
        return "udp", addr, s
        
    except Exception as e:
        raise RuntimeError(f"Could not create any IPC socket: {e}")

def _handle_ipc_msg(data: bytes):
    """Process incoming IPC messages with validation"""
    global _USER_TYPING, _IPC_MSG_COUNT
    _IPC_MSG_COUNT += 1
    
    try:
        msg = data.decode("utf-8", errors="ignore")
    except Exception as e:
        return
    
    if msg.startswith("TYPING\t"):
        parts = msg.split("\t", 1)
        if len(parts) == 2:
            new_state = (parts[1].strip() == "1")
            if new_state != _USER_TYPING:
                _USER_TYPING = new_state
            
    elif msg.startswith("SUBMIT\t"):
        parts = msg.split("\t", 1)
        if len(parts) == 2:
            payload = parts[1].strip()
            if payload:
                _SUBMITTED_TEXTS.put(payload)

def _ipc_listener():
    """Background thread for IPC socket listening"""
    sock = _IPC_SOCK
    sock.settimeout(0.5)
    
    while True:
        try:
            data, addr = sock.recvfrom(8192)
            _handle_ipc_msg(data)
        except socket.timeout:
            continue
        except Exception as e:
            break

# =========================
#   Utility helpers
# =========================
def float_to_int16(arr: np.ndarray) -> np.ndarray:
    return (arr * 32767).astype(np.int16)

def rms_dbfs(s16: np.ndarray) -> float:
    if len(s16) == 0:
        return -120.0
    rms_val = float(np.sqrt(np.mean(s16.astype(np.float64)**2)))
    if rms_val < 1e-9:
        return -120.0
    return 20 * math.log10(rms_val / 32768.0)

def drain_queue(q: queue.Queue):
    """Clear all items from the queue"""
    try:
        while True:
            q.get_nowait()
    except queue.Empty:
        pass

@dataclass
class WakeResult:
    triggered: bool
    text: str = ""
    confidence: float = 0.0

class VoskWake:
    def __init__(self, model_dir: str, rate: int):
        self.model = VoskModel(model_dir)
        self.vad = webrtcvad.Vad(3)
        self.reset(rate)

    def reset(self, rate: int):
        self.rec = KaldiRecognizer(self.model, rate)
        self.rec.SetWords(True)
        self.rec.SetPartialWords(True)

    def feed(self, s16: np.ndarray) -> WakeResult:
        chunk = s16.tobytes()
        active = self.vad.is_speech(chunk, SAMPLE_RATE)
        self.rec.AcceptWaveform(chunk)
        partial_obj = json.loads(self.rec.PartialResult())
        partial_text = partial_obj.get("partial", "").lower()
        
        if active and partial_text:
            triggered, conf = match_trigger(partial_text)
            if triggered:
                return WakeResult(triggered=True, text=partial_text, confidence=conf)
        
        return WakeResult(triggered=False)

def match_trigger(text: str) -> Tuple[bool, float]:
    """Check if text contains any trigger words with fuzzy matching"""
    words = text.strip().split()
    
    # Check single words
    for w in words:
        if w in TRIGGER_WORDS:
            return (True, 1.0)
    
    # Check bigrams
    for i in range(len(words) - 1):
        bigram = f"{words[i]} {words[i+1]}"
        if bigram in TRIGGER_WORDS:
            return (True, 1.0)
    
    # Fuzzy matching
    for w in words:
        for tw in TRIGGER_WORDS:
            ratio = difflib.SequenceMatcher(None, w, tw).ratio()
            if ratio >= FUZZY_THRESHOLD:
                return (True, ratio)
    
    return (False, 0.0)

# =========================
#  Streaming ASR
# =========================
def make_streaming_vosk_asr(rate: int, model_dir: str):
    """Create new streaming recognizer"""
    model = VoskModel(model_dir)
    rec = KaldiRecognizer(model, rate)
    rec.SetWords(True)
    return rec

class LiveSession:
    def __init__(self, recognizer, sample_rate: int, typing_fn, submitted_fn):
        self.rec = recognizer
        self.rate = sample_rate
        self.typing_fn = typing_fn
        self.submitted_fn = submitted_fn
        self.partial_buf = ""
        self.user_stopped = False
        self.timeout_at = time.monotonic() + 5.0

    def feed_and_maybe_print(self, s16: np.ndarray) -> Tuple[Optional[str], bool]:
        # Check for submission
        sub = self.submitted_fn()
        if sub:
            return (sub, False)

        # Check typing state
        if self.typing_fn():
            self.timeout_at = time.monotonic() + 5.0
            return (None, True)

        # Check timeout
        if time.monotonic() > self.timeout_at:
            self.user_stopped = True

        # Process audio
        chunk = s16.tobytes()
        accepted = self.rec.AcceptWaveform(chunk)
        
        if accepted:
            res = json.loads(self.rec.Result())
            text = res.get("text", "").strip()
            if text:
                return (text, False)
        else:
            partial = json.loads(self.rec.PartialResult())
            self.partial_buf = partial.get("partial", "")

        # Check for user stop
        if self.user_stopped:
            if self.partial_buf:
                return (self.partial_buf, False)
            return (None, False)

        return (None, True)

# =========================
#      Face overlay
# =========================
FACE_PROC = None

def start_face():
    """Launch face.py overlay as a separate process"""
    global FACE_PROC, _IPC_SOCK, _IPC_KIND, _IPC_ADDR, _IPC_THREAD_STARTED
    
    # Initialize IPC if needed
    if _IPC_SOCK is None:
        _IPC_KIND, _IPC_ADDR, _IPC_SOCK = _start_ipc_listener()
        
        if _IPC_KIND == "unix":
            os.environ[PHOTON_IPC_ENV] = f"unix:{_IPC_ADDR}"
        elif _IPC_KIND == "udp":
            host, port = _IPC_ADDR
            os.environ[PHOTON_IPC_ENV] = f"udp:{host}:{port}"
    
    # Start listener thread
    if not _IPC_THREAD_STARTED:
        t = threading.Thread(target=_ipc_listener, daemon=True)
        t.start()
        _IPC_THREAD_STARTED = True
        time.sleep(0.1)
    
    if FACE_PROC is not None:
        return
    
    env = os.environ.copy()
    
    # Flatpak integration
    flatpak_id = env.get("FLATPAK_ID")
    if flatpak_id:
        env["FLATPAK_ID"] = flatpak_id
    
    # Force XCB on Wayland for better overlay support
    session_type = env.get("XDG_SESSION_TYPE", "unknown")
    if session_type.lower() == "wayland":
        env["QT_QPA_PLATFORM"] = "xcb"

    # Locate face.py
    face_path = os.path.join(os.path.dirname(__file__), "face.py")
    if not os.path.isfile(face_path):
        return
    
    try:
        FACE_PROC = subprocess.Popen(
            [sys.executable, face_path],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        
        # Give it a moment to start
        time.sleep(0.4)
        
        # Check if it's still running
        if FACE_PROC.poll() is not None:
            FACE_PROC = None
            
    except Exception as e:
        FACE_PROC = None

def stop_face():
    """Terminate face overlay with proper cleanup"""
    global FACE_PROC
    if FACE_PROC is None:
        return
    
    if FACE_PROC.poll() is None:
        try:
            FACE_PROC.terminate()
            try:
                FACE_PROC.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                FACE_PROC.kill()
                FACE_PROC.wait()
        except Exception as e:
            pass
    
    FACE_PROC = None

# =========================
#   Main loop
# =========================
def main():
    # Warm the app cache
    try:
        refresh_apps_cache()
    except Exception as e:
        pass

    # Initialize wake word detector
    wake = VoskWake(VOSK_MODEL_DIR, SAMPLE_RATE)
    q = queue.Queue()

    def _cb(indata, frames, time_info, status):
        q.put(indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=BLOCK_SAMPLES,
        callback=_cb,
        device=MIC_DEVICE,
    )

    last_trigger_time = 0.0
    refractory_until = 0.0
    in_session = False
    wake_count = 0
    
    with stream:
        while True:
            buf = q.get()
            s16 = float_to_int16(buf[:, 0])

            level = rms_dbfs(s16)
            wr = wake.feed(s16)

            now = time.monotonic()
            can_trigger = (now >= refractory_until) and (level >= WAKE_DBFS_GATE)

            if can_trigger and wr.triggered and (now - last_trigger_time) > COOLDOWN_SEC and not in_session:
                wake_count += 1
                
                in_session = True
                last_trigger_time = now

                try:
                    # Start face overlay
                    start_face()
                    
                    # Background refresh
                    activate_async()
                    
                    # Clear audio queue
                    drain_queue(q)

                    def _is_typing():
                        result = _USER_TYPING
                        return result
                    
                    def _pull_submit():
                        try:
                            result = _SUBMITTED_TEXTS.get_nowait()
                            return result
                        except Exception:
                            return None

                    # Create live ASR
                    live_rec = make_streaming_vosk_asr(SAMPLE_RATE, VOSK_MODEL_DIR)
                    session = LiveSession(live_rec, SAMPLE_RATE, typing_fn=_is_typing, submitted_fn=_pull_submit)

                    final_text = None
                    
                    # Session loop
                    while True:
                        # Check for immediate submission
                        sub_now = _pull_submit()
                        if sub_now:
                            final_text = sub_now
                            break

                        # Process audio
                        buf_live = q.get()
                        s16_live = float_to_int16(buf_live[:, 0])
                        final_text, keep_listening = session.feed_and_maybe_print(s16_live)
                        
                        if not keep_listening:
                            break

                    # Dispatch command
                    if final_text:
                        try:
                            launch_from_text(final_text)
                        except Exception as e:
                            pass

                finally:
                    # Cleanup
                    stop_face()
                    wake.reset(SAMPLE_RATE)
                    drain_queue(q)
                    refractory_until = time.monotonic() + POST_SESSION_REFRACTORY
                    in_session = False

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            stop_face()
        except Exception:
            pass