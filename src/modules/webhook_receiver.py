"""
Webhook Receiver for The Workplace Brain.
Listens for incoming webhook triggers from:
- Monitoring systems (Zabbix, Prometheus Alertmanager, Datadog, etc.)
- Helpdesk / ticketing systems (Jira, GLPI, etc.)

Provides an HTTP server (Flask-based, lightweight) that receives POST payloads,
parses them into a standardized incident context, and passes them to the agent pipeline.
"""

import json
import logging
from datetime import datetime
from typing import Any

from http.server import HTTPServer, BaseHTTPRequestHandler

log = logging.getLogger("agent.webhook")


class WebhookPayload:
    """Standardized webhook payload structure."""

    def __init__(self):
        self.source = ""          # "prometheus", "zabbix", "jira", "manual", etc.
        self.alert_name = ""
        self.severity = "warning"
        self.message = ""
        self.server = "localhost"
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.raw_payload = {}

    def to_incident_context(self) -> dict:
        """Convert to incident context for the agent pipeline."""
        return {
            "text": self.message,
            "patterns": [self.alert_name] if self.alert_name else [],
            "server": self.server,
            "source": self.source,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "raw": self.raw_payload,
        }

    def __repr__(self):
        return f"WebhookPayload(source={self.source}, alert={self.alert_name}, severity={self.severity}, server={self.server})"


def parse_prometheus_alert(payload: dict) -> WebhookPayload:
    """Parse Prometheus Alertmanager webhook payload."""
    wp = WebhookPayload()
    wp.source = "prometheus"
    wp.raw_payload = payload

    alerts = payload.get("alerts", [])
    if alerts:
        alert = alerts[0]
        wp.alert_name = alert.get("labels", {}).get("alertname", "")
        wp.severity = alert.get("labels", {}).get("severity", "warning")
        wp.server = alert.get("labels", {}).get("instance", "localhost")
        wp.message = alert.get("annotations", {}).get("summary", "") or \
                     alert.get("annotations", {}).get("description", "")
        wp.timestamp = alert.get("startsAt", wp.timestamp)

    return wp


def parse_zabbix_alert(payload: dict) -> WebhookPayload:
    """Parse Zabbix webhook payload."""
    wp = WebhookPayload()
    wp.source = "zabbix"
    wp.raw_payload = payload

    wp.alert_name = payload.get("event", {}).get("name", "") or payload.get("trigger_name", "")
    wp.severity = payload.get("event", {}).get("severity", "warning")
    wp.server = payload.get("event", {}).get("host", "localhost") or payload.get("hostname", "localhost")
    wp.message = payload.get("event", {}).get("message", "") or payload.get("message", "")
    wp.timestamp = payload.get("event", {}).get("timestamp", wp.timestamp)

    return wp


def parse_generic_alert(payload: dict) -> WebhookPayload:
    """Parse a generic webhook payload with standard fields."""
    wp = WebhookPayload()
    wp.source = payload.get("source", "generic")
    wp.raw_payload = payload

    wp.alert_name = payload.get("alert_name", payload.get("title", ""))
    wp.severity = payload.get("severity", "warning")
    wp.server = payload.get("server", payload.get("host", payload.get("hostname", "localhost")))
    wp.message = payload.get("message", payload.get("description", payload.get("text", "")))
    wp.timestamp = payload.get("timestamp", wp.timestamp)

    return wp


def parse_jira_ticket(payload: dict) -> WebhookPayload:
    """Parse Jira webhook payload (simplified)."""
    wp = WebhookPayload()
    wp.source = "jira"
    wp.raw_payload = payload

    issue = payload.get("issue", {})
    wp.alert_name = issue.get("key", "")
    fields = issue.get("fields", {})
    wp.severity = fields.get("priority", {}).get("name", "warning").lower()
    wp.message = fields.get("summary", "") + " - " + fields.get("description", "")
    wp.timestamp = fields.get("created", wp.timestamp)

    return wp


def parse_webhook(source: str, payload: dict) -> WebhookPayload:
    """
    Route webhook parsing based on source type.

    Args:
        source: webhook source identifier (from URL path or header)
        payload: raw JSON body

    Returns:
        WebhookPayload object
    """
    parsers = {
        "prometheus": parse_prometheus_alert,
        "alertmanager": parse_prometheus_alert,
        "zabbix": parse_zabbix_alert,
        "jira": parse_jira_ticket,
        "helpdesk": parse_jira_ticket,
        "generic": parse_generic_alert,
    }

    parser = parsers.get(source.lower(), parse_generic_alert)
    try:
        wp = parser(payload)
        if not wp.source or wp.source == "generic":
            wp.source = source
        log.info("Parsed webhook [%s]: %s", source, wp)
        return wp
    except Exception as e:
        log.error("Error parsing webhook payload from %s: %s", source, e)
        wp = parse_generic_alert(payload)
        wp.source = source
        return wp


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for incoming webhooks."""

    agent = None  # Set externally before starting server

    def _send_response(self, code: int, message: str):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": message}).encode("utf-8"))

    def do_POST(self):
        """Handle POST webhook requests."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            log.error("Invalid JSON in webhook body")
            self._send_response(400, "invalid JSON")
            return

        # Extract source from path: /webhook/<source>
        path_parts = self.path.strip("/").split("/")
        source = path_parts[-1] if len(path_parts) > 1 else "generic"

        log.info("Received webhook from source: %s, path: %s", source, self.path)

        # Parse the webhook
        wp = parse_webhook(source, payload)
        incident_context = wp.to_incident_context()

        # Process through agent pipeline if agent is set
        if self.agent:
            try:
                log.info("Passing incident to agent pipeline: %s", wp.alert_name)
                self.agent.process_incident(incident_context)
                self._send_response(200, "incident processed")
            except Exception as e:
                log.error("Agent processing error: %s", e)
                self._send_response(500, f"agent error: {e}")
        else:
            log.warning("No agent connected to webhook handler")
            self._send_response(200, "received but no agent")

    def do_GET(self):
        """Health check endpoint."""
        if self.path == "/health":
            self._send_response(200, "ok")
        else:
            self._send_response(404, "not found")

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        log.debug("HTTP: " + format % args)


def start_webhook_server(agent, host: str = "0.0.0.0", port: int = 8080):
    """
    Start the webhook receiver server.

    Args:
        agent: ServerMonitoringAgent instance (must have process_incident method)
        host: bind address
        port: bind port
    """
    WebhookHandler.agent = agent
    server = HTTPServer((host, port), WebhookHandler)

    log.info("=" * 50)
    log.info("Webhook receiver started on %s:%d", host, port)
    log.info("Endpoints:")
    log.info("  POST /webhook/prometheus   - Prometheus alerts")
    log.info("  POST /webhook/zabbix        - Zabbix alerts")
    log.info("  POST /webhook/jira         - Jira ticket events")
    log.info("  POST /webhook/generic       - Generic alerts")
    log.info("  GET  /health                - Health check")
    log.info("=" * 50)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Webhook server stopped by user")
        server.server_close()
