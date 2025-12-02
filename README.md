# Photon  
**Desktop Assistant (Beta – version 0.2)**

Tested only on Ubuntu, should work on all major Linux distros with Flatpak support.

---

## What you can do right now
- Read emails — the original or a summary  
- Write Gmail using AI (your own prompt) or manually type your email  
- Install apps (may have bugs)  
- This version is **not local** — it uses the OpenAI API because making it local is very resource-intensive and requires VRAM most laptops (including mine) don’t have  
- Voice feature for opening apps has been removed in this version  

**Main value proposition is focus and simplicity!**

---

## Long-term plan
Photon’s core will always remain open-source. If this project gains traction, I may introduce optional **Pro features** to cover API/server costs and sustain full-time development after I graduate from college in May.

Saying this early so there are no surprises later.

This is a beta release and my first release. I plan to integrate Photon with email, calendar, Slack, etc.

---

## Download Photon

➡️ **Go to [photondesktop.com](https://photondesktop.com)** to download and try it.  
No need to package anything yourself!

**Important:** I can only give access to the first 100 users because Google API still hasn’t approved my app. Google limits to 100 test users until full approval.

You can still register even if it hits the limit — you’ll be notified when full API access is granted.

---

# How to package Photon yourself (using your own API keys)

1. **Download all files from this repo and place them in one folder.**

2. **Inside the `wheels` folder, download dependencies with:**

    ```bash
    pip download --dest wheels \
      PySide6 \
      google-auth \
      google-auth-oauthlib \
      google-auth-httplib2 \
      google-api-python-client \
      openai \
      python-dotenv
    ```

3. **Create your own Google API**  
   (include Gmail API and People API)  
   and an **OpenAI API key**.  
   If you don’t know how, ask GPT or Claude — it’s not hard.

4. **Create `.env` with these variables:**

    ```env
    OPENAI_API_KEY="?"
    id="?"
    secret="?"
    ```

5. **Build the Flatpak:**

    ```bash
    flatpak-builder --force-clean build-dir org.desktop.Photon.yml
    ```

6. **Export + bundle it:**

    ```bash
    flatpak build-export repo build-dir
    flatpak build-bundle repo photon.flatpak org.desktop.Photon
    ```

7. **Install locally:**

    ```bash
    flatpak install --user photon.flatpak
    ```

8. **Run it:**

    ```bash
    flatpak run org.desktop.Photon
    ```

---

## If you get any error or bug
Don’t panic — just copy/paste:
- this README  
- all files  
- the error message  

into GPT or Claude, and you’ll be able to resolve it.

---

