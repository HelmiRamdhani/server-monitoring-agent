"""
The Workplace Brain — IT Ops & Incident Co-Pilot
================================================
Main orchestrator for the agent. Supports two modes:

  1. Scheduled polling mode (legacy): periodically collects metrics, parses logs
  2. Event-driven webhook mode (new): listens for webhook triggers from
     monitoring systems and helpdesk tickets, then runs the full 6-stage pipeline

Pipeline (event-driven mode):
  1. Trigger: webhook receives alert/ticket
  2. Ingestion: parse alert message, extract incident context
  3. Knowledge base lookup: match incident to SOPs, past incidents, architecture
  4. Diagnosis: run read-only checks (network, system, log query, monitoring API)
  5. Output: generate PDF report + send Teams/email notification
  6. Feedback loop: update KB, resolve ticket, create post-mortem (if critical)

Usage:
    python main.py                          # run scheduled polling once
    python main.py --loop                   # run scheduled polling continuously
    python main.py --webhook                # start webhook server (event-driven)
    python main.py --webhook --loop         # both: webhook server + scheduled polling
    python main.py --config path/cfg.yaml
"""

import sys
import os
import time
import signal
import logging
import argparse
import threading
from datetime import datetime

# Ensure src/ is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.config_loader import load_config, setup_logging
from modules.server_monitor import collect_metrics, check_thresholds
from modules.syslog_parser import parse_syslog, summarize_incidents
from modules.report_generator import generate_report, generate_periodic_report
from modules.notifier import send_email, send_teams, send_telegram, send_telegram_log_report
from modules.knowledge_base import KnowledgeBase
from modules.diagnosis_engine import DiagnosisEngine
from modules.feedback_loop import FeedbackLoop
from modules.webhook_receiver import start_webhook_server

log = logging.getLogger("agent.main")


class ServerMonitoringAgent:
    """
    Main agent that orchestrates the full IT ops co-pilot pipeline.
    Supports both scheduled polling and event-driven webhook modes.
    """

    def __init__(self, config_path: str = None):
        self.config = load_config(config_path)
        setup_logging(self.config)
        self.running = True

        # Initialize KB
        kb_dir = None
        kb_cfg = self.config.get("knowledge_base")
        if kb_cfg:
            kb_dir = kb_cfg.get("dir", None) if hasattr(kb_cfg, "get") else None
        self.kb = KnowledgeBase(kb_dir=kb_dir)

        # Initialize diagnosis engine
        self.diagnosis = DiagnosisEngine(config=self.config)

        # Initialize feedback loop
        self.feedback = FeedbackLoop(kb=self.kb, config=self.config)

        log.info("=" * 60)
        log.info("The Workplace Brain — IT Ops & Incident Co-Pilot")
        log.info("Server: %s", self.config.get("server", {}).get("label", "unknown"))
        log.info("KB: %d SOPs, %d incidents loaded",
                 len(self.kb.sops), len(self.kb.incidents))
        log.info("=" * 60)

    # ================================================================
    # Mode 1: Scheduled polling (legacy)
    # ================================================================
    def run_cycle(self) -> dict:
        """Execute one scheduled monitoring cycle (metrics + syslog + report)."""
        cycle_start = datetime.now()
        log.info("--- Starting monitoring cycle ---")

        results = {
            "cycle_start": cycle_start.strftime("%Y-%m-%d %H:%M:%S"),
            "metrics": None,
            "threshold_alerts": [],
            "incidents": [],
            "incident_summary": {},
            "report_path": None,
            "email_sent": False,
            "teams_sent": False,
            "errors": [],
        }

        # Collect metrics
        try:
            metrics = collect_metrics()
            results["metrics"] = metrics
        except Exception as e:
            log.error("Failed to collect metrics: %s", e)
            results["errors"].append(f"metrics: {e}")

        # Check thresholds
        try:
            if metrics:
                thresholds = self.config.get("thresholds")
                if thresholds:
                    alerts = check_thresholds(metrics, thresholds)
                    results["threshold_alerts"] = alerts
        except Exception as e:
            log.error("Failed to check thresholds: %s", e)
            results["errors"].append(f"thresholds: {e}")

        # Parse syslog
        try:
            incidents = parse_syslog(self.config)
            results["incidents"] = incidents
            results["incident_summary"] = summarize_incidents(incidents)
        except Exception as e:
            log.error("Failed to parse syslog: %s", e)
            results["errors"].append(f"syslog: {e}")

        # Generate report
        try:
            if metrics:
                report_path = generate_report(
                    metrics=metrics,
                    threshold_alerts=results["threshold_alerts"],
                    incidents=results["incidents"],
                    incident_summary=results["incident_summary"],
                    config=self.config,
                )
                results["report_path"] = report_path
        except Exception as e:
            log.error("Failed to generate report: %s", e)
            results["errors"].append(f"report: {e}")

        # Send notifications
        try:
            if results["report_path"]:
                results["email_sent"] = send_email(results["report_path"], self.config)
                results["teams_sent"] = send_teams(
                    results["report_path"],
                    metrics,
                    results["incident_summary"],
                    self.config,
                )
                results["telegram_sent"] = send_telegram(
                    results["report_path"],
                    metrics,
                    results["incident_summary"],
                    self.config,
                )
        except Exception as e:
            log.error("Failed to send notifications: %s", e)
            results["errors"].append(f"notify: {e}")

        cycle_end = datetime.now()
        duration = (cycle_end - cycle_start).total_seconds()
        log.info("--- Cycle completed in %.1fs ---", duration)
        self._print_summary(results)
        return results

    # ================================================================
    # Mode 2: Event-driven (webhook trigger)
    # ================================================================
    def process_incident(self, incident_context: dict) -> dict:
        """
        Process a single incident through the full 6-stage co-pilot pipeline.

        This is called by the webhook receiver when an alert or ticket arrives.

        Args:
            incident_context: dict with:
                - text: alert message or log text
                - patterns: list of pattern names
                - server: hostname
                - source: webhook source (prometheus, zabbix, jira, etc.)
                - severity: incident severity
                - timestamp: when alert was triggered

        Returns:
            Full results dict
        """
        pipeline_start = datetime.now()
        log.info("=" * 50)
        log.info("INCIDENT PIPELINE STARTED")
        log.info("Source: %s | Server: %s | Severity: %s",
                 incident_context.get("source", "unknown"),
                 incident_context.get("server", "unknown"),
                 incident_context.get("severity", "unknown"))
        log.info("Alert: %s", incident_context.get("text", "")[:200])
        log.info("=" * 50)

        results = {
            "pipeline_start": pipeline_start.strftime("%Y-%m-%d %H:%M:%S"),
            "incident_context": incident_context,
            "kb_match": None,
            "diagnosis_results": [],
            "diagnosis_summary": {},
            "metrics": None,
            "report_path": None,
            "email_sent": False,
            "teams_sent": False,
            "feedback": None,
            "errors": [],
        }

        # Stage 1: Ingestion (already done — incident_context is parsed)

        # Stage 2: Knowledge base lookup
        log.info("--- Stage 2: Knowledge base lookup ---")
        try:
            kb_match = self.kb.lookup(
                incident_text=incident_context.get("text", ""),
                incident_patterns=incident_context.get("patterns", []),
                server_name=incident_context.get("server"),
            )
            results["kb_match"] = kb_match

            if kb_match["matched_sops"]:
                log.info("Matched SOPs: %s",
                         [s["title"] for s in kb_match["matched_sops"][:3]])
            if kb_match["similar_incidents"]:
                log.info("Similar past incidents: %s",
                         [i["title"] for i in kb_match["similar_incidents"][:3]])
            if kb_match["escalation_target"]:
                log.info("Escalation target: %s", kb_match["escalation_target"])

        except Exception as e:
            log.error("KB lookup failed: %s", e)
            results["errors"].append(f"kb: {e}")

        # Stage 3: Diagnosis — run read-only checks
        log.info("--- Stage 3: Diagnosis ---")
        try:
            diagnosis_results = self.diagnosis.run_all_checks(
                incident_context=incident_context,
                kb_match=results.get("kb_match"),
            )
            results["diagnosis_results"] = diagnosis_results
            results["diagnosis_summary"] = self.diagnosis.summarize_results()
            log.info("Diagnosis: %d checks, %d critical/warning",
                     results["diagnosis_summary"]["total_checks"],
                     sum(v for k, v in results["diagnosis_summary"]["by_status"].items()
                         if k in ("critical", "warning")))
        except Exception as e:
            log.error("Diagnosis failed: %s", e)
            results["errors"].append(f"diagnosis: {e}")

        # Also collect current metrics for the report
        try:
            metrics = collect_metrics()
            results["metrics"] = metrics
        except Exception as e:
            log.error("Metrics collection failed: %s", e)
            results["errors"].append(f"metrics: {e}")

        # Stage 4: Generate enhanced report
        log.info("--- Stage 4: Report generation ---")
        try:
            if metrics:
                report_path = generate_report(
                    metrics=metrics,
                    threshold_alerts=[],  # threshold alerts not applicable for webhook mode
                    incidents=[{
                        "timestamp_raw": incident_context.get("timestamp", ""),
                        "source_file": incident_context.get("source", "webhook"),
                        "pattern_name": ", ".join(incident_context.get("patterns", [])),
                        "severity": incident_context.get("severity", "warning"),
                        "matched_line": incident_context.get("text", "")[:300],
                        "line_number": 0,
                    }],
                    incident_summary=summarize_incidents([{
                        "severity": incident_context.get("severity", "warning"),
                        "pattern_name": ", ".join(incident_context.get("patterns", [])),
                    }]),
                    config=self.config,
                    diagnosis_results=results.get("diagnosis_results"),
                    diagnosis_summary=results.get("diagnosis_summary"),
                    kb_match=results.get("kb_match"),
                )
                results["report_path"] = report_path
        except Exception as e:
            log.error("Report generation failed: %s", e)
            results["errors"].append(f"report: {e}")

        # Stage 5: Send notifications
        log.info("--- Stage 5: Notifications ---")
        try:
            if results["report_path"]:
                results["email_sent"] = send_email(results["report_path"], self.config)
                results["teams_sent"] = send_teams(
                    results["report_path"],
                    metrics if metrics else {},
                    {
                        "total": 1,
                        "by_severity": {incident_context.get("severity", "warning"): 1},
                        "by_pattern": {", ".join(incident_context.get("patterns", [])): 1},
                        "top_incidents": [],
                    },
                    self.config,
                )
                # Send single unified Telegram incident alert (Clarissa-style text with Action buttons)
                results["telegram_sent"] = send_telegram_log_report(
                    metrics=metrics if metrics else {},
                    config=self.config,
                    diagnosis_results=results.get("diagnosis_results"),
                    kb_match=results.get("kb_match"),
                    incident_context=incident_context,
                )
        except Exception as e:
            log.error("Notification failed: %s", e)
            results["errors"].append(f"notify: {e}")

        # Stage 6: Feedback loop (auto-resolve for non-critical)
        log.info("--- Stage 6: Feedback loop ---")
        try:
            incident_for_kb = {
                "incident_id": f"INC-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "server": incident_context.get("server", "unknown"),
                "severity": incident_context.get("severity", "warning"),
                "title": ", ".join(incident_context.get("patterns", ["Detected incident"])),
                "symptoms": [incident_context.get("text", "")],
                "root_cause": "TBD - requires manual review",
                "resolution": "Agent processed incident and generated diagnostic report. Manual review required.",
                "sop_used": results["kb_match"]["matched_sops"][0]["id"] if results["kb_match"] and results["kb_match"]["matched_sops"] else "N/A",
                "diagnosis_commands_run": [r["command"] for r in results.get("diagnosis_results", [])],
                "time_to_resolve": f"{(datetime.now() - pipeline_start).total_seconds():.0f} seconds (automated)",
                "follow_up": "Review diagnostic results, determine root cause, apply fix",
                "pattern_signatures": incident_context.get("patterns", []),
                "ticket_id": incident_context.get("raw", {}).get("ticket_id"),
            }

            feedback_results = self.feedback.process_resolution(incident_for_kb)
            results["feedback"] = feedback_results
        except Exception as e:
            log.error("Feedback loop failed: %s", e)
            results["errors"].append(f"feedback: {e}")

        pipeline_end = datetime.now()
        duration = (pipeline_end - pipeline_start).total_seconds()
        log.info("=" * 50)
        log.info("INCIDENT PIPELINE COMPLETE in %.1fs", duration)
        log.info("Report: %s", results.get("report_path", "N/A"))
        log.info("Email: %s | Teams: %s", results["email_sent"], results["teams_sent"])
        if results["feedback"]:
            log.info("KB updated: %s | Post-mortem: %s",
                     results["feedback"]["kb_updated"],
                     results["feedback"]["post_mortem_created"])
        log.info("=" * 50)

        return results

    # ================================================================
    # Utilities
    # ================================================================
    def _print_summary(self, results: dict):
        """Print a human-readable summary to the log."""
        log.info("=" * 40)
        log.info("CYCLE SUMMARY")
        log.info("=" * 40)
        if results["metrics"]:
            m = results["metrics"]
            log.info("CPU: %.1f%% | MEM: %.1f%% | DISK: %.1f%%",
                     m.get("cpu_percent", 0), m.get("memory_percent", 0), m.get("disk_percent", 0))
        log.info("Threshold alerts: %d", len(results["threshold_alerts"]))
        log.info("Incidents found: %d", results["incident_summary"].get("total", 0))
        log.info("Report: %s", results.get("report_path", "N/A"))
        log.info("Email sent: %s", results["email_sent"])
        log.info("Teams sent: %s", results["teams_sent"])
        if results["errors"]:
            log.warning("Errors: %s", results["errors"])
        log.info("=" * 40)

    def run_periodic_report(self, period: str = "weekly") -> dict:
        """
        Generate and deliver an executive periodic report (Weekly or Monthly).
        Aggregates incidents over the period and includes SLA/KPI metrics.

        Args:
            period: "weekly" (past 7 days) or "monthly" (past 30 days)

        Returns:
            dict with report results
        """
        period_lower = period.lower()
        days = 7 if period_lower == "weekly" else 30
        log.info("=" * 60)
        log.info("GENERATING %s EXECUTIVE REPORT (Past %d Days)", period_lower.upper(), days)
        log.info("=" * 60)

        results = {
            "period": period_lower,
            "period_days": days,
            "metrics": None,
            "analytics": None,
            "report_path": None,
            "email_sent": False,
            "teams_sent": False,
            "errors": [],
        }

        # 1. Collect current server metrics
        try:
            results["metrics"] = collect_metrics()
        except Exception as e:
            log.error("Failed to collect metrics for periodic report: %s", e)
            results["errors"].append(f"metrics: {e}")

        # 2. Collect incident analytics from KB
        try:
            results["analytics"] = self.kb.get_incident_analytics(days=days)
        except Exception as e:
            log.error("Failed to get incident analytics: %s", e)
            results["errors"].append(f"analytics: {e}")

        # 3. Generate Periodic PDF report
        try:
            if results["metrics"] and results["analytics"]:
                report_path = generate_periodic_report(
                    period=period_lower,
                    metrics=results["metrics"],
                    analytics=results["analytics"],
                    config=self.config,
                )
                results["report_path"] = report_path
        except Exception as e:
            log.error("Failed to generate periodic report: %s", e)
            results["errors"].append(f"report: {e}")

        # 4. Deliver notifications
        try:
            if results["report_path"]:
                results["email_sent"] = send_email(results["report_path"], self.config)
                analytics = results["analytics"] or {}
                results["teams_sent"] = send_teams(
                    results["report_path"],
                    results["metrics"] or {},
                    {
                        "total": analytics.get("total_incidents", 0),
                        "by_severity": analytics.get("by_severity", {}),
                        "by_pattern": dict(analytics.get("top_root_causes", [])),
                        "top_incidents": [],
                    },
                    self.config,
                )
        except Exception as e:
            log.error("Failed to send periodic notifications: %s", e)
            results["errors"].append(f"notify: {e}")

        log.info("=" * 60)
        log.info("%s REPORT COMPLETED: %s", period_lower.upper(), results.get("report_path", "N/A"))
        log.info("Email: %s | Teams: %s", results["email_sent"], results["teams_sent"])
        log.info("=" * 60)
        return results

    def schedule_periodic_reports(self):
        """
        Run built-in scheduler for Weekly (Mondays at 08:00) and Monthly (Day 1 at 07:00).
        """
        import schedule
        log.info("Starting built-in periodic report scheduler...")
        log.info("  Weekly report scheduled: Mondays at 08:00")
        log.info("  Monthly report scheduled: Daily check at 07:00 (triggers on 1st of month)")

        def _weekly_job():
            log.info("Triggering scheduled weekly report...")
            self.run_periodic_report("weekly")

        def _monthly_check():
            if datetime.now().day == 1:
                log.info("Triggering scheduled monthly report...")
                self.run_periodic_report("monthly")

        schedule.every().monday.at("08:00").do(_weekly_job)
        schedule.every().day.at("07:00").do(_monthly_check)

        def _signal_handler(sig, frame):
            log.info("Stopping periodic report scheduler...")
            self.running = False

        signal.signal(signal.SIGINT, _signal_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _signal_handler)

        while self.running:
            schedule.run_pending()
            time.sleep(30)

        log.info("Periodic report scheduler stopped.")

    def run_once(self):
        """Run a single scheduled monitoring cycle."""
        self.run_cycle()

    def run_loop(self):
        """Run scheduled monitoring cycles continuously."""
        schedule_cfg = self.config.get("schedule", {})
        if isinstance(schedule_cfg, dict):
            interval = schedule_cfg.get("interval_minutes", 30)
        else:
            interval = getattr(schedule_cfg, "interval_minutes", 30)

        log.info("Starting continuous polling mode — interval: %d minutes", interval)

        def _signal_handler(sig, frame):
            log.info("Received interrupt signal, stopping...")
            self.running = False

        signal.signal(signal.SIGINT, _signal_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _signal_handler)

        while self.running:
            self.run_cycle()
            if not self.running:
                break
            log.info("Next cycle in %d minutes...", interval)
            sleep_seconds = interval * 60
            slept = 0
            while slept < sleep_seconds and self.running:
                time.sleep(1)
                slept += 1

        log.info("Agent stopped.")

    def start_webhook_mode(self):
        """Start the webhook server for event-driven mode."""
        webhook_cfg = self.config.get("webhook", {})
        host = webhook_cfg.get("host", "0.0.0.0") if webhook_cfg else "0.0.0.0"
        port = webhook_cfg.get("port", 8080) if webhook_cfg else 8080

        log.info("Starting webhook server (event-driven mode)")
        start_webhook_server(agent=self, host=host, port=port)


def main():
    parser = argparse.ArgumentParser(
        description="The Workplace Brain — IT Ops & Incident Co-Pilot"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config YAML file (default: config/config.yaml)",
        default=None,
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run scheduled polling continuously (interval from config)",
    )
    parser.add_argument(
        "--webhook",
        action="store_true",
        help="Start webhook server for event-driven mode",
    )
    parser.add_argument(
        "--report-period",
        choices=["snapshot", "weekly", "monthly"],
        default="snapshot",
        help="Generate periodic executive report (weekly=past 7 days, monthly=past 30 days)",
    )
    parser.add_argument(
        "--schedule-reports",
        action="store_true",
        help="Run background scheduler for automated Weekly (Mondays 08:00) and Monthly (1st 07:00) reports",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scheduled polling cycle and exit (default)",
    )
    args = parser.parse_args()

    agent = ServerMonitoringAgent(config_path=args.config)

    if args.schedule_reports:
        # Built-in periodic scheduler
        agent.schedule_periodic_reports()
    elif args.report_period in ("weekly", "monthly"):
        # Periodic report generation (one-shot, ideal for OS cron jobs)
        agent.run_periodic_report(args.report_period)
    elif args.webhook and args.loop:
        # Both: start webhook server in background + scheduled polling in foreground
        log.info("Starting in hybrid mode: webhook + scheduled polling")
        webhook_thread = threading.Thread(target=agent.start_webhook_mode, daemon=True)
        webhook_thread.start()
        agent.run_loop()
    elif args.webhook:
        # Only webhook mode
        agent.start_webhook_mode()
    elif args.loop:
        # Only scheduled polling
        agent.run_loop()
    else:
        # Default: run once
        agent.run_once()


if __name__ == "__main__":
    main()
