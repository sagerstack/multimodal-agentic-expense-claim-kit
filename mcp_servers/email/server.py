"""Email MCP Server for sending notifications via SMTP."""

import os
import uuid
from email.message import EmailMessage
from typing import Any

import aiosmtplib
from fastmcp import FastMCP

# Environment configuration
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# Initialize FastMCP server
mcp = FastMCP("email-server")


async def sendEmailViaSmtp(to: str, subject: str, body: str) -> dict[str, Any]:
    """Send email via SMTP (async)."""
    # For local dev with mailhog or localhost, just log the email
    if SMTP_HOST in ["mailhog", "localhost", "127.0.0.1"]:
        print(f"[LOCAL EMAIL] To: {to}")
        print(f"[LOCAL EMAIL] Subject: {subject}")
        print(f"[LOCAL EMAIL] Body:\n{body}")
        print("[LOCAL EMAIL] ---")
        messageId = f"<{uuid.uuid4()}@local>"
        return {"success": True, "messageId": messageId, "mode": "local-stub"}

    # Production SMTP sending
    try:
        message = EmailMessage()
        message["From"] = SMTP_USER if SMTP_USER else "noreply@sutd.edu.sg"
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        await aiosmtplib.send(
            message,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER if SMTP_USER else None,
            password=SMTP_PASSWORD if SMTP_PASSWORD else None,
            start_tls=False,  # Adjust based on SMTP server requirements
        )

        messageId = message["Message-ID"] if "Message-ID" in message else f"<{uuid.uuid4()}@smtp>"
        return {"success": True, "messageId": messageId, "mode": "smtp"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def sendEmail(to: str, subject: str, body: str) -> dict[str, Any]:
    """
    Send email via SMTP.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)

    Returns:
        Success status and message ID
    """
    return await sendEmailViaSmtp(to, subject, body)


@mcp.tool()
async def sendClaimNotification(
    to: str, claimNumber: str, status: str, message: str
) -> dict[str, Any]:
    """
    Send claim-related notification email.

    Args:
        to: Recipient email address
        claimNumber: Claim number
        status: Claim status (draft, pending, approved, rejected, paid)
        message: Notification message

    Returns:
        Success status and message ID
    """
    subject = f"Expense Claim {claimNumber} - Status: {status.upper()}"

    body = f"""Dear Employee,

Your expense claim has been updated:

Claim Number: {claimNumber}
Status: {status.upper()}

{message}

---
This is an automated notification from SUTD Expense Claims System.
Please do not reply to this email.
"""

    return await sendEmailViaSmtp(to, subject, body)


@mcp.resource("smtp://health")
def getSmtpHealth() -> str:
    """Check SMTP configuration."""
    if SMTP_HOST in ["mailhog", "localhost", "127.0.0.1"]:
        return f"Local dev mode (stub). SMTP_HOST={SMTP_HOST}:{SMTP_PORT}"
    return f"Production mode. SMTP_HOST={SMTP_HOST}:{SMTP_PORT}"


if __name__ == "__main__":
    # Start FastMCP server with Streamable HTTP transport
    mcp.run(transport="streamable-http")
