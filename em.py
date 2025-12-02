#!/usr/bin/env python3
import os
if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
    os.environ["QT_QPA_PLATFORM"] = "xcb"

import sys
import pickle
import socket
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox, QScrollArea, QFrame, QCheckBox,
    QTextEdit, QSizePolicy, QLineEdit, QCompleter
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QStringListModel
from PySide6.QtGui import QFont, QPixmap

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import base64
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from openai import OpenAI
from dotenv import load_dotenv
import os
import time
import re
from pathlib import Path

# Use writable config directory - MUST BE BEFORE load_dotenv()
CONFIG_DIR = Path.home() / ".config" / "photon"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Load .env from config directory
load_dotenv(CONFIG_DIR / '.env')

# --- AUTO-SET DEFAULT IPC SOCKET PATH IF NOT PROVIDED ---
if "PHOTON_IPC" not in os.environ or not os.environ["PHOTON_IPC"].strip():
    os.environ["PHOTON_IPC"] = "unix:///tmp/photon"

SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/userinfo.profile']

TOKEN_FILE = str(CONFIG_DIR / 'token.pickle')
CACHE_FILE = str(CONFIG_DIR / 'email_cache.pickle')
APP_START_TIME_FILE = str(CONFIG_DIR / 'app_start_time.txt')
CONTACTS_CACHE_FILE = str(CONFIG_DIR / 'contacts_cache.pickle')
USER_PROFILE_CACHE_FILE = str(CONFIG_DIR / 'user_profile_cache.pickle')


# IPC receiver for messages from face
class IPCReceiver(QThread):
    message_received = Signal(str, str)  # type, content

    def __init__(self):
        super().__init__()
        self.running = True
        self.socket = None

    def run(self):
        """Listen for IPC messages from the face"""
        ipc_env = os.environ.get("PHOTON_IPC", "")

        if ipc_env.startswith("unix://"):
            socket_path = ipc_env[len("unix://"):]
            try:
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                try:
                    os.unlink(socket_path)
                except:
                    pass
                self.socket.bind(socket_path)

                while self.running:
                    try:
                        data, addr = self.socket.recvfrom(4096)
                        message = data.decode('utf-8')
                        if '\t' in message:
                            msg_type, content = message.split('\t', 1)
                            self.message_received.emit(msg_type, content)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self.running:
                            print(f"IPC receive error: {e}")
            except Exception as e:
                print(f"Failed to create IPC socket: {e}")
        elif ipc_env.startswith("udp://"):
            # Handle UDP if needed
            pass

    def stop(self):
        self.running = False
        if self.socket:
            self.socket.close()


class ComposeAndSendThread(QThread):
    success = Signal(dict)   # full Gmail message resource
    error = Signal(str)

    def __init__(self, credentials, openai_client, short_text, current_email_context, thread_id, user_name=None):
        super().__init__()
        self.credentials = credentials
        self.openai_client = openai_client
        self.short_text = short_text
        self.current_email_context = current_email_context
        self.thread_id = thread_id
        self.user_name = user_name or "Me"

    def run(self):
        try:
            import email.utils

            # Use current email body as context excerpt
            original_body = self.current_email_context.get("body", "")
            short_body = original_body[-400:]

            # GPT rewrite of user's short reply
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an email writing assistant. Expand the user's short message into a natural reply.

RULES:
- if avaible and you can surely infer tile of sender, start with title usern gave you ifs example professor, or doctor etc if you can infer only or was give to you by the inputs, dont make it up on your own  and a greeting using the sender's name if available.
- Must be short, simple, friendly.
- dont use intro Hi There, use Hi + (Name or title or nothing), not respetcful!
- No signatures.
-must used prnoun the sender used dont add new pronouce
- No subject line.
-make sure to maintain senders vibe and don't add extra info sender sent
- greet lastely like email say thank yoou or have good one etc depending on vibe
- Sign off with just the user's name provided below
- Sign off with just the user's name provided below

"""
                    },
                    {
                        "role": "user",
                        "content": f"The sender's name is: there\n"
                                   f"Original email excerpt: {short_body}\n"
                                   f"User wants to reply with: {self.short_text}"
                                   f"User's name to sign off with: {self.user_name}"
                    }
                ],
                max_tokens=150,
                temperature=0.5
            )

            expanded_text = response.choices[0].message.content.strip()

            # Build Gmail service
            service = build('gmail', 'v1', credentials=self.credentials)

            # Fetch original FULL message to get proper headers for reply-all + threading
            orig_msg_id = self.current_email_context.get("message_id")
            orig_full = None
            headers = []

            if orig_msg_id:
                orig_full = service.users().messages().get(
                    userId='me',
                    id=orig_msg_id,
                    format='full'
                ).execute()
                headers = orig_full.get("payload", {}).get("headers", [])

            def get_header(name):
                for h in headers:
                    if h.get("name", "").lower() == name.lower():
                        return h.get("value", "")
                return ""

            # Subject
            header_subject = get_header("Subject")
            subject = header_subject or self.current_email_context.get("subject", "").strip()
            if not subject:
                subject = "Re: (no subject)"
            if not subject.lower().startswith("re:"):
                subject = "Re: " + subject

            # Reply-all recipients: From + To + Cc of the latest message
            from_hdr = get_header("From")
            to_hdr = get_header("To")
            cc_hdr = get_header("Cc")

            all_addrs = []
            for hdr in (from_hdr, to_hdr, cc_hdr):
                if hdr:
                    all_addrs.extend(email.utils.getaddresses([hdr]))

            # Deduplicate
            seen = set()
            recipients = []
            for name, addr in all_addrs:
                addr = addr.strip()
                if addr and addr not in seen:
                    seen.add(addr)
                    recipients.append(addr)

            # Fallback: if no recipients, at least the From address
            if not recipients and from_hdr:
                _, sender_email = email.utils.parseaddr(from_hdr)
                if sender_email:
                    recipients.append(sender_email)

            # Build MIME reply
            msg = MIMEText(expanded_text)
            if recipients:
                msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject

            # Threading headers
            message_id_header = get_header("Message-ID")
            refs_header = get_header("References")
            if message_id_header:
                msg["In-Reply-To"] = message_id_header
                if refs_header:
                    msg["References"] = refs_header + " " + message_id_header
                else:
                    msg["References"] = message_id_header
            elif "message_id" in self.current_email_context:
                mid = self.current_email_context["message_id"]
                msg["In-Reply-To"] = f"<{mid}>"
                msg["References"] = f"<{mid}>"

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

            body = {'raw': raw}
            if self.thread_id:
                body['threadId'] = self.thread_id  # ensures Gmail keeps it in same conversation

            sent = service.users().messages().send(
                userId='me',
                body=body
            ).execute()

            self.success.emit(sent)

        except Exception as e:
            self.error.emit(str(e))
# ============================
# NEW: Full Compose Thread
# ============================
class AIComposeThread(QThread):
    success = Signal(str, str)   # subject, body
    error = Signal(str)

    def __init__(self, openai_client, prompt_text, user_name=None):
        super().__init__()
        self.openai_client = openai_client
        self.prompt_text = prompt_text
        self.user_name = user_name or "Me"


    def run(self):
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": f"""You write complete emails,  .

    Return output EXACTLY like this:
    SUBJECT: <one-line subject>
    BODY:
    <full body text>

    Rules:
    -never add extra info just make it polite and full
    - Sign off with the user's name: {self.user_name}
    - Never place BODY on same line as SUBJECT."""
                    },
                    {"role": "user", "content": self.prompt_text}
                ],
                max_tokens=350,
                temperature=0.3,
            )

            full = response.choices[0].message.content.strip()

            # ---- ROBUST SUBJECT EXTRACTION ----
            subject = "No subject"
            body = full

            # Find SUBJECT line safely
            lines = full.splitlines()
            for idx, line in enumerate(lines):
                if line.upper().startswith("SUBJECT:"):
                    subject = line[len("SUBJECT:"):].strip()

                    # Body is everything after a line starting with BODY:
                    for j in range(idx + 1, len(lines)):
                        if lines[j].upper().startswith("BODY"):
                            body = "\n".join(lines[j + 1:]).strip()
                            break
                    break

            self.success.emit(subject, body)

        except Exception as e:
            self.error.emit(str(e))


class ComposeBodyThread(QThread):
    """Turns a short line (from face.py) into a full email body for compose mode."""
    success = Signal(str)
    error = Signal(str)

    def __init__(self, openai_client, short_text):
        super().__init__()
        self.openai_client = openai_client
        self.short_text = short_text

    def run(self):
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an email writing assistant.

Expand the user's short note into a natural email.

Rules:
- Keep it short, simple, friendly.
- No signature.
- No subject line.
- Keep the same vibe and details the user gave, don't add new info.
- End with a light thanks / well wish if it fits the user's tone.
-End the body with a sign-off and the user's name: {self.user_name}

"""
                    },
                    {
                        "role": "user",
                        "content": f"User wants to send this email:\n{self.short_text}"
                    }
                ],
                max_tokens=220,
                temperature=0.5
            )
            expanded = response.choices[0].message.content.strip()
            self.success.emit(expanded)
        except Exception as e:
            self.error.emit(str(e))


class SendNewEmailThread(QThread):
    """Send a brand new email (not a reply)."""
    success = Signal(dict)
    error = Signal(str)

    def __init__(self, credentials, to_addrs, subject, body):
        super().__init__()
        self.credentials = credentials
        self.to_addrs = to_addrs
        self.subject = subject
        self.body = body

    def run(self):
        try:
            service = build('gmail', 'v1', credentials=self.credentials)
            msg = MIMEText(self.body)
            msg['To'] = self.to_addrs
            msg['Subject'] = self.subject if self.subject.strip() else "(no subject)"

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            sent = service.users().messages().send(
                userId='me',
                body={'raw': raw}
            ).execute()
            self.success.emit(sent)
        except Exception as e:
            self.error.emit(str(e))


class EmailFetchThread(QThread):
    success = Signal(list, str)
    error = Signal(str)

    def __init__(self, credentials, unread_only=True, max_results=5, page_token=None, after_timestamp=None):
        super().__init__()
        self.credentials = credentials
        self.unread_only = unread_only
        self.max_results = max_results
        self.page_token = page_token
        self.after_timestamp = after_timestamp

    def run(self):
        try:
            service = build('gmail', 'v1', credentials=self.credentials)
            query_parts = []
            if self.unread_only:
                query_parts.append('is:unread')
            if self.after_timestamp:
                dt = datetime.fromtimestamp(self.after_timestamp)
                query_parts.append(f'after:{dt.strftime("%Y/%m/%d")}')
            query = ' '.join(query_parts)

            params = {
                'userId': 'me',
                'maxResults': self.max_results,
                'labelIds': ['INBOX']
            }
            if query:
                params['q'] = query
            if self.page_token:
                params['pageToken'] = self.page_token

            results = service.users().threads().list(**params).execute()

            threads = results.get('threads', [])
            next_page_token = results.get('nextPageToken', None)
            emails_list = []

            for thread in threads:
                thread_detail = service.users().threads().get(
                    userId='me',
                    id=thread['id'],
                    format='full'
                ).execute()

                messages = thread_detail.get('messages', [])
                thread_emails = []

                for msg in messages:
                    headers = msg['payload']['headers']
                    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                    from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                    to_email = next((h['value'] for h in headers if h['name'] == 'To'), '')
                    date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                    is_unread = 'UNREAD' in msg.get('labelIds', [])
                    message_id = msg['id']

                    body = ""
                    images = []

                    def extract_parts(payload):
                        nonlocal body, images
                        if 'parts' in payload:
                            for part in payload['parts']:
                                mime_type = part.get('mimeType', '')
                                if 'parts' in part:
                                    extract_parts(part)
                                elif mime_type == 'text/html' and not body:
                                    if 'data' in part['body']:
                                        body = base64.urlsafe_b64decode(
                                            part['body']['data']
                                        ).decode('utf-8', errors='ignore')
                                elif mime_type == 'text/plain' and not body:
                                    if 'data' in part['body']:
                                        body = base64.urlsafe_b64decode(
                                            part['body']['data']
                                        ).decode('utf-8', errors='ignore')
                                elif mime_type.startswith('image/'):
                                    if 'data' in part['body']:
                                        images.append(base64.urlsafe_b64decode(part['body']['data']))
                                    elif 'attachmentId' in part['body']:
                                        try:
                                            attachment = service.users().messages().attachments().get(
                                                userId='me',
                                                messageId=msg['id'],
                                                id=part['body']['attachmentId']
                                            ).execute()
                                            images.append(base64.urlsafe_b64decode(attachment['data']))
                                        except:
                                            pass
                        else:
                            if 'body' in payload and 'data' in payload['body']:
                                if payload.get('mimeType', '') == 'text/html':
                                    body = base64.urlsafe_b64decode(
                                        payload['body']['data']
                                    ).decode('utf-8', errors='ignore')
                                elif payload.get('mimeType', '') == 'text/plain' and not body:
                                    body = base64.urlsafe_b64decode(
                                        payload['body']['data']
                                    ).decode('utf-8', errors='ignore')

                    extract_parts(msg['payload'])

                    def clean_email_body(text):
                        if not text:
                            return text
                        markers = [
                            '\nOn ', '\n>', '\n> ', '\nFrom:',
                            '\n-----Original Message-----',
                            '\n________________________________',
                            '\n---'
                        ]
                        earliest = len(text)
                        for m in markers:
                            pos = text.find(m)
                            if pos != -1 and pos < earliest:
                                earliest = pos
                        if earliest < len(text):
                            text = text[:earliest].strip()
                        return text

                    body = clean_email_body(body)

                    thread_emails.append({
                        'subject': subject,
                        'from': from_email,
                        'to': to_email,
                        'date': date,
                        'body': body if body else "[No text content]",
                        'images': images,
                        'is_unread': is_unread,
                        'message_id': message_id
                    })

                # Most recent first
                thread_emails.reverse()

                emails_list.append({
                    'is_thread': len(thread_emails) > 1,
                    'thread_count': len(thread_emails),
                    'messages': thread_emails,
                    'thread_id': thread['id']
                })

            self.success.emit(emails_list, next_page_token)

        except Exception as e:
            self.error.emit(f"Error fetching emails: {str(e)}")


class MarkReadThread(QThread):
    success = Signal()
    error = Signal(str)

    def __init__(self, credentials, message_ids):
        super().__init__()
        self.credentials = credentials
        self.message_ids = message_ids

    def run(self):
        try:
            service = build('gmail', 'v1', credentials=self.credentials)
            for message_id in self.message_ids:
                service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()
            self.success.emit()
        except Exception as e:
            self.error.emit(f"Error marking as read: {str(e)}")


class OAuthLoginThread(QThread):
    success = Signal(object)
    error = Signal(str)

    def __init__(self, client_config):
        super().__init__()
        self.client_config = client_config

    def run(self):
        try:
            creds = None
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, 'rb') as token:
                    creds = pickle.load(token)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_config(
                        self.client_config, SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                with open(TOKEN_FILE, 'wb') as token:
                    pickle.dump(creds, token)

            self.success.emit(creds)
        except Exception as e:
            self.error.emit(f"Authentication error: {str(e)}")


class SummarizeThread(QThread):
    success = Signal(str, str)
    error = Signal(str, str)

    def __init__(self, openai_client, email_body, subject, message_id):
        super().__init__()
        self.openai_client = openai_client
        self.email_body = email_body
        self.subject = subject
        self.message_id = message_id

    def run(self):
        try:
            word_count = len(self.email_body.split())

            if word_count < 50:
                bullet_count = "1 to 2"
                words_per_bullet = "6"
                max_tokens = 50
            elif word_count < 150:
                bullet_count = "1 to 3"
                words_per_bullet = "8"
                max_tokens = 60
            elif word_count < 300:
                bullet_count = "1 to 4"
                words_per_bullet = "8"
                max_tokens = 80
            elif word_count < 500:
                bullet_count = "2 to 5"
                words_per_bullet = "10"
                max_tokens = 100
            else:
                bullet_count = "2 to 6"
                words_per_bullet = "10"
                max_tokens = 120

            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content":
f"""You are an ultra-literal email summarizer.

RULES:
1. Write {bullet_count} bullets, each {words_per_bullet} words or fewer.
2. Start each bullet with •
3. Do NOT infer anything.
4. MATCH the sender's vibe and wording. 
   - If the email uses casual words, your summary must also use casual words.
   - If the email uses simple vocabulary, your summary must also use simple vocabulary.
   - Never use words that sound more formal or sophisticated than the sender's.
5. Only restate what is actually said, using the same tone and style.
6. If the email is short, the summary must be short.
7, if there is location include it
8. If there's a deadline, include it
9. If there's a decision/update, include it

Format: Just bullet points, nothing else."""
                    },
                    {
                        "role": "user",
                        "content": f"Subject: {self.subject}\n\nEmail content:\n{self.email_body}"
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=30
            )
            summary = response.choices[0].message.content
            self.success.emit(self.message_id, summary)
        except Exception as e:
            self.error.emit(self.message_id, f"[Summary error: {str(e)}]")


class EmailReaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.credentials = None
        self.fetch_thread = None
        self.oauth_thread = None
        self.mark_read_thread = None
        self.compose_send_thread = None

        self.compose_mode = False
        self.compose_body_thread = None
        self.send_new_thread = None

        self.summarize_threads = []
        self.summarizing_messages = set()
        self.max_concurrent_summaries = 3
        self.active_summary_threads = []

        self.show_unread_only = True
        self.show_summary = True

        self.openai_client = None
        self.email_cache = {}
        self.app_start_timestamp = None

        self.sent_replies = []

        self.ipc_receiver = None

        self.temp_threads = []
        self.locally_read_thread_ids = set()  # Threads user has viewed in this session

        self.known_addresses = {}
        self.suggestion_list = []  # Add this line
        self.contacts_data = []  # Structured contact data for search

        self.user_first_name = None

        self.recipient_model = QStringListModel()
        self.recipient_completer = None

        self.load_app_start_time()
        self.load_cache()
        self.setup_openai()
        self.init_ui()
        self.setup_ipc()

        try:
            if "EM_WINDOW_X" in os.environ and "EM_WINDOW_Y" in os.environ:
                x = int(os.environ["EM_WINDOW_X"])
                y = int(os.environ["EM_WINDOW_Y"])
                QTimer.singleShot(100, lambda: self.move(x, y))
        except:
            pass

        self.auto_authenticate()

    def setup_ipc(self):
        """Setup IPC receiver to get messages from face"""
        self.ipc_receiver = IPCReceiver()
        self.ipc_receiver.message_received.connect(self.handle_ipc_message)
        self.ipc_receiver.start()

    def handle_ipc_message(self, msg_type, content):

        # NEW: a compose request from face
        if msg_type == "COMPOSE":
            # Ensure UI is in compose screen
            self.enter_compose_mode()
            self.generate_ai_compose(content)
            return

        # Existing behavior (reply)
        if msg_type == "SUBMIT":
            if self.compose_mode:
                self.generate_ai_compose(content)
                return

            if not self.emails_data or self.current_email_index >= len(self.emails_data):
                return

            thread = self.emails_data[self.current_email_index]
            messages = thread['messages']
            if not messages:
                return

            target_message = messages[0]
            self.compose_and_send_reply(content, target_message, thread['thread_id'])

    def compose_and_send_reply(self, short_text, current_email, thread_id):
        """Compose and send a reply based on short text input"""
        if not self.credentials or not self.openai_client:
            self.show_reply_notification("Cannot send: Not authenticated or OpenAI not configured")
            return

        self.compose_send_thread = ComposeAndSendThread(
            self.credentials,
            self.openai_client,
            short_text,
            current_email,
            thread_id,
            self.user_first_name
        )
        self.compose_send_thread.success.connect(self.on_reply_sent)
        self.compose_send_thread.error.connect(self.on_reply_error)
        self.compose_send_thread.start()

        self.show_reply_notification("Composing and sending reply...")

    def on_reply_sent(self, gmail_message):
        """
        Fetch full message body and insert real reply into thread.
        """
        if not self.emails_data or self.current_email_index >= len(self.emails_data):
            return

        service = build('gmail', 'v1', credentials=self.credentials)

        msg_id = gmail_message['id']
        full_msg = service.users().messages().get(
            userId='me',
            id=msg_id,
            format='full'
        ).execute()

        body = ""
        payload = full_msg.get("payload", {})

        def extract_body(p):
            nonlocal body
            if 'parts' in p:
                for part in p['parts']:
                    extract_body(part)
            else:
                if p.get('mimeType') == 'text/plain' and 'data' in p.get('body', {}):
                    body = base64.urlsafe_b64decode(p['body']['data']).decode('utf-8', errors='ignore')

        extract_body(payload)

        if not body:
            body = "(no text content)"

        subject = "Re: (no subject)"
        headers = full_msg['payload'].get('headers', [])
        for h in headers:
            if h['name'].lower() == 'subject':
                subject = h['value']
                break

        new_msg = {
            'subject': subject,
            'from': "Me <me>",
            'date': full_msg.get('internalDate', ''),
            'body': body,
            'images': [],
            'is_unread': False,
            'message_id': msg_id,
            'to': ''
        }

        thread = self.emails_data[self.current_email_index]
        thread['messages'].insert(0, new_msg)
        thread['thread_count'] = len(thread['messages'])
        thread['is_thread'] = thread['thread_count'] > 1

        self.display_current_email()
        self.show_reply_notification("Reply sent.")

    def on_reply_error(self, error_msg):
        self.show_reply_notification(f"Error: {error_msg}")

    def show_reply_notification(self, message):
        if hasattr(self, 'notification_label'):
            self.notification_label.setText(message)
            self.notification_label.setVisible(True)
            QTimer.singleShot(3000, lambda: self.notification_label.setVisible(False))

    def load_app_start_time(self):
        if os.path.exists(APP_START_TIME_FILE):
            with open(APP_START_TIME_FILE, 'r') as f:
                self.app_start_timestamp = float(f.read().strip())
        else:
            self.app_start_timestamp = datetime.now().timestamp()
            with open(APP_START_TIME_FILE, 'w') as f:
                f.write(str(self.app_start_timestamp))

    def load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'rb') as f:
                    self.email_cache = pickle.load(f)
                now = datetime.now().timestamp()
                old_keys = [k for k, v in self.email_cache.items()
                            if now - v.get('timestamp', 0) > 30 * 24 * 3600]
                for k in old_keys:
                    del self.email_cache[k]
                if old_keys:
                    self.save_cache()
            except:
                self.email_cache = {}

    def save_cache(self):
        try:
            with open(CACHE_FILE, 'wb') as f:
                pickle.dump(self.email_cache, f)
        except:
            pass

    def setup_openai(self):
        try:
            api_key = os.environ.get('OPENAI_API_KEY')
            
            if api_key:
                self.openai_client = OpenAI(api_key=api_key)
                print("OpenAI client initialized from .env")
            else:
                print("No OPENAI_API_KEY in .env")
                self.openai_client = None
        except Exception as e:
            print(f"OpenAI setup failed: {e}")
            self.openai_client = None

    def cleanup_finished_threads(self):
        still_running = []
        for t in self.active_summary_threads:
            if t.isRunning():
                still_running.append(t)
            else:
                t.deleteLater()
        self.active_summary_threads = still_running

        if len(self.active_summary_threads) > self.max_concurrent_summaries:
            excess = len(self.active_summary_threads) - self.max_concurrent_summaries
            for i in range(excess):
                thread = self.active_summary_threads[0]
                thread.quit()
                thread.wait(100)
                thread.deleteLater()
                self.active_summary_threads.pop(0)

    def prefetch_upcoming_summaries(self):
        if not self.openai_client:
            return

        self.cleanup_finished_threads()

        for offset in range(1, 4):
            next_index = self.current_email_index + offset
            if next_index >= len(self.emails_data):
                break

            thread_data = self.emails_data[next_index]

            for message in thread_data['messages']:
                message_id = message['message_id']

                if message_id in self.email_cache and 'summary' in self.email_cache[message_id]:
                    continue
                if message_id in self.summarizing_messages:
                    continue

                if offset != 1 and len(self.active_summary_threads) >= self.max_concurrent_summaries:
                    return

                self.summarizing_messages.add(message_id)

                t = SummarizeThread(
                    self.openai_client,
                    message['body'],
                    message['subject'],
                    message_id
                )
                t.success.connect(self.on_summary_success)
                t.error.connect(self.on_summary_error)
                t.finished.connect(self.cleanup_finished_threads)
                self.active_summary_threads.append(t)
                t.start()

    def summarize_email_async(self, email_body, subject, message_id):
        if message_id in self.email_cache and 'summary' in self.email_cache[message_id]:
            return self.email_cache[message_id]['summary']

        if message_id in self.summarizing_messages:
            return "[Generating summary...]"

        if not self.openai_client:
            return "[OpenAI not configured - add your API key]"

        self.cleanup_finished_threads()

        self.summarizing_messages.add(message_id)

        t = SummarizeThread(self.openai_client, email_body, subject, message_id)
        t.success.connect(self.on_summary_success)
        t.error.connect(self.on_summary_error)
        t.finished.connect(self.cleanup_finished_threads)
        self.active_summary_threads.append(t)
        t.start()

        return "[Generating summary...]"

    def on_summary_success(self, message_id, summary):
        self.summarizing_messages.discard(message_id)

        if message_id not in self.email_cache:
            self.email_cache[message_id] = {}
        self.email_cache[message_id]['summary'] = summary
        self.email_cache[message_id]['timestamp'] = datetime.now().timestamp()
        self.save_cache()

        if self.emails_data and self.current_email_index < len(self.emails_data):
            thread = self.emails_data[self.current_email_index]
            for msg in thread['messages']:
                if msg['message_id'] == message_id:
                    self.display_current_email()
                    break

    def on_summary_error(self, message_id, error_msg):
        self.summarizing_messages.discard(message_id)

        if message_id not in self.email_cache:
            self.email_cache[message_id] = {}

        self.email_cache[message_id]['summary'] = error_msg
        self.email_cache[message_id]['timestamp'] = datetime.now().timestamp()
        self.save_cache()

        if self.emails_data and self.current_email_index < len(self.emails_data):
            thread = self.emails_data[self.current_email_index]
            for msg in thread['messages']:
                if msg['message_id'] == message_id:
                    self.display_current_email()
                    break

    def init_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint 
           # Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setWindowTitle("Gmail OAuth Reader")
        self.setFixedSize(700, 800)

        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(15)
        self.main_layout.setContentsMargins(30, 30, 30, 30)

        # notification label
        self.notification_label = QLabel()
        self.notification_label.setAlignment(Qt.AlignCenter)
        self.notification_label.setStyleSheet("""
            QLabel {
                background-color: rgba(100, 200, 100, 200);
                color: white;
                border-radius: 5px;
                padding: 10px;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        self.notification_label.setVisible(False)
        self.main_layout.addWidget(self.notification_label)

        top_controls = QWidget()
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)

        toggle_style = """
            QPushButton {
                background-color: rgba(206, 212, 211, 200);
                color: black;
                border: 1px solid #000;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:checked {
                background-color: rgba(100, 150, 255, 200);
                color: white;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 230);
                border: 2px solid #000;
            }
            QPushButton:checked:hover {
                background-color: rgba(150, 200, 255, 255);
                border: 2px solid #000;
            }
        """

        new_all_container = QWidget()
        new_all_layout = QHBoxLayout()
        new_all_layout.setContentsMargins(0, 0, 0, 0)
        new_all_layout.setSpacing(0)

        self.new_button = QPushButton("New")
        self.new_button.setFixedSize(60, 30)
        self.new_button.setCheckable(True)
        self.new_button.setChecked(True)
        self.new_button.clicked.connect(lambda: self.switch_to_new())
        self.new_button.setStyleSheet(toggle_style + """
            QPushButton {
                border-top-left-radius: 5px;
                border-bottom-left-radius: 5px;
                border-right: none;
            }
        """)

        self.all_button = QPushButton("All")
        self.all_button.setFixedSize(60, 30)
        self.all_button.setCheckable(True)
        self.all_button.clicked.connect(lambda: self.switch_to_all())
        self.all_button.setStyleSheet(toggle_style + """
            QPushButton {
                border-top-right-radius: 5px;
                border-bottom-right-radius: 5px;
            }
        """)

        new_all_layout.addWidget(self.new_button)
        new_all_layout.addWidget(self.all_button)
        new_all_container.setLayout(new_all_layout)
        top_layout.addWidget(new_all_container)

        # ---- Compose button (C) in red between All and Refresh ----
        self.compose_button = QPushButton("C")
        self.compose_button.setFixedSize(40, 30)
        self.compose_button.setToolTip("Compose new email")
        self.compose_button.clicked.connect(self.start_compose)
        self.compose_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 80, 80, 220);
                color: white;
                border-radius: 5px;
                font-weight: bold;
                font-size: 16px;
                border: 1px solid #000;
            }
            QPushButton:hover {
                background-color: rgba(255, 180, 180, 255);
                border: 2px solid #000;
            }
        """)


        top_layout.addWidget(self.compose_button)

        self.refresh_button = QPushButton("↻")
        self.refresh_button.setFixedSize(40, 30)
        self.refresh_button.setToolTip("Refresh emails")
        self.refresh_button.clicked.connect(self.on_refresh_clicked)
        self.refresh_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 200, 100, 150);
                color: black;
                border: 1px solid #000;
                border-radius: 5px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: rgba(150, 255, 150, 255);
                border: 2px solid #000;
            }
        """)
        top_layout.addWidget(self.refresh_button)

        top_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 100, 100, 200);
                color: black;
                border: none;
                border-radius: 3px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 150, 150, 255);
                border: 2px solid #000;
            }
        """)
        controls = QWidget()
        cl = QHBoxLayout()
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(close_btn)
        controls.setLayout(cl)
        top_layout.addWidget(controls)

        top_controls.setLayout(top_layout)
        self.main_layout.addWidget(top_controls)

        # LOGIN SECTION
        self.login_widget = QWidget()
        login_layout = QVBoxLayout()

        info = QLabel(
" "        )
        info.setFont(QFont("Arial", 10))
        info.setWordWrap(True)
        login_layout.addWidget(info)
        login_layout.addSpacing(20)

        self.login_button = QPushButton("Login with Google")
        self.login_button.setFont(QFont("Arial", 12, QFont.Bold))
        self.login_button.setFixedHeight(50)
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.clicked.connect(self.start_oauth)
        self.login_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(206, 212, 211, 200);
                color: black;
                border-radius: 5px;
            }
        """)
        login_layout.addWidget(self.login_button)

        self.fetch_button = QPushButton("Fetch Emails")
        self.fetch_button.setFont(QFont("Arial", 12, QFont.Bold))
        self.fetch_button.setFixedHeight(50)
        self.fetch_button.clicked.connect(self.fetch_emails)
        self.fetch_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(206, 212, 211, 200);
                color: black;
                border-radius: 5px;
            }
        """)
        login_layout.addWidget(self.fetch_button)

        self.clear_token_button = QPushButton("Clear Token & Re-authenticate")
        self.clear_token_button.setFont(QFont("Arial", 10))
        self.clear_token_button.setFixedHeight(40)
        self.clear_token_button.clicked.connect(self.clear_token_and_reauth)
        self.clear_token_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 152, 0, 200);
                color: black;
                border-radius: 5px;
            }
        """)
        login_layout.addWidget(self.clear_token_button)

        self.status_label = QLabel("Checking authentication...")
        self.status_label.setFont(QFont("Arial", 10))
        self.status_label.setAlignment(Qt.AlignCenter)
        login_layout.addWidget(self.status_label)

        self.login_widget.setLayout(login_layout)
        self.main_layout.addWidget(self.login_widget)

        # EMAIL DISPLAY SECTION
        self.email_display_widget = QWidget()
        self.email_display_widget.setVisible(False)
        display_layout = QVBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(650)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: rgba(255,255,255,150);
                border-radius: 10px;
                padding: 10px;
            }
        """)

        self.email_container = QWidget()
        self.email_container_layout = QVBoxLayout()
        self.email_container_layout.setContentsMargins(10, 10, 10, 0)
        self.email_container.setLayout(self.email_container_layout)
        scroll.setWidget(self.email_container)

        display_layout.addWidget(scroll)

        nav_container = QWidget()
        nav_layout = QVBoxLayout()
        nav_buttons = QHBoxLayout()

        self.prev_button = QPushButton("◄ Previous")
        self.prev_button.setFixedHeight(40)
        self.prev_button.clicked.connect(self.show_previous_email)
        self.prev_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(206,212,211,200);
                color: black;
                border-radius: 5px;
                padding-left: 50px;
                padding-right: 50px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 255);
                border: 2px solid #000;
            }
        """)
        nav_buttons.addWidget(self.prev_button)

        nav_buttons.addStretch()

        self.next_button = QPushButton("Next ►")
        self.next_button.setFixedHeight(40)
        self.next_button.clicked.connect(self.show_next_email)
        self.next_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(206,212,211,200);
                color: black;
                border-radius: 5px;
                padding-left: 50px;
                padding-right: 50px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 255);
                border: 2px solid #000;
            }
        """)
        nav_buttons.addWidget(self.next_button)

        nav_layout.addLayout(nav_buttons)
        nav_container.setLayout(nav_layout)
        display_layout.addWidget(nav_container)

        self.email_display_widget.setLayout(display_layout)
        self.main_layout.addWidget(self.email_display_widget)

        # ---- FIXED COMPOSE SECTION ----
        self.compose_widget = QWidget()
        self.compose_widget.setVisible(False)

        compose_layout = QVBoxLayout()
        compose_layout.setContentsMargins(0, 0, 0, 0)
        compose_layout.setSpacing(12)

        # ---------------- HEADER ----------------
        header_box = QWidget()
        header_box.setStyleSheet("background: rgba(206,212,211,200); border-radius: 6px;")
        hb = QVBoxLayout()
        hb.setContentsMargins(12, 12, 12, 12)
        hb.setSpacing(10)

        # SUBJECT
        row_sub = QHBoxLayout()
        label_sub = QLabel("<b>Subject:</b>")
        self.compose_subject_input = QLineEdit()
        self.compose_subject_input.setPlaceholderText("Subject")
        self.compose_subject_input.setFocusPolicy(Qt.StrongFocus)
        self.compose_subject_input.setStyleSheet("""
            QLineEdit {
                background: white;
                color: black;
                border-radius: 5px;
                padding: 6px 10px;
            }
        """)
        row_sub.addWidget(label_sub)
        row_sub.addWidget(self.compose_subject_input)
        hb.addLayout(row_sub)

        # TO
        row_to = QHBoxLayout()
        label_to = QLabel("<b>To:</b>")
        self.compose_to_input = QLineEdit()
        self.compose_to_input.setPlaceholderText("Recipient email...")
        self.compose_to_input.setFocusPolicy(Qt.StrongFocus)
        self.compose_to_input.setStyleSheet("""
            QLineEdit {
                background: white;
                color: black;
                border-radius: 5px;
                padding: 6px 10px;
            }
        """)
        row_to.addWidget(label_to)
        row_to.addWidget(self.compose_to_input)
        hb.addLayout(row_to)

        header_box.setLayout(hb)
        
        # Initialize autocomplete for recipient field
        self.setup_recipient_completer()
        compose_layout.addWidget(header_box)

        # ----------- CONTENT LABEL ----------
        lbl_content = QLabel("<b style='font-size:14px;'>Content:</b>")
        compose_layout.addWidget(lbl_content)

        # ----------- CONTENT BOX (NO SCROLLAREA WRAPPER!) ----------
        self.compose_body_edit = QTextEdit()
        self.compose_body_edit.setPlaceholderText("Write your message or use face input…")
        self.compose_body_edit.setFocusPolicy(Qt.StrongFocus)
        self.compose_body_edit.setStyleSheet("""
            QTextEdit {
                background: rgba(30,30,30,220);
                color: white;
                padding: 18px;
                border-radius: 6px;
                border: 1px solid rgba(200,200,150,200);
                font-size: 18px;
            }
        """)
        self.compose_body_edit.setMinimumHeight(480)
        compose_layout.addWidget(self.compose_body_edit)

        # -------------- SEND BUTTON ---------------
        send_row = QHBoxLayout()
        send_row.addStretch()
        self.send_button = QPushButton("✈")
        self.send_button.setFixedSize(50, 50)
        self.send_button.clicked.connect(self.send_new_email)
        self.send_button.setStyleSheet("""
            QPushButton {
                background: white;
                color: black;
                border-radius: 25px;
                border: 2px solid black;
                font-size: 22px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #f0f0f0;
            }
        """)
        send_row.addWidget(self.send_button)

        compose_layout.addLayout(send_row)


        self.compose_widget.setLayout(compose_layout)
        self.main_layout.addWidget(self.compose_widget)

        self.current_email_index = 0
        self.emails_data = []
        self.page_token = None
        self.is_loading_more = False
        self.has_more_emails = True

        self.new_emails_count = 0
        self.viewed_email_ids = set()
        self.last_navigation_time = 0
        self.navigation_cooldown = 0.3

        self.new_email_check_timer = QTimer()
        self.new_email_check_timer.timeout.connect(self.check_for_new_emails)
        self.new_email_check_timer.setInterval(60000)

        self.main_layout.addStretch()
        central.setLayout(self.main_layout)

        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: transparent; }
        """)

    def _cleanup_temp_thread(self, thread):
        try:
            if thread in self.temp_threads:
                self.temp_threads.remove(thread)
            thread.deleteLater()
        except:
            pass

    def check_for_new_emails(self):
        pass

    def on_new_emails_checked(self, new_emails, next_page_token):
        if not new_emails or not self.emails_data:
            return

        # Get all thread IDs we already have
        current_ids = {e['thread_id'] for e in self.emails_data}
        
        # Get all thread IDs we've already viewed/read
        viewed_ids = self.viewed_email_ids | self.locally_read_thread_ids
        
        # Only add threads that are:
        # 1. Not already in our list
        # 2. Not already viewed/read by user
        fresh = [
            t for t in new_emails 
            if t['thread_id'] not in current_ids 
            and t['thread_id'] not in viewed_ids
        ]

        if not fresh:
            return

        # Add to END of list, not beginning (prevents index shifting issues)
        self.emails_data.extend(fresh)
        self.new_emails_count += len(fresh)
        
        self.update_next_button()
        # DON'T call display_current_email() here - it causes the "pop up" issue
        self.update_recipient_suggestions()

    def update_next_button(self):
        if self.show_unread_only:
            # In "New" mode - show remaining unviewed emails
            total = len(self.emails_data)
            # Remaining = total - current position - 1 (since current is being viewed)
            remaining = total - self.current_email_index - 1
            if remaining > 0:
                self.next_button.setText(f"Next ({remaining} new) ►")
            else:
                self.next_button.setText("Next ►")
        else:
            # In "All" mode - only show NEW count if there are actually new emails
            if self.new_emails_count > 0:
                self.next_button.setText(f"Next ({self.new_emails_count} NEW) ►")
            else:
                self.next_button.setText("Next ►")


    def start_compose(self):
        if not self.credentials:
            QMessageBox.warning(self, "Not Logged In", "Please login first to compose a new email.")
            return
        self.enter_compose_mode()

    def enter_compose_mode(self):
        self.compose_mode = True
        self.login_widget.setVisible(False)
        self.email_display_widget.setVisible(False)
        self.compose_widget.setVisible(True)

        self.compose_subject_input.clear()
        self.compose_to_input.clear()
        self.compose_body_edit.clear()

        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)

        QTimer.singleShot(100, lambda: self.compose_to_input.setFocus())

    def exit_compose_mode(self):
        self.compose_mode = False
        self.compose_widget.setVisible(False)
        self.email_display_widget.setVisible(True)

        # Re-enable navigation based on current index
        if not self.show_unread_only:
            self.prev_button.setEnabled(self.current_email_index > 0)
        else:
            self.prev_button.setEnabled(False)

        self.next_button.setEnabled(
            self.current_email_index < len(self.emails_data) - 1 or
            (self.has_more_emails and not self.is_loading_more)
        )
        self.update_next_button()

    def generate_compose_body(self, short_text):
        if not self.openai_client:
            self.show_reply_notification("Cannot use AI: OpenAI not configured")
            return
        if not short_text.strip():
            return

        if self.compose_body_thread and self.compose_body_thread.isRunning():
            self.show_reply_notification("Already writing draft, please wait...")
            return

        self.compose_body_thread = ComposeBodyThread(self.openai_client, short_text)
        self.compose_body_thread.success.connect(self.on_compose_body_ready)
        self.compose_body_thread.error.connect(self.on_compose_body_error)
        self.compose_body_thread.start()
        self.show_reply_notification("Writing email from your text...")
        # --- NEW: full AI email generator for composing ---
    
    def generate_ai_compose(self, prompt_text):
        """Generate subject + body using GPT and fill compose UI."""
        if not self.openai_client:
            self.show_reply_notification("Cannot use AI: OpenAI not configured")
            return

        if not prompt_text.strip():
            return

        # Thread for GPT call
        thread = AIComposeThread(self.openai_client, prompt_text, self.user_first_name)
        thread.success.connect(self.on_ai_compose_ready)
        thread.error.connect(self.on_ai_compose_error)
        thread.start()

        self.temp_threads.append(thread)
        self.show_reply_notification("Writing full email...")


    def on_compose_body_ready(self, text):
        self.compose_body_edit.setPlainText(text)
        self.show_reply_notification("Draft updated.")
    
    # NEW: fill compose UI with AI result
    def on_ai_compose_ready(self, subject, body):
        print("===== AI COMPOSE DEBUG =====")
        print("SUBJECT RECEIVED FROM GPT:")
        print(repr(subject))
        print("BODY RECEIVED FROM GPT:")
        print(repr(body))
        print("========== END =============")

        # Delay until UI is rendered
        def _apply():
            print("===== APPLYING TO UI =====")
            print("Setting subject to:", repr(subject))
            print("Setting body to:", repr(body))

            self.compose_subject_input.setText(subject)
            self.compose_body_edit.setPlainText(body)

            self.show_reply_notification("Draft ready.")

        QTimer.singleShot(150, _apply)

    def on_ai_compose_error(self, msg):
        self.show_reply_notification(f"AI error: {msg}")


    def on_compose_body_error(self, error_msg):
        self.show_reply_notification(f"AI error: {error_msg}")



    def on_send_new_success(self, gmail_message):
        self.show_reply_notification("Email sent.")
        # Go back to inbox view after sending
        if self.emails_data:
            self.exit_compose_mode()
        else:
            # If no emails yet, hide compose, show login or fetch
            self.compose_mode = False
            self.compose_widget.setVisible(False)
            self.email_display_widget.setVisible(True)

    def on_send_new_error(self, error_msg):
        self.show_reply_notification(f"Send error: {error_msg}")



    def update_recipient_suggestions(self):
            """Build list of known addresses for To: auto-suggest from loaded emails."""
            import email.utils

            addrs = set(self.known_addresses)  # Keep existing contacts
            
            for thread in self.emails_data or []:
                for msg in thread['messages']:
                    from_hdr = msg.get('from', '')
                    to_hdr = msg.get('to', '')

                    for name, addr in email.utils.getaddresses([from_hdr]):
                        addr = addr.strip().lower()
                        if addr and '@' in addr:
                            addrs.add(addr)

                    if to_hdr:
                        for name, addr in email.utils.getaddresses([to_hdr]):
                            addr = addr.strip().lower()
                            if addr and '@' in addr:
                                addrs.add(addr)

            self.known_addresses = addrs
            self.recipient_model.setStringList(sorted(self.known_addresses))


    def setup_recipient_completer(self):
        """Setup autocomplete with dynamic search on each keystroke."""
        self.recipient_completer = QCompleter(self.recipient_model, self)
        self.recipient_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.recipient_completer.setFilterMode(Qt.MatchContains)
        self.recipient_completer.setMaxVisibleItems(15)
        self.compose_to_input.setCompleter(self.recipient_completer)
        
        # Connect textChanged for dynamic search on EVERY keystroke
        self.compose_to_input.textChanged.connect(self.on_recipient_text_changed)


    def fetch_all_gmail_contacts(self):
        """Fetch ALL emails from Gmail history and build structured contact list.
        Fetches 500 messages per batch, saves cache after each batch, and can resume from interruption.
        """
        import email.utils
        import time
        
        print("=" * 50)
        print("🔍 DEBUG: fetch_all_gmail_contacts() STARTED")
        print("=" * 50)
        
        # Check cache first - load existing contacts and check if complete
        print(f"DEBUG: Checking if cache exists at: {CONTACTS_CACHE_FILE}")
        cache_complete = self.load_contacts_cache()
        
        if cache_complete:
            print(f"✅ Cache is COMPLETE with {len(self.contacts_data)} contacts - no fetch needed")
            return
        
        # Check if we need to resume from a previous incomplete fetch
        resume_token = getattr(self, '_resume_page_token', None)
        if resume_token:
            print(f"🔄 Resuming from page_token: {resume_token[:20]}...")
        else:
            print("DEBUG: Starting fresh fetch (no resume token)")
        
        if not self.credentials:
            print("❌ DEBUG: No credentials! Cannot fetch contacts.")
            return
        
        print("DEBUG: Credentials OK, starting Gmail fetch...")
        print("🔄 Fetching emails from Gmail to build contact list (500 per batch)...")
        
        try:
            print("DEBUG: Building Gmail service...")
            service = build('gmail', 'v1', credentials=self.credentials)
            print("DEBUG: Gmail service built successfully")
            
            # Build contacts_dict from existing contacts_data (for resuming)
            contacts_dict = {}
            for contact in self.contacts_data:
                contacts_dict[contact["email"]] = {
                    "first": contact["first"],
                    "last": contact["last"],
                    "email": contact["email"]
                }
            print(f"DEBUG: Starting with {len(contacts_dict)} existing contacts")
            
            # Patterns to filter out junk/automated emails
            junk_patterns = [
                r'.*noreply.*', r'.*no-reply.*', r'.*donotreply.*', r'.*do-not-reply.*',
                r'.*bounce.*', r'.*mailer-daemon.*', r'.*postmaster.*',
                r'^[a-z0-9]{20,}@.*', r'.*@.*\.hubspotemail\.net.*',
                r'.*@.*sendgrid\.net.*', r'.*@.*mailchimp.*', r'.*@.*amazonses.*',
                r'.*@.*postmarkapp.*', r'.*@.*mailgun.*', r'.*=.*@.*',
                r'.*@notifications\..*', r'.*@alerts\..*', r'.*@updates\..*',
                r'.*@news\..*', r'.*@marketing\..*',
            ]
            
            def is_junk_email(addr):
                addr_lower = addr.lower()
                for pattern in junk_patterns:
                    if re.match(pattern, addr_lower):
                        return True
                local = addr_lower.split('@')[0]
                if len(local) > 30:
                    return True
                digit_count = sum(1 for c in local if c.isdigit())
                if digit_count > 10:
                    return True
                return False
            
            def parse_name(display_name, email_addr):
                """Parse first and last name from display name or email."""
                first, last = "", ""
                
                # Clean display name
                if display_name:
                    display_name = display_name.strip().strip('"').strip("'")
                    if '=' not in display_name and len(display_name) < 60:
                        parts = display_name.split()
                        if len(parts) >= 2:
                            first = parts[0].capitalize()
                            last = parts[-1].capitalize()
                        elif len(parts) == 1:
                            first = parts[0].capitalize()
                
                # Fallback: extract from email
                if not first and email_addr:
                    local = email_addr.split('@')[0]
                    if '.' in local:
                        parts = local.split('.')
                        first = parts[0].capitalize()
                        if len(parts) > 1:
                            last = parts[-1].capitalize()
                    elif '_' in local:
                        parts = local.split('_')
                        first = parts[0].capitalize()
                        if len(parts) > 1:
                            last = parts[-1].capitalize()
                    else:
                        first = local.capitalize()
                
                return first, last
            
            total_processed = 0
            batch_count = 0
            page_token = resume_token  # Start from resume token if available
            BATCH_SIZE = 500
            
            print("DEBUG: Starting message fetch loop...")
            
            while True:
                try:
                    batch_count += 1
                    batch_processed = 0
                    
                    # Fetch up to 500 messages per batch
                    while batch_processed < BATCH_SIZE:
                        params = {'userId': 'me', 'maxResults': min(500, BATCH_SIZE - batch_processed)}
                        if page_token:
                            params['pageToken'] = page_token
                        
                        print(f"DEBUG: Fetching messages (batch {batch_count}, processed so far: {total_processed})...")
                        results = service.users().messages().list(**params).execute()
                        messages = results.get('messages', [])
                        
                        print(f"DEBUG: Got {len(messages)} messages in this request")
                        
                        if not messages:
                            print("DEBUG: No more messages, fetch complete!")
                            page_token = None  # Mark as complete
                            break
                        
                        for msg_ref in messages:
                            try:
                                msg = service.users().messages().get(
                                    userId='me',
                                    id=msg_ref['id'],
                                    format='metadata',
                                    metadataHeaders=['From', 'To', 'Cc', 'Bcc']
                                ).execute()
                                
                                headers = msg.get('payload', {}).get('headers', [])
                                
                                for header in headers:
                                    header_name = header.get('name', '').lower()
                                    if header_name in ['from', 'to', 'cc', 'bcc']:
                                        value = header.get('value', '')
                                        if value:
                                            for display_name, addr in email.utils.getaddresses([value]):
                                                addr = addr.strip().lower()
                                                
                                                if not addr or '@' not in addr:
                                                    continue
                                                if is_junk_email(addr):
                                                    continue
                                                
                                                first, last = parse_name(display_name, addr)
                                                
                                                # Store or update contact
                                                if addr not in contacts_dict:
                                                    contacts_dict[addr] = {"first": first, "last": last, "email": addr}
                                                else:
                                                    # Update if we got better name info
                                                    if first and not contacts_dict[addr]["first"]:
                                                        contacts_dict[addr]["first"] = first
                                                    if last and not contacts_dict[addr]["last"]:
                                                        contacts_dict[addr]["last"] = last
                                                        
                            except Exception as msg_err:
                                # Skip individual message errors silently
                                continue
                        
                        batch_processed += len(messages)
                        total_processed += len(messages)
                        
                        page_token = results.get('nextPageToken')
                        if not page_token:
                            print("DEBUG: No nextPageToken, fetch complete!")
                            break
                        
                        time.sleep(0.05)  # Small delay between requests
                    
                    # END OF BATCH - Update contacts_data and save cache
                    print(f"   Batch {batch_count} complete: {total_processed} messages, {len(contacts_dict)} contacts")
                    
                    # Build contacts_data from contacts_dict
                    self.contacts_data = []
                    for addr, info in contacts_dict.items():
                        first = info["first"]
                        last = info["last"]
                        
                        if first and last:
                            display = f"{first} {last} ({addr})"
                        elif first:
                            display = f"{first} ({addr})"
                        else:
                            display = addr
                        
                        self.contacts_data.append({
                            "first": first,
                            "last": last,
                            "email": addr,
                            "display": display
                        })
                    
                    # Sort by first name, then last name
                    self.contacts_data.sort(key=lambda x: (x["first"].lower(), x["last"].lower()))
                    
                    # Update completer model immediately (so recommendations work)
                    all_displays = [c["display"] for c in self.contacts_data]
                    self.recipient_model.setStringList(all_displays)
                    print(f"DEBUG: Updated recipient_model with {len(all_displays)} items")
                    
                    # Save cache with page_token (None if complete)
                    self.save_contacts_cache(page_token=page_token)
                    
                    # Check if we're done
                    if not page_token:
                        print(f"✅ Finished! Found {len(contacts_dict)} unique contacts (COMPLETE)")
                        break
                    
                    time.sleep(0.1)  # Small delay between batches
                        
                except Exception as e:
                    print(f"❌ DEBUG: Error during fetch loop: {e}")
                    import traceback
                    traceback.print_exc()
                    # Save what we have so far with current page_token for resuming
                    self.save_contacts_cache(page_token=page_token)
                    break
            
            print("=" * 50)
            print("🔍 DEBUG: fetch_all_gmail_contacts() ENDED")
            print("=" * 50)
            
        except Exception as e:
            print(f"❌ Error fetching contacts: {e}")
            import traceback
            traceback.print_exc()
    def save_contacts_cache(self, page_token=None):
        """Save structured contacts to cache with optional page_token for resuming."""
        print(f"DEBUG save_contacts_cache: Saving {len(self.contacts_data)} contacts...")
        print(f"DEBUG save_contacts_cache: page_token = {page_token}")
        print(f"DEBUG save_contacts_cache: File path = {CONTACTS_CACHE_FILE}")
        try:
            cache_data = {
                'contacts_data': self.contacts_data,
                'timestamp': time.time(),
                'page_token': page_token  # None means complete, otherwise resume from here
            }
            with open(CONTACTS_CACHE_FILE, 'wb') as f:
                pickle.dump(cache_data, f)
            print(f"✅ Saved {len(self.contacts_data)} contacts to cache (complete={page_token is None})")
            
            # Verify file was created
            if os.path.exists(CONTACTS_CACHE_FILE):
                size = os.path.getsize(CONTACTS_CACHE_FILE)
                print(f"DEBUG: Cache file created, size = {size} bytes")
            else:
                print("❌ DEBUG: Cache file NOT created!")
                
        except Exception as e:
            print(f"❌ Cache save error: {e}")
            import traceback
            traceback.print_exc()


    def load_contacts_cache(self):
        """Load structured contacts from cache. Returns (success, page_token)."""
        print(f"DEBUG load_contacts_cache: Looking for {CONTACTS_CACHE_FILE}")
        print(f"DEBUG load_contacts_cache: File exists? {os.path.exists(CONTACTS_CACHE_FILE)}")
        
        if os.path.exists(CONTACTS_CACHE_FILE):
            try:
                with open(CONTACTS_CACHE_FILE, 'rb') as f:
                    cache_data = pickle.load(f)
                
                self.contacts_data = cache_data.get('contacts_data', [])
                page_token = cache_data.get('page_token', None)  # None = complete
                print(f"DEBUG: Loaded {len(self.contacts_data)} contacts from cache")
                print(f"DEBUG: page_token = {page_token} (None means complete)")
                
                if self.contacts_data:
                    # Update completer model with all displays
                    all_displays = [c["display"] for c in self.contacts_data]
                    self.recipient_model.setStringList(all_displays)
                    print(f"DEBUG: Updated recipient_model with {len(all_displays)} items")
                
                # Return True if cache is COMPLETE (page_token is None)
                # Return False if cache is incomplete (need to resume)
                if page_token is None:
                    return True  # Complete, no need to fetch
                else:
                    # Store page_token for resuming
                    self._resume_page_token = page_token
                    return False  # Incomplete, need to resume
                    
            except Exception as e:
                print(f"❌ Cache load error: {e}")
                import traceback
                traceback.print_exc()
        
        self._resume_page_token = None
        return False

    def fetch_user_profile(self):
        """Fetch user's real name from Gmail profile or Google People API."""

        #We had to enable people API for this to work 
        # Try cache first
        if self.load_user_profile_cache():
            return
        
        if not self.credentials:
            print("❌ No credentials available for profile fetch")
            return
        
        try:
            # First try: Get from Gmail profile
            gmail_service = build('gmail', 'v1', credentials=self.credentials)
            profile = gmail_service.users().getProfile(userId='me').execute()
            email_address = profile.get('emailAddress', '')
            
            # Extract name from email if it's in "firstname.lastname@" format
            if email_address:
                local_part = email_address.split('@')[0]
                # Try to get first name from email
                if '.' in local_part:
                    first_name = local_part.split('.')[0].capitalize()
                    self.user_first_name = first_name
                    self.save_user_profile_cache()
                    print(f"✅ Got user's name from email: {self.user_first_name}")
                    return
            
            # Second try: People API (if available)
            try:
                people_service = build('people', 'v1', credentials=self.credentials)
                person = people_service.people().get(
                    resourceName='people/me',
                    personFields='names'
                ).execute()
                
                names = person.get('names', [])
                if names:
                    first_name = names[0].get('givenName', '')
                    if first_name:
                        self.user_first_name = first_name
                        self.save_user_profile_cache()
                        print(f"✅ Got user's real name from People API: {self.user_first_name}")
                        return
            except Exception as pe:
                print(f"⚠️ People API not available: {pe}")
            
            # Fallback: just use the local part of email
            if email_address:
                local_part = email_address.split('@')[0]
                name = local_part.replace('.', ' ').replace('_', ' ').replace('-', ' ')
                name = ' '.join(word.capitalize() for word in name.split())
                first_word = name.split()[0] if name else None
                if first_word:
                    self.user_first_name = first_word
                    self.save_user_profile_cache()
                    print(f"✅ Using fallback name: {self.user_first_name}")
                
        except Exception as e:
            print(f"❌ Error fetching profile: {e}")
    def load_user_profile_cache(self):
        """Load user's first name from cache."""
        if os.path.exists(USER_PROFILE_CACHE_FILE):
            try:
                with open(USER_PROFILE_CACHE_FILE, 'rb') as f:
                    cache_data = pickle.load(f)
                self.user_first_name = cache_data.get('first_name', None)
                if self.user_first_name:
                    print(f"✅ Loaded user name from cache: {self.user_first_name}")
                    return True
            except:
                pass
        return False

    def save_user_profile_cache(self):
        """Save user's first name to cache."""
        try:
            cache_data = {
                'first_name': self.user_first_name,
                'timestamp': time.time()
            }
            with open(USER_PROFILE_CACHE_FILE, 'wb') as f:
                pickle.dump(cache_data, f)
        except Exception as e:
            print(f"Cache save error: {e}")

    def send_new_email(self):
        """Send new email - extracts email from autocomplete selection."""
        if not self.credentials:
            QMessageBox.warning(self, "Not Logged In", "Please login first.")
            return

        to_text = self.compose_to_input.text().strip()

        # Extract email from "Name (email@example.com)" format
        email_match = re.search(r'\(([^)]+@[^)]+)\)', to_text)
        if email_match:
            to_text = email_match.group(1)  # Just the email
        # Otherwise assume they typed the email directly

        subject_text = self.compose_subject_input.text().strip()
        body_text = self.compose_body_edit.toPlainText().strip()

        if not to_text or '@' not in to_text:
            QMessageBox.warning(self, "Invalid email", "Please enter a valid email address.")
            return
        if not subject_text:
            QMessageBox.warning(self, "Missing subject", "Please write a subject.")
            return
        if not body_text:
            QMessageBox.warning(self, "Empty email", "Email body is empty.")
            return

        self.send_new_thread = SendNewEmailThread(
            self.credentials,
            to_text,
            subject_text,
            body_text
        )
        self.send_new_thread.success.connect(self.on_send_new_success)
        self.send_new_thread.error.connect(self.on_send_new_error)
        self.send_new_thread.start()
        self.show_reply_notification("Sending email...")


    def on_recipient_text_changed(self, text):
        """Dynamic search triggered on every keystroke."""
        if not text:
            # Show all contacts if empty
            all_displays = [c["display"] for c in self.contacts_data]
            self.recipient_model.setStringList(all_displays[:50])
            return
        
        text_lower = text.lower().strip()
        
        if not text_lower:
            return
        
        prefix_matches = []
        contains_matches = []
        
        for contact in self.contacts_data:
            first_lower = contact["first"].lower()
            last_lower = contact["last"].lower()
            email_lower = contact["email"].lower()
            
            # Check prefix matches (highest priority)
            if (first_lower.startswith(text_lower) or 
                last_lower.startswith(text_lower) or 
                email_lower.startswith(text_lower)):
                prefix_matches.append(contact["display"])
            # Check contains matches (lower priority)
            elif (text_lower in first_lower or 
                text_lower in last_lower or 
                text_lower in email_lower):
                contains_matches.append(contact["display"])
        
        # Combine: prefix matches first, then contains matches
        all_matches = prefix_matches + contains_matches
        
        # Update the dropdown
        self.recipient_model.setStringList(all_matches[:15])




    def switch_to_new(self):
        if self.compose_mode:
            self.exit_compose_mode()

        if not self.new_button.isChecked():
            self.new_button.setChecked(True)
            return

        self.all_button.setChecked(False)
        self.show_unread_only = True
        self.current_email_index = 0

        # Stop the new email check timer (not needed in New mode)
        self.new_email_check_timer.stop()
        
        # Reset counts when switching modes
        self.new_emails_count = 0
        self.viewed_email_ids.clear()
        self.locally_read_thread_ids.clear()

        if self.credentials:
            self.fetch_emails()

    def switch_to_all(self):
        if self.compose_mode:
            self.exit_compose_mode()

        if not self.all_button.isChecked():
            self.all_button.setChecked(True)
            return

        self.new_button.setChecked(False)
        self.show_unread_only = False
        self.current_email_index = 0

        # Reset counts when switching modes
        self.new_emails_count = 0
        self.viewed_email_ids.clear()
        self.locally_read_thread_ids.clear()

        # DON'T start the timer - it causes bugs
        # self.new_email_check_timer.start()

        if self.credentials:
            self.fetch_emails()  

    def switch_to_original(self):
        self.show_summary = False
        if self.emails_data:
            self.display_current_email()

    def switch_to_summary(self):
        self.show_summary = True
        if self.emails_data:
            self.display_current_email()

    def mark_thread_as_read_immediate(self, thread_data):
        thread_id = thread_data.get('thread_id')
        
        # Track this thread as read locally for this session
        if thread_id:
            self.locally_read_thread_ids.add(thread_id)
        
        mids = [m['message_id'] for m in thread_data['messages'] if m['is_unread']]
        if mids and self.credentials:
            for m in thread_data['messages']:
                m['is_unread'] = False

            self.mark_read_thread = MarkReadThread(self.credentials, mids)
            self.mark_read_thread.success.connect(lambda: None)
            self.mark_read_thread.error.connect(lambda err: None)
            self.mark_read_thread.start()

    def display_no_emails(self):
        self.refresh_button.setEnabled(True)
        for i in reversed(range(self.email_container_layout.count())):
            w = self.email_container_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        msg = "No new emails." if self.show_unread_only else "No emails found."
        lab = QLabel(msg)
        lab.setAlignment(Qt.AlignCenter)
        lab.setStyleSheet("font-size: 14px; color: black;")
        self.email_container_layout.addWidget(lab)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
    def show_no_more_new_emails(self):
        """Show a screen indicating no more new emails"""
        # Clear current display
        for i in reversed(range(self.email_container_layout.count())):
            w = self.email_container_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        # Create "no more" message
        container = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel("✓")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 72px; color: #4CAF50;")
        layout.addWidget(icon_label)

        msg_label = QLabel("All caught up!")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #333;")
        layout.addWidget(msg_label)

        sub_label = QLabel("No more new emails")
        sub_label.setAlignment(Qt.AlignCenter)
        sub_label.setStyleSheet("font-size: 16px; color: #666;")
        layout.addWidget(sub_label)

        container.setLayout(layout)
        self.email_container_layout.addWidget(container)
        self.email_container_layout.addStretch()

        # Disable next, enable prev ONLY if there are emails to go back to
        self.next_button.setEnabled(False)
        self.next_button.setText("Next ►")
        self.prev_button.setEnabled(self.current_email_index > 0 and len(self.emails_data) > 0)
    def open_link(self, url):
        """Open URL in default browser"""
        import webbrowser
        webbrowser.open(url.toString())

    def clear_token_and_reauth(self):
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)

        self.credentials = None
        self.status_label.setText("Token cleared. Click 'Login with Google' to re-authenticate.")
        self.login_button.setVisible(True)
        self.login_button.setEnabled(True)

        QMessageBox.information(
            self,
            "Token Cleared",
            "Your old token has been cleared.\n\n"
            "Click 'Login with Google' to re-authenticate."
        )

    def auto_authenticate(self):
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'rb') as token:
                    creds = pickle.load(token)

                if creds and hasattr(creds, 'scopes'):
                    required_scopes = {'https://www.googleapis.com/auth/gmail.modify',
                                       'https://www.googleapis.com/auth/gmail.send'}
                    if not required_scopes.issubset(set(creds.scopes or [])):
                        os.remove(TOKEN_FILE)
                        self.status_label.setText("Old token insufficient. Re-login required.")
                        self.login_button.setVisible(True)
                        return

                if creds and creds.valid:
                    self.credentials = creds
                    self.fetch_user_profile()

                    self.login_button.setVisible(False)
                    self.status_label.setText("Logged in! Fetching contacts and emails...")
                    
                    # Fetch contacts in background
                    contact_thread = threading.Thread(target=self.fetch_all_gmail_contacts)
                    contact_thread.daemon = True
                    contact_thread.start()
                    
                    self.fetch_emails()
                    return

                elif creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(TOKEN_FILE, 'wb') as token:
                        pickle.dump(creds, token)
                    self.credentials = creds
                    self.fetch_user_profile()

                    self.login_button.setVisible(False)
                    self.status_label.setText("Session refreshed! Fetching contacts and emails...")
                    
                    # Fetch contacts in background
                    contact_thread = threading.Thread(target=self.fetch_all_gmail_contacts)
                    contact_thread.daemon = True
                    contact_thread.start()
                    
                    self.fetch_emails()
                    return
            except:
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)

        self.status_label.setText("Click 'Login with Google' to start")
        self.login_button.setVisible(True)

    def start_oauth(self):
        google_id = os.environ.get('GOOGLE_CLIENT_ID') or os.environ.get('id')
        google_secret = os.environ.get('GOOGLE_CLIENT_SECRET') or os.environ.get('secret')
        
        print(f"DEBUG: google_id = {google_id[:20] if google_id else 'None'}...")
        print(f"DEBUG: google_secret = {google_secret[:10] if google_secret else 'None'}...")

        client_config = {
            "installed": {
                "client_id": google_id,
                "client_secret": google_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"]
            }
        }

        if not google_id or not google_secret:
            QMessageBox.critical(
                self,
                "Missing Credentials",
                "Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to your .env file."
            )
            return


    def on_oauth_success(self, credentials):
        self.credentials = credentials
        self.login_button.setVisible(False)
        self.status_label.setText("Logged in! Fetching contacts and emails...")
        
        # Fetch contacts first
        contact_thread = threading.Thread(target=self.fetch_all_gmail_contacts)
        contact_thread.daemon = True
        contact_thread.start()
        
        self.fetch_emails()

    def on_oauth_error(self, error):
        self.login_button.setEnabled(True)
        self.login_button.setText("Login with Google")
        self.status_label.setText("Login failed")
        QMessageBox.critical(self, "Error", error)

    def fetch_emails(self, silent=False, load_more=False):
        #FIX: Clean up old thread properly before checking
        if self.fetch_thread is not None:
            if self.fetch_thread.isRunning():
                print("Already fetching, skipping...")
                return
            else:
                # Thread finished but object still exists - clean it up
                try:
                    self.fetch_thread.deleteLater()
                except:
                    pass
                self.fetch_thread = None
            
        if not self.credentials:
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, 'rb') as t:
                    self.credentials = pickle.load(t)
            else:
                QMessageBox.warning(self, "Not Logged In", "Please login first!")
                return

        if not silent:
            self.fetch_button.setEnabled(False)
            self.fetch_button.setText("Fetching...")
            self.refresh_button.setEnabled(False)
            self.status_label.setText("Fetching emails...")

        after_ts = self.app_start_timestamp if self.show_unread_only else None
        max_results = 50 if self.show_unread_only else 4

        self.fetch_thread = EmailFetchThread(
            self.credentials,
            self.show_unread_only,
            max_results=max_results,
            after_timestamp=after_ts
        )

        #  FIX: Connect finished signal to cleanup
        self.fetch_thread.finished.connect(self._on_fetch_thread_finished)

        if load_more:
            self.fetch_thread.success.connect(self.append_more_emails)
        else:
            self.fetch_thread.success.connect(self.display_emails)

        self.fetch_thread.error.connect(self.on_fetch_error)
        self.fetch_thread.start()


    def _on_fetch_thread_finished(self):
        """Clean up fetch thread after it completes"""
        # Re-enable buttons
        self.refresh_button.setEnabled(True)
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("Fetch Emails")
        
        # Clean up thread object
        if self.fetch_thread is not None:
            try:
                self.fetch_thread.deleteLater()
            except:
                pass
            self.fetch_thread = None
    def on_refresh_clicked(self):
        """Handle refresh button click"""
        if self.credentials:
            self.fetch_emails()
        elif os.path.exists(TOKEN_FILE):
            # Try to load credentials from file
            try:
                with open(TOKEN_FILE, 'rb') as t:
                    self.credentials = pickle.load(t)
                self.fetch_emails()
            except:
                pass
    def show_previous_email(self):
        import time
        now = time.time()
        if now - self.last_navigation_time < self.navigation_cooldown:
            return
        self.last_navigation_time = now

        if self.show_unread_only:
            return

        if self.current_email_index > 0:
            self.current_email_index -= 1
            self.display_current_email()
            self.prefetch_upcoming_summaries()

    def show_next_email(self):
        import time
        now = time.time()
        if now - self.last_navigation_time < self.navigation_cooldown:
            return
        self.last_navigation_time = now

        # Handle empty email list in New mode
        if not self.emails_data and self.show_unread_only:
            self.show_no_more_new_emails()
            return

        if self.current_email_index < len(self.emails_data) - 1:
            self.current_email_index += 1
            self.update_next_button()
            self.display_current_email()
            self.prefetch_upcoming_summaries()

            if self.current_email_index == len(self.emails_data) - 1:
                if self.has_more_emails and not self.is_loading_more:
                    self.load_more_emails()
        else:
            # At the last email or beyond
            if self.show_unread_only:
                self.show_no_more_new_emails()
            elif self.has_more_emails and not self.is_loading_more:
                self.load_more_emails()


    def load_more_emails(self):
        if self.is_loading_more or not self.has_more_emails:
            return

        self.is_loading_more = True
        after_ts = self.app_start_timestamp if self.show_unread_only else None

        self.fetch_thread = EmailFetchThread(
            self.credentials,
            self.show_unread_only,
            max_results=5,
            page_token=self.page_token,
            after_timestamp=after_ts
        )
        self.fetch_thread.success.connect(self.append_more_emails)
        self.fetch_thread.error.connect(self.on_load_more_error)
        self.fetch_thread.start()

    def append_more_emails(self, new_emails, next_page_token):
        if not new_emails:
            self.has_more_emails = False
            self.page_token = None
            if self.current_email_index >= len(self.emails_data) - 3:
                self.next_button.setEnabled(False)
        else:
            self.emails_data.extend(new_emails)
            self.page_token = next_page_token
            self.has_more_emails = next_page_token is not None
            self.next_button.setEnabled(self.current_email_index < len(self.emails_data) - 1)
            self.prefetch_upcoming_summaries()
            self.update_recipient_suggestions()

        self.is_loading_more = False

    def on_load_more_error(self, error):
        self.is_loading_more = False
        QMessageBox.warning(self, "Error", f"Failed to load more emails: {error}")

    def display_current_email(self):
        self.cleanup_finished_threads()

        if not self.emails_data:
            return

        thread_data = self.emails_data[self.current_email_index]
        messages = thread_data['messages']
        is_thread = thread_data['is_thread']
        thread_count = thread_data['thread_count']
        thread_id = thread_data['thread_id']

        if thread_id not in self.viewed_email_ids:
            self.viewed_email_ids.add(thread_id)
            # Decrease new count when viewing an email in "All" mode
            if not self.show_unread_only and self.new_emails_count > 0:
                self.new_emails_count -= 1

        self.update_next_button()

        has_unread = any(m['is_unread'] for m in messages)
        if has_unread:
            self.mark_thread_as_read_immediate(thread_data)

        for i in reversed(range(self.email_container_layout.count())):
            w = self.email_container_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        if self.show_unread_only:
            self.prev_button.setEnabled(False)
        else:
            self.prev_button.setEnabled(self.current_email_index > 0)

        # WITH this:
        if self.show_unread_only:
            # In "New" mode, always enable Next so user can see "all caught up" screen
            self.next_button.setEnabled(True)
        else:
            # In "All" mode, disable if at end and no more to load
            self.next_button.setEnabled(
                self.current_email_index < len(self.emails_data) - 1 or
                (self.has_more_emails and not self.is_loading_more)
            )


        for idx, message in enumerate(messages):
            is_latest = (idx == 0)
            msg_position = idx + 1

            card = self.create_email_card(
                message,
                idx,
                thread_count,
                is_thread,
                is_latest,
                msg_position
            )
            self.email_container_layout.addWidget(card)

            if is_thread and idx < len(messages) - 1:
                spacer = QLabel()
                spacer.setFixedHeight(15)
                spacer.setStyleSheet("background-color: transparent;")
                self.email_container_layout.addWidget(spacer)

        self.email_container_layout.addStretch()
        self.prefetch_upcoming_summaries()

    def create_email_card(self, email_data, idx, thread_count, is_thread, is_latest, message_position):
        frame = QFrame()
        frame.setStyleSheet("QFrame { background-color: transparent; }")
        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)

        HEADER_OPACITY = 200
        CONTENT_OPACITY = 220

        if is_thread:
            msg_label = QLabel(f"<b>Message {message_position} of {thread_count}</b>")
            msg_label.setAlignment(Qt.AlignCenter)
            msg_label.setStyleSheet("""
                color: #0066cc;
                font-size: 13px;
                font-weight: bold;
                padding: 5px;
                background-color: rgba(100,150,255,100);
                border-radius: 5px;
            """)
            layout.addWidget(msg_label)

        header_widget = QWidget()
        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(10, 10, 10, 10)
        header_widget.setStyleSheet(
            f"background-color: rgba(206,212,211,{HEADER_OPACITY}); "
            "border-radius: 5px;"
        )

        subject = QLabel(f"<span style='font-size: 16px;'><b>Subject:</b> {email_data['subject']}</span>")
        subject.setWordWrap(True)
        subject.setTextInteractionFlags(Qt.TextSelectableByMouse)
        subject.setStyleSheet("background-color: transparent;")
        header_layout.addWidget(subject)


        sender = QLabel(f"<b>From:</b> {email_data['from']}")
        sender.setWordWrap(True)
        sender.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sender.setStyleSheet("background-color: transparent;")
        header_layout.addWidget(sender)

        date = QLabel(f"<b>Sent:</b> {email_data['date']}")
        date.setTextInteractionFlags(Qt.TextSelectableByMouse)
        date.setStyleSheet("background-color: transparent;")
        header_layout.addWidget(date)

        header_widget.setLayout(header_layout)
        layout.addWidget(header_widget)

        summary_header = QWidget()
        sh_layout = QHBoxLayout()
        sh_layout.setContentsMargins(0, 0, 0, 5)

        toggle_style = """
                    QPushButton {
                        background-color: rgba(206,212,211,200);
                        color: black;
                        border: 1px solid #000;
                        font-weight: bold;
                        font-size: 10px;
                        padding: 2px 8px;
                    }
                    QPushButton:checked {
                        background-color: rgba(100,150,255,200);
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: rgba(255, 255, 255, 255);
                        border: 2px solid #000;
                    }
                    QPushButton:checked:hover {
                        background-color: rgba(150, 200, 255, 255);
                        border: 2px solid #000;
                    }
                """

        if self.show_summary:
            sh_layout.addWidget(QLabel("<b style='font-size: 14px;'>Summary:</b>"))
        else:
            sh_layout.addWidget(QLabel("<b style='font-size: 14px;'>Content:</b>"))

        sh_layout.addStretch()

        summary_btn = QPushButton("Summary")
        summary_btn.setFixedSize(70, 25)
        summary_btn.setCheckable(True)
        summary_btn.setChecked(self.show_summary)
        summary_btn.clicked.connect(self.switch_to_summary)
        summary_btn.setStyleSheet(toggle_style)

        original_btn = QPushButton("Orgn")
        original_btn.setFixedSize(70, 25)
        original_btn.setCheckable(True)
        original_btn.setChecked(not self.show_summary)
        original_btn.clicked.connect(self.switch_to_original)
        original_btn.setStyleSheet(toggle_style)

        sh_layout.addWidget(summary_btn)
        sh_layout.addWidget(original_btn)

        summary_header.setLayout(sh_layout)
        layout.addWidget(summary_header)

        content_scroll = QScrollArea()
        content_scroll.setWidgetResizable(True)
        content_scroll.setMinimumHeight(500)
        content_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)

        if email_data['images']:
            for img_data in email_data['images']:
                pix = QPixmap()
                pix.loadFromData(img_data)

                if pix.width() > 500:
                    pix = pix.scaledToWidth(500, Qt.SmoothTransformation)

                img_label = QLabel()
                img_label.setPixmap(pix)
                img_label.setAlignment(Qt.AlignCenter)
                content_layout.addWidget(img_label)

        if self.show_summary:
            summary_text = self.summarize_email_async(
                email_data['body'],
                email_data['subject'],
                email_data['message_id']
            )

            html = summary_text.replace('\n\n', '<br><br>').replace('\n', '<br>')

            html = re.sub(r'<br>([•\-\*])\s*', r'<br>• ', html)
            html = re.sub(r'<br>(\d+\.)\s*', r'<br>\1 ', html)

            body_label = QLabel()
            body_label.setTextFormat(Qt.RichText)
            body_label.setText(
                f"""
                <div style='line-height: 1.8; font-size: 18px; color: #f5f5eb; text-align: left;'>
                    {html}
                </div>
                """
            )
            body_label.setWordWrap(True)
            body_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            body_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            body_label.setStyleSheet(
                f"""
                QLabel {{
                    color: white;
                    background-color: rgba(30, 30, 30, {CONTENT_OPACITY});
                    padding-top: 43px;
                    padding-left: 35px;
                    padding-right: 18px;
                    padding-bottom: 18px;
                    border-radius: 5px;
                    border: 1px solid rgba(200, 200, 150, 200);
                    font-size: 18px;
                }}
                """
            )
        else:
            email_html = email_data['body']

            # Check if email is HTML or plain text
            if '<html' in email_html.lower() or '<div' in email_html.lower() or '<table' in email_html.lower():
                # It's HTML - render as-is
                pass
            else:
                # It's plain text - smart newline handling
                email_html = email_html.replace('\r\n', '\n')
                
                # Split into lines
                lines = email_html.split('\n')
                result = []
                
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    
                    # Empty line = paragraph break
                    if not stripped:
                        result.append('<br><br>')
                    # Line ends with punctuation or is short = likely end of paragraph
                    elif stripped.endswith(('.', '!', '?', ':', ')')) and len(stripped) < 60:
                        result.append(stripped + '<br>')
                    # Line is very short (like "Best," or signature) = keep break
                    elif len(stripped) < 40:
                        result.append(stripped + '<br>')
                    # Otherwise join with space (soft wrap)
                    else:
                        result.append(stripped + ' ')
                
                email_html = ''.join(result)
                # Clean up multiple <br>
                email_html = re.sub(r'(<br>){3,}', '<br><br>', email_html)
                # Convert plain text URLs to clickable links
                url_pattern = r'(https?://[^\s<>"\']+)'
                email_html = re.sub(url_pattern, r'<a href="\1" style="color: #6eb5ff;">\1</a>', email_html)


            body_label = QLabel()
            body_label.setTextFormat(Qt.RichText)
            body_label.setText(email_html)
            body_label.setWordWrap(True)
            body_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            body_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            body_label.setOpenExternalLinks(False)
            body_label.linkActivated.connect(lambda url: __import__('webbrowser').open(url))
            body_label.setStyleSheet(
                f"""
                QLabel {{
                    color: white;
                    background-color: rgba(30,30,30,{CONTENT_OPACITY});
                    padding: 18px;
                    padding-top: 38px;
                    padding-left: 30px;
                    border-radius: 5px;
                    border: 1px solid rgba(200,200,150,200);
                    font-size: 18px;
                }}
                """
            )


        content_layout.addWidget(body_label, 1)
        content_widget.setLayout(content_layout)
        content_scroll.setWidget(content_widget)
        layout.addWidget(content_scroll, 1)

        frame.setLayout(layout)
        return frame

    def display_emails(self, emails, next_page_token):
        # Leaving compose mode if we were there
        if self.compose_mode:
            self.exit_compose_mode()

        # FILTER OUT threads user has already viewed this session (fixes "still showing as unseen" bug)
        if self.show_unread_only and self.locally_read_thread_ids:
            emails = [e for e in emails if e.get('thread_id') not in self.locally_read_thread_ids]

        self.emails_data = emails

        self.page_token = next_page_token
        self.is_loading_more = False
        self.has_more_emails = next_page_token is not None
        self.current_email_index = 0
        self.viewed_email_ids.clear()

        if self.show_unread_only:
            self.new_emails_count = len(emails)
        else:
            self.new_emails_count = 0

        self.update_next_button()
        self.update_recipient_suggestions()

        if not emails:
            for i in reversed(range(self.email_container_layout.count())):
                w = self.email_container_layout.itemAt(i).widget()
                if w:
                    w.setParent(None)

            empty = QLabel("<b>NO EMAILS</b>")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("font-size: 28px; font-weight: bold;")
            self.email_container_layout.addWidget(empty)
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
        else:
            self.display_current_email()
            self.prefetch_upcoming_summaries()

        self.login_widget.setVisible(False)
        self.email_display_widget.setVisible(True)
        self.compose_widget.setVisible(False)
        pass

    def on_fetch_error(self, error):
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("Fetch Emails")
        self.refresh_button.setEnabled(True)
        self.status_label.setText("Failed to fetch")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, 'drag_position'):
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def show_login(self):
        self.login_widget.setVisible(True)
        self.email_display_widget.setVisible(False)
        self.compose_widget.setVisible(False)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self._position_below_face)
        QTimer.singleShot(500, self._position_below_face)

    def _position_below_face(self):
        try:
            from PySide6.QtGui import QGuiApplication
            import tempfile, json

            pos_file = os.path.join(tempfile.gettempdir(), "photon_face_pos.json")
            face_pos = None

            if os.path.exists(pos_file):
                try:
                    with open(pos_file, "r") as f:
                        face_pos = json.load(f)
                except:
                    pass

            screen = QGuiApplication.primaryScreen()
            if not screen:
                return

            geo = screen.availableGeometry()
            margin = max(int(0.02 * min(geo.width(), geo.height())), 8)

            if face_pos:
                x = face_pos["x"]
                y = face_pos["y"] + face_pos["height"] +10
            else:
                FACE_SIZE_INCH = 1.25
                dpi = screen.logicalDotsPerInch() or 96.0
                face_height_px = int(FACE_SIZE_INCH * dpi)
                face_total_h = face_height_px -40
                #change faceheight

                x = geo.x() + geo.width() - self.width() - margin
                y = geo.y() + margin + 50 + face_total_h + 10

            if y + self.height() > geo.y() + geo.height():
                y = geo.y() + geo.height() - self.height() - margin

            if x + self.width() > geo.x() + geo.width():
                x = geo.x() + geo.width() - self.width() - margin

            self.move(x, y)
            self.setGeometry(x, y, self.width(), self.height())
        except:
            pass

    def closeEvent(self, event):
        self.new_email_check_timer.stop()

        if self.ipc_receiver:
            self.ipc_receiver.stop()
            self.ipc_receiver.wait(1000)

        if self.fetch_thread and self.fetch_thread.isRunning():
            self.fetch_thread.quit()
            self.fetch_thread.wait(1000)

        if self.oauth_thread and self.oauth_thread.isRunning():
            self.oauth_thread.quit()
            self.oauth_thread.wait(1000)

        if self.mark_read_thread and self.mark_read_thread.isRunning():
            self.mark_read_thread.quit()
            self.mark_read_thread.wait(1000)

        if self.compose_send_thread and self.compose_send_thread.isRunning():
            self.compose_send_thread.quit()
            self.compose_send_thread.wait(1000)

        if self.compose_body_thread and self.compose_body_thread.isRunning():
            self.compose_body_thread.quit()
            self.compose_body_thread.wait(1000)

        if self.send_new_thread and self.send_new_thread.isRunning():
            self.send_new_thread.quit()
            self.send_new_thread.wait(1000)

        for t in self.active_summary_threads:
            if t.isRunning():
                t.quit()
                t.wait(500)

        for t in self.summarize_threads:
            if t.isRunning():
                t.quit()
                t.wait(500)

        for t in list(self.temp_threads):
            try:
                if t.isRunning():
                    t.quit()
                    t.wait(500)
                t.deleteLater()
            except:
                pass
        self.temp_threads.clear()

        event.accept()


def main():
    app = QApplication(sys.argv)
    window = EmailReaderWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
