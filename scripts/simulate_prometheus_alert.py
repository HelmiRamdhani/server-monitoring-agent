"""
Prometheus Alertmanager Webhook Simulator
Tests the Server Monitoring Agent's event-driven incident pipeline locally.

Can run in two ways:
  1. Standalone (In-Process): Runs full 6-stage pipeline directly in-process and generates PDF report.
  2. HTTP Client: Fires HTTP POST to a running webhook server (http://localhost:8080/webhook/prometheus).
"""

import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.main import ServerMonitoringAgent
from src.modules.webhook_receiver import parse_prometheus_alert


# Realistic alert templates matching the Platform Bigdata environment
ALERT_PRESETS = {
    "crashloop": {
        "title": "Kubernetes Pod CrashLoopBackOff",
        "payload": {
            "receiver": "server-monitoring-agent",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "KubePodCrashLooping",
                        "severity": "critical",
                        "pod": "kafka-broker-1",
                        "namespace": "platform-bigdata",
                        "instance": "k8s-worker-04",
                        "container": "kafka",
                    },
                    "annotations": {
                        "summary": "Pod kafka-broker-1 is in CrashLoopBackOff",
                        "description": "Pod kafka-broker-1 in namespace platform-bigdata has crashed and restarted 6 times in 10 minutes. Container terminated with exit code 137 (OOMKilled).",
                    },
                    "startsAt": "2026-10-26T06:15:00Z",
                }
            ],
            "groupLabels": {"alertname": "KubePodCrashLooping"},
            "commonLabels": {"severity": "critical"},
        },
    },
    "storage": {
        "title": "Longhorn Volume Degraded",
        "payload": {
            "receiver": "server-monitoring-agent",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "LonghornVolumeDegraded",
                        "severity": "critical",
                        "volume": "pvc-clickhouse-analytics-01",
                        "instance": "k8s-storage-02",
                        "storage_pool": "longhorn-nvme-pool",
                    },
                    "annotations": {
                        "summary": "Longhorn storage volume replica degraded",
                        "description": "Volume pvc-clickhouse-analytics-01 has 1 of 3 replicas faulted on node k8s-storage-02. Auto-rebuild initiated.",
                    },
                    "startsAt": "2026-10-26T06:16:30Z",
                }
            ],
            "groupLabels": {"alertname": "LonghornVolumeDegraded"},
            "commonLabels": {"severity": "critical"},
        },
    },
    "oom": {
        "title": "Out of Memory (OOM) Killer Event",
        "payload": {
            "receiver": "server-monitoring-agent",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HostHighMemoryPressure",
                        "severity": "critical",
                        "instance": "k8s-worker-02",
                        "job": "node-exporter",
                    },
                    "annotations": {
                        "summary": "Host out of memory - oom-killer invoked",
                        "description": "Kernel invoked oom-killer: killed process 45892 (java-worker) total-vm:32GB anon-rss:28GB.",
                    },
                    "startsAt": "2026-10-26T06:18:00Z",
                }
            ],
        },
    },
    "disk": {
        "title": "Host Disk Full Warning",
        "payload": {
            "receiver": "server-monitoring-agent",
            "status": "warning",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HostDiskFillingUp",
                        "severity": "warning",
                        "instance": "k8s-master-01",
                        "mountpoint": "/var/log",
                    },
                    "annotations": {
                        "summary": "Disk partition /var/log is 92% full",
                        "description": "No space left on device imminent: /var/log utilization exceeded 90% threshold.",
                    },
                    "startsAt": "2026-10-26T06:20:00Z",
                }
            ],
        },
    },
}


def run_http_simulation(preset_name: str, host: str = "127.0.0.1", port: int = 8080):
    """Send alert via HTTP POST to the running webhook receiver."""
    preset = ALERT_PRESETS[preset_name]
    url = f"http://{host}:{port}/webhook/prometheus"
    data = json.dumps(preset["payload"]).encode("utf-8")

    print(f"\n[HTTP CLIENT] Sending '{preset['title']}' to {url}...")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start_t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            elapsed = time.time() - start_t
            resp_body = resp.read().decode("utf-8")
            print(f"[HTTP CLIENT] Status: {resp.status} OK (took {elapsed:.2f}s)")
            print(f"[HTTP CLIENT] Response: {resp_body}")
            return True
    except urllib.error.URLError as e:
        print(f"[ERROR] Could not connect to {url}: {e}")
        print("Tip: Make sure the agent webhook server is running, or run without --http to test in-process.")
        return False


def run_inprocess_simulation(preset_name: str, config_path: str = "config/config.testing.yaml"):
    """Run full 6-stage pipeline directly in-process and show results."""
    preset = ALERT_PRESETS[preset_name]
    payload = preset["payload"]

    print("=" * 60)
    print(f" SIMULASI PROMETHEUS ALERT: {preset['title'].upper()}")
    print("=" * 60)
    print(f"Target Alert  : {payload['alerts'][0]['labels']['alertname']}")
    print(f"Severity      : {payload['alerts'][0]['labels'].get('severity')}")
    print(f"Instance/Node : {payload['alerts'][0]['labels'].get('instance', 'N/A')}")
    print(f"Description   : {payload['alerts'][0]['annotations'].get('description')}")
    print("-" * 60)

    # Step 1: Initialize Agent
    print("\n[Stage 1] Inisialisasi Agent & Webhook Ingestion...")
    agent = ServerMonitoringAgent(config_path=config_path)

    # Step 2: Parse standard Prometheus Alertmanager payload
    wp = parse_prometheus_alert(payload)
    incident_context = wp.to_incident_context()
    print(f"  -> Parsed Alert Name : {wp.alert_name}")
    print(f"  -> Incident Text     : {incident_context['text']}")

    # Step 3: Execute Agent Incident Pipeline (Stages 2-6)
    print("\n[Stage 2 - 6] Menjalankan Pipeline Co-Pilot...")
    results = agent.process_incident(incident_context)

    # Step 4: Summary of Results
    print("\n" + "=" * 60)
    print(" HASIL EKSEKUSI PIPELINE AGENT")
    print("=" * 60)

    # SOP Matches
    kb_match = results.get("kb_match", {})
    matched_sops = kb_match.get("matched_sops", [])
    if matched_sops:
        print("\n[+] SOP KNOWLEDGE BASE YANG COCOK:")
        for s in matched_sops[:3]:
            print(f"    * ID      : {s.get('id')}")
            print(f"    * Judul   : {s.get('title')}")
            print(f"    * Severity: {s.get('severity')}")
    else:
        print("\n[-] Tidak ada SOP yang cocok persis (Masuk ke investigasi umum)")

    # Diagnosis Summary
    diag_summary = results.get("diagnosis_summary", {})
    if diag_summary:
        print(f"\n[+] HASIL DIAGNOSTIK:")
        print(f"    * Total Pemeriksaan Sistem: {diag_summary.get('total_checks', 0)}")
        print(f"    * Status Breakdown: {diag_summary.get('by_status', {})}")

    # Report Path
    report_path = results.get("report_path")
    if report_path:
        print(f"\n[+] DOKUMEN LAPORAN INSIDEN (PDF) BERHASIL DIBUAT:")
        print(f"    >>> {report_path} <<<")

    # Feedback Loop Status
    feedback = results.get("feedback", {})
    if feedback:
        print(f"\n[+] FEEDBACK LOOP & KB HISTORY:")
        print(f"    * Mode         : {feedback.get('mode', 'triage')}")
        print(f"    * KB Updated   : {feedback.get('kb_updated')}")
        print(f"    * Post-Mortem  : {feedback.get('post_mortem_created')}")

    print("=" * 60 + "\n")
    return results


def main():
    parser = argparse.ArgumentParser(description="Simulate Prometheus Alert to Monitoring Agent")
    parser.add_argument(
        "--scenario", "-s",
        choices=list(ALERT_PRESETS.keys()),
        default="crashloop",
        help="Alert scenario to trigger (default: crashloop)",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Send via HTTP POST to running webhook server (default: run in-process)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Webhook host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Webhook port (default: 8080)",
    )
    parser.add_argument(
        "--config", "-c",
        default="config/config.testing.yaml",
        help="Agent config file (default: config/config.testing.yaml)",
    )
    args = parser.parse_args()

    if args.http:
        run_http_simulation(args.scenario, host=args.host, port=args.port)
    else:
        run_inprocess_simulation(args.scenario, config_path=args.config)


if __name__ == "__main__":
    main()

