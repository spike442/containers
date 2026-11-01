import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

MAX_BYTES = 18 * 1024 * 1024


@dataclass(frozen=True)
class Kindle:
    address: str
    user: str
    password: str
    host: str = "smtp.gmail.com"
    port: int = 587

    @classmethod
    def from_env(cls) -> "Kindle":
        return cls(
            address=os.environ["KINDLE_ADDRESS"], user=os.environ["SMTP_USER"], password=os.environ["SMTP_PASSWORD"]
        )

    def send(self, filename: str, content: bytes, content_type: str) -> None:
        maintype, subtype = content_type.split("/")
        message = EmailMessage()
        message["From"] = self.user
        message["To"] = self.address
        message["Subject"] = Path(filename).stem
        message.set_content(filename)
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
        with smtplib.SMTP(self.host, self.port, timeout=60) as client:
            client.starttls()
            client.login(self.user, self.password)
            client.send_message(message)
