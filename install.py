#!/usr/bin/env python3
"""
install.py - Ubuntu App Installer with Fallback
Tries: Flatpak → Snap → APT (in order until one works)
"""

import sys
import subprocess
import os

# ============================================================================
# INSTALL COMMANDS - Each app has flatpak, snap, apt options
# Format: "app": ("flatpak_cmd or None", "snap_cmd or None", "apt_cmd or None")
# ============================================================================

INSTALL_COMMANDS = {
    # ============ BROWSERS ============
    "chrome": (
        "flatpak install -y flathub com.google.Chrome",
        None,
        "wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O /tmp/chrome.deb && sudo apt install -y /tmp/chrome.deb"
    ),
    "firefox": (
        "flatpak install -y flathub org.mozilla.firefox",
        "sudo snap install firefox",
        "sudo apt install -y firefox"
    ),
    "brave": (
        "flatpak install -y flathub com.brave.Browser",
        "sudo snap install brave",
        "sudo apt install -y brave-browser"
    ),
    "opera": (
        "flatpak install -y flathub com.opera.Opera",
        "sudo snap install opera",
        None
    ),
    "chromium": (
        "flatpak install -y flathub org.chromium.Chromium",
        "sudo snap install chromium",
        "sudo apt install -y chromium-browser"
    ),
    "vivaldi": (
        "flatpak install -y flathub com.vivaldi.Vivaldi",
        None,
        "wget -q https://downloads.vivaldi.com/stable/vivaldi-stable_amd64.deb -O /tmp/vivaldi.deb && sudo apt install -y /tmp/vivaldi.deb"
    ),
    "edge": (
        "flatpak install -y flathub com.microsoft.Edge",
        None,
        "wget -q https://packages.microsoft.com/repos/edge/pool/main/m/microsoft-edge-stable/microsoft-edge-stable_amd64.deb -O /tmp/edge.deb && sudo apt install -y /tmp/edge.deb"
    ),
    "tor": (
        "flatpak install -y flathub org.torproject.torbrowser-launcher",
        None,
        "sudo apt install -y torbrowser-launcher"
    ),
    "tor-browser": (
        "flatpak install -y flathub org.torproject.torbrowser-launcher",
        None,
        "sudo apt install -y torbrowser-launcher"
    ),
    "midori": (
        "flatpak install -y flathub org.midori_browser.Midori",
        None,
        "sudo apt install -y midori"
    ),
    "epiphany": (
        "flatpak install -y flathub org.gnome.Epiphany",
        "sudo snap install epiphany",
        "sudo apt install -y epiphany-browser"
    ),
    "gnome-web": (
        "flatpak install -y flathub org.gnome.Epiphany",
        "sudo snap install epiphany",
        "sudo apt install -y epiphany-browser"
    ),
    "falkon": (
        "flatpak install -y flathub org.kde.falkon",
        None,
        "sudo apt install -y falkon"
    ),
    "min": (
        "flatpak install -y flathub com.minbrowser.Min",
        "sudo snap install min",
        None
    ),
    "librewolf": (
        "flatpak install -y flathub io.gitlab.librewolf-community",
        None,
        None
    ),
    "lynx": (
        None,
        None,
        "sudo apt install -y lynx"
    ),

    # ============ COMMUNICATION & SOCIAL ============
    "slack": (
        "flatpak install -y flathub com.slack.Slack",
        "sudo snap install slack --classic",
        None
    ),
    "discord": (
        "flatpak install -y flathub com.discordapp.Discord",
        "sudo snap install discord",
        None
    ),
    "telegram": (
        "flatpak install -y flathub org.telegram.desktop",
        "sudo snap install telegram-desktop",
        "sudo apt install -y telegram-desktop"
    ),
    "telegram-desktop": (
        "flatpak install -y flathub org.telegram.desktop",
        "sudo snap install telegram-desktop",
        "sudo apt install -y telegram-desktop"
    ),
    "zoom": (
        "flatpak install -y flathub us.zoom.Zoom",
        "sudo snap install zoom-client",
        "wget -q https://zoom.us/client/latest/zoom_amd64.deb -O /tmp/zoom.deb && sudo apt install -y /tmp/zoom.deb"
    ),
    "teams": (
        "flatpak install -y flathub com.microsoft.Teams",
        "sudo snap install teams",
        None
    ),
    "microsoft-teams": (
        "flatpak install -y flathub com.microsoft.Teams",
        "sudo snap install teams",
        None
    ),
    "signal": (
        "flatpak install -y flathub org.signal.Signal",
        "sudo snap install signal-desktop",
        None
    ),
    "whatsapp": (
        "flatpak install -y flathub io.github.nickvergessen.nickvergessen",
        "sudo snap install whatsapp-for-linux",
        None
    ),
    "skype": (
        "flatpak install -y flathub com.skype.Client",
        "sudo snap install skype",
        None
    ),
    "viber": (
        "flatpak install -y flathub com.viber.Viber",
        None,
        "wget -q https://download.cdn.viber.com/cdn/desktop/Linux/viber.deb -O /tmp/viber.deb && sudo apt install -y /tmp/viber.deb"
    ),
    "element": (
        "flatpak install -y flathub im.element.Element",
        "sudo snap install element-desktop",
        "sudo apt install -y element-desktop"
    ),
    "wire": (
        "flatpak install -y flathub com.wire.WireDesktop",
        "sudo snap install wire",
        None
    ),
    "mattermost": (
        "flatpak install -y flathub com.mattermost.Desktop",
        "sudo snap install mattermost-desktop",
        None
    ),
    "rocket.chat": (
        "flatpak install -y flathub chat.rocket.RocketChat",
        "sudo snap install rocketchat-desktop",
        None
    ),
    "rocketchat": (
        "flatpak install -y flathub chat.rocket.RocketChat",
        "sudo snap install rocketchat-desktop",
        None
    ),
    "zulip": (
        "flatpak install -y flathub org.zulip.Zulip",
        "sudo snap install zulip",
        None
    ),
    "hexchat": (
        "flatpak install -y flathub io.github.Hexchat",
        "sudo snap install hexchat",
        "sudo apt install -y hexchat"
    ),
    "pidgin": (
        "flatpak install -y flathub im.pidgin.Pidgin3",
        None,
        "sudo apt install -y pidgin"
    ),
    "weechat": (
        None,
        None,
        "sudo apt install -y weechat"
    ),
    "irssi": (
        None,
        None,
        "sudo apt install -y irssi"
    ),
    "jitsi": (
        "flatpak install -y flathub org.jitsi.jitsi-meet",
        "sudo snap install jitsi",
        None
    ),
    "mumble": (
        "flatpak install -y flathub info.mumble.Mumble",
        "sudo snap install mumble",
        "sudo apt install -y mumble"
    ),
    "teamspeak": (
        None,
        "sudo snap install teamspeak3",
        None
    ),
    "caprine": (
        "flatpak install -y flathub com.sindresorhus.Caprine",
        "sudo snap install caprine",
        None
    ),
    "ferdium": (
        "flatpak install -y flathub org.ferdium.Ferdium",
        None,
        "wget -q https://github.com/ferdium/ferdium-app/releases/latest/download/Ferdium-linux-amd64.deb -O /tmp/ferdium.deb && sudo apt install -y /tmp/ferdium.deb"
    ),
    "rambox": (
        "flatpak install -y flathub com.rambox.Rambox",
        "sudo snap install rambox",
        None
    ),
    "franz": (
        "flatpak install -y flathub com.meetfranz.Franz",
        "sudo snap install franz",
        None
    ),
    "dino": (
        "flatpak install -y flathub im.dino.Dino",
        None,
        "sudo apt install -y dino-im"
    ),
    "gajim": (
        "flatpak install -y flathub org.gajim.Gajim",
        None,
        "sudo apt install -y gajim"
    ),
    "polari": (
        "flatpak install -y flathub org.gnome.Polari",
        None,
        "sudo apt install -y polari"
    ),
    "fractal": (
        "flatpak install -y flathub org.gnome.Fractal",
        None,
        None
    ),
    "fluffychat": (
        "flatpak install -y flathub im.fluffychat.Fluffychat",
        "sudo snap install fluffychat",
        None
    ),
    "session": (
        "flatpak install -y flathub network.loki.Session",
        "sudo snap install session-desktop",
        None
    ),
    "keybase": (
        "flatpak install -y flathub io.keybase.Client",
        "sudo snap install keybase",
        None
    ),

    # ============ CODE EDITORS & IDEs ============
    "vscode": (
        "flatpak install -y flathub com.visualstudio.code",
        "sudo snap install code --classic",
        "wget -q https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64 -O /tmp/vscode.deb && sudo apt install -y /tmp/vscode.deb"
    ),
    "code": (
        "flatpak install -y flathub com.visualstudio.code",
        "sudo snap install code --classic",
        "wget -q https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64 -O /tmp/vscode.deb && sudo apt install -y /tmp/vscode.deb"
    ),
    "vscodium": (
        "flatpak install -y flathub com.vscodium.codium",
        "sudo snap install codium --classic",
        None
    ),
    "codium": (
        "flatpak install -y flathub com.vscodium.codium",
        "sudo snap install codium --classic",
        None
    ),
    "sublime": (
        "flatpak install -y flathub com.sublimetext.three",
        "sudo snap install sublime-text --classic",
        None
    ),
    "sublime-text": (
        "flatpak install -y flathub com.sublimetext.three",
        "sudo snap install sublime-text --classic",
        None
    ),
    "atom": (
        "flatpak install -y flathub io.atom.Atom",
        "sudo snap install atom --classic",
        None
    ),
    "brackets": (
        "flatpak install -y flathub io.brackets.Brackets",
        "sudo snap install brackets --classic",
        None
    ),
    "geany": (
        "flatpak install -y flathub org.geany.Geany",
        None,
        "sudo apt install -y geany"
    ),
    "gedit": (
        "flatpak install -y flathub org.gnome.gedit",
        None,
        "sudo apt install -y gedit"
    ),
    "gnome-text-editor": (
        "flatpak install -y flathub org.gnome.TextEditor",
        None,
        "sudo apt install -y gnome-text-editor"
    ),
    "kate": (
        "flatpak install -y flathub org.kde.kate",
        "sudo snap install kate --classic",
        "sudo apt install -y kate"
    ),
    "kwrite": (
        "flatpak install -y flathub org.kde.kwrite",
        None,
        "sudo apt install -y kwrite"
    ),
    "vim": (
        None,
        None,
        "sudo apt install -y vim"
    ),
    "neovim": (
        "flatpak install -y flathub io.neovim.nvim",
        "sudo snap install nvim --classic",
        "sudo apt install -y neovim"
    ),
    "nvim": (
        "flatpak install -y flathub io.neovim.nvim",
        "sudo snap install nvim --classic",
        "sudo apt install -y neovim"
    ),
    "emacs": (
        "flatpak install -y flathub org.gnu.emacs",
        "sudo snap install emacs --classic",
        "sudo apt install -y emacs"
    ),
    "nano": (
        None,
        None,
        "sudo apt install -y nano"
    ),
    "micro": (
        None,
        "sudo snap install micro --classic",
        "sudo apt install -y micro"
    ),
    "lite-xl": (
        "flatpak install -y flathub com.lite_xl.LiteXL",
        None,
        None
    ),
    "notepadqq": (
        "flatpak install -y flathub com.notepadqq.Notepadqq",
        "sudo snap install notepadqq",
        "sudo apt install -y notepadqq"
    ),
    "bluefish": (
        "flatpak install -y flathub nl.openoffice.bluefish",
        None,
        "sudo apt install -y bluefish"
    ),
    "eclipse": (
        "flatpak install -y flathub org.eclipse.Java",
        "sudo snap install eclipse --classic",
        None
    ),
    "intellij": (
        "flatpak install -y flathub com.jetbrains.IntelliJ-IDEA-Community",
        "sudo snap install intellij-idea-community --classic",
        None
    ),
    "intellij-idea": (
        "flatpak install -y flathub com.jetbrains.IntelliJ-IDEA-Community",
        "sudo snap install intellij-idea-community --classic",
        None
    ),
    "pycharm": (
        "flatpak install -y flathub com.jetbrains.PyCharm-Community",
        "sudo snap install pycharm-community --classic",
        None
    ),
    "webstorm": (
        "flatpak install -y flathub com.jetbrains.WebStorm",
        "sudo snap install webstorm --classic",
        None
    ),
    "phpstorm": (
        "flatpak install -y flathub com.jetbrains.PhpStorm",
        "sudo snap install phpstorm --classic",
        None
    ),
    "clion": (
        "flatpak install -y flathub com.jetbrains.CLion",
        "sudo snap install clion --classic",
        None
    ),
    "goland": (
        "flatpak install -y flathub com.jetbrains.GoLand",
        "sudo snap install goland --classic",
        None
    ),
    "rider": (
        "flatpak install -y flathub com.jetbrains.Rider",
        "sudo snap install rider --classic",
        None
    ),
    "rubymine": (
        "flatpak install -y flathub com.jetbrains.RubyMine",
        "sudo snap install rubymine --classic",
        None
    ),
    "datagrip": (
        "flatpak install -y flathub com.jetbrains.DataGrip",
        "sudo snap install datagrip --classic",
        None
    ),
    "android-studio": (
        "flatpak install -y flathub com.google.AndroidStudio",
        "sudo snap install android-studio --classic",
        None
    ),
    "netbeans": (
        "flatpak install -y flathub org.apache.netbeans",
        "sudo snap install netbeans --classic",
        None
    ),
    "arduino": (
        "flatpak install -y flathub cc.arduino.IDE2",
        "sudo snap install arduino",
        "sudo apt install -y arduino"
    ),
    "godot": (
        "flatpak install -y flathub org.godotengine.Godot",
        "sudo snap install godot-4 --classic",
        None
    ),
    "unity-hub": (
        None,
        "sudo snap install unityhub --classic",
        None
    ),
    "codeblocks": (
        "flatpak install -y flathub org.codeblocks.codeblocks",
        "sudo snap install codeblocks --classic",
        "sudo apt install -y codeblocks"
    ),
    "qtcreator": (
        "flatpak install -y flathub io.qt.QtCreator",
        "sudo snap install qtcreator --classic",
        "sudo apt install -y qtcreator"
    ),
    "lazarus": (
        None,
        "sudo snap install lazarus --classic",
        "sudo apt install -y lazarus"
    ),
    "gambas": (
        None,
        None,
        "sudo apt install -y gambas3"
    ),
    "spyder": (
        "flatpak install -y flathub org.spyder_ide.spyder",
        None,
        "sudo apt install -y spyder"
    ),
    "jupyter": (
        None,
        None,
        "pip install jupyter --break-system-packages"
    ),
    "jupyterlab": (
        None,
        None,
        "pip install jupyterlab --break-system-packages"
    ),
    "rstudio": (
        "flatpak install -y flathub org.rstudio.RStudio",
        None,
        "wget -q https://download1.rstudio.org/electron/jammy/amd64/rstudio-2023.12.1-402-amd64.deb -O /tmp/rstudio.deb && sudo apt install -y /tmp/rstudio.deb"
    ),
    "zed": (
        None,
        None,
        "curl -f https://zed.dev/install.sh | sh"
    ),
    "lapce": (
        "flatpak install -y flathub dev.lapce.lapce",
        "sudo snap install lapce",
        None
    ),
    "pulsar": (
        "flatpak install -y flathub dev.pulsar_edit.Pulsar",
        None,
        None
    ),
    "gnome-builder": (
        "flatpak install -y flathub org.gnome.Builder",
        None,
        "sudo apt install -y gnome-builder"
    ),
    "kdevelop": (
        "flatpak install -y flathub org.kde.kdevelop",
        "sudo snap install kdevelop --classic",
        "sudo apt install -y kdevelop"
    ),
    "thonny": (
        "flatpak install -y flathub org.thonny.Thonny",
        "sudo snap install thonny",
        "sudo apt install -y thonny"
    ),

    # ============ DEVELOPMENT TOOLS ============
    "git": (
        None,
        None,
        "sudo apt install -y git"
    ),
    "github-cli": (
        None,
        "sudo snap install gh",
        "sudo apt install -y gh"
    ),
    "gh": (
        None,
        "sudo snap install gh",
        "sudo apt install -y gh"
    ),
    "gitlab-runner": (
        None,
        "sudo snap install gitlab-runner",
        None
    ),
    "nodejs": (
        None,
        "sudo snap install node --classic",
        "sudo apt install -y nodejs npm"
    ),
    "node": (
        None,
        "sudo snap install node --classic",
        "sudo apt install -y nodejs npm"
    ),
    "npm": (
        None,
        None,
        "sudo apt install -y npm"
    ),
    "yarn": (
        None,
        None,
        "sudo npm install -g yarn"
    ),
    "pnpm": (
        None,
        None,
        "sudo npm install -g pnpm"
    ),
    "bun": (
        None,
        None,
        "curl -fsSL https://bun.sh/install | bash"
    ),
    "deno": (
        None,
        None,
        "curl -fsSL https://deno.land/install.sh | sh"
    ),
    "python3": (
        None,
        None,
        "sudo apt install -y python3 python3-pip python3-venv"
    ),
    "python": (
        None,
        None,
        "sudo apt install -y python3 python3-pip python3-venv"
    ),
    "pip": (
        None,
        None,
        "sudo apt install -y python3-pip"
    ),
    "pipx": (
        None,
        None,
        "sudo apt install -y pipx"
    ),
    "poetry": (
        None,
        None,
        "pipx install poetry"
    ),
    "rust": (
        None,
        None,
        "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"
    ),
    "rustup": (
        None,
        None,
        "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"
    ),
    "cargo": (
        None,
        None,
        "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"
    ),
    "golang": (
        None,
        "sudo snap install go --classic",
        "sudo apt install -y golang"
    ),
    "go": (
        None,
        "sudo snap install go --classic",
        "sudo apt install -y golang"
    ),
    "java": (
        None,
        None,
        "sudo apt install -y default-jdk"
    ),
    "openjdk": (
        None,
        "sudo snap install openjdk",
        "sudo apt install -y default-jdk"
    ),
    "ruby": (
        None,
        "sudo snap install ruby --classic",
        "sudo apt install -y ruby-full"
    ),
    "php": (
        None,
        None,
        "sudo apt install -y php"
    ),
    "perl": (
        None,
        None,
        "sudo apt install -y perl"
    ),
    "lua": (
        None,
        None,
        "sudo apt install -y lua5.4"
    ),
    "julia": (
        "flatpak install -y flathub org.julialang.Julia",
        "sudo snap install julia --classic",
        None
    ),
    "kotlin": (
        None,
        "sudo snap install kotlin --classic",
        None
    ),
    "scala": (
        None,
        "sudo snap install scala --classic",
        "sudo apt install -y scala"
    ),
    "clojure": (
        None,
        None,
        "sudo apt install -y clojure"
    ),
    "haskell": (
        None,
        None,
        "sudo apt install -y haskell-platform"
    ),
    "ghc": (
        None,
        "sudo snap install ghc --classic",
        "sudo apt install -y ghc"
    ),
    "erlang": (
        None,
        "sudo snap install erlang --classic",
        "sudo apt install -y erlang"
    ),
    "elixir": (
        None,
        None,
        "sudo apt install -y elixir"
    ),
    "ocaml": (
        None,
        None,
        "sudo apt install -y ocaml"
    ),
    "dotnet": (
        None,
        "sudo snap install dotnet-sdk --classic",
        "sudo apt install -y dotnet-sdk-8.0"
    ),
    "mono": (
        None,
        None,
        "sudo apt install -y mono-complete"
    ),
    "cmake": (
        None,
        "sudo snap install cmake --classic",
        "sudo apt install -y cmake"
    ),
    "make": (
        None,
        None,
        "sudo apt install -y make build-essential"
    ),
    "gcc": (
        None,
        None,
        "sudo apt install -y gcc g++"
    ),
    "clang": (
        None,
        None,
        "sudo apt install -y clang"
    ),
    "llvm": (
        None,
        None,
        "sudo apt install -y llvm"
    ),
    "meson": (
        None,
        None,
        "sudo apt install -y meson"
    ),
    "ninja": (
        None,
        None,
        "sudo apt install -y ninja-build"
    ),
    "autoconf": (
        None,
        None,
        "sudo apt install -y autoconf automake"
    ),
    "vagrant": (
        None,
        "sudo snap install vagrant",
        "sudo apt install -y vagrant"
    ),
    "ansible": (
        None,
        None,
        "sudo apt install -y ansible"
    ),
    "terraform": (
        None,
        "sudo snap install terraform --classic",
        None
    ),
    "kubectl": (
        None,
        "sudo snap install kubectl --classic",
        None
    ),
    "helm": (
        None,
        "sudo snap install helm --classic",
        None
    ),
    "minikube": (
        None,
        "sudo snap install minikube",
        None
    ),
    "k9s": (
        None,
        "sudo snap install k9s",
        None
    ),
    "podman": (
        None,
        None,
        "sudo apt install -y podman"
    ),
    "docker": (
        None,
        "sudo snap install docker",
        "sudo apt install -y docker.io docker-compose"
    ),
    "docker-compose": (
        None,
        None,
        "sudo apt install -y docker-compose"
    ),
    "lazydocker": (
        None,
        "sudo snap install lazydocker",
        None
    ),
    "dbeaver": (
        "flatpak install -y flathub io.dbeaver.DBeaverCommunity",
        "sudo snap install dbeaver-ce",
        None
    ),
    "mysql-workbench": (
        None,
        "sudo snap install mysql-workbench-community",
        "sudo apt install -y mysql-workbench"
    ),
    "pgadmin": (
        "flatpak install -y flathub io.pgadmin.pgadmin4",
        None,
        None
    ),
    "pgadmin4": (
        "flatpak install -y flathub io.pgadmin.pgadmin4",
        "sudo snap install pgadmin4",
        None
    ),
    "mongodb-compass": (
        "flatpak install -y flathub com.mongodb.Compass",
        "sudo snap install mongodb-compass",
        None
    ),
    "redis": (
        None,
        "sudo snap install redis",
        "sudo apt install -y redis"
    ),
    "postgresql": (
        None,
        None,
        "sudo apt install -y postgresql postgresql-contrib"
    ),
    "postgres": (
        None,
        None,
        "sudo apt install -y postgresql postgresql-contrib"
    ),
    "mysql": (
        None,
        None,
        "sudo apt install -y mysql-server"
    ),
    "mariadb": (
        None,
        None,
        "sudo apt install -y mariadb-server"
    ),
    "sqlite": (
        None,
        None,
        "sudo apt install -y sqlite3"
    ),
    "insomnia": (
        "flatpak install -y flathub rest.insomnia.Insomnia",
        "sudo snap install insomnia",
        None
    ),
    "postman": (
        "flatpak install -y flathub com.getpostman.Postman",
        "sudo snap install postman",
        None
    ),
    "httpie": (
        None,
        "sudo snap install httpie",
        "sudo apt install -y httpie"
    ),
    "curl": (
        None,
        None,
        "sudo apt install -y curl"
    ),
    "wget": (
        None,
        None,
        "sudo apt install -y wget"
    ),
    "jq": (
        None,
        "sudo snap install jq",
        "sudo apt install -y jq"
    ),
    "yq": (
        None,
        "sudo snap install yq",
        None
    ),
    "ngrok": (
        None,
        "sudo snap install ngrok",
        None
    ),
    "meld": (
        "flatpak install -y flathub org.gnome.meld",
        "sudo snap install meld --classic",
        "sudo apt install -y meld"
    ),
    "kdiff3": (
        "flatpak install -y flathub org.kde.kdiff3",
        "sudo snap install kdiff3",
        "sudo apt install -y kdiff3"
    ),
    "gitg": (
        "flatpak install -y flathub org.gnome.gitg",
        None,
        "sudo apt install -y gitg"
    ),
    "gitk": (
        None,
        None,
        "sudo apt install -y gitk"
    ),
    "gitkraken": (
        "flatpak install -y flathub com.axosoft.GitKraken",
        "sudo snap install gitkraken --classic",
        None
    ),
    "lazygit": (
        None,
        "sudo snap install lazygit",
        None
    ),
    "tig": (
        None,
        None,
        "sudo apt install -y tig"
    ),

    # ============ MEDIA PLAYERS ============
    "vlc": (
        "flatpak install -y flathub org.videolan.VLC",
        "sudo snap install vlc",
        "sudo apt install -y vlc"
    ),
    "mpv": (
        "flatpak install -y flathub io.mpv.Mpv",
        "sudo snap install mpv",
        "sudo apt install -y mpv"
    ),
    "smplayer": (
        "flatpak install -y flathub info.smplayer.SMPlayer",
        None,
        "sudo apt install -y smplayer"
    ),
    "celluloid": (
        "flatpak install -y flathub io.github.celluloid_player.Celluloid",
        "sudo snap install celluloid",
        "sudo apt install -y celluloid"
    ),
    "totem": (
        "flatpak install -y flathub org.gnome.Totem",
        None,
        "sudo apt install -y totem"
    ),
    "parole": (
        None,
        None,
        "sudo apt install -y parole"
    ),
    "kodi": (
        "flatpak install -y flathub tv.kodi.Kodi",
        "sudo snap install kodi",
        "sudo apt install -y kodi"
    ),
    "stremio": (
        "flatpak install -y flathub com.stremio.Stremio",
        None,
        "wget -q https://dl.strem.io/shell-linux/v4.4.168/stremio_4.4.168-1_amd64.deb -O /tmp/stremio.deb && sudo apt install -y /tmp/stremio.deb"
    ),
    "plex": (
        "flatpak install -y flathub tv.plex.PlexDesktop",
        "sudo snap install plex-desktop",
        None
    ),
    "jellyfin": (
        "flatpak install -y flathub com.github.iwalton3.jellyfin-media-player",
        "sudo snap install jellyfin",
        "sudo apt install -y jellyfin"
    ),
    "spotify": (
        "flatpak install -y flathub com.spotify.Client",
        "sudo snap install spotify",
        "curl -sS https://download.spotify.com/debian/pubkey_7A3A762FAFD4A51F.gpg | sudo gpg --dearmor --yes -o /etc/apt/trusted.gpg.d/spotify.gpg && echo 'deb http://repository.spotify.com stable non-free' | sudo tee /etc/apt/sources.list.d/spotify.list && sudo apt update && sudo apt install -y spotify-client"
    ),
    "audacious": (
        "flatpak install -y flathub org.atheme.audacious",
        None,
        "sudo apt install -y audacious"
    ),
    "rhythmbox": (
        "flatpak install -y flathub org.gnome.Rhythmbox3",
        None,
        "sudo apt install -y rhythmbox"
    ),
    "clementine": (
        "flatpak install -y flathub org.clementine_player.Clementine",
        None,
        "sudo apt install -y clementine"
    ),
    "strawberry": (
        "flatpak install -y flathub org.strawberrymusicplayer.strawberry",
        None,
        "sudo apt install -y strawberry"
    ),
    "lollypop": (
        "flatpak install -y flathub org.gnome.Lollypop",
        None,
        "sudo apt install -y lollypop"
    ),
    "elisa": (
        "flatpak install -y flathub org.kde.elisa",
        "sudo snap install elisa",
        "sudo apt install -y elisa"
    ),
    "amarok": (
        None,
        None,
        "sudo apt install -y amarok"
    ),
    "deadbeef": (
        "flatpak install -y flathub io.github.nickvergessen.deadbeef",
        "sudo snap install deadbeef",
        None
    ),
    "cmus": (
        None,
        None,
        "sudo apt install -y cmus"
    ),
    "moc": (
        None,
        None,
        "sudo apt install -y moc"
    ),
    "ncmpcpp": (
        None,
        None,
        "sudo apt install -y ncmpcpp"
    ),
    "mpd": (
        None,
        "sudo snap install mpd",
        "sudo apt install -y mpd"
    ),
    "tidal-hifi": (
        "flatpak install -y flathub com.mastermindzh.tidal-hifi",
        "sudo snap install tidal-hifi",
        None
    ),
    "tidal": (
        "flatpak install -y flathub com.mastermindzh.tidal-hifi",
        "sudo snap install tidal-hifi",
        None
    ),
    "youtube-music": (
        "flatpak install -y flathub app.ytmdesktop.ytmdesktop",
        "sudo snap install youtube-music-desktop-app",
        None
    ),
    "spotube": (
        "flatpak install -y flathub com.github.KRTirtho.Spotube",
        None,
        None
    ),
    "amberol": (
        "flatpak install -y flathub io.bassi.Amberol",
        None,
        None
    ),
    "shortwave": (
        "flatpak install -y flathub de.haeckerfelix.Shortwave",
        None,
        None
    ),
    "podcasts": (
        "flatpak install -y flathub org.gnome.Podcasts",
        None,
        "sudo apt install -y gnome-podcasts"
    ),
    "gpodder": (
        "flatpak install -y flathub org.gpodder.gpodder",
        None,
        "sudo apt install -y gpodder"
    ),

    # ============ VIDEO EDITING ============
    "kdenlive": (
        "flatpak install -y flathub org.kde.kdenlive",
        "sudo snap install kdenlive",
        "sudo apt install -y kdenlive"
    ),
    "shotcut": (
        "flatpak install -y flathub org.shotcut.Shotcut",
        "sudo snap install shotcut --classic",
        None
    ),
    "openshot": (
        "flatpak install -y flathub org.openshot.OpenShot",
        "sudo snap install openshot-community",
        "sudo apt install -y openshot-qt"
    ),
    "pitivi": (
        "flatpak install -y flathub org.pitivi.Pitivi",
        None,
        "sudo apt install -y pitivi"
    ),
    "flowblade": (
        "flatpak install -y flathub io.github.jliljebl.Flowblade",
        None,
        "sudo apt install -y flowblade"
    ),
    "olive": (
        "flatpak install -y flathub org.olivevideoeditor.Olive",
        "sudo snap install olive-editor",
        None
    ),
    "lightworks": (
        None,
        None,
        "wget -q https://cdn.lwks.com/releases/2023.1/lightworks_2023.1_amd64.deb -O /tmp/lightworks.deb && sudo apt install -y /tmp/lightworks.deb"
    ),
    "handbrake": (
        "flatpak install -y flathub fr.handbrake.ghb",
        "sudo snap install handbrake-jz",
        "sudo apt install -y handbrake"
    ),
    "ffmpeg": (
        None,
        None,
        "sudo apt install -y ffmpeg"
    ),
    "avidemux": (
        "flatpak install -y flathub org.avidemux.Avidemux",
        None,
        "sudo apt install -y avidemux2.8-qt"
    ),
    "vidcutter": (
        "flatpak install -y flathub com.ozmartians.VidCutter",
        None,
        None
    ),
    "losslesscut": (
        "flatpak install -y flathub no.mifi.losslesscut",
        None,
        None
    ),

    # ============ AUDIO PRODUCTION ============
    "audacity": (
        "flatpak install -y flathub org.audacityteam.Audacity",
        "sudo snap install audacity",
        "sudo apt install -y audacity"
    ),
    "ardour": (
        "flatpak install -y flathub org.ardour.Ardour",
        None,
        "sudo apt install -y ardour"
    ),
    "lmms": (
        "flatpak install -y flathub io.lmms.LMMS",
        "sudo snap install lmms",
        "sudo apt install -y lmms"
    ),
    "hydrogen": (
        "flatpak install -y flathub org.hydrogenmusic.Hydrogen",
        None,
        "sudo apt install -y hydrogen"
    ),
    "rosegarden": (
        "flatpak install -y flathub com.rosegardenmusic.rosegarden",
        None,
        "sudo apt install -y rosegarden"
    ),
    "musescore": (
        "flatpak install -y flathub org.musescore.MuseScore",
        "sudo snap install musescore",
        None
    ),
    "sonic-pi": (
        "flatpak install -y flathub net.sonic_pi.SonicPi",
        None,
        "sudo apt install -y sonic-pi"
    ),
    "mixxx": (
        "flatpak install -y flathub org.mixxx.Mixxx",
        None,
        "sudo apt install -y mixxx"
    ),
    "bitwig": (
        "flatpak install -y flathub com.bitwig.BitwigStudio",
        "sudo snap install bitwig-studio",
        None
    ),
    "tenacity": (
        "flatpak install -y flathub org.tenacityaudio.Tenacity",
        None,
        None
    ),
    "ocenaudio": (
        "flatpak install -y flathub com.ocenaudio.ocenaudio",
        None,
        None
    ),
    "soundconverter": (
        "flatpak install -y flathub org.soundconverter.SoundConverter",
        None,
        "sudo apt install -y soundconverter"
    ),
    "gnome-sound-recorder": (
        "flatpak install -y flathub org.gnome.SoundRecorder",
        None,
        "sudo apt install -y gnome-sound-recorder"
    ),
    "helvum": (
        "flatpak install -y flathub org.pipewire.Helvum",
        None,
        None
    ),
    "carla": (
        "flatpak install -y flathub studio.kx.carla",
        None,
        "sudo apt install -y carla"
    ),

    # ============ GRAPHICS & DESIGN ============
    "gimp": (
        "flatpak install -y flathub org.gimp.GIMP",
        "sudo snap install gimp",
        "sudo apt install -y gimp"
    ),
    "inkscape": (
        "flatpak install -y flathub org.inkscape.Inkscape",
        "sudo snap install inkscape",
        "sudo apt install -y inkscape"
    ),
    "krita": (
        "flatpak install -y flathub org.kde.krita",
        "sudo snap install krita",
        "sudo apt install -y krita"
    ),
    "darktable": (
        "flatpak install -y flathub org.darktable.Darktable",
        "sudo snap install darktable",
        "sudo apt install -y darktable"
    ),
    "rawtherapee": (
        "flatpak install -y flathub com.rawtherapee.RawTherapee",
        "sudo snap install rawtherapee",
        "sudo apt install -y rawtherapee"
    ),
    "digikam": (
        "flatpak install -y flathub org.kde.digikam",
        "sudo snap install digikam",
        "sudo apt install -y digikam"
    ),
    "shotwell": (
        "flatpak install -y flathub org.gnome.Shotwell",
        None,
        "sudo apt install -y shotwell"
    ),
    "gthumb": (
        "flatpak install -y flathub org.gnome.gThumb",
        None,
        "sudo apt install -y gthumb"
    ),
    "pinta": (
        "flatpak install -y flathub com.github.PintaProject.Pinta",
        "sudo snap install pinta",
        "sudo apt install -y pinta"
    ),
    "mypaint": (
        "flatpak install -y flathub org.mypaint.MyPaint",
        None,
        "sudo apt install -y mypaint"
    ),
    "tuxpaint": (
        "flatpak install -y flathub org.tuxpaint.Tuxpaint",
        None,
        "sudo apt install -y tuxpaint"
    ),
    "kolourpaint": (
        "flatpak install -y flathub org.kde.kolourpaint",
        None,
        "sudo apt install -y kolourpaint"
    ),
    "imagemagick": (
        None,
        None,
        "sudo apt install -y imagemagick"
    ),
    "scribus": (
        "flatpak install -y flathub net.scribus.Scribus",
        "sudo snap install scribus",
        "sudo apt install -y scribus"
    ),
    "figma-linux": (
        "flatpak install -y flathub io.github.nickvergessen.figma-linux",
        "sudo snap install figma-linux",
        None
    ),
    "lunacy": (
        None,
        "sudo snap install lunacy",
        None
    ),
    "pencil2d": (
        "flatpak install -y flathub org.pencil2d.Pencil2D",
        None,
        "sudo apt install -y pencil2d"
    ),
    "synfig": (
        "flatpak install -y flathub org.synfig.SynfigStudio",
        None,
        "sudo apt install -y synfigstudio"
    ),
    "opentoonz": (
        "flatpak install -y flathub io.github.OpenToonz",
        None,
        "sudo apt install -y opentoonz"
    ),
    "fontforge": (
        "flatpak install -y flathub org.fontforge.FontForge",
        "sudo snap install fontforge",
        "sudo apt install -y fontforge"
    ),
    "upscayl": (
        "flatpak install -y flathub org.upscayl.Upscayl",
        "sudo snap install upscayl",
        None
    ),
    "drawing": (
        "flatpak install -y flathub com.github.maoschanz.drawing",
        None,
        "sudo apt install -y drawing"
    ),
    "curtail": (
        "flatpak install -y flathub com.github.hulber.Curtail",
        None,
        None
    ),
    "eyedropper": (
        "flatpak install -y flathub com.github.finefindus.eyedropper",
        None,
        None
    ),
    "pixelorama": (
        "flatpak install -y flathub com.orama_interactive.Pixelorama",
        None,
        None
    ),

    # ============ 3D & CAD ============
    "blender": (
        "flatpak install -y flathub org.blender.Blender",
        "sudo snap install blender --classic",
        "sudo apt install -y blender"
    ),
    "freecad": (
        "flatpak install -y flathub org.freecadweb.FreeCAD",
        "sudo snap install freecad",
        "sudo apt install -y freecad"
    ),
    "openscad": (
        "flatpak install -y flathub org.openscad.OpenSCAD",
        "sudo snap install openscad",
        "sudo apt install -y openscad"
    ),
    "librecad": (
        "flatpak install -y flathub org.librecad.librecad",
        "sudo snap install librecad",
        "sudo apt install -y librecad"
    ),
    "wings3d": (
        None,
        None,
        "sudo apt install -y wings3d"
    ),
    "meshlab": (
        "flatpak install -y flathub net.meshlab.MeshLab",
        "sudo snap install meshlab",
        "sudo apt install -y meshlab"
    ),
    "cura": (
        "flatpak install -y flathub com.ultimaker.cura",
        "sudo snap install cura-slicer",
        None
    ),
    "prusa-slicer": (
        "flatpak install -y flathub com.prusa3d.PrusaSlicer",
        "sudo snap install prusa-slicer",
        None
    ),
    "prusaslicer": (
        "flatpak install -y flathub com.prusa3d.PrusaSlicer",
        "sudo snap install prusa-slicer",
        None
    ),
    "sweethome3d": (
        "flatpak install -y flathub com.sweethome3d.Sweethome3d",
        "sudo snap install sweethome3d-homedesign",
        "sudo apt install -y sweethome3d"
    ),

    #second part
        "libreoffice": (
        "flatpak install -y flathub org.libreoffice.LibreOffice",
        "sudo snap install libreoffice",
        "sudo apt install -y libreoffice"
    ),
    "onlyoffice": (
        "flatpak install -y flathub org.onlyoffice.desktopeditors",
        "sudo snap install onlyoffice-desktopeditors",
        None
    ),
    "wps-office": (
        "flatpak install -y flathub com.wps.Office",
        "sudo snap install wps-office",
        None
    ),
    "wps": (
        "flatpak install -y flathub com.wps.Office",
        "sudo snap install wps-office",
        None
    ),
    "calligra": (
        "flatpak install -y flathub org.kde.calligra",
        "sudo snap install calligra",
        "sudo apt install -y calligra"
    ),
    "abiword": (
        None,
        None,
        "sudo apt install -y abiword"
    ),
    "gnumeric": (
        "flatpak install -y flathub org.gnumeric.Gnumeric",
        None,
        "sudo apt install -y gnumeric"
    ),
    "evolution": (
        "flatpak install -y flathub org.gnome.Evolution",
        None,
        "sudo apt install -y evolution"
    ),
    "geary": (
        "flatpak install -y flathub org.gnome.Geary",
        None,
        "sudo apt install -y geary"
    ),
    "mailspring": (
        "flatpak install -y flathub com.getmailspring.Mailspring",
        "sudo snap install mailspring",
        None
    ),
    "betterbird": (
        "flatpak install -y flathub eu.betterbird.Betterbird",
        None,
        None
    ),
    "thunderbird": (
        "flatpak install -y flathub org.mozilla.Thunderbird",
        "sudo snap install thunderbird",
        "sudo apt install -y thunderbird"
    ),
    "notesnook": (
        "flatpak install -y flathub com.notesnook.Notesnook",
        "sudo snap install notesnook",
        None
    ),
    "standard-notes": (
        "flatpak install -y flathub org.standardnotes.standardnotes",
        "sudo snap install standard-notes",
        None
    ),
    "simplenote": (
        "flatpak install -y flathub com.automattic.Simplenote",
        "sudo snap install simplenote",
        None
    ),
    "joplin": (
        "flatpak install -y flathub net.cozic.joplin_desktop",
        "sudo snap install joplin-desktop",
        None
    ),
    "obsidian": (
        "flatpak install -y flathub md.obsidian.Obsidian",
        "sudo snap install obsidian --classic",
        None
    ),
    "logseq": (
        "flatpak install -y flathub com.logseq.Logseq",
        "sudo snap install logseq",
        None
    ),
    "anytype": (
        "flatpak install -y flathub io.anytype.anytype",
        "sudo snap install anytype",
        None
    ),
    "zettlr": (
        "flatpak install -y flathub com.zettlr.Zettlr",
        "sudo snap install zettlr --classic",
        None
    ),
    "marktext": (
        "flatpak install -y flathub com.github.marktext.marktext",
        "sudo snap install marktext",
        None
    ),
    "typora": (
        "flatpak install -y flathub io.typora.Typora",
        "sudo snap install typora",
        None
    ),
    "ghostwriter": (
        "flatpak install -y flathub io.github.wereturtle.ghostwriter",
        None,
        "sudo apt install -y ghostwriter"
    ),
    "focuswriter": (
        "flatpak install -y flathub org.gottcode.FocusWriter",
        None,
        "sudo apt install -y focuswriter"
    ),
    "manuskript": (
        "flatpak install -y flathub org.kde.manuskript",
        None,
        "sudo apt install -y manuskript"
    ),
    "calibre": (
        "flatpak install -y flathub com.calibre_ebook.calibre",
        "sudo snap install calibre",
        "sudo apt install -y calibre"
    ),
    "foliate": (
        "flatpak install -y flathub com.github.johnfactotum.Foliate",
        "sudo snap install foliate",
        "sudo apt install -y foliate"
    ),
    "okular": (
        "flatpak install -y flathub org.kde.okular",
        "sudo snap install okular",
        "sudo apt install -y okular"
    ),
    "evince": (
        "flatpak install -y flathub org.gnome.Evince",
        "sudo snap install evince",
        "sudo apt install -y evince"
    ),
    "zathura": (
        None,
        None,
        "sudo apt install -y zathura"
    ),
    "xournalpp": (
        "flatpak install -y flathub com.github.xournalpp.xournalpp",
        "sudo snap install xournalpp",
        "sudo apt install -y xournalpp"
    ),
    "rnote": (
        "flatpak install -y flathub com.github.flxzt.rnote",
        "sudo snap install rnote",
        None
    ),
    "gnucash": (
        "flatpak install -y flathub org.gnucash.GnuCash",
        "sudo snap install gnucash",
        "sudo apt install -y gnucash"
    ),
    "kmymoney": (
        "flatpak install -y flathub org.kde.kmymoney",
        "sudo snap install kmymoney",
        "sudo apt install -y kmymoney"
    ),
    "homebank": (
        "flatpak install -y flathub fr.free.Homebank",
        None,
        "sudo apt install -y homebank"
    ),
    "todoist": (
        "flatpak install -y flathub com.todoist.Todoist",
        "sudo snap install todoist",
        None
    ),
    "super-productivity": (
        "flatpak install -y flathub com.super_productivity.SuperProductivity",
        "sudo snap install superproductivity",
        None
    ),
    "taskwarrior": (
        None,
        None,
        "sudo apt install -y taskwarrior"
    ),

    # ============ SCREEN RECORDING & SCREENSHOTS ============
    "obs": (
        "flatpak install -y flathub com.obsproject.Studio",
        "sudo snap install obs-studio",
        "sudo apt install -y obs-studio"
    ),
    "obs-studio": (
        "flatpak install -y flathub com.obsproject.Studio",
        "sudo snap install obs-studio",
        "sudo apt install -y obs-studio"
    ),
    "simplescreenrecorder": (
        None,
        None,
        "sudo apt install -y simplescreenrecorder"
    ),
    "kazam": (
        None,
        None,
        "sudo apt install -y kazam"
    ),
    "peek": (
        "flatpak install -y flathub com.uploadedlobster.peek",
        "sudo snap install peek",
        "sudo apt install -y peek"
    ),
    "vokoscreen": (
        "flatpak install -y flathub com.github.vkohaupt.vokoscreenNG",
        None,
        "sudo apt install -y vokoscreen-ng"
    ),
    "kooha": (
        "flatpak install -y flathub io.github.seadve.Kooha",
        None,
        None
    ),
    "screenkey": (
        None,
        None,
        "sudo apt install -y screenkey"
    ),
    "flameshot": (
        "flatpak install -y flathub org.flameshot.Flameshot",
        "sudo snap install flameshot",
        "sudo apt install -y flameshot"
    ),
    "shutter": (
        None,
        None,
        "sudo apt install -y shutter"
    ),
    "ksnip": (
        "flatpak install -y flathub org.ksnip.ksnip",
        "sudo snap install ksnip",
        "sudo apt install -y ksnip"
    ),
    "spectacle": (
        "flatpak install -y flathub org.kde.spectacle",
        "sudo snap install spectacle",
        "sudo apt install -y kde-spectacle"
    ),
    "gnome-screenshot": (
        None,
        None,
        "sudo apt install -y gnome-screenshot"
    ),
    "scrot": (
        None,
        None,
        "sudo apt install -y scrot"
    ),
    "maim": (
        None,
        None,
        "sudo apt install -y maim"
    ),

    # ============ GAMES & GAMING ============
    "steam": (
        "flatpak install -y flathub com.valvesoftware.Steam",
        "sudo snap install steam",
        "sudo apt install -y steam"
    ),
    "lutris": (
        "flatpak install -y flathub net.lutris.Lutris",
        "sudo snap install lutris --edge",
        "sudo apt install -y lutris"
    ),
    "heroic": (
        "flatpak install -y flathub com.heroicgameslauncher.hgl",
        "sudo snap install heroic",
        None
    ),
    "bottles": (
        "flatpak install -y flathub com.usebottles.bottles",
        "sudo snap install bottles",
        None
    ),
    "wine": (
        None,
        None,
        "sudo apt install -y wine"
    ),
    "playonlinux": (
        None,
        None,
        "sudo apt install -y playonlinux"
    ),
    "protonup-qt": (
        "flatpak install -y flathub net.davidotek.pupgui2",
        "sudo snap install protonup-qt",
        None
    ),
    "gamemode": (
        None,
        None,
        "sudo apt install -y gamemode"
    ),
    "mangohud": (
        "flatpak install -y flathub org.freedesktop.Platform.VulkanLayer.MangoHud",
        None,
        "sudo apt install -y mangohud"
    ),
    "retroarch": (
        "flatpak install -y flathub org.libretro.RetroArch",
        "sudo snap install retroarch",
        "sudo apt install -y retroarch"
    ),
    "dolphin-emu": (
        "flatpak install -y flathub org.DolphinEmu.dolphin-emu",
        "sudo snap install dolphin-emulator",
        "sudo apt install -y dolphin-emu"
    ),
    "pcsx2": (
        "flatpak install -y flathub net.pcsx2.PCSX2",
        "sudo snap install pcsx2-emu",
        None
    ),
    "rpcs3": (
        "flatpak install -y flathub net.rpcs3.RPCS3",
        "sudo snap install rpcs3-emu",
        None
    ),
    "yuzu": (
        "flatpak install -y flathub org.yuzu_emu.yuzu",
        "sudo snap install yuzu",
        None
    ),
    "ryujinx": (
        "flatpak install -y flathub org.ryujinx.Ryujinx",
        None,
        None
    ),
    "citra": (
        "flatpak install -y flathub org.citra_emu.citra",
        "sudo snap install citra-emu",
        None
    ),
    "desmume": (
        "flatpak install -y flathub org.desmume.DeSmuME",
        None,
        "sudo apt install -y desmume"
    ),
    "melonds": (
        "flatpak install -y flathub net.kuribo64.melonDS",
        "sudo snap install melonds",
        None
    ),
    "mgba": (
        "flatpak install -y flathub io.mgba.mGBA",
        "sudo snap install mgba",
        "sudo apt install -y mgba-qt"
    ),
    "snes9x": (
        "flatpak install -y flathub com.snes9x.Snes9x",
        None,
        "sudo apt install -y snes9x-gtk"
    ),
    "ppsspp": (
        "flatpak install -y flathub org.ppsspp.PPSSPP",
        "sudo snap install ppsspp-emu",
        "sudo apt install -y ppsspp"
    ),
    "mame": (
        "flatpak install -y flathub org.mamedev.MAME",
        "sudo snap install mame",
        "sudo apt install -y mame"
    ),
    "scummvm": (
        "flatpak install -y flathub org.scummvm.ScummVM",
        "sudo snap install scummvm",
        "sudo apt install -y scummvm"
    ),
    "dosbox": (
        "flatpak install -y flathub com.dosbox.DOSBox",
        "sudo snap install dosbox-x",
        "sudo apt install -y dosbox"
    ),
    "minigalaxy": (
        "flatpak install -y flathub io.github.sharkwouter.Minigalaxy",
        None,
        "sudo apt install -y minigalaxy"
    ),
    "itch": (
        "flatpak install -y flathub io.itch.itch",
        None,
        None
    ),
    "minecraft": (
        "flatpak install -y flathub com.mojang.Minecraft",
        "sudo snap install mc-installer",
        None
    ),
    "prismlauncher": (
        "flatpak install -y flathub org.prismlauncher.PrismLauncher",
        "sudo snap install prismlauncher",
        None
    ),
    "supertuxkart": (
        "flatpak install -y flathub net.supertuxkart.SuperTuxKart",
        "sudo snap install supertuxkart",
        "sudo apt install -y supertuxkart"
    ),
    "0ad": (
        "flatpak install -y flathub com.play0ad.zeroad",
        "sudo snap install 0ad",
        "sudo apt install -y 0ad"
    ),
    "openttd": (
        "flatpak install -y flathub org.openttd.OpenTTD",
        "sudo snap install openttd",
        "sudo apt install -y openttd"
    ),
    "wesnoth": (
        "flatpak install -y flathub org.wesnoth.Wesnoth",
        "sudo snap install wesnoth",
        "sudo apt install -y wesnoth"
    ),
    "freeciv": (
        "flatpak install -y flathub org.freeciv.Freeciv",
        "sudo snap install freeciv",
        "sudo apt install -y freeciv-client-gtk3"
    ),
    "openra": (
        "flatpak install -y flathub net.openra.OpenRA",
        "sudo snap install openra",
        None
    ),
    "veloren": (
        "flatpak install -y flathub net.veloren.veloren",
        "sudo snap install veloren",
        None
    ),
    "xonotic": (
        "flatpak install -y flathub org.xonotic.Xonotic",
        "sudo snap install xonotic",
        "sudo apt install -y xonotic"
    ),
    "teeworlds": (
        "flatpak install -y flathub com.teeworlds.Teeworlds",
        "sudo snap install teeworlds",
        "sudo apt install -y teeworlds"
    ),
    "hedgewars": (
        "flatpak install -y flathub org.hedgewars.Hedgewars",
        "sudo snap install hedgewars",
        "sudo apt install -y hedgewars"
    ),
    "supertux": (
        "flatpak install -y flathub org.supertuxproject.SuperTux",
        "sudo snap install supertux",
        "sudo apt install -y supertux"
    ),
    "extremetuxracer": (
        "flatpak install -y flathub net.sourceforge.ExtremeTuxRacer",
        None,
        "sudo apt install -y extremetuxracer"
    ),

    # ============ SYSTEM UTILITIES ============
    "gparted": (
        "flatpak install -y flathub org.gnome.GParted",
        None,
        "sudo apt install -y gparted"
    ),
    "gnome-disks": (
        "flatpak install -y flathub org.gnome.DiskUtility",
        None,
        "sudo apt install -y gnome-disk-utility"
    ),
    "baobab": (
        "flatpak install -y flathub org.gnome.baobab",
        None,
        "sudo apt install -y baobab"
    ),
    "bleachbit": (
        "flatpak install -y flathub org.bleachbit.BleachBit",
        None,
        "sudo apt install -y bleachbit"
    ),
    "stacer": (
        None,
        None,
        "sudo apt install -y stacer"
    ),
    "synaptic": (
        None,
        None,
        "sudo apt install -y synaptic"
    ),
    "timeshift": (
        None,
        None,
        "sudo apt install -y timeshift"
    ),
    "deja-dup": (
        "flatpak install -y flathub org.gnome.DejaDup",
        "sudo snap install deja-dup --classic",
        "sudo apt install -y deja-dup"
    ),
    "backintime": (
        None,
        None,
        "sudo apt install -y backintime-qt"
    ),
    "pika-backup": (
        "flatpak install -y flathub org.gnome.World.PikaBackup",
        None,
        None
    ),
    "rclone": (
        None,
        "sudo snap install rclone",
        "sudo apt install -y rclone"
    ),
    "syncthing": (
        "flatpak install -y flathub me.kozec.syncthingtk",
        "sudo snap install syncthing",
        "sudo apt install -y syncthing"
    ),
    "restic": (
        None,
        "sudo snap install restic --classic",
        "sudo apt install -y restic"
    ),
    "borgbackup": (
        None,
        "sudo snap install borg --classic",
        "sudo apt install -y borgbackup"
    ),
    "vorta": (
        "flatpak install -y flathub com.borgbase.Vorta",
        None,
        None
    ),
    "balena-etcher": (
        "flatpak install -y flathub com.balena.etcher",
        "sudo snap install balena-etcher",
        None
    ),
    "etcher": (
        "flatpak install -y flathub com.balena.etcher",
        "sudo snap install balena-etcher",
        None
    ),
    "unetbootin": (
        None,
        None,
        "sudo apt install -y unetbootin"
    ),
    "grub-customizer": (
        None,
        None,
        "sudo apt install -y grub-customizer"
    ),
    "hardinfo": (
        None,
        None,
        "sudo apt install -y hardinfo"
    ),
    "inxi": (
        None,
        None,
        "sudo apt install -y inxi"
    ),
    "neofetch": (
        None,
        "sudo snap install neofetch",
        "sudo apt install -y neofetch"
    ),
    "fastfetch": (
        None,
        None,
        "sudo apt install -y fastfetch"
    ),
    "htop": (
        None,
        "sudo snap install htop",
        "sudo apt install -y htop"
    ),
    "btop": (
        "flatpak install -y flathub io.github.aristocratos.btop",
        "sudo snap install btop",
        "sudo apt install -y btop"
    ),
    "glances": (
        None,
        "sudo snap install glances",
        "sudo apt install -y glances"
    ),
    "nvtop": (
        None,
        "sudo snap install nvtop",
        "sudo apt install -y nvtop"
    ),
    "iotop": (
        None,
        None,
        "sudo apt install -y iotop"
    ),
    "nmon": (
        None,
        None,
        "sudo apt install -y nmon"
    ),
    "mission-center": (
        "flatpak install -y flathub io.missioncenter.MissionCenter",
        None,
        None
    ),
    "resources": (
        "flatpak install -y flathub net.nokyan.Resources",
        None,
        None
    ),
    "conky": (
        None,
        None,
        "sudo apt install -y conky-all"
    ),
    "gnome-system-monitor": (
        "flatpak install -y flathub org.gnome.SystemMonitor",
        None,
        "sudo apt install -y gnome-system-monitor"
    ),

    # ============ TERMINALS ============
    "terminator": (
        None,
        None,
        "sudo apt install -y terminator"
    ),
    "guake": (
        None,
        None,
        "sudo apt install -y guake"
    ),
    "tilix": (
        "flatpak install -y flathub com.gexperts.Tilix",
        "sudo snap install tilix",
        "sudo apt install -y tilix"
    ),
    "alacritty": (
        None,
        "sudo snap install alacritty --classic",
        "sudo apt install -y alacritty"
    ),
    "kitty": (
        None,
        "sudo snap install kitty",
        "sudo apt install -y kitty"
    ),
    "wezterm": (
        "flatpak install -y flathub org.wezfurlong.wezterm",
        None,
        None
    ),
    "cool-retro-term": (
        "flatpak install -y flathub com.github.nickvergessen.cool-retro-term",
        "sudo snap install cool-retro-term --classic",
        "sudo apt install -y cool-retro-term"
    ),
    "yakuake": (
        None,
        "sudo snap install yakuake",
        "sudo apt install -y yakuake"
    ),
    "tilda": (
        None,
        None,
        "sudo apt install -y tilda"
    ),
    "konsole": (
        "flatpak install -y flathub org.kde.konsole",
        "sudo snap install konsole",
        "sudo apt install -y konsole"
    ),
    "gnome-terminal": (
        None,
        None,
        "sudo apt install -y gnome-terminal"
    ),
    "xfce4-terminal": (
        None,
        None,
        "sudo apt install -y xfce4-terminal"
    ),
    "xterm": (
        None,
        None,
        "sudo apt install -y xterm"
    ),
    "blackbox": (
        "flatpak install -y flathub com.raggesilver.BlackBox",
        None,
        None
    ),
    "tmux": (
        None,
        None,
        "sudo apt install -y tmux"
    ),
    "screen": (
        None,
        None,
        "sudo apt install -y screen"
    ),
    "byobu": (
        None,
        None,
        "sudo apt install -y byobu"
    ),

    # ============ SHELLS & CLI TOOLS ============
    "zsh": (
        None,
        None,
        "sudo apt install -y zsh"
    ),
    "fish": (
        None,
        "sudo snap install fish",
        "sudo apt install -y fish"
    ),
    "starship": (
        None,
        "sudo snap install starship",
        "curl -sS https://starship.rs/install.sh | sh -s -- -y"
    ),
    "fzf": (
        None,
        None,
        "sudo apt install -y fzf"
    ),
    "ripgrep": (
        None,
        "sudo snap install ripgrep --classic",
        "sudo apt install -y ripgrep"
    ),
    "fd-find": (
        None,
        "sudo snap install fd",
        "sudo apt install -y fd-find"
    ),
    "bat": (
        None,
        "sudo snap install bat",
        "sudo apt install -y bat"
    ),
    "exa": (
        None,
        "sudo snap install exa",
        "sudo apt install -y exa"
    ),
    "lsd": (
        None,
        "sudo snap install lsd",
        "sudo apt install -y lsd"
    ),
    "dust": (
        None,
        "sudo snap install dust",
        None
    ),
    "duf": (
        None,
        "sudo snap install duf",
        "sudo apt install -y duf"
    ),
    "ncdu": (
        None,
        "sudo snap install ncdu",
        "sudo apt install -y ncdu"
    ),
    "tree": (
        None,
        None,
        "sudo apt install -y tree"
    ),
    "tldr": (
        None,
        "sudo snap install tldr",
        "sudo apt install -y tldr"
    ),
    "thefuck": (
        None,
        "sudo snap install thefuck --classic",
        "sudo apt install -y thefuck"
    ),
    "autojump": (
        None,
        None,
        "sudo apt install -y autojump"
    ),
    "zoxide": (
        None,
        None,
        "sudo apt install -y zoxide"
    ),

    # ============ FILE MANAGERS ============
    "ranger": (
        None,
        "sudo snap install ranger --classic",
        "sudo apt install -y ranger"
    ),
    "nnn": (
        None,
        "sudo snap install nnn",
        "sudo apt install -y nnn"
    ),
    "lf": (
        None,
        "sudo snap install lf",
        None
    ),
    "mc": (
        None,
        "sudo snap install mc-installer",
        "sudo apt install -y mc"
    ),
    "midnight-commander": (
        None,
        None,
        "sudo apt install -y mc"
    ),
    "vifm": (
        None,
        None,
        "sudo apt install -y vifm"
    ),
    "thunar": (
        None,
        None,
        "sudo apt install -y thunar"
    ),
    "pcmanfm": (
        None,
        None,
        "sudo apt install -y pcmanfm"
    ),
    "nemo": (
        None,
        None,
        "sudo apt install -y nemo"
    ),
    "dolphin": (
        "flatpak install -y flathub org.kde.dolphin",
        "sudo snap install dolphin",
        "sudo apt install -y dolphin"
    ),
    "nautilus": (
        "flatpak install -y flathub org.gnome.Nautilus",
        None,
        "sudo apt install -y nautilus"
    ),
    "krusader": (
        "flatpak install -y flathub org.kde.krusader",
        "sudo snap install krusader",
        "sudo apt install -y krusader"
    ),
    "double-commander": (
        "flatpak install -y flathub org.doublecmd.DoubleCommander",
        "sudo snap install doublecmd-qt",
        "sudo apt install -y doublecmd-qt"
    ),
    "spacefm": (
        None,
        None,
        "sudo apt install -y spacefm"
    ),
    "caja": (
        None,
        None,
        "sudo apt install -y caja"
    ),

    # ============ NETWORK & SECURITY ============
    "wireshark": (
        None,
        "sudo snap install wireshark",
        "sudo apt install -y wireshark"
    ),
    "nmap": (
        None,
        "sudo snap install nmap",
        "sudo apt install -y nmap"
    ),
    "zenmap": (
        None,
        None,
        "sudo apt install -y zenmap"
    ),
    "netcat": (
        None,
        None,
        "sudo apt install -y netcat"
    ),
    "tcpdump": (
        None,
        None,
        "sudo apt install -y tcpdump"
    ),
    "traceroute": (
        None,
        None,
        "sudo apt install -y traceroute"
    ),
    "mtr": (
        None,
        None,
        "sudo apt install -y mtr"
    ),
    "iperf3": (
        None,
        None,
        "sudo apt install -y iperf3"
    ),
    "speedtest-cli": (
        None,
        "sudo snap install speedtest-cli",
        "sudo apt install -y speedtest-cli"
    ),
    "openvpn": (
        None,
        "sudo snap install openvpn-connector",
        "sudo apt install -y openvpn"
    ),
    "wireguard": (
        None,
        None,
        "sudo apt install -y wireguard"
    ),
    "protonvpn": (
        "flatpak install -y flathub com.protonvpn.www",
        "sudo snap install protonvpn",
        None
    ),
    "nordvpn": (
        None,
        "sudo snap install nordvpn",
        "sh <(curl -sSf https://downloads.nordcdn.com/apps/linux/install.sh)"
    ),
    "keepassxc": (
        "flatpak install -y flathub org.keepassxc.KeePassXC",
        "sudo snap install keepassxc",
        "sudo apt install -y keepassxc"
    ),
    "bitwarden": (
        "flatpak install -y flathub com.bitwarden.desktop",
        "sudo snap install bitwarden",
        None
    ),
    "1password": (
        "flatpak install -y flathub com.onepassword.OnePassword",
        "sudo snap install 1password",
        None
    ),
    "enpass": (
        None,
        "sudo snap install enpass",
        None
    ),
    "seahorse": (
        "flatpak install -y flathub org.gnome.seahorse.Application",
        None,
        "sudo apt install -y seahorse"
    ),
    "secrets": (
        "flatpak install -y flathub org.gnome.World.Secrets",
        None,
        None
    ),
    "veracrypt": (
        None,
        None,
        "sudo apt install -y veracrypt"
    ),
    "cryptomator": (
        "flatpak install -y flathub org.cryptomator.Cryptomator",
        "sudo snap install cryptomator",
        None
    ),
    "ufw": (
        None,
        None,
        "sudo apt install -y ufw gufw"
    ),
    "gufw": (
        None,
        None,
        "sudo apt install -y gufw"
    ),
    "clamav": (
        None,
        "sudo snap install clamav",
        "sudo apt install -y clamav clamtk"
    ),
    "clamtk": (
        "flatpak install -y flathub com.gitlab.davem.ClamTk",
        None,
        "sudo apt install -y clamtk"
    ),

    # ============ DOWNLOAD & TORRENT ============
    "qbittorrent": (
        "flatpak install -y flathub org.qbittorrent.qBittorrent",
        "sudo snap install qbittorrent-arnatious",
        "sudo apt install -y qbittorrent"
    ),
    "transmission": (
        "flatpak install -y flathub com.transmissionbt.Transmission",
        "sudo snap install transmission",
        "sudo apt install -y transmission-gtk"
    ),
    "deluge": (
        "flatpak install -y flathub org.deluge_torrent.deluge",
        "sudo snap install deluge",
        "sudo apt install -y deluge"
    ),
    "ktorrent": (
        "flatpak install -y flathub org.kde.ktorrent",
        "sudo snap install ktorrent",
        "sudo apt install -y ktorrent"
    ),
    "fragments": (
        "flatpak install -y flathub de.haeckerfelix.Fragments",
        None,
        None
    ),
    "rtorrent": (
        None,
        None,
        "sudo apt install -y rtorrent"
    ),
    "aria2": (
        None,
        None,
        "sudo apt install -y aria2"
    ),
    "yt-dlp": (
        None,
        "sudo snap install yt-dlp",
        "sudo apt install -y yt-dlp"
    ),
    "youtube-dl": (
        None,
        "sudo snap install youtube-dl",
        "sudo apt install -y youtube-dl"
    ),
    "parabolic": (
        "flatpak install -y flathub org.nickvergessen.tubeconverter",
        None,
        None
    ),
    "jdownloader": (
        "flatpak install -y flathub org.jdownloader.JDownloader",
        "sudo snap install jdownloader2",
        None
    ),
    "uget": (
        None,
        None,
        "sudo apt install -y uget"
    ),
    "persepolis": (
        "flatpak install -y flathub com.github.nickvergessen.persepolis",
        None,
        "sudo apt install -y persepolis"
    ),
    "motrix": (
        "flatpak install -y flathub net.agalwood.Motrix",
        "sudo snap install motrix",
        None
    ),

    # ============ VIRTUALIZATION ============
    "virtualbox": (
        None,
        None,
        "sudo apt install -y virtualbox"
    ),
    "virt-manager": (
        None,
        None,
        "sudo apt install -y virt-manager qemu-kvm libvirt-daemon-system"
    ),
    "gnome-boxes": (
        "flatpak install -y flathub org.gnome.Boxes",
        "sudo snap install gnome-boxes",
        "sudo apt install -y gnome-boxes"
    ),
    "boxes": (
        "flatpak install -y flathub org.gnome.Boxes",
        "sudo snap install gnome-boxes",
        "sudo apt install -y gnome-boxes"
    ),
    "qemu": (
        None,
        None,
        "sudo apt install -y qemu-system"
    ),
    "lxd": (
        None,
        "sudo snap install lxd",
        "sudo apt install -y lxd"
    ),
    "distrobox": (
        None,
        None,
        "sudo apt install -y distrobox"
    ),

    # ============ REMOTE ACCESS ============
    "remmina": (
        "flatpak install -y flathub org.remmina.Remmina",
        "sudo snap install remmina",
        "sudo apt install -y remmina"
    ),
    "anydesk": (
        "flatpak install -y flathub com.anydesk.Anydesk",
        "sudo snap install anydesk",
        "wget -q https://download.anydesk.com/linux/anydesk_6.3.0-1_amd64.deb -O /tmp/anydesk.deb && sudo apt install -y /tmp/anydesk.deb"
    ),
    "teamviewer": (
        None,
        "sudo snap install teamviewer-snap",
        "wget -q https://download.teamviewer.com/download/linux/teamviewer_amd64.deb -O /tmp/teamviewer.deb && sudo apt install -y /tmp/teamviewer.deb"
    ),
    "rustdesk": (
        "flatpak install -y flathub com.rustdesk.RustDesk",
        "sudo snap install rustdesk",
        None
    ),
    "parsec": (
        "flatpak install -y flathub com.parsecgaming.parsec",
        "sudo snap install parsec",
        None
    ),
    "moonlight": (
        "flatpak install -y flathub com.moonlight_stream.Moonlight",
        "sudo snap install moonlight",
        None
    ),
    "barrier": (
        "flatpak install -y flathub com.github.nickvergessen.barrier",
        "sudo snap install barrier",
        "sudo apt install -y barrier"
    ),
    "tigervnc": (
        None,
        None,
        "sudo apt install -y tigervnc-viewer"
    ),
    "vinagre": (
        None,
        None,
        "sudo apt install -y vinagre"
    ),
    "krdc": (
        "flatpak install -y flathub org.kde.krdc",
        "sudo snap install krdc",
        "sudo apt install -y krdc"
    ),
    "connections": (
        "flatpak install -y flathub org.gnome.Connections",
        None,
        "sudo apt install -y gnome-connections"
    ),
    "openssh": (
        None,
        None,
        "sudo apt install -y openssh-server openssh-client"
    ),
    "mosh": (
        None,
        "sudo snap install mosh",
        "sudo apt install -y mosh"
    ),
    "filezilla": (
        "flatpak install -y flathub org.filezillaproject.Filezilla",
        "sudo snap install filezilla",
        "sudo apt install -y filezilla"
    ),

    # ============ CLOUD STORAGE ============
    "dropbox": (
        "flatpak install -y flathub com.dropbox.Client",
        "sudo snap install dropbox",
        "sudo apt install -y nautilus-dropbox"
    ),
    "megasync": (
        "flatpak install -y flathub nz.mega.MEGAsync",
        "sudo snap install megasync",
        None
    ),
    "mega": (
        "flatpak install -y flathub nz.mega.MEGAsync",
        "sudo snap install megasync",
        None
    ),
    "nextcloud": (
        "flatpak install -y flathub com.nextcloud.desktopclient.nextcloud",
        "sudo snap install nextcloud-desktop-client",
        None
    ),
    "owncloud": (
        None,
        None,
        "sudo apt install -y owncloud-client"
    ),
    "onedrive": (
        None,
        "sudo snap install onedrive",
        None
    ),
    "pcloud": (
        "flatpak install -y flathub com.pcloud.pCloud",
        None,
        None
    ),
    "localsend": (
        "flatpak install -y flathub org.localsend.localsend_app",
        "sudo snap install localsend",
        None
    ),
    "warpinator": (
        "flatpak install -y flathub org.x.Warpinator",
        "sudo snap install warpinator",
        "sudo apt install -y warpinator"
    ),

    # ============ SCIENCE & MATH ============
    "octave": (
        "flatpak install -y flathub org.octave.Octave",
        "sudo snap install octave",
        "sudo apt install -y octave"
    ),
    "scilab": (
        "flatpak install -y flathub org.scilab.Scilab",
        "sudo snap install scilab",
        "sudo apt install -y scilab"
    ),
    "maxima": (
        None,
        "sudo snap install maxima",
        "sudo apt install -y wxmaxima"
    ),
    "wxmaxima": (
        None,
        None,
        "sudo apt install -y wxmaxima"
    ),
    "geogebra": (
        "flatpak install -y flathub org.geogebra.GeoGebra",
        "sudo snap install geogebra --classic",
        None
    ),
    "stellarium": (
        "flatpak install -y flathub org.stellarium.Stellarium",
        "sudo snap install stellarium-daily",
        "sudo apt install -y stellarium"
    ),
    "celestia": (
        None,
        None,
        "sudo apt install -y celestia"
    ),
    "kstars": (
        "flatpak install -y flathub org.kde.kstars",
        "sudo snap install kstars",
        "sudo apt install -y kstars"
    ),
    "marble": (
        "flatpak install -y flathub org.kde.marble",
        "sudo snap install marble",
        "sudo apt install -y marble"
    ),
    "gnuplot": (
        None,
        "sudo snap install gnuplot",
        "sudo apt install -y gnuplot"
    ),
    "r-base": (
        None,
        None,
        "sudo apt install -y r-base"
    ),
    "sagemath": (
        None,
        None,
        "sudo apt install -y sagemath"
    ),

    # ============ SYSTEM CUSTOMIZATION ============
    "gnome-tweaks": (
        "flatpak install -y flathub org.gnome.tweaks",
        None,
        "sudo apt install -y gnome-tweaks"
    ),
    "tweaks": (
        "flatpak install -y flathub org.gnome.tweaks",
        None,
        "sudo apt install -y gnome-tweaks"
    ),
    "dconf-editor": (
        "flatpak install -y flathub ca.desrt.dconf-editor",
        "sudo snap install dconf-editor",
        "sudo apt install -y dconf-editor"
    ),
    "extension-manager": (
        "flatpak install -y flathub com.mattjakeman.ExtensionManager",
        None,
        None
    ),
    "gradience": (
        "flatpak install -y flathub com.github.GradienceTeam.Gradience",
        None,
        None
    ),
    "lxappearance": (
        None,
        None,
        "sudo apt install -y lxappearance"
    ),
    "qt5ct": (
        None,
        None,
        "sudo apt install -y qt5ct"
    ),
    "kvantum": (
        None,
        None,
        "sudo apt install -y qt5-style-kvantum"
    ),
    "variety": (
        None,
        None,
        "sudo apt install -y variety"
    ),
    "nitrogen": (
        None,
        None,
        "sudo apt install -y nitrogen"
    ),
    "feh": (
        None,
        None,
        "sudo apt install -y feh"
    ),
    "plank": (
        None,
        None,
        "sudo apt install -y plank"
    ),
    "cairo-dock": (
        None,
        None,
        "sudo apt install -y cairo-dock"
    ),
    "latte-dock": (
        None,
        None,
        "sudo apt install -y latte-dock"
    ),
    "polybar": (
        None,
        None,
        "sudo apt install -y polybar"
    ),
    "redshift": (
        None,
        None,
        "sudo apt install -y redshift-gtk"
    ),
    "caffeine": (
        None,
        None,
        "sudo apt install -y caffeine"
    ),

    # ============ CLIPBOARD & LAUNCHERS ============
    "copyq": (
        "flatpak install -y flathub com.github.hluk.copyq",
        "sudo snap install copyq",
        "sudo apt install -y copyq"
    ),
    "diodon": (
        None,
        None,
        "sudo apt install -y diodon"
    ),
    "albert": (
        None,
        None,
        "sudo apt install -y albert"
    ),
    "ulauncher": (
        "flatpak install -y flathub io.ulauncher.Ulauncher",
        "sudo snap install ulauncher",
        None
    ),
    "rofi": (
        None,
        None,
        "sudo apt install -y rofi"
    ),
    "dmenu": (
        None,
        None,
        "sudo apt install -y dmenu"
    ),

    # ============ HARDWARE & PERIPHERALS ============
    "piper": (
        "flatpak install -y flathub org.freedesktop.Piper",
        None,
        "sudo apt install -y piper"
    ),
    "solaar": (
        "flatpak install -y flathub io.github.nickvergessen.Solaar",
        "sudo snap install solaar",
        "sudo apt install -y solaar"
    ),
    "openrgb": (
        "flatpak install -y flathub org.openrgb.OpenRGB",
        "sudo snap install openrgb",
        "sudo apt install -y openrgb"
    ),
    "corectrl": (
        "flatpak install -y flathub org.corectrl.CoreCtrl",
        None,
        "sudo apt install -y corectrl"
    ),
    "psensor": (
        None,
        None,
        "sudo apt install -y psensor"
    ),
    "lm-sensors": (
        None,
        None,
        "sudo apt install -y lm-sensors"
    ),
    "tlp": (
        None,
        None,
        "sudo apt install -y tlp tlp-rdw"
    ),
    "auto-cpufreq": (
        None,
        "sudo snap install auto-cpufreq",
        None
    ),
    "powertop": (
        None,
        None,
        "sudo apt install -y powertop"
    ),

    # ============ WINDOW MANAGERS & DESKTOPS ============
    "i3": (
        None,
        "sudo snap install i3",
        "sudo apt install -y i3"
    ),
    "sway": (
        None,
        None,
        "sudo apt install -y sway"
    ),
    "openbox": (
        None,
        None,
        "sudo apt install -y openbox"
    ),
    "awesome": (
        None,
        None,
        "sudo apt install -y awesome"
    ),
    "bspwm": (
        None,
        None,
        "sudo apt install -y bspwm"
    ),
    "xfce4": (
        None,
        None,
        "sudo apt install -y xfce4"
    ),
    "lxde": (
        None,
        None,
        "sudo apt install -y lxde"
    ),
    "lxqt": (
        None,
        None,
        "sudo apt install -y lxqt"
    ),
    "mate": (
        None,
        None,
        "sudo apt install -y mate-desktop-environment"
    ),
    "cinnamon": (
        None,
        None,
        "sudo apt install -y cinnamon-desktop-environment"
    ),
    "kde-plasma": (
        None,
        None,
        "sudo apt install -y kde-plasma-desktop"
    ),
    "kde": (
        None,
        None,
        "sudo apt install -y kde-plasma-desktop"
    ),
    "plasma": (
        None,
        None,
        "sudo apt install -y kde-plasma-desktop"
    ),
    "gnome": (
        None,
        None,
        "sudo apt install -y gnome-shell ubuntu-gnome-desktop"
    ),
    "budgie": (
        None,
        None,
        "sudo apt install -y budgie-desktop"
    ),

    # ============ MISCELLANEOUS ============
    "grsync": (
        None,
        None,
        "sudo apt install -y grsync"
    ),
    "rsync": (
        None,
        None,
        "sudo apt install -y rsync"
    ),
    "unzip": (
        None,
        None,
        "sudo apt install -y unzip"
    ),
    "zip": (
        None,
        None,
        "sudo apt install -y zip"
    ),
    "p7zip": (
        None,
        None,
        "sudo apt install -y p7zip-full"
    ),
    "7zip": (
        None,
        None,
        "sudo apt install -y p7zip-full"
    ),
    "rar": (
        None,
        None,
        "sudo apt install -y rar unrar"
    ),
    "unrar": (
        None,
        None,
        "sudo apt install -y unrar"
    ),
    "ark": (
        "flatpak install -y flathub org.kde.ark",
        "sudo snap install ark",
        "sudo apt install -y ark"
    ),
    "file-roller": (
        "flatpak install -y flathub org.gnome.FileRoller",
        None,
        "sudo apt install -y file-roller"
    ),
    "engrampa": (
        None,
        None,
        "sudo apt install -y engrampa"
    ),
    "xarchiver": (
        None,
        None,
        "sudo apt install -y xarchiver"
    ),
    "peazip": (
        "flatpak install -y flathub io.github.nickvergessen.PeaZip",
        "sudo snap install peazip",
        None
    )
}


# ============================================================================
# ALIASES - Maps common names to canonical names
# ============================================================================

ALIASES = {
    "google chrome": "chrome",
    "google-chrome": "chrome",
    "visual studio code": "vscode",
    "vs code": "vscode",
    "vs-code": "vscode",
    "sublime text": "sublime",
    "sublime-text": "sublime",
    "intellij idea": "intellij",
    "intellij-idea": "intellij",
    "android studio": "android-studio",
    "gnome boxes": "gnome-boxes",
    "gnome disks": "gnome-disks",
    "gnome tweaks": "gnome-tweaks",
    "obs studio": "obs",
    "libre office": "libreoffice",
    "libre-office": "libreoffice",
    "wps office": "wps",
    "git kraken": "gitkraken",
    "microsoft edge": "edge",
    "microsoft-edge": "edge",
    "microsoft teams": "teams",
    "telegram desktop": "telegram",
    "prism launcher": "prismlauncher",
    "prism-launcher": "prismlauncher",
    "heroic games launcher": "heroic",
    "heroic-games-launcher": "heroic",
    "qbit": "qbittorrent",
    "qbit-torrent": "qbittorrent",
    "youtube music": "youtube-music",
    "yt music": "youtube-music",
    "pycharm community": "pycharm",
    "pycharm-community": "pycharm",
    "intellij community": "intellij",
    "intellij-community": "intellij",
    "sweet home 3d": "sweethome3d",
    "sweet-home-3d": "sweethome3d",
    "prusa slicer": "prusaslicer",
    "visual-studio-code": "vscode",
}


# ============================================================================
# TERMINAL DETECTION
# ============================================================================

def find_terminal():
    """Find terminal on HOST system"""
    in_flatpak = os.path.exists("/app") or "FLATPAK_ID" in os.environ
    terminals = ['gnome-terminal', 'konsole', 'xfce4-terminal', 'tilix', 'terminator', 'alacritty', 'kitty', 'xterm', 'x-terminal-emulator']
    
    for term in terminals:
        try:
            if in_flatpak:
                result = subprocess.run(
                    ['flatpak-spawn', '--host', 'which', term],
                    capture_output=True,
                    timeout=2,
                    cwd="/"
                )
            else:
                result = subprocess.run(
                    ['which', term],
                    capture_output=True,
                    timeout=1,
                    cwd="/"
                )
            
            if result.returncode == 0:
                return term
                
        except Exception:
            continue
    
    return None


# ============================================================================
# LAUNCH INSTALL WITH FALLBACK
# ============================================================================

def launch_install(app_name: str, flatpak_cmd, snap_cmd, apt_cmd):
    """Launch installation in terminal with fallback"""
    
    terminal = find_terminal()
    if not terminal:
        print("[install] ✗ Terminal not found")
        return False
    
    # Build fallback script
    commands = []
    if flatpak_cmd:
        commands.append(f'''
echo ">>> Trying Flatpak..."
{flatpak_cmd}
if [ $? -eq 0 ]; then
    echo "✓ Installed via Flatpak!"
    INSTALL_SUCCESS=1
fi
''')
    
    if snap_cmd:
        commands.append(f'''
if [ "$INSTALL_SUCCESS" != "1" ]; then
    echo ""
    echo ">>> Trying Snap..."
    {snap_cmd}
    if [ $? -eq 0 ]; then
        echo "✓ Installed via Snap!"
        INSTALL_SUCCESS=1
    fi
fi
''')
    
    if apt_cmd:
        commands.append(f'''
if [ "$INSTALL_SUCCESS" != "1" ]; then
    echo ""
    echo ">>> Trying APT..."
    {apt_cmd}
    if [ $? -eq 0 ]; then
        echo "✓ Installed via APT!"
        INSTALL_SUCCESS=1
    fi
fi
''')
    
    script = f'''#!/bin/bash
INSTALL_SUCCESS=0
echo "========================================"
echo "Installing {app_name}"
echo "========================================"
echo ""
{''.join(commands)}
echo ""
if [ "$INSTALL_SUCCESS" = "1" ]; then
    echo "========================================"
    echo "✓ Installation complete!"
    echo "========================================"
else
    echo "========================================"
    echo "✗ All installation methods failed!"
    echo "========================================"
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
    elif terminal == 'tilix':
        cmd = ['tilix', '-e', 'bash', '-c', script]
    elif terminal == 'terminator':
        cmd = ['terminator', '-e', f'bash -c {repr(script)}']
    elif terminal == 'alacritty':
        cmd = ['alacritty', '-e', 'bash', '-c', script]
    elif terminal == 'kitty':
        cmd = ['kitty', 'bash', '-c', script]
    elif terminal == 'xterm':
        cmd = ['xterm', '-hold', '-e', 'bash', '-c', script]
    else:
        cmd = [terminal, '-e', 'bash', '-c', script]
    
    try:
        if os.path.exists("/app") or "FLATPAK_ID" in os.environ:
            cmd = ['flatpak-spawn', '--host'] + cmd
        
        subprocess.Popen(
            cmd, 
            cwd="/",
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        print(f"[install] ✓ Terminal opened for {app_name}")
        return True
        
    except Exception as e:
        print(f"[install] ✗ Failed: {e}")
        return False


# ============================================================================
# MAIN INSTALL FUNCTION
# ============================================================================

def install_app(app_name: str):
    """Install app with fallback: Flatpak → Snap → APT"""
    
    print(f"[install] Installing: {app_name}")
    
    # Normalize the app name
    app = app_name.lower().strip()
    
    # Check aliases first
    app = ALIASES.get(app, app)
    
    # Get the install commands
    if app in INSTALL_COMMANDS:
        flatpak_cmd, snap_cmd, apt_cmd = INSTALL_COMMANDS[app]
    else:
        # Unknown app - try apt only
        flatpak_cmd = None
        snap_cmd = None
        apt_cmd = f"sudo apt update && sudo apt install -y {app}"
    
    return launch_install(app_name, flatpak_cmd, snap_cmd, apt_cmd)


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: install.py <app_name>")
        print("\nExamples:")
        print("  install.py chrome")
        print("  install.py vscode")
        print("  install.py discord")
        return 1
    
    app = ' '.join(sys.argv[1:])
    install_app(app)
    return 0


if __name__ == '__main__':
    sys.exit(main())