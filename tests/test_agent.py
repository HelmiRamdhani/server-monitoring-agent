"""
Comprehensive test suite for Server Monitoring Agent.
Covers all modules including the new KB, Diagnosis, Webhook, and Feedback Loop.

Run: python -m pytest tests/test_agent.py -v
  or: python tests/test_agent.py
"""

import sys
import os
import json
import unittest
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from modules.config_loader import load_config, Config
from modules.server_monitor import collect_metrics, check_thresholds
from modules.syslog_parser import parse_syslog, summarize_incidents
from modules.knowledge_base import KnowledgeBase
from modules.diagnosis_engine import DiagnosisEngine
from modules.feedback_loop import FeedbackLoop
from modules.webhook_receiver import (
    parse_prometheus_alert,
    parse_zabbix_alert,
    parse_generic_alert,
    parse_jira_ticket,
    parse_webhook,
)


# ================================================================
# Helper: get project root and testing config
# ================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTING_CONFIG_PATH = str(PROJECT_ROOT / "config" / "config.testing.yaml")


def get_test_config():
    """Load the testing config (safe: no email, no Teams)."""
    return load_config(TESTING_CONFIG_PATH)


# ================================================================
# 1. Server Monitor Tests
# ================================================================
class TestServerMonitor(unittest.TestCase):
    """Test server metric collection."""

    def test_collect_metrics(self):
        metrics = collect_metrics()
        self.assertIn("cpu_percent", metrics)
        self.assertIn("memory_percent", metrics)
        self.assertIn("disk_percent", metrics)
        self.assertIn("hostname", metrics)
        self.assertIsInstance(metrics["cpu_percent"], (int, float))
        self.assertGreaterEqual(metrics["cpu_percent"], 0)
        self.assertLessEqual(metrics["cpu_percent"], 100)

    def test_check_thresholds_no_alerts(self):
        """Low values should not trigger alerts."""
        thresholds = Config({
            "cpu_warning": 75,
            "cpu_critical": 90,
            "memory_warning": 80,
            "memory_critical": 92,
            "disk_warning": 80,
            "disk_critical": 90,
            "uptime_min_seconds": 0,
        })
        metrics = {
            "cpu_percent": 10,
            "memory_percent": 20,
            "disk_percent": 30,
            "uptime_seconds": 999999,
            "uptime_human": "10d 0h 0m",
        }
        alerts = check_thresholds(metrics, thresholds)
        self.assertEqual(len(alerts), 0)

    def test_check_thresholds_critical(self):
        """High CPU should trigger critical alert."""
        thresholds = Config({
            "cpu_warning": 75,
            "cpu_critical": 90,
            "memory_warning": 80,
            "memory_critical": 92,
            "disk_warning": 80,
            "disk_critical": 90,
            "uptime_min_seconds": 0,
        })
        metrics = {
            "cpu_percent": 95,
            "memory_percent": 50,
            "disk_percent": 50,
            "uptime_seconds": 999999,
            "uptime_human": "10d 0h 0m",
        }
        alerts = check_thresholds(metrics, thresholds)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "critical")
        self.assertEqual(alerts[0]["metric"], "CPU")

    def test_check_thresholds_warning(self):
        """Memory at 85% should trigger warning."""
        thresholds = Config({
            "cpu_warning": 75,
            "cpu_critical": 90,
            "memory_warning": 80,
            "memory_critical": 92,
            "disk_warning": 80,
            "disk_critical": 90,
            "uptime_min_seconds": 0,
        })
        metrics = {
            "cpu_percent": 10,
            "memory_percent": 85,
            "disk_percent": 30,
            "uptime_seconds": 999999,
            "uptime_human": "10d 0h 0m",
        }
        alerts = check_thresholds(metrics, thresholds)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "warning")
        self.assertEqual(alerts[0]["metric"], "Memory")

    def test_check_thresholds_uptime(self):
        """Recent reboot should trigger uptime warning."""
        thresholds = Config({
            "cpu_warning": 75,
            "cpu_critical": 90,
            "memory_warning": 80,
            "memory_critical": 92,
            "disk_warning": 80,
            "disk_critical": 90,
            "uptime_min_seconds": 300,
        })
        metrics = {
            "cpu_percent": 10,
            "memory_percent": 20,
            "disk_percent": 30,
            "uptime_seconds": 60,
            "uptime_human": "0d 0h 1m",
        }
        alerts = check_thresholds(metrics, thresholds)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["metric"], "Uptime")

    def test_check_thresholds_multiple(self):
        """Multiple breached thresholds."""
        thresholds = Config({
            "cpu_warning": 75,
            "cpu_critical": 90,
            "memory_warning": 80,
            "memory_critical": 92,
            "disk_warning": 80,
            "disk_critical": 90,
            "uptime_min_seconds": 0,
        })
        metrics = {
            "cpu_percent": 95,
            "memory_percent": 95,
            "disk_percent": 95,
            "uptime_seconds": 999999,
            "uptime_human": "10d 0h 0m",
        }
        alerts = check_thresholds(metrics, thresholds)
        self.assertEqual(len(alerts), 3)
        self.assertTrue(all(a["severity"] == "critical" for a in alerts))


# ================================================================
# 2. Syslog Parser Tests
# ================================================================
class TestSyslogParser(unittest.TestCase):
    """Test syslog parsing functions."""

    def test_summarize_incidents_empty(self):
        summary = summarize_incidents([])
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["by_severity"], {})
        self.assertEqual(summary["top_incidents"], [])

    def test_summarize_incidents_with_data(self):
        incidents = [
            {"pattern_name": "SSH failed login", "severity": "warning", "timestamp_raw": "2026-01-01 10:00:00", "matched_line": "test"},
            {"pattern_name": "SSH failed login", "severity": "warning", "timestamp_raw": "2026-01-01 10:01:00", "matched_line": "test"},
            {"pattern_name": "Out of memory", "severity": "critical", "timestamp_raw": "2026-01-01 10:02:00", "matched_line": "test"},
        ]
        summary = summarize_incidents(incidents)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["by_severity"]["warning"], 2)
        self.assertEqual(summary["by_severity"]["critical"], 1)
        self.assertEqual(summary["by_pattern"]["SSH failed login"], 2)
        self.assertEqual(summary["by_pattern"]["Out of memory"], 1)
        self.assertEqual(len(summary["top_incidents"]), 1)

    def test_parse_syslog_with_sample_file(self):
        """Test parsing the sample syslog file with testing config."""
        config = get_test_config()
        incidents = parse_syslog(config)
        self.assertGreater(len(incidents), 0, "Should detect incidents from sample syslog")

        # Verify specific patterns detected
        patterns_found = set(i["pattern_name"] for i in incidents)
        self.assertIn("SSH failed login", patterns_found)
        self.assertIn("Out of memory", patterns_found)
        self.assertIn("Service crash", patterns_found)
        self.assertIn("Disk full", patterns_found)

    def test_parse_syslog_severity_distribution(self):
        """Ensure sample syslog produces both warnings and criticals."""
        config = get_test_config()
        incidents = parse_syslog(config)
        summary = summarize_incidents(incidents)
        self.assertIn("warning", summary["by_severity"])
        self.assertIn("critical", summary["by_severity"])


# ================================================================
# 3. Config Loader Tests
# ================================================================
class TestConfigLoader(unittest.TestCase):
    """Test config loading."""

    def test_load_config(self):
        config = load_config()
        self.assertIsNotNone(config)
        server = config.get("server")
        self.assertIsNotNone(server)

    def test_load_testing_config(self):
        config = get_test_config()
        self.assertIsNotNone(config)
        # Email should be disabled in testing config
        email_cfg = config.get("email")
        self.assertFalse(email_cfg.get("enabled", True))

    def test_config_attribute_access(self):
        config = Config({"server": {"host": "localhost", "label": "Test"}})
        server = config.get("server")
        self.assertEqual(server.get("host"), "localhost")
        self.assertEqual(server.get("label"), "Test")

    def test_config_get_with_default(self):
        config = Config({"key1": "value1"})
        self.assertEqual(config.get("key1"), "value1")
        self.assertEqual(config.get("nonexistent", "default"), "default")


# ================================================================
# 4. Knowledge Base Tests
# ================================================================
class TestKnowledgeBase(unittest.TestCase):
    """Test knowledge base loading and lookup."""

    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase(kb_dir=str(PROJECT_ROOT / "kb"))

    def test_sops_loaded(self):
        """At least 5 SOP files should be loaded (including K8s and Longhorn SOPs)."""
        self.assertGreaterEqual(len(self.kb.sops), 5, f"Expected at least 5 SOPs, got {len(self.kb.sops)}")

    def test_sop_ids_parsed(self):
        """Each SOP should have a non-empty ID parsed from Markdown metadata."""
        for sop in self.kb.sops:
            self.assertTrue(sop["id"], f"SOP has empty ID: {sop['filepath']}")
            self.assertTrue(sop["id"].startswith("sop-"),
                            f"SOP ID should start with 'sop-': got '{sop['id']}' from {sop['filepath']}")

    def test_sop_triggers_parsed(self):
        """Each SOP should have at least one trigger parsed."""
        for sop in self.kb.sops:
            self.assertGreater(len(sop["triggers"]), 0,
                               f"SOP '{sop['id']}' has no triggers — parser may be broken")

    def test_sop_titles_parsed(self):
        """Each SOP should have a meaningful title."""
        for sop in self.kb.sops:
            self.assertNotEqual(sop["title"], sop["id"],
                                f"SOP '{sop['id']}' title not parsed, using filename fallback")

    def test_incidents_loaded(self):
        """Incident history should have at least 3 entries."""
        self.assertGreaterEqual(len(self.kb.incidents), 3)

    def test_architecture_loaded(self):
        """Architecture data should be loaded."""
        self.assertIn("servers", self.kb.architecture)

    def test_lookup_oom(self):
        """OOM incident text should match OOM SOP."""
        result = self.kb.lookup(
            incident_text="Out of memory: Kill process 8899 (php-fpm)",
            incident_patterns=["Out of memory"],
            server_name="web-prod-01",
        )
        self.assertGreater(len(result["matched_sops"]), 0, "No SOPs matched for OOM incident")
        # The best match should be the OOM killer SOP
        best_sop = result["matched_sops"][0]
        self.assertIn("oom", best_sop["id"].lower())

    def test_lookup_ssh(self):
        """SSH brute force text should match SSH SOP."""
        result = self.kb.lookup(
            incident_text="Failed password for root from 192.168.1.100",
            incident_patterns=["SSH failed login"],
        )
        self.assertGreater(len(result["matched_sops"]), 0, "No SOPs matched for SSH incident")
        best_sop = result["matched_sops"][0]
        self.assertIn("ssh", best_sop["id"].lower())

    def test_lookup_disk_full(self):
        """Disk full text should match disk full SOP."""
        result = self.kb.lookup(
            incident_text="No space left on device",
            incident_patterns=["Disk full"],
        )
        self.assertGreater(len(result["matched_sops"]), 0, "No SOPs matched for disk full")

    def test_lookup_similar_incidents(self):
        """OOM incident should find similar past incidents."""
        result = self.kb.lookup(
            incident_text="Out of memory: Kill process php-fpm",
            incident_patterns=["Out of memory"],
            server_name="web-prod-01",
        )
        self.assertGreater(len(result["similar_incidents"]), 0,
                           "No similar incidents found for OOM on web-prod-01")

    def test_lookup_architecture_context(self):
        """Looking up a known server should return architecture context."""
        result = self.kb.lookup(
            incident_text="some error",
            server_name="web-prod-01",
        )
        self.assertIsNotNone(result["architecture_context"],
                             "Architecture context not found for web-prod-01")
        self.assertEqual(result["architecture_context"]["hostname"], "web-prod-01")

    def test_lookup_escalation_target(self):
        """Known server should have an escalation target."""
        result = self.kb.lookup(
            incident_text="some error",
            server_name="web-prod-01",
        )
        self.assertIsNotNone(result["escalation_target"])

    def test_incident_analytics_structure(self):
        """Analytics should return the correct structure and period filtering."""
        analytics_7 = self.kb.get_incident_analytics(days=7)
        self.assertEqual(analytics_7["period_days"], 7)
        self.assertIn("total_incidents", analytics_7)
        self.assertIn("by_severity", analytics_7)
        self.assertIn("by_server", analytics_7)
        self.assertIn("status_counts", analytics_7)
        self.assertIn("top_root_causes", analytics_7)
        self.assertIn("top_sops_used", analytics_7)

        analytics_30 = self.kb.get_incident_analytics(days=30)
        self.assertEqual(analytics_30["period_days"], 30)
        self.assertGreaterEqual(analytics_30["total_incidents"], analytics_7["total_incidents"])


# ================================================================
# 5. Diagnosis Engine Tests
# ================================================================
class TestDiagnosisEngine(unittest.TestCase):
    """Test diagnosis engine logic."""

    @classmethod
    def setUpClass(cls):
        cls.config = get_test_config()
        cls.engine = DiagnosisEngine(config=cls.config)

    def test_determine_status_critical(self):
        """Error conditions should return critical."""
        self.assertEqual(self.engine._determine_status("connection refused"), "critical")
        self.assertEqual(self.engine._determine_status("ping timed out"), "critical")
        self.assertEqual(self.engine._determine_status("DNS resolution failed for xyz"), "critical")

    def test_determine_status_ok(self):
        """Clean/healthy outputs should return ok."""
        self.assertEqual(self.engine._determine_status("no matches found for terms: [error]"), "ok")
        self.assertEqual(self.engine._determine_status("host is local, ping not needed"), "ok")
        self.assertEqual(self.engine._determine_status("no failed services"), "ok")
        self.assertEqual(self.engine._determine_status("docker not installed"), "ok")

    def test_determine_status_port_closed_is_not_critical(self):
        """A closed port should NOT be critical (it's expected for non-configured services)."""
        status = self.engine._determine_status("port 6379 is CLOSED")
        self.assertNotEqual(status, "critical",
                            "Closed port should not be marked critical — it may be expected")

    def test_determine_status_explicit_markers(self):
        """Explicit status markers should take priority."""
        self.assertEqual(
            self.engine._determine_status("Memory: 95% used (8GB / 8GB) — status: CRITICAL"),
            "critical"
        )
        self.assertEqual(
            self.engine._determine_status("C:\\: 45% used (status: OK) - 500GB total"),
            "ok"
        )
        self.assertEqual(
            self.engine._determine_status("Memory: 85% used — status: WARNING"),
            "warning"
        )

    def test_run_all_checks(self):
        """Running all checks should produce at least some results."""
        incident = {
            "text": "Out of memory: Kill process php-fpm",
            "patterns": ["Out of memory"],
            "server": "localhost",
        }
        results = self.engine.run_all_checks(incident)
        self.assertGreater(len(results), 0, "Diagnosis should produce at least 1 check result")

    def test_summarize_results(self):
        """Summary should have the expected structure."""
        incident = {
            "text": "Out of memory",
            "patterns": ["Out of memory"],
            "server": "localhost",
        }
        self.engine.run_all_checks(incident)
        summary = self.engine.summarize_results()
        self.assertIn("total_checks", summary)
        self.assertIn("by_status", summary)
        self.assertIn("by_type", summary)
        self.assertGreater(summary["total_checks"], 0)


# ================================================================
# 6. Webhook Receiver Tests (parser only)
# ================================================================
class TestWebhookReceiver(unittest.TestCase):
    """Test webhook payload parsing."""

    def test_parse_prometheus_alert(self):
        payload = {
            "alerts": [{
                "labels": {
                    "alertname": "HighMemoryUsage",
                    "severity": "critical",
                    "instance": "web-prod-01",
                },
                "annotations": {
                    "summary": "Memory usage above 90% on web-prod-01",
                },
                "startsAt": "2026-10-23T09:00:00Z",
            }]
        }
        wp = parse_prometheus_alert(payload)
        ctx = wp.to_incident_context()
        self.assertEqual(wp.source, "prometheus")
        self.assertEqual(ctx["severity"], "critical")
        self.assertEqual(ctx["server"], "web-prod-01")
        self.assertIn("HighMemoryUsage", ctx["patterns"])
        self.assertIn("Memory usage", ctx["text"])

    def test_parse_zabbix_alert(self):
        payload = {
            "event": {
                "name": "Disk space critical",
                "severity": "critical",
                "host": "db-prod-01",
                "message": "Disk usage exceeded 95% on /var",
            }
        }
        wp = parse_zabbix_alert(payload)
        ctx = wp.to_incident_context()
        self.assertEqual(wp.source, "zabbix")
        self.assertEqual(ctx["server"], "db-prod-01")
        self.assertIn("Disk space critical", ctx["patterns"])

    def test_parse_generic_alert(self):
        payload = {
            "source": "datadog",
            "alert_name": "CPU spike",
            "severity": "warning",
            "server": "app-prod-01",
            "message": "CPU at 98% for 5 minutes",
        }
        wp = parse_generic_alert(payload)
        ctx = wp.to_incident_context()
        self.assertEqual(wp.source, "datadog")
        self.assertEqual(ctx["severity"], "warning")
        self.assertEqual(ctx["server"], "app-prod-01")

    def test_parse_jira_ticket(self):
        payload = {
            "issue": {
                "key": "OPS-1234",
                "fields": {
                    "priority": {"name": "High"},
                    "summary": "Server web-prod-01 unresponsive",
                    "description": "Users report 502 errors since 09:00",
                    "created": "2026-10-23T09:00:00+07:00",
                },
            }
        }
        wp = parse_jira_ticket(payload)
        ctx = wp.to_incident_context()
        self.assertEqual(wp.source, "jira")
        self.assertIn("OPS-1234", ctx["patterns"])

    def test_parse_webhook_routing(self):
        """parse_webhook should route to the correct parser."""
        payload = {"alerts": [{"labels": {"alertname": "Test"}}]}
        wp = parse_webhook("prometheus", payload)
        self.assertEqual(wp.source, "prometheus")

        wp2 = parse_webhook("unknown_system", {"message": "test"})
        self.assertEqual(wp2.source, "unknown_system")


# ================================================================
# 7. Feedback Loop Tests
# ================================================================
class TestFeedbackLoop(unittest.TestCase):
    """Test feedback loop safety logic."""

    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase(kb_dir=str(PROJECT_ROOT / "kb"))
        cls.config = get_test_config()
        cls.feedback = FeedbackLoop(kb=cls.kb, config=cls.config)

    def test_triage_mode_no_ticket_resolution(self):
        """When root_cause is TBD, ticket should NOT be resolved."""
        incident = {
            "incident_id": "TEST-TRIAGE-001",
            "title": "Test triage incident",
            "severity": "critical",
            "server": "web-prod-01",
            "symptoms": ["test symptom"],
            "root_cause": "TBD - requires manual review",
            "resolution": "Agent generated report",
            "ticket_id": "OPS-9999",
            "pattern_signatures": ["test"],
        }
        results = self.feedback.process_resolution(incident)
        self.assertEqual(results["mode"], "triage")
        self.assertFalse(results["ticket_resolved"],
                         "Ticket should NOT be resolved in triage mode")
        self.assertFalse(results["post_mortem_created"],
                         "Post-mortem should NOT be created when root cause is TBD")

    def test_resolution_mode_with_confirmed_root_cause(self):
        """When root_cause is confirmed, feedback should process fully."""
        incident = {
            "incident_id": "TEST-RESOLVED-001",
            "title": "Test resolved incident",
            "severity": "warning",
            "server": "web-prod-01",
            "symptoms": ["test symptom"],
            "root_cause": "PHP memory leak in v2.4.1",
            "resolution": "Deployed hotfix v2.4.2",
            "pattern_signatures": ["test"],
        }
        results = self.feedback.process_resolution(incident)
        self.assertEqual(results["mode"], "resolution")
        self.assertTrue(results["kb_updated"])

    def test_triage_mode_empty_root_cause(self):
        """Empty root_cause should be treated as triage."""
        incident = {
            "incident_id": "TEST-EMPTY-001",
            "title": "Test",
            "severity": "critical",
            "root_cause": "",
            "resolution": "",
            "pattern_signatures": [],
        }
        results = self.feedback.process_resolution(incident)
        self.assertEqual(results["mode"], "triage")

    def test_kb_updated_in_both_modes(self):
        """KB should be updated in both triage and resolution modes (records the event)."""
        incident_triage = {
            "incident_id": "TEST-KB-TRIAGE",
            "title": "Triage test",
            "severity": "warning",
            "root_cause": "TBD",
            "pattern_signatures": ["test"],
        }
        results = self.feedback.process_resolution(incident_triage)
        self.assertTrue(results["kb_updated"])


# ================================================================
# 8. Report Generator Tests
# ================================================================
class TestReportGenerator(unittest.TestCase):
    """Test PDF report generation."""

    def test_generate_basic_report(self):
        """Generate a basic report with metrics only."""
        from modules.report_generator import generate_report
        config = get_test_config()
        metrics = collect_metrics()

        report_path = generate_report(
            metrics=metrics,
            threshold_alerts=[],
            incidents=[],
            incident_summary={"total": 0, "by_severity": {}, "by_pattern": {}, "top_incidents": []},
            config=config,
        )
        self.assertTrue(os.path.exists(report_path), f"Report not generated at {report_path}")
        self.assertTrue(report_path.endswith(".pdf"))
        self.assertGreater(os.path.getsize(report_path), 0)

    def test_generate_report_with_diagnosis(self):
        """Generate a report that includes diagnosis results and KB match."""
        from modules.report_generator import generate_report
        config = get_test_config()
        metrics = collect_metrics()

        diagnosis_results = [
            {"check_type": "network", "check_name": "ping", "command": "ping localhost",
             "status": "ok", "output": "host is local, ping not needed", "duration_ms": 1,
             "timestamp": "2026-10-23 10:00:00"},
            {"check_type": "system", "check_name": "memory_usage", "command": "free -h",
             "status": "ok", "output": "Memory: 60% used — status: OK", "duration_ms": 5,
             "timestamp": "2026-10-23 10:00:01"},
        ]
        diagnosis_summary = {
            "total_checks": 2,
            "by_status": {"ok": 2},
            "by_type": {"network": 1, "system": 1},
            "critical_checks": [],
        }
        kb_match = {
            "matched_sops": [
                {"id": "sop-oom-killer", "title": "OOM Killer SOP", "severity": "critical",
                 "relevance_score": 25, "matched_triggers": ["out of memory"]},
            ],
            "similar_incidents": [
                {"incident_id": "INC-2026-001", "title": "OOM on web-prod-01",
                 "resolution": "Restarted php-fpm", "similarity_score": 20},
            ],
        }

        report_path = generate_report(
            metrics=metrics,
            threshold_alerts=[],
            incidents=[{
                "timestamp_raw": "2026-10-23 09:05:22",
                "source_file": "webhook",
                "pattern_name": "Out of memory",
                "severity": "critical",
                "matched_line": "Out of memory: Kill process php-fpm",
                "line_number": 0,
            }],
            incident_summary={"total": 1, "by_severity": {"critical": 1},
                              "by_pattern": {"Out of memory": 1}, "top_incidents": []},
            config=config,
            diagnosis_results=diagnosis_results,
            diagnosis_summary=diagnosis_summary,
            kb_match=kb_match,
        )
        self.assertTrue(os.path.exists(report_path))
        # Enhanced report with diagnosis should be larger than basic report
        self.assertGreater(os.path.getsize(report_path), 1000)

    def test_generate_periodic_report_weekly(self):
        """Generate executive weekly report with analytics."""
        from modules.report_generator import generate_periodic_report
        config = get_test_config()
        metrics = collect_metrics()
        kb = KnowledgeBase(kb_dir=str(PROJECT_ROOT / "kb"))
        analytics = kb.get_incident_analytics(days=7)

        report_path = generate_periodic_report(
            period="weekly",
            metrics=metrics,
            analytics=analytics,
            config=config,
        )
        self.assertTrue(os.path.exists(report_path))
        self.assertIn("report_weekly_", report_path)
        self.assertGreater(os.path.getsize(report_path), 1000)

    def test_generate_periodic_report_monthly(self):
        """Generate executive monthly report with analytics."""
        from modules.report_generator import generate_periodic_report
        config = get_test_config()
        metrics = collect_metrics()
        kb = KnowledgeBase(kb_dir=str(PROJECT_ROOT / "kb"))
        analytics = kb.get_incident_analytics(days=30)

        report_path = generate_periodic_report(
            period="monthly",
            metrics=metrics,
            analytics=analytics,
            config=config,
        )
        self.assertTrue(os.path.exists(report_path))
        self.assertIn("report_monthly_", report_path)
        self.assertGreater(os.path.getsize(report_path), 1000)


# ================================================================
# 9. Integration Test: Full Pipeline
# ================================================================
class TestIntegration(unittest.TestCase):
    """Integration tests for the full agent pipeline."""

    def test_run_periodic_report_agent_weekly(self):
        """Test agent.run_periodic_report('weekly') end-to-end."""
        from main import ServerMonitoringAgent
        agent = ServerMonitoringAgent(config_path=TESTING_CONFIG_PATH)
        results = agent.run_periodic_report("weekly")

        self.assertEqual(results["period"], "weekly")
        self.assertEqual(results["period_days"], 7)
        self.assertIsNotNone(results["report_path"])
        self.assertTrue(os.path.exists(results["report_path"]))
        self.assertIn("report_weekly_", results["report_path"])

    def test_run_periodic_report_agent_monthly(self):
        """Test agent.run_periodic_report('monthly') end-to-end."""
        from main import ServerMonitoringAgent
        agent = ServerMonitoringAgent(config_path=TESTING_CONFIG_PATH)
        results = agent.run_periodic_report("monthly")

        self.assertEqual(results["period"], "monthly")
        self.assertEqual(results["period_days"], 30)
        self.assertIsNotNone(results["report_path"])
        self.assertTrue(os.path.exists(results["report_path"]))
        self.assertIn("report_monthly_", results["report_path"])

    def test_full_scheduled_cycle(self):
        """Run a full scheduled cycle with testing config."""
        from main import ServerMonitoringAgent
        agent = ServerMonitoringAgent(config_path=TESTING_CONFIG_PATH)
        results = agent.run_cycle()

        self.assertIsNotNone(results["metrics"])
        self.assertIsNotNone(results["report_path"])
        self.assertTrue(os.path.exists(results["report_path"]))
        # Email and Teams should be disabled
        self.assertFalse(results["email_sent"])
        self.assertFalse(results["teams_sent"])

    def test_full_incident_pipeline(self):
        """Run the full event-driven incident pipeline."""
        from main import ServerMonitoringAgent
        agent = ServerMonitoringAgent(config_path=TESTING_CONFIG_PATH)

        incident_context = {
            "text": "Out of memory: Kill process 8899 (php-fpm)",
            "patterns": ["Out of memory", "Service crash"],
            "server": "web-prod-01",
            "source": "test",
            "severity": "critical",
            "timestamp": "2026-10-23T09:05:22+07:00",
        }

        results = agent.process_incident(incident_context)

        # Verify all pipeline stages produced output
        self.assertIsNotNone(results["kb_match"])
        self.assertGreater(len(results["kb_match"]["matched_sops"]), 0,
                           "KB should find matching SOPs for OOM incident")
        self.assertGreater(len(results["diagnosis_results"]), 0,
                           "Diagnosis should have produced check results")
        self.assertIsNotNone(results["report_path"],
                             "Report should have been generated")
        self.assertTrue(os.path.exists(results["report_path"]))
        # Email/Teams disabled
        self.assertFalse(results["email_sent"])
        self.assertFalse(results["teams_sent"])
        # Feedback should be in triage mode (root_cause is TBD)
        self.assertIsNotNone(results["feedback"])
        self.assertEqual(results["feedback"]["mode"], "triage")
        self.assertFalse(results["feedback"]["ticket_resolved"],
                         "Ticket should not be auto-resolved for new alerts")


# ================================================================
# 10. Cloud-Native (K8s & Longhorn) Diagnostics Tests
# ================================================================
class TestCloudNativeDiagnostics(unittest.TestCase):
    """Test Kubernetes and Longhorn storage diagnostics."""

    def setUp(self):
        from src.modules.k8s_diagnostics import K8sDiagnosticEngine
        self.engine = K8sDiagnosticEngine()

    def test_k8s_simulation_pod_health(self):
        """Simulated pod health should detect CrashLoopBackOff."""
        res = self.engine.diagnose_pod_health()
        self.assertIn("status", res)
        self.assertEqual(res["status"], "critical")
        self.assertGreater(len(res["failing_pods"]), 0)
        self.assertIn("kafka-broker-1", res["summary"])

    def test_longhorn_storage_health(self):
        """Simulated Longhorn diagnosis should report degraded volumes."""
        res = self.engine.diagnose_longhorn_storage()
        self.assertIn("status", res)
        self.assertEqual(res["status"], "critical")
        self.assertGreater(len(res["degraded_volumes"]), 0)
        self.assertIn("pvc-clickhouse-analytics-01", res["summary"])

    def test_k8s_get_pod_logs(self):
        """Deep container crash logs should detect OutOfMemoryError stack trace."""
        res = self.engine.get_pod_logs("kafka-broker-1")
        self.assertEqual(res["status"], "critical")
        self.assertTrue(res["has_crash_signature"])
        self.assertIn("OutOfMemoryError", res["detected_signature"])
        self.assertIn("Java heap space", res["logs"])

    def test_k8s_get_pod_events(self):
        """Pod event inspection should detect BackOff and probe failure warnings."""
        res = self.engine.get_pod_events("kafka-broker-1")
        self.assertEqual(res["status"], "critical")
        self.assertGreater(res["warning_count"], 0)
        self.assertIn("BackOff", res["summary"])

    def test_k8s_diagnose_pod_resources(self):
        """Resource limits evaluation should detect near-OOM memory usage."""
        res = self.engine.diagnose_pod_resources()
        self.assertEqual(res["status"], "critical")
        self.assertGreater(res["total_inspected"], 0)
        kafka_pod = next((p for p in res["pods"] if "kafka" in p["pod"]), None)
        self.assertIsNotNone(kafka_pod)
        self.assertGreaterEqual(kafka_pod["mem_pct"], 95.0)

    def test_k8s_restart_pod(self):
        """Safe pod restart should return success and audit message."""
        res = self.engine.restart_pod("kafka-broker-1", initiator="Test-Operator")
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "restart_pod")
        self.assertEqual(res["initiator"], "Test-Operator")
        self.assertIn("kafka-broker-1", res["message"])


# ================================================================
# 11. Telegram Notifier Tests
# ================================================================
class TestTelegramNotifier(unittest.TestCase):
    """Test Telegram notification logic."""

    def test_telegram_disabled_returns_false(self):
        """When telegram.enabled is false, send_telegram should safely return False."""
        from src.modules.notifier import send_telegram
        cfg = {"telegram": {"enabled": False}}
        result = send_telegram("dummy.pdf", {}, {}, cfg)
        self.assertFalse(result)

    def test_telegram_incomplete_config_returns_false(self):
        """When credentials are empty, send_telegram should fail gracefully."""
        from src.modules.notifier import send_telegram
        cfg = {"telegram": {"enabled": True, "bot_token": "", "chat_id": ""}}
        result = send_telegram("dummy.pdf", {}, {}, cfg)
        self.assertFalse(result)


# ================================================================
# Cleanup: remove test-generated incident files
# ================================================================
def cleanup_test_incidents():
    """Remove incidents created during testing."""
    history_dir = PROJECT_ROOT / "kb" / "incident_history"
    for f in history_dir.glob("TEST-*.json"):
        f.unlink(missing_ok=True)
    for f in history_dir.glob("INC-2026*.json"):
        # Only remove auto-generated test incidents
        try:
            with open(f, "r") as fh:
                data = json.load(fh)
            if data.get("root_cause") in ("TBD - requires manual review", "TBD", ""):
                f.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        cleanup_test_incidents()
