"""Task completion notifications: desktop toast, SMTP email, webhook.

Config example:

    {
        "desktop": {"enabled": true},
        "email": {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "sender@example.com",
            "password": "secret",
            "from_addr": "sender@example.com",
            "to": ["ops@example.com"]
        },
        "webhook": {
            "url": "https://example.com/hooks/task",
            "headers": {"X-Token": "abc"}
        }
    }

Channels are best-effort: one failing channel never fails the worker task.
"""

from __future__ import annotations

import json
import shutil
import smtplib
import subprocess
import sys
import urllib.request
from email.message import EmailMessage
from typing import Any


class Notifier:
    """Best-effort multi-channel notifier for task lifecycle events."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.desktop_config = self.config.get("desktop") or {}
        self.email_config = self.config.get("email") or {}
        self.webhook_config = self.config.get("webhook") or {}

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> Notifier:
        return cls(config or {})

    def enabled_channels(self) -> list[str]:
        channels: list[str] = []
        if self.desktop_config.get("enabled"):
            channels.append("desktop")
        if self.email_config.get("smtp_host") and self.email_config.get("to"):
            channels.append("email")
        if self.webhook_config.get("url"):
            channels.append("webhook")
        return channels

    def send(
        self,
        title: str,
        message: str,
        task: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for channel in self.enabled_channels():
            try:
                if channel == "desktop":
                    results[channel] = self._send_desktop(title, message)
                elif channel == "email":
                    results[channel] = self._send_email(title, message)
                elif channel == "webhook":
                    results[channel] = self._send_webhook(title, message, task)
            except Exception:
                results[channel] = False
        return results

    def notify_task(self, task: dict[str, Any]) -> dict[str, bool]:
        task_id = task.get("id", "?")
        status = str(task.get("status", "unknown"))
        title = f"Task {task_id} {status}"
        parts = [
            f"kind: {task.get('kind', '')}",
            f"stage: {task.get('stage') or '-'}",
        ]
        if task.get("error"):
            parts.append(f"error: {task['error']}")
        if task.get("result_path"):
            parts.append(f"result: {task['result_path']}")
        return self.send(title, "\n".join(parts), task=task)

    def _send_desktop(self, title: str, message: str) -> bool:
        if sys.platform == "win32":
            escaped_title = title.replace("'", "''")
            escaped_message = message.replace("'", "''")
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                f"$n.BalloonTipTitle = '{escaped_title}'; "
                f"$n.BalloonTipText = '{escaped_message}'; "
                "$n.Visible = $true; $n.ShowBalloonTip(5000); "
                "Start-Sleep -Seconds 6; $n.Dispose()"
            )
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                creationflags=creation_flags,
            )
            return True
        if sys.platform == "darwin":
            if not shutil.which("osascript"):
                return False
            subprocess.Popen(
                [
                    "osascript",
                    "-e",
                    f'display notification "{message.replace(chr(34), "")}" '
                    f'with title "{title.replace(chr(34), "")}"',
                ]
            )
            return True
        if shutil.which("notify-send"):
            subprocess.Popen(["notify-send", title, message])
            return True
        return False

    def _send_email(self, title: str, message: str) -> bool:
        host = str(self.email_config.get("smtp_host", ""))
        port = int(self.email_config.get("smtp_port", 587))
        username = str(self.email_config.get("username", "") or "")
        password = str(self.email_config.get("password", "") or "")
        from_addr = str(self.email_config.get("from_addr") or username or host)
        to = self.email_config.get("to")
        to_list = [to] if isinstance(to, str) else [str(item) for item in (to or [])]
        if not host or not to_list:
            return False
        email = EmailMessage()
        email["Subject"] = title
        email["From"] = from_addr
        email["To"] = ", ".join(to_list)
        email.set_content(message)
        use_ssl = bool(self.email_config.get("use_ssl", port == 465))
        server: smtplib.SMTP | smtplib.SMTP_SSL
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
        try:
            if username:
                server.login(username, password)
            server.send_message(email)
        finally:
            server.quit()
        return True

    def _send_webhook(self, title: str, message: str, task: dict[str, Any] | None) -> bool:
        url = str(self.webhook_config.get("url", ""))
        if not url:
            return False
        headers = dict(self.webhook_config.get("headers") or {})
        headers.setdefault("Content-Type", "application/json")
        payload = json.dumps(
            {"title": title, "message": message, "task": task},
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=15) as response:
            return 200 <= int(response.status) < 400


if __name__ == "__main__":
    print("desktop-app-dev notifier: import Notifier for desktop / email / webhook notifications.")
