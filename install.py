#!/usr/bin/env python3
"""
install.py - UBUNTU ONLY, ACTUALLY WORKS NOW
Critical fix: ALL subprocess calls use cwd="/" to avoid Flatpak directory errors
"""

import sys
import subprocess
import os

# ============================================================================
# UBUNTU INSTALL COMMANDS
# ============================================================================

INSTALL_COMMANDS = {
    "chrome": "wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O /tmp/chrome.deb && sudo apt install -y /tmp/chrome.deb",
    "firefox": "sudo apt install -y firefox",
    "brave": "sudo apt install -y brave-browser",
    "opera": "sudo snap install opera",
    "chromium": "sudo apt install -y chromium-browser",
    "slack": "sudo snap install slack --classic",
    "discord": "sudo snap install discord",
    "telegram": "sudo snap install telegram-desktop",
    "zoom": "wget -q https://zoom.us/client/latest/zoom_amd64.deb -O /tmp/zoom.deb && sudo apt install -y /tmp/zoom.deb",
    "teams": "sudo snap install teams",
    "vscode": "sudo snap install code --classic",
    "code": "sudo snap install code --classic",
    "sublime": "sudo snap install sublime-text --classic",
    "docker": "sudo apt install -y docker.io",
    "postman": "sudo snap install postman",
    "spotify": "curl -sS https://download.spotify.com/debian/pubkey_7A3A762FAFD4A51F.gpg | sudo gpg --dearmor --yes -o /etc/apt/trusted.gpg.d/spotify.gpg && echo 'deb http://repository.spotify.com stable non-free' | sudo tee /etc/apt/sources.list.d/spotify.list && sudo apt update && sudo apt install -y spotify-client",
    "vlc": "sudo snap install vlc",
    "obs": "sudo snap install obs-studio",
    "gimp": "sudo apt install -y gimp",
    "inkscape": "sudo apt install -y inkscape",
    "blender": "sudo snap install blender --classic",
    "htop": "sudo apt install -y htop",
    "terminator": "sudo apt install -y terminator",
    "filezilla": "sudo apt install -y filezilla",
    "libreoffice": "sudo apt install -y libreoffice",
    "thunderbird": "sudo apt install -y thunderbird",
}

ALIASES = {
    "google chrome": "chrome",
    "visual studio code": "vscode",
    "vs code": "vscode",
}

# ============================================================================
# TERMINAL DETECTION - WITH cwd="/" FIX
# ============================================================================

def find_terminal():
    """Find terminal on HOST system"""
    
    in_flatpak = os.path.exists("/app") or "FLATPAK_ID" in os.environ
    terminals = ['gnome-terminal', 'konsole', 'xfce4-terminal', 'xterm', 'x-terminal-emulator']
    
    print(f"[install] Checking for terminal (flatpak={in_flatpak})...")
    
    for term in terminals:
        try:
            if in_flatpak:
                # CRITICAL: Use cwd="/" to avoid directory errors
                result = subprocess.run(
                    ['flatpak-spawn', '--host', 'which', term],
                    capture_output=True,
                    timeout=2,
                    cwd="/"  # ← THE FIX!
                )
            else:
                result = subprocess.run(
                    ['which', term],
                    capture_output=True,
                    timeout=1,
                    cwd="/"  # ← ALWAYS USE ROOT
                )
            
            if result.returncode == 0:
                print(f"[install] ✓ Found terminal: {term}")
                return term
                
        except Exception as e:
            print(f"[install] Error checking {term}: {e}")
            continue
    
    print("[install] ✗ No terminal found")
    return None


# ============================================================================
# LAUNCH INSTALL
# ============================================================================

def launch_install(app_name: str, install_cmd: str):
    """Launch installation in terminal"""
    
    terminal = find_terminal()
    if not terminal:
        print("[install] ✗ Terminal not found. Install with: sudo apt install gnome-terminal")
        return False
    
    # Build install script
    script = f'''
echo "========================================"
echo "Installing {app_name}"
echo "========================================"
echo ""
{install_cmd}
echo ""
if [ $? -eq 0 ]; then
    echo "✓ Installation complete!"
else
    echo "✗ Installation failed!"
fi
echo ""
echo "Press Enter to close..."
read
'''
    
    # Build terminal command
    if terminal == 'gnome-terminal':
        cmd = ['gnome-terminal', '--', 'bash', '-c', script]
    elif terminal == 'konsole':
        cmd = ['konsole', '-e', 'bash', '-c', script]
    elif terminal == 'xfce4-terminal':
        cmd = ['xfce4-terminal', '--hold', '-e', f'bash -c {repr(script)}']
    elif terminal == 'xterm':
        cmd = ['xterm', '-hold', '-e', 'bash', '-c', script]
    else:
        cmd = [terminal, '-e', 'bash', '-c', script]
    
    try:
        # If in Flatpak, prepend flatpak-spawn
        if os.path.exists("/app") or "FLATPAK_ID" in os.environ:
            cmd = ['flatpak-spawn', '--host'] + cmd
        
        # CRITICAL: Use cwd="/" to avoid directory errors
        subprocess.Popen(
            cmd, 
            cwd="/",  # ← THE FIX!
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        print(f"[install] ✓ Terminal opened for {app_name}")
        return True
        
    except Exception as e:
        print(f"[install] ✗ Failed: {e}")
        return False


# ============================================================================
# MAIN
# ============================================================================

def install_app(app_name: str):
    """Install app on Ubuntu"""
    
    print(f"[install] Installing: {app_name}")
    
    # Normalize
    app = app_name.lower().strip()
    app = ALIASES.get(app, app)
    
    # Get command
    if app in INSTALL_COMMANDS:
        cmd = INSTALL_COMMANDS[app]
    else:
        cmd = f"sudo apt update && sudo apt install -y {app}"
    
    return launch_install(app_name, cmd)


def main():
    if len(sys.argv) < 2:
        print("Usage: install.py <app_name>")
        return 1
    
    app = ' '.join(sys.argv[1:])
    install_app(app)
    return 0


if __name__ == '__main__':
    sys.exit(main())