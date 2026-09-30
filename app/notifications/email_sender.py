"""Send a finished travel plan by email over SMTP (STARTTLS).

The Markdown plan is sent as an HTML body with a plain-text alternative, and
attached as `travel_plan.md`. Credentials come from `.env` only.
"""
import re
import smtplib
from email.message import EmailMessage

import markdown

from app.config import Settings, settings as default_settings

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_HTML_TEMPLATE = """<html><body style="font-family:Arial,Helvetica,sans-serif;line-height:1.5;color:#222;max-width:760px">
<style>table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:4px 10px;text-align:left}}</style>
{body}
</body></html>"""


class EmailError(RuntimeError):
    """The plan could not be emailed (bad address, missing config, SMTP failure)."""


def is_valid_email(address: str) -> bool:
    return bool(_EMAIL_PATTERN.match(address.strip()))


def build_message(plan_markdown: str, recipient: str, subject: str, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(plan_markdown)
    html = markdown.markdown(plan_markdown, extensions=["tables", "sane_lists"])
    msg.add_alternative(_HTML_TEMPLATE.format(body=html), subtype="html")
    msg.add_attachment(plan_markdown.encode("utf-8"), maintype="text", subtype="markdown",
                       filename="travel_plan.md")
    return msg


def send_plan_email(plan_markdown: str, recipient: str, subject: str, cfg: Settings | None = None) -> None:
    cfg = cfg or default_settings
    recipient = recipient.strip()
    if not is_valid_email(recipient):
        raise EmailError(f"'{recipient}' is not a valid email address")
    if not cfg.email_enabled:
        raise EmailError("Email is not configured: set SMTP_USERNAME and SMTP_PASSWORD in .env")

    msg = build_message(plan_markdown, recipient, subject, cfg.EMAIL_SENDER or cfg.SMTP_USERNAME)
    try:
        with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(cfg.SMTP_USERNAME, cfg.SMTP_PASSWORD)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailError("SMTP login failed. For Gmail, use an App Password, not your account password.") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"Sending email failed: {exc}") from exc
