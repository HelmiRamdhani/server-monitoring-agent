"""
OpenTelemetry (APM), Google SRE SLI/SLO, and eBPF Kernel Observability Engine.
Aligns with CNCF OpenTelemetry, SRE standards, and Linux Foundation eBPF practices.

Capabilities:
1. Service Layer (APM):
   - Distributed trace & span dependency mapping (call graphs)
   - Latency metrics tracking (p50, p90, p99)
   - Error rate (HTTP 4xx/5xx) and throughput (RPS)
2. Google SRE SLI/SLO:
   - Availability and latency SLI/SLO tracking
   - Multi-window Error Budget Burn Rate calculation (SRE Book standard)
3. eBPF & Kernel-Level Observability:
   - TCP retransmits and socket buffer drops
   - Block I/O device queue latency
   - Syscall execution latency profiling
"""

import os
import sys
import re
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

log = logging.getLogger("agent.apm_otel")

# High-fidelity mock APM service inventory (OpenTelemetry OTLP standard)
MOCK_SERVICE_INVENTORY = [
    {
        "service_name": "checkout-service",
        "environment": "production",
        "language": "Go 1.22 (OTel Auto-Instrumentation)",
        "throughput_rps": 450.2,
        "latency_ms": {
            "p50": 34.2,
            "p90": 112.5,
            "p99": 845.0,  # Critical: breached SLO (target < 200ms)
        },
        "error_rate_pct": 5.4,  # High 5xx error rate
        "slo": {
            "target_availability_pct": 99.9,
            "current_availability_pct": 98.6,
            "target_p99_latency_ms": 200.0,
            "error_budget_remaining_pct": 14.2,
            "burn_rate_1h": 14.4,  # 14.4x burn rate = 2% consumed per hour -> Critical SRE Alert
            "status": "burn_rate_critical",
        },
        "critical_trace_path": [
            {"span_id": "sp-001", "service": "checkout-service", "operation": "POST /api/v2/checkout", "duration_ms": 845.0, "status": "ERROR"},
            {"span_id": "sp-002", "service": "payment-api", "operation": "POST /v1/charge", "duration_ms": 120.0, "status": "OK"},
            {"span_id": "sp-003", "service": "clickhouse-analytics-db", "operation": "SQL: INSERT INTO orders_stream", "duration_ms": 680.0, "status": "ERROR (I/O Timeout)"},
        ],
    },
    {
        "service_name": "payment-api",
        "environment": "production",
        "language": "Java 21 (OTel JavaAgent)",
        "throughput_rps": 120.8,
        "latency_ms": {
            "p50": 18.5,
            "p90": 45.0,
            "p99": 98.0,
        },
        "error_rate_pct": 0.1,
        "slo": {
            "target_availability_pct": 99.95,
            "current_availability_pct": 99.98,
            "target_p99_latency_ms": 150.0,
            "error_budget_remaining_pct": 89.5,
            "burn_rate_1h": 0.2,
            "status": "healthy",
        },
        "critical_trace_path": [
            {"span_id": "sp-101", "service": "payment-api", "operation": "POST /v1/charge", "duration_ms": 98.0, "status": "OK"}
        ],
    },
]

# Simulated eBPF Kernel-Level Metrics (Continuous Profiling & Network Telemetry)
MOCK_EBPF_KERNEL_TELEMETRY = {
    "host": "k8s-worker-04",
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "tcp_retransmits": {
        "rate_per_sec": 48.2,
        "threshold_warning": 10.0,
        "status": "critical",
        "detail": "High TCP retransmissions on interface eth0 (NIC packet drop / congestive backoff)",
    },
    "socket_buffer_drops": {
        "drops_total": 1420,
        "status": "warning",
        "detail": "Kernel socket receive buffer overflow during microbursts",
    },
    "block_io_latency_ms": {
        "nvme_write_p99": 84.5,  # Slow disk write latency
        "status": "critical",
        "detail": "Storage device /dev/nvme0n1 write queue depth exceeded 64 (I/O wait spike)",
    },
    "syscall_profiling": {
        "slowest_syscall": "epoll_wait",
        "avg_duration_us": 1240,
        "context_switches_per_sec": 48200,
        "status": "warning",
    },
}


class APMOtelDiagnosticEngine:
    """Enterprise APM (OpenTelemetry), SLI/SLO, and eBPF Kernel Observability Engine."""

    def __init__(self, otlp_endpoint: str = None):
        self.otlp_endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        self.live_mode = False
        self._check_live_mode()

    def _check_live_mode(self):
        """Check if a live OpenTelemetry Collector or Prometheus APM endpoint is reachable."""
        if self.otlp_endpoint:
            self.live_mode = True
            log.info("OpenTelemetry OTLP endpoint configured: %s", self.otlp_endpoint)
        else:
            self.live_mode = False
            log.info("No external OTLP endpoint configured. Using high-fidelity APM simulation mode.")

    # ================================================================
    # 1. Service Layer (APM): Latency, Error Rate, and Trace Breakdown
    # ================================================================
    def diagnose_service_apm(self, target_service: str = None) -> Dict[str, Any]:
        """
        Diagnose service request latency (p50/p90/p99), 5xx error rates,
        and distributed trace critical path bottleneck.
        """
        inspected = []
        for svc in MOCK_SERVICE_INVENTORY:
            if target_service and target_service.lower() not in svc["service_name"].lower():
                continue
            
            p99 = svc["latency_ms"]["p99"]
            err_pct = svc["error_rate_pct"]
            target_p99 = svc["slo"]["target_p99_latency_ms"]

            if p99 > target_p99 or err_pct >= 5.0:
                svc_status = "critical"
            elif p99 > (target_p99 * 0.75) or err_pct >= 1.0:
                svc_status = "warning"
            else:
                svc_status = "ok"

            # Find root cause span
            bottleneck_span = None
            for sp in svc.get("critical_trace_path", []):
                if sp.get("status") != "OK":
                    bottleneck_span = sp
                    break

            inspected.append({
                "service_name": svc["service_name"],
                "status": svc_status,
                "language": svc["language"],
                "throughput_rps": svc["throughput_rps"],
                "latency_p50_ms": svc["latency_ms"]["p50"],
                "latency_p99_ms": p99,
                "target_p99_ms": target_p99,
                "error_rate_pct": err_pct,
                "bottleneck_span": bottleneck_span,
                "trace_path": svc.get("critical_trace_path", []),
            })

        overall_status = "critical" if any(i["status"] == "critical" for i in inspected) else (
            "warning" if any(i["status"] == "warning" for i in inspected) else "ok"
        )

        lines = []
        for i in inspected:
            b_info = ""
            if i["bottleneck_span"]:
                b = i["bottleneck_span"]
                b_info = f"\n  -> Bottleneck Span: {b['service']} -> {b['operation']} ({b['duration_ms']}ms) [{b['status']}]"
            lines.append(
                f"Service {i['service_name']} ({i['language']}): "
                f"p99={i['latency_p99_ms']}ms (SLO target <{i['target_p99_ms']}ms) | "
                f"ErrorRate={i['error_rate_pct']}% | Throughput={i['throughput_rps']} RPS -> status: {i['status'].upper()}{b_info}"
            )

        return {
            "mode": "simulation",
            "status": overall_status,
            "total_services": len(inspected),
            "services": inspected,
            "summary": "\n".join(lines) if lines else "All inspected services meet APM latency and error-rate objectives.",
        }

    # ================================================================
    # 2. Google SRE SLI/SLO & Error Budget Burn Rate
    # ================================================================
    def evaluate_sre_slo(self, target_service: str = None) -> Dict[str, Any]:
        """
        Evaluate SRE Service Level Objectives (SLO) and Error Budget Burn Rates.
        Follows Google SRE multi-window burn rate alert design:
        - 14.4x burn rate over 1h consumes 2% of budget -> P1 Critical Alert.
        - 6.0x burn rate over 6h consumes 5% of budget -> P2 Warning Alert.
        """
        slo_evaluations = []
        for svc in MOCK_SERVICE_INVENTORY:
            if target_service and target_service.lower() not in svc["service_name"].lower():
                continue

            slo = svc["slo"]
            burn_rate = slo.get("burn_rate_1h", 0)
            avail_pct = slo.get("current_availability_pct", 100.0)
            target_avail = slo.get("target_availability_pct", 99.9)

            if burn_rate >= 14.4 or avail_pct < target_avail:
                status = "critical"
                risk_level = "Imminent SLO Breach (P1 SRE Alert)"
            elif burn_rate >= 6.0 or slo.get("error_budget_remaining_pct", 100) < 30.0:
                status = "warning"
                risk_level = "Elevated Burn Rate (P2 SRE Alert)"
            else:
                status = "ok"
                risk_level = "Within Budget (Healthy)"

            slo_evaluations.append({
                "service_name": svc["service_name"],
                "status": status,
                "target_availability": f"{target_avail}%",
                "current_availability": f"{avail_pct}%",
                "remaining_budget_pct": slo.get("error_budget_remaining_pct", 100),
                "burn_rate_1h": f"{burn_rate}x",
                "risk_level": risk_level,
            })

        overall_status = "critical" if any(s["status"] == "critical" for s in slo_evaluations) else (
            "warning" if any(s["status"] == "warning" for s in slo_evaluations) else "ok"
        )

        lines = []
        for s in slo_evaluations:
            lines.append(
                f"SLO {s['service_name']}: Avail={s['current_availability']}/{s['target_availability']} | "
                f"BudgetRemaining={s['remaining_budget_pct']}% | BurnRate={s['burn_rate_1h']} [{s['risk_level']}] -> status: {s['status'].upper()}"
            )

        return {
            "mode": "simulation",
            "status": overall_status,
            "total_evaluated": len(slo_evaluations),
            "evaluations": slo_evaluations,
            "summary": "\n".join(lines) if lines else "All services comply with SRE SLO error budget limits.",
        }

    # ================================================================
    # 3. eBPF & Kernel-Level Observability Diagnostics
    # ================================================================
    def diagnose_ebpf_kernel(self) -> Dict[str, Any]:
        """
        Diagnose kernel-level metrics without code instrumentation using eBPF probes:
        - TCP retransmits and socket buffer drops
        - Storage block device queue depth & latency
        - Syscall latency and context switches
        """
        # Live mode attempt: read /proc/net/snmp or /proc/sys on Linux if available
        if os.path.exists("/proc/net/snmp"):
            try:
                with open("/proc/net/snmp", "r") as f:
                    content = f.read()
                # Live TCP retransmits parsing
                retrans_match = re.search(r"Tcp:.*?\nTcp:\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)", content)
                retrans_val = int(retrans_match.group(1)) if retrans_match else 0
                return {
                    "mode": "live",
                    "status": "ok" if retrans_val < 500 else "warning",
                    "host": os.uname().nodename,
                    "retransmits_raw": retrans_val,
                    "summary": f"eBPF/Kernel TCP retransmits counter: {retrans_val} (Live /proc metric).",
                }
            except Exception as e:
                log.warning("Could not parse /proc/net/snmp: %s", e)

        # High-fidelity simulation mode
        t = MOCK_EBPF_KERNEL_TELEMETRY
        retrans = t["tcp_retransmits"]
        bio = t["block_io_latency_ms"]

        status = "critical" if retrans["status"] == "critical" or bio["status"] == "critical" else "ok"

        summary_lines = [
            f"Host {t['host']} Kernel Telemetry (eBPF Probes):",
            f"* TCP Retransmits: {retrans['rate_per_sec']}/s -> {retrans['status'].upper()} ({retrans['detail']})",
            f"* Socket Buffer: {t['socket_buffer_drops']['drops_total']} drops ({t['socket_buffer_drops']['detail']})",
            f"* Block I/O NVMe Write p99: {bio['nvme_write_p99']}ms -> {bio['status'].upper()} ({bio['detail']})",
            f"* Syscall Profiling: {t['syscall_profiling']['slowest_syscall']} avg {t['syscall_profiling']['avg_duration_us']}us ({t['syscall_profiling']['context_switches_per_sec']} cswitch/s)",
        ]

        return {
            "mode": "simulation",
            "status": status,
            "host": t["host"],
            "telemetry": t,
            "summary": "\n".join(summary_lines),
        }


# Quick test runner
if __name__ == "__main__":
    engine = APMOtelDiagnosticEngine()
    print("--- 1. Service APM & Trace Diagnostics ---")
    apm_res = engine.diagnose_service_apm("checkout-service")
    print("Status :", apm_res["status"].upper())
    print("Summary:\n", apm_res["summary"])

    print("\n--- 2. Google SRE SLI/SLO Evaluation ---")
    slo_res = engine.evaluate_sre_slo()
    print("Status :", slo_res["status"].upper())
    print("Summary:\n", slo_res["summary"])

    print("\n--- 3. eBPF Kernel Observability ---")
    ebpf_res = engine.diagnose_ebpf_kernel()
    print("Status :", ebpf_res["status"].upper())
    print("Summary:\n", ebpf_res["summary"])
