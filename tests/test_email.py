import smtplib

import pytest

from app.config import Settings
from app.notifications import email_sender
from app.notifications.email_sender import EmailError, build_message, is_valid_email, send_plan_email

PLAN = "# Travel Plan\n\n| Item | Cost |\n|---|---|\n| Hotel | 100 USD |\n"


def smtp_cfg(**overrides):
    values = dict(_env_file=None, SMTP_USERNAME="sender@gmail.com", SMTP_PASSWORD="app-password")
    return Settings(**{**values, **overrides})


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        if password != "app-password":
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)


def test_default_recipient_is_configured():
    assert Settings(_env_file=None).EMAIL_RECIPIENT == "vsalma.mohamed24@gmail.com"


def test_email_validation():
    assert is_valid_email("vsalma.mohamed24@gmail.com")
    assert not is_valid_email("not-an-email")


def test_message_has_html_table_text_and_attachment():
    msg = build_message(PLAN, "a@b.com", "Plan", "me@x.com")
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "<table>" in html and "<h1>Travel Plan</h1>" in html
    assert msg.get_body(preferencelist=("plain",)).get_content().startswith("# Travel Plan")
    assert [p.get_filename() for p in msg.iter_attachments()] == ["travel_plan.md"]


def test_send_plan_email():
    send_plan_email(PLAN, "vsalma.mohamed24@gmail.com", "Your plan", smtp_cfg())
    assert FakeSMTP.sent[0]["To"] == "vsalma.mohamed24@gmail.com"
    assert FakeSMTP.sent[0]["From"] == "sender@gmail.com"


def test_missing_smtp_config_raises():
    with pytest.raises(EmailError, match="not configured"):
        send_plan_email(PLAN, "a@b.com", "s", Settings(_env_file=None))


def test_bad_credentials_raise_helpful_error():
    with pytest.raises(EmailError, match="App Password"):
        send_plan_email(PLAN, "a@b.com", "s", smtp_cfg(SMTP_PASSWORD="wrong"))


def test_invalid_recipient_raises():
    with pytest.raises(EmailError, match="not a valid"):
        send_plan_email(PLAN, "nope", "s", smtp_cfg())
