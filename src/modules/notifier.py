"""
Notification sender module.
Sends PDF reports via:
1. Email (SMTP with TLS)
2. Microsoft Teams (Incoming Webhook)
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import Any

import requests

import logging

log = logging.getLogger("agent.sender")


def send_email(pdf_path: str, config: Any) -> bool:
    """
    Send the PDF report via email with attachment.

    Args:
        pdf_path: path to the PDF file
        config: Config object with email section

    Returns:
        True if successful, False otherwise
    """
    email_cfg = config.get("email")
    if not email_cfg or not email_cfg.get("enabled", False):
        log.info("Email notification disabled")
        return False

    smtp_host = email_cfg.get("smtp_host")
    smtp_port = email_cfg.get("smtp_port", 587)
    smtp_user = email_cfg.get("smtp_user")
    smtp_pass = email_cfg.get("smtp_password")
    use_tls = email_cfg.get("use_tls", True)
    from_addr = email_cfg.get("from_addr", smtp_user)
    to_addrs = email_cfg.get("to_addrs", [])

    if not smtp_host or not smtp_user or not to_addrs:
        log.error("Email config incomplete — smtp_host, smtp_user, to_addrs are required")
        return False

    if not os.path.exists(pdf_path):
        log.error("PDF file not found: %s", pdf_path)
        return False

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject_template = email_cfg.get("subject", "Server Monitoring Report - {date}")
    subject = subject_template.replace("{date}", date_str)

    log.info("Sending email to %s via %s:%d", to_addrs, smtp_host, smtp_port)

    # Build email
    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject

    # Email body (HTML)
    body = f"""
    <html>
    <body>
    <h2>Server Monitoring Report</h2>
    <p>Berikut terlampir report monitoring server tanggal <strong>{date_str}</strong>.</p>
    <p>Mohon untuk review insiden dan alert yang terdeteksi.</p>
    <hr>
    <p style="color:#888;font-size:12px;">
    Email ini dikirim otomatis oleh Server Monitoring Agent.
    </p>
    </body>
    </html>
    """
    msg.attach(MIMEText(body, "html"))

    # Attach PDF
    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "pdf")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(pdf_path)}"',
        )
        msg.attach(part)

    # Send
    try:
        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)

        server.login(smtp_user, smtp_pass)
        server.sendmail(from_addr, to_addrs, msg.as_string())
        server.quit()

        log.info("Email sent successfully to %s", to_addrs)
        return True

    except smtplib.SMTPAuthenticationError as e:
        log.error("SMTP authentication failed: %s", e)
        return False
    except smtplib.SMTPException as e:
        log.error("SMTP error: %s", e)
        return False
    except Exception as e:
        log.error("Failed to send email: %s", e)
        return False


def send_teams(pdf_path: str, metrics: dict, incident_summary: dict, config: Any) -> bool:
    """
    Send a notification to Microsoft Teams via incoming webhook.
    The PDF file itself cannot be attached to a webhook message,
    so we send a summary card with key metrics and incident counts.

    Args:
        pdf_path: path to the PDF file (for reference in message)
        metrics: server metrics dict
        incident_summary: incident summary dict
        config: Config object with teams section

    Returns:
        True if successful, False otherwise
    """
    teams_cfg = config.get("teams")
    if not teams_cfg or not teams_cfg.get("enabled", False):
        log.info("Teams notification disabled")
        return False

    webhook_url = teams_cfg.get("webhook_url")
    if not webhook_url:
        log.error("Teams webhook_url not configured")
        return False

    title = teams_cfg.get("message_title", "Server Monitoring Report")
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total_incidents = incident_summary.get("total", 0)
    by_severity = incident_summary.get("by_severity", {})

    # Build summary text
    severity_lines = ""
    for sev in ["critical", "error", "warning"]:
        count = by_severity.get(sev, 0)
        if count > 0:
            severity_lines += f"- **{sev.upper()}**: {count}\n"

    if not severity_lines:
        severity_lines = "- Tidak ada insiden terdeteksi"

    # Build Adaptive Card for Teams
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": title,
                            "size": "Large",
                            "weight": "Bolder",
                            "color": "default",
                        },
                        {
                            "type": "TextBlock",
                            "text": f"Generated: {date_str}",
                            "isSubtle": True,
                            "spacing": "Small",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Hostname", "value": metrics.get("hostname", "N/A")},
                                {"title": "CPU", "value": f"{metrics.get('cpu_percent', 0)}%"},
                                {"title": "Memory", "value": f"{metrics.get('memory_percent', 0)}%"},
                                {"title": "Disk", "value": f"{metrics.get('disk_percent', 0)}%"},
                                {"title": "Uptime", "value": metrics.get("uptime_human", "N/A")},
                                {"title": "Total incidents", "value": str(total_incidents)},
                            ],
                        },
                        {
                            "type": "TextBlock",
                            "text": "Incident summary:",
                            "weight": "Bolder",
                            "spacing": "Medium",
                        },
                        {
                            "type": "TextBlock",
                            "text": severity_lines,
                            "wrap": True,
                            "spacing": "Small",
                        },
                        {
                            "type": "TextBlock",
                            "text": f"Report PDF: {os.path.basename(pdf_path)}",
                            "isSubtle": True,
                            "spacing": "Medium",
                            "wrap": True,
                        },
                    ],
                    "actions": [],
                },
            }
        ],
    }

    log.info("Sending Teams notification to webhook")

    try:
        response = requests.post(webhook_url, json=payload, timeout=30)
        if response.status_code == 200 or response.status_code == 202:
            log.info("Teams notification sent successfully")
            return True
        else:
            log.error("Teams webhook returned %d: %s", response.status_code, response.text[:200])
            return False
    except requests.exceptions.Timeout:
        log.error("Teams webhook request timed out")
        return False
    except requests.exceptions.ConnectionError as e:
        log.error("Teams webhook connection error: %s", e)
        return False
    except Exception as e:
        log.error("Failed to send Teams notification: %s", e)
        return False


def send_telegram(
    pdf_path: str,
    metrics: dict,
    incident_summary: dict,
    config: Any,
    kb_match: dict = None,
    incident_context: dict = None,
) -> bool:
    """
    Send incident alert and summary to Telegram Bot.
    Uses Telegram Bot API (sendMessage and sendDocument).
    Supports inline keyboard action buttons (Acknowledge, SOP, PDF).

    Args:
        pdf_path: path to the PDF report
        metrics: collected server metrics dict
        incident_summary: summary dict
        config: agent config
        kb_match: matched SOP and past incidents
        incident_context: incoming incident context

    Returns:
        True if successfully sent, False otherwise
    """
    telegram_cfg = config.get("telegram") if config else None
    if not telegram_cfg or not telegram_cfg.get("enabled", False):
        log.info("Telegram notification disabled")
        return False

    bot_token = telegram_cfg.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = telegram_cfg.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID")
    send_pdf = telegram_cfg.get("send_pdf", True)

    if not bot_token or not chat_id:
        log.error("Telegram config incomplete — bot_token and chat_id are required")
        return False

    server_name = incident_context.get("server", "localhost") if incident_context else metrics.get("hostname", "localhost")
    severity = incident_context.get("severity", "warning").upper() if incident_context else "ALERT"
    alert_text = incident_context.get("text", "Server metric threshold exceeded") if incident_context else "Automated Alert"
    patterns = ", ".join(incident_context.get("patterns", [])) if incident_context else "Threshold Alert"

    # Matched SOP info
    sop_text = "Tidak ada SOP yang cocok — Investigasi Umum"
    sop_id = ""
    if kb_match and kb_match.get("matched_sops"):
        top_sop = kb_match["matched_sops"][0]
        sop_id = top_sop.get("id", "")
        sop_text = f"{top_sop.get('title', 'SOP')} (`{sop_id}`)"

    inc_id = f"INC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    ts_now = datetime.now().strftime("%d %b %Y, %H:%M WIB")

    msg_lines = [
        f"*[{severity}] [PLATFORM BIGDATA] Incident Alert*",
        f"",
        f"*Environment:* Platform Bigdata K8s Cluster",
        f"",
        f"Dear Ops Team,",
        f"",
        f"Alert baru telah terdeteksi pada sistem monitoring:",
        f"",
        f"• *Node:* `{server_name}`",
        f"• *Incident ID:* `{inc_id}`",
        f"• *Waktu Deteksi:* {ts_now}",
        f"• *Trigger:* {patterns}",
        f"",
        f"_{alert_text}_",
        f"",
        f"*Matched SOP:* {sop_text}",
        f"",
        f"*Telemetri Host:* CPU `{metrics.get('cpu_percent', 0)}%` | MEM `{metrics.get('memory_percent', 0)}%` | DISK `{metrics.get('disk_percent', 0)}%` | Uptime `{metrics.get('uptime_human', 'N/A')}`",
        f"",
        f"— Platform Bigdata Monitoring Agent",
    ]
    message_text = "\n".join(msg_lines)

    # Inline Keyboard Action Buttons
    inline_keyboard = [
        [
            {"text": "Buka SOP Runbook", "callback_data": f"sop:{sop_id or 'general'}"},
            {"text": "Acknowledge", "callback_data": f"ack:{server_name}"},
        ],
        [
            {"text": "Restart Pod", "callback_data": f"restart:{server_name}"},
            {"text": "Full Telemetry", "callback_data": f"status:{server_name}"},
        ],
    ]

    send_msg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": inline_keyboard},
    }

    try:
        log.info("Sending Telegram alert to chat %s...", chat_id)
        resp = requests.post(send_msg_url, json=payload, timeout=15)
        if resp.status_code != 200:
            log.error("Telegram API error: %d - %s", resp.status_code, resp.text[:200])
            return False

        log.info("Telegram alert sent successfully")

        # Send PDF report if requested and available
        if send_pdf and pdf_path and os.path.exists(pdf_path):
            send_doc_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
            with open(pdf_path, "rb") as f:
                doc_payload = {
                    "chat_id": chat_id,
                    "caption": f"Laporan Diagnosa Insiden — {os.path.basename(pdf_path)}",
                }
                doc_files = {"document": (os.path.basename(pdf_path), f, "application/pdf")}
                doc_resp = requests.post(send_doc_url, data=doc_payload, files=doc_files, timeout=30)
                if doc_resp.status_code == 200:
                    log.info("Telegram PDF report delivered successfully")
                else:
                    log.warning("Failed to send Telegram PDF: %s", doc_resp.text[:100])

        return True
    except Exception as e:
        log.error("Failed to send Telegram notification: %s", e)
        return False


def send_telegram_log_report(
    metrics: dict,
    config: Any,
    diagnosis_results: list = None,
    kb_match: dict = None,
    incident_context: dict = None,
) -> bool:
    """
    Send a detailed incident log report to Telegram — inline text format.
    Styled after the enterprise alert email format (Clarissa / Prometheus):
    - Per-check/per-node breakdown
    - Sample log lines from critical diagnosis results
    - SOP reference and host telemetry

    Args:
        metrics: collected server metrics dict
        config: agent config
        diagnosis_results: list of diagnosis check results
        kb_match: matched SOP and past incidents
        incident_context: incoming incident context

    Returns:
        True if successfully sent, False otherwise
    """
    telegram_cfg = config.get("telegram") if config else None
    if not telegram_cfg or not telegram_cfg.get("enabled", False):
        log.info("Telegram log report disabled")
        return False

    bot_token = telegram_cfg.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = telegram_cfg.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        log.error("Telegram config incomplete — bot_token and chat_id are required")
        return False

    server_name = incident_context.get("server", "localhost") if incident_context else metrics.get("hostname", "localhost")
    severity = incident_context.get("severity", "warning").upper() if incident_context else "ALERT"
    patterns = incident_context.get("patterns", []) if incident_context else []
    pattern_str = ", ".join(patterns) if patterns else "Threshold Alert"
    alert_text = incident_context.get("text", "") if incident_context else ""

    inc_id = incident_context.get("incident_id") if incident_context and incident_context.get("incident_id") else f"INC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Day name in Indonesian
    day_names = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    now = datetime.now()
    day_id = day_names[now.weekday()]
    ts_header = now.strftime(f"{day_id}, %d %B %Y %H:%M WIB")

    # Matched SOP
    sop_line = "Tidak ada SOP yang cocok — Investigasi Umum"
    sop_id = ""
    if kb_match and kb_match.get("matched_sops"):
        top_sop = kb_match["matched_sops"][0]
        sop_id = top_sop.get("id", "")
        sop_line = f"{top_sop.get('title', 'SOP')} (`{sop_id}`)"

    # Collect critical/warning checks for per-check breakdown
    flagged = [r for r in (diagnosis_results or []) if r.get("status") in ("critical", "warning")]
    ok_count = len([r for r in (diagnosis_results or []) if r.get("status") == "ok"])
    total_count = len(diagnosis_results) if diagnosis_results else 0

    # Unified Header block with Company Branding
    lines = [
        f"*[{severity}] [PLATFORM BIGDATA] Incident Alert*",
        f"_{ts_header}_",
        f"",
        f"*Environment :* Platform Bigdata K8s Cluster",
        f"*Incident ID  :* `{inc_id}`",
        f"*Target Node  :* `{server_name}`",
        f"",
        f"Dear Ops Team,",
        f"",
    ]

    if flagged:
        lines.append(
            f"Terdapat *{len(flagged)} peringatan* dari pemantauan sistem "
            f"(total {total_count} check dijalankan, {ok_count} OK):"
        )
        lines.append(f"• *Trigger Event:* `{pattern_str}`")
        if alert_text and alert_text != pattern_str:
            lines.append(f"• *Ringkasan:* _{alert_text}_")
    else:
        lines.append(
            f"Sistem menjalankan *{total_count} check* otomatis — semua dalam status normal, "
            f"tidak ditemukan anomali yang memerlukan eskalasi."
        )

    lines.append("")

    # Per-check breakdown block (styled like Clarissa's table rows)
    DIVIDER = "─" * 32
    for r in flagged:
        status_label = r.get("status", "info").upper()
        check_name = r.get("check_name", r.get("command", "check"))
        check_output = r.get("output", "").strip()
        node = r.get("target", server_name)

        lines.append(DIVIDER)
        lines.append(f"*{status_label} | BARU*")
        lines.append(f"Check: `{check_name}`")
        lines.append(f"Node / Sumber: `{node}`")
        lines.append(f"")

        if check_output:
            # Show up to 6 lines for crash logs / events, 4 lines for others
            max_lines = 6 if "log" in check_name or "event" in check_name else 4
            output_lines = [l for l in check_output.splitlines() if l.strip() and not l.strip().lower().startswith("status:")][:max_lines]
            if output_lines:
                lines.append("Output Terdeteksi:")
                lines.append("```")
                for ol in output_lines:
                    lines.append(ol[:120])
                lines.append("```")

    if flagged:
        lines.append(DIVIDER)

    # SOP section
    lines.append("")
    lines.append(f"*Matched SOP:* {sop_line}")
    lines.append("")

    # Telemetry footer
    cpu = metrics.get("cpu_percent", 0)
    mem = metrics.get("memory_percent", 0)
    disk = metrics.get("disk_percent", 0)
    uptime = metrics.get("uptime_human", "N/A")
    lines.append(f"*Telemetri Host:* CPU `{cpu}%` | MEM `{mem}%` | DISK `{disk}%` | Uptime `{uptime}`")
    lines.append("")
    lines.append("_Peringatan yang sama tidak dikirim ulang selama periode insiden berlangsung._")
    lines.append("")
    lines.append("— Platform Bigdata Monitoring Agent")

    message_text = "\n".join(lines)

    # Truncate if needed (Telegram max 4096 chars)
    if len(message_text) > 4000:
        message_text = message_text[:3980] + "\n...\n— Platform Bigdata Monitoring Agent"

    # Inline Keyboard Action Buttons
    inline_keyboard = [
        [
            {"text": "Buka SOP Runbook", "callback_data": f"sop:{sop_id or 'general'}"},
            {"text": "Acknowledge", "callback_data": f"ack:{server_name}"},
        ],
        [
            {"text": "Restart Pod", "callback_data": f"restart:{server_name}"},
            {"text": "Full Telemetry", "callback_data": f"status:{server_name}"},
        ],
    ]

    send_msg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": inline_keyboard},
    }

    try:
        log.info("Sending Telegram log report to chat %s...", chat_id)
        resp = requests.post(send_msg_url, json=payload, timeout=15)
        if resp.status_code != 200:
            log.error("Telegram API error (log report): %d - %s", resp.status_code, resp.text[:200])
            return False
        log.info("Telegram log report sent successfully")
        return True
    except Exception as e:
        log.error("Failed to send Telegram log report: %s", e)
        return False

