# Photon 
Desktop Assistant (Beta - version 0.2)

Tested only on Ubuntu, should work on all major Linux distros with Flatpak support.

You can only:
- Read emails the original or summary
- Write gmail using AI by submitting your own prompt or write email by yourself
- Install apps

This version is not local, I use openAI API because making it local is very resource intensive and require VRAM which most laptops don't have (including mine). Voice feature for opening apps is removed on this version.

Main value proposition is focus and simplicity!

## Long term plan

Photon's core will always remain open-source. If this project gains traction, I may introduce optional Pro features to cover API/server costs and sustain full-time development after I graduate from college in May. I want to say this early so there are no surprises later.


## Download Photon

Please go to [photondesktop.com](https://photondesktop.com) to download and try it no need to package or do anything! I can only give first 100 access to photon because I haven't gotten approval from Google API access yet, and they limit users only for 100 users until they give approval. At the same time please go there and try to download it if it reaches limit, you still register and will let you know as soon as I get full API access.

## How to package photon on your own (your own API keys)

Please download all files from here and put it one folder.

Get inside wheels folder and download these dependencies with command below:
```
pip download --dest wheels \
  PySide6 \
  google-auth \
  google-auth-oauthlib \
  google-auth-httplib2 \
  google-api-python-client \
  openai \
  python-dotenv
```

Create your own google api (with gmail and people API included), openAI API (if you don't know how to do these just ask GPT or Claude, its not hard).

Then create .env with the variables below and fill it with your own API keys:
```
OPENAI_API_KEY= "?"
id="?"
secret="?"
```

Then we build the flatpak with code below:
```
flatpak-builder --force-clean build-dir org.desktop.Photon.yml
```

After that make it shareable/installable with these code below:
```
flatpak build-export repo build-dir
flatpak build-bundle repo photon.flatpak org.desktop.Photon
```

Finally we install it:
```
flatpak install --user photon.flatpak
```

To run it:
```
flatpak run org.desktop.Photon
```

Thats all to package and install it. If you run into any error or bug, don't panic just copy paste these readme, all files, and bugs to GPT and Claude and you will be able to resolve it!!
