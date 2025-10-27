#!/usr/bin/env python3
# launch.py (no fuzzy or phonetic code)
import sys, os, re, subprocess, time, shutil
from typing import Optional, Tuple, List, Dict
sys.path.insert(0, os.path.dirname(__file__))

from activ import get_apps_cached, get_cache_obj, cache_is_fresh, refresh_apps_cache
from functools import lru_cache
from alias import app_alias
from install import install_app

try:
    from gi.repository import Gio
    HAVE_GIO = True
except Exception:
    HAVE_GIO = False

import traceback
from pathlib import Path
from datetime import datetime

SKIP_WARM_START = os.environ.get("PHOTON_SKIP_WARM_START", "0") == "1"
_APP_ID = "org.henok.Photon"

def _gio_log(msg: str):
    """Log Gio-related errors to a file under Photon state directory."""
    try:
        base = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".var" / "app" / _APP_ID / "state")))
        d = base / "photon"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "launch.log"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{ts} [GIO] {msg}\n")
    except Exception:
        pass


# ---------- intent ----------
OPEN_WORDS  = {"open","launch","start","run"}
CLOSE_WORDS = {"close","quit","exit","kill","terminate","stop"}
STOPWORDS   = {
    "please","can","could","you","me","the","a","an","now","hey","ok","okay","photon",
    "go","to","for","from","my","on","in","at","and","into","then","just"
}
import json
from pathlib import Path

def _fallback_prewarm_path() -> Path:
    base = Path(os.environ.get(
        "XDG_STATE_HOME",
        str(Path.home() / ".var" / "app" / _APP_ID / "state")
    ))
    return base / "photon" / "prewarm.json"


@lru_cache(maxsize=128)
def normalize(text: str) -> str:
    toks = re.findall(r"[a-zA-Z0-9.'+-]+", (text or "").lower())
    toks = [t for t in toks if t not in STOPWORDS]
    return " ".join(toks).strip()

def extract_intent_and_query(text: str) -> Tuple[Optional[str], Optional[str]]:
    t = normalize(text)
    if not t:
        return None, None
    m = re.search(rf"\b({'|'.join(OPEN_WORDS)})\b\s+(.+)$", t)
    if m: return "open", m.group(2).strip()
    m = re.search(rf"\b({'|'.join(CLOSE_WORDS)})\b\s+(.+)$", t)
    if m: return "close", m.group(2).strip()
    m = re.search(rf"^(.+?)\s+\b({'|'.join(OPEN_WORDS)})\b$", t)
    if m: return "open", m.group(1).strip()
    m = re.search(rf"^(.+?)\s+\b({'|'.join(CLOSE_WORDS)})\b$", t)
    if m: return "close", m.group(1).strip()
    return "open", t  # default intent


# ---------- main app matching (exact / prefix / contains only) ----------
def find_best_app(app_query: str, apps: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    q = (app_query or "").strip()
    if not q:
        return None

    raw = q.lower()
    clean = raw.replace(" ", "")

    if raw in app_alias:
        q = app_alias[raw]
    elif clean in app_alias:
        q = app_alias[clean]

    lq = q.lower()

    # Exact match
    for a in apps:
        ln, li = a["name"].lower(), a["id"].lower()
        if lq == ln or lq == li:
            return a

    # Startswith
    for a in apps:
        ln, li = a["name"].lower(), a["id"].lower()
        if ln.startswith(lq) or li.startswith(lq):
            return a

    # Contains
    for a in apps:
        ln, li = a["name"].lower(), a["id"].lower()
        if lq in ln or lq in li:
            return a

    return None


# ---------- app launching helpers ----------
OPEN_EXISTING_IDS = {
    "google-chrome.desktop", "google-chrome-stable.desktop",
    "chromium-browser.desktop", "org.chromium.Chromium.desktop", "chromium_chromium.desktop",
    "firefox.desktop", "org.mozilla.firefox.desktop", "firefox_firefox.desktop",
    "slack.desktop", "slack_slack.desktop", "com.slack.Slack.desktop",
    "code.desktop", "code-url-handler.desktop", "code_code.desktop", "com.visualstudio.code.desktop",
    "org.gnome.Terminal.desktop",
}
def _is_open_existing_target(app: Dict[str, str]) -> bool:
    return (app.get("id") or "") in OPEN_EXISTING_IDS

def _run0(args: List[str]) -> int:
    try:
        return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    except Exception:
        return 1

def _run_host(args: List[str]) -> int:
    """Run a command on the host (outside Flatpak) if possible."""
    try:
        if shutil.which("flatpak-spawn"):
            return subprocess.run(
                ["flatpak-spawn", "--host"] + args,
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                cwd="/"
            ).returncode
        return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    except Exception:
        return 1

def _popen(args: List[str]) -> None:
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    except Exception:
        pass

# Fast path: read precomputed exec basenames (written by today2.py prewarm)
def _get_exec_map_from_cache() -> Dict[str, list]:
    try:
        c = get_cache_obj()
        if hasattr(c, "get"):
            em = c.get("exec_map")
            if isinstance(em, dict):
                return em
    except Exception:
        pass

    try:
        fpath = _fallback_prewarm_path()
        if fpath.is_file():
            with fpath.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            em = data.get("exec_map")
            if isinstance(em, dict):
                return em
    except Exception:
        pass

    return {}


def _desktop_exec_basename(app_id: str) -> List[str]:
    em = _get_exec_map_from_cache()
    if app_id in em:
        out = []
        for x in em[app_id]:
            x = (x or "").strip()
            if x and x not in out:
                out.append(x)
        if out:
            return out

    cands: List[str] = []

    if HAVE_GIO:
        try:
            appinfo = Gio.DesktopAppInfo.new(app_id)
            if appinfo:
                try:
                    exe = appinfo.get_executable()
                    if exe:
                        cands.append(os.path.basename(exe))
                except Exception as e:
                    _gio_log(f"get_executable() failed for {app_id}: {e}\n{traceback.format_exc()}")

                try:
                    exec_line = appinfo.get_string("Exec")
                    if exec_line:
                        first = exec_line.split()[0]
                        cands.append(os.path.basename(first))
                except Exception as e:
                    _gio_log(f"get_string('Exec') failed for {app_id}: {e}\n{traceback.format_exc()}")
        except Exception as e:
            _gio_log(f"Gio.DesktopAppInfo.new({app_id}) failed: {e}\n{traceback.format_exc()}")

    desktop_file = None
    for base in (
        os.path.expanduser("~/.local/share/applications"),
        "/usr/share/applications",
        "/usr/local/share/applications",
        "/var/lib/snapd/desktop/applications",
        os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
        "/var/lib/flatpak/exports/share/applications",
    ):
        path = os.path.join(base, app_id)
        if os.path.isfile(path):
            desktop_file = path
            break

    if desktop_file:
        try:
            with open(desktop_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("Exec="):
                        first = line[5:].strip().split()[0]
                        cands.append(os.path.basename(first))
                        break
        except Exception:
            pass

    out = []
    for x in cands:
        if x and x.strip() not in out:
            out.append(x.strip())
    return out


def _any_proc_running_by_app(app: Dict[str, str]) -> bool:
    names = set()

    for exe in _desktop_exec_basename(app["id"]):
        if exe:
            names.add(exe)
            if "-" in exe:
                names.add(exe.split("-")[0])
            if "." in exe:
                names.add(exe.split(".")[0])

    names.add(app["name"])
    base_id = (app["id"] or "").replace(".desktop", "")
    names.add(base_id)
    if "." in base_id:
        names.add(base_id.split(".")[-1])
    if "_" in base_id:
        names.add(base_id.split("_")[-1])

    names = {n for n in names if isinstance(n, str) and len(n.strip()) >= 3}

    if not shutil.which("pgrep"):
        return False

    for n in sorted(names, key=len, reverse=True):
        if _run_host(["pgrep", "-x", n]) == 0:
            return True
        if _run_host(["pgrep", "-f", n]) == 0:
            return True

    return False



def launch_by_desktop_id(desktop_id: str):
    """Launch an app by its .desktop ID, inside or outside Flatpak."""
    
    if HAVE_GIO:
        try:
            appinfo = Gio.DesktopAppInfo.new(desktop_id)
            if appinfo:
                appinfo.launch([], None)
                return
        except Exception as e:
            _gio_log(f"GIO launch failed for {desktop_id}: {e}\n{traceback.format_exc()}")

    if shutil.which("flatpak-spawn"):
        rc = subprocess.run(["flatpak-spawn", "--host", "gtk-launch", desktop_id], 
                        check=False, cwd="/").returncode
        if rc == 0:
            return
        subprocess.run(["flatpak-spawn", "--host", "xdg-open", desktop_id], 
                    check=False, cwd="/")
        return

    if shutil.which("gtk-launch"):
        subprocess.run(["gtk-launch", desktop_id], check=False)
    else:
        subprocess.run(["xdg-open", desktop_id], check=False)


def _warm_start_if_needed_then_activate(app: Dict[str, str], wait_s: float = 2.0):
    if SKIP_WARM_START:
        launch_by_desktop_id(app["id"])
        return

    running = _any_proc_running_by_app(app)
    if not running:
        launch_by_desktop_id(app["id"])
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if _any_proc_running_by_app(app):
                break
            time.sleep(0.05)
    try:
        launch_by_desktop_id(app["id"])
    except Exception:
        pass



def close_app_best_effort(app: Dict[str, str]):
    app_id = app.get("id", "") or ""
    app_name = app.get("name", "")
    base_id = app_id.replace(".desktop", "")
    low = (app_name + " " + app_id).lower()

    if shutil.which("wmctrl"):
        _run_host(["wmctrl", "-c", app_name])
    if "." in base_id and shutil.which("flatpak"):
        _run_host(["flatpak", "kill", base_id])

    safe_exact = set(_desktop_exec_basename(app_id))
    if "chrome" in low or "chromium" in low:
        safe_exact.update({"google-chrome", "chromium", "chromium-browser"})
    if "firefox" in low:
        safe_exact.update({"firefox"})
    if "slack" in low:
        safe_exact.update({"slack"})
    if "code" in low:
        safe_exact.update({"code"})
    if "terminal" in low:
        safe_exact.update({"gnome-terminal", "gnome-terminal-server"})

    for name in safe_exact:
        _run_host(["pkill", "-x", name])


# ---------- entry points ----------
def list_apps() -> List[Dict[str, str]]:
    return get_apps_cached()

def system_action_terminate(action: str):
    if action == "logout":
        os.system("gnome-session-quit --logout --no-prompt")
    elif action == "lock":
        os.system("loginctl lock-session")
    elif action == "shutdown":
        os.system("systemctl poweroff")
    else:
        raise ValueError(f"Unknown action: {action}")


def launch_from_text(live_partial: str):
    """Launch app from text command"""
    
    cur = live_partial.lower().strip()
    if cur in app_alias:
        cur = app_alias[cur]
        if cur in ["logout", "lock", "shutdown"]:
            system_action_terminate(cur)
            return
    
    temp = cur.split(" ")
    intent2 = temp[0].lower().strip()
    app2 = " ".join(temp[1:])
    if intent2 == "install":
        install_app(app2)
        return
    
    intent, app_phrase = extract_intent_and_query(live_partial)
    
    if not intent or not app_phrase:
        return
        
    if not cache_is_fresh():
        refresh_apps_cache()

    apps = get_apps_cached()
    
    match = find_best_app(app_phrase, apps)

    if not match:
        refresh_apps_cache()
        apps = get_apps_cached()
        match = find_best_app(app_phrase, apps)

    if not match:
        return
    
    if intent == "open":
        if _is_open_existing_target(match):
            _warm_start_if_needed_then_activate(match)
        else:
            launch_by_desktop_id(match["id"])
    else:
        close_app_best_effort(match)


def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    live_partial = " ".join(sys.argv[1:])
    launch_from_text(live_partial)


if __name__ == "__main__":
    main()