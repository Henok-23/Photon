#!/usr/bin/env python3
# activ.py — no jellyfish; enumerate host apps via flatpak-spawn
import os, time, pickle, threading, concurrent.futures, subprocess
from typing import List, Dict, Optional

try:
    from gi.repository import Gio
    HAVE_GIO = True
except Exception:
    HAVE_GIO = False

CACHE_FILE = os.path.expanduser("~/.cache/photon_apps.pkl")
CACHE_MAX_AGE = 3600  # 1 hour


class AppCache:
    def __init__(self):
        self.apps: List[Dict[str, str]] = []
        self.last_update: float = 0.0

    def is_stale(self) -> bool:
        return (time.time() - self.last_update) > CACHE_MAX_AGE

    def save(self):
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "wb") as f:
                pickle.dump(self, f)
        except Exception as e:
            pass
            # print(f"[ERROR] Failed to save cache: {e}")

    @classmethod
    def load(cls):
        try:
            with open(CACHE_FILE, "rb") as f:
                obj = pickle.load(f)
                if not hasattr(obj, "apps"): obj.apps = []
                if not hasattr(obj, "last_update"): obj.last_update = 0.0
                return obj
        except Exception:
            return cls()


_cache = AppCache.load()


# ---------- sandbox local listing (may see only Photon) ----------
def _list_apps_gio() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    try:
        apps = Gio.AppInfo.get_all()
        for a in apps:
            try:
                if hasattr(a, "should_show") and a.should_show():
                    name = a.get_name()
                    app_id = a.get_id()
                    if name and app_id:
                        out.append({"name": name, "id": app_id})
            except Exception:
                continue
    except Exception:
        pass
    out.sort(key=lambda x: x["name"].lower())
    return out


# ---------- host listing via flatpak-spawn (works reliably) ----------
_HOST_APP_DIRS = [
    "/usr/share/applications",
    os.path.expanduser("~/.local/share/applications"),
    "/var/lib/flatpak/exports/share/applications",
    os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
    # Snap directories
    "/var/lib/snapd/desktop/applications",
    os.path.expanduser("~/snap"),  # User snap apps may have .desktop files here
]

def _host_ls_desktop_files() -> List[str]:
    files: List[str] = []
    for d in _HOST_APP_DIRS:
        try:
            cmd = f'ls -1 {d}/*.desktop 2>/dev/null || true'
            p = subprocess.run(
                ["flatpak-spawn", "--host", "--", "sh", "-c", cmd],
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                check=False,
                cwd="/"

            )
            # if p.stderr:
            #     print(f"[DEBUG] stderr from ls {d}: {p.stderr.strip()}")
            if p.stdout:
                found = [line.strip() for line in p.stdout.splitlines() if line.strip()]
                # print(f"[DEBUG] Found {len(found)} .desktop files in {d}")
                files.extend(found)
        except Exception as e:
            # print(f"[DEBUG] Exception scanning {d}: {e}")
            continue
    # print(f"[DEBUG] Total desktop files found: {len(files)}")
    return files

def _host_read_name(path: str) -> Optional[str]:
    try:
        p = subprocess.run(
            ["flatpak-spawn", "--host", "awk", "-F=", r'/^Name=/{print $2; exit}', path],
            stdout=subprocess.PIPE, 
            stderr=subprocess.DEVNULL, 
            text=True, 
            check=False,
            cwd="/"
        )
        name = (p.stdout or "").strip()
        return name or None
    except Exception:
        return None

def _host_hidden_or_nodisplay(path: str) -> bool:
    try:
        nd = subprocess.run(
            ["flatpak-spawn", "--host", "grep", "-m1", "^NoDisplay=true", path],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            cwd="/"
        ).returncode == 0
        hd = subprocess.run(
            ["flatpak-spawn", "--host", "grep", "-m1", "^Hidden=true", path],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            cwd="/"
        ).returncode == 0
        return nd or hd
    except Exception:
        return False

def _list_apps_host_via_spawn() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    files = _host_ls_desktop_files()
    # print(f"[DEBUG] Processing {len(files)} desktop files")
    
    # parallelize a bit
    def _one(fpath: str) -> Optional[Dict[str, str]]:
        if _host_hidden_or_nodisplay(fpath):
            return None
        name = _host_read_name(fpath)
        if not name:
            return None
        return {"name": name, "id": os.path.basename(fpath)}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(_one, files):
            if res: out.append(res)
    
    # print(f"[DEBUG] Processed into {len(out)} apps")
    out.sort(key=lambda x: x["name"].lower())
    return out


# ---------- public API ----------
def refresh_apps_cache() -> List[Dict[str, str]]:
    """
    Prefer host scan (flatpak-spawn) so we can see system apps like Chrome.
    Fall back to in-sandbox listing if something goes wrong.
    """
    global _cache
    apps: List[Dict[str, str]] = []
    try:
        apps = _list_apps_host_via_spawn()
    except Exception as e:
        # print(f"[DEBUG] Host scan failed: {e}")
        apps = []
    if not apps:
        try:
            apps = _list_apps_gio()
        except Exception as e:
            # print(f"[DEBUG] GIO scan failed: {e}")
            apps = []
    
    # print(f"[DEBUG] refresh_apps_cache found {len(apps)} apps")
    _cache.apps = apps
    _cache.last_update = time.time()
    
    # FIXED: Save synchronously instead of in a daemon thread
    _cache.save()
    
    return apps

def activate_async():
    t = threading.Thread(target=refresh_apps_cache, daemon=True)
    t.start()
    return t

def get_apps_cached() -> List[Dict[str, str]]:
    return _cache.apps or []

def get_cache_obj() -> AppCache:
    return _cache

def cache_is_fresh() -> bool:
    return (len(_cache.apps) > 0) and (not _cache.is_stale())