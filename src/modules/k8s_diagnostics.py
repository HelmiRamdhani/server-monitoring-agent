"""
Kubernetes & Longhorn Storage Diagnostic Engine for Platform Bigdata.
Supports Dual Mode:
  1. Live Mode: Uses kubernetes-client / Longhorn REST API when kubeconfig / cluster credentials exist.
  2. Simulation / Mock Mode: Allows safe, full-fidelity local testing on laptops without a live cluster.
"""

import os
import re
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

log = logging.getLogger("agent.k8s_diagnosis")

# Simulated Cluster Pod Inventory (for local testing/simulation)
MOCK_POD_INVENTORY = [
    {
        "name": "kafka-broker-1",
        "namespace": "platform-bigdata",
        "node": "k8s-worker-04",
        "phase": "Running",
        "status": "CrashLoopBackOff",
        "restart_count": 6,
        "exit_code": 137,
        "termination_reason": "OOMKilled",
        "message": "Memory limit (4Gi) exceeded during high-throughput message ingestion batch.",
        "resources": {
            "cpu_request_m": 1000,
            "cpu_limit_m": 2000,
            "cpu_usage_m": 1850,
            "mem_request_mb": 2048,
            "mem_limit_mb": 4096,
            "mem_usage_mb": 4010,  # 97.9% of limit (Near-OOM critical)
        },
        "previous_logs": (
            "[2026-10-28 10:14:02,104] INFO [KafkaServer id=1] Starting kafka broker on k8s-worker-04...\n"
            "[2026-10-28 10:14:15,312] WARN [ReplicaManager] High watermark lagging behind leader on partition __consumer_offsets-12\n"
            "[2026-10-28 10:14:28,881] ERROR [KafkaServer id=1] Fatal error during startup. Prepare to shutdown (kafka.server.KafkaServer)\n"
            "java.lang.OutOfMemoryError: Java heap space\n"
            "    at java.base/java.nio.ByteBuffer.allocate(ByteBuffer.java:348)\n"
            "    at org.apache.kafka.common.memory.SimpleMemoryPool.allocate(SimpleMemoryPool.java:45)\n"
            "    at org.apache.kafka.common.record.FileRecords.readInto(FileRecords.java:180)\n"
            "[2026-10-28 10:14:29,002] INFO [KafkaServer id=1] Shutting down...\n"
            "exit code 137: container killed by Linux OOM killer"
        ),
        "events": [
            {
                "type": "Warning",
                "reason": "BackOff",
                "message": "Back-off restarting failed container kafka in pod kafka-broker-1_platform-bigdata",
                "count": 14,
            },
            {
                "type": "Warning",
                "reason": "Unhealthy",
                "message": "Liveness probe failed: Get http://10.244.2.14:8080/health: connect connection refused",
                "count": 3,
            },
            {
                "type": "Normal",
                "reason": "Pulled",
                "message": "Container image confluentinc/cp-kafka:7.4.0 already present on machine",
                "count": 1,
            },
        ],
    },
    {
        "name": "clickhouse-server-0",
        "namespace": "platform-bigdata",
        "node": "k8s-worker-03",
        "phase": "Running",
        "status": "Running",
        "restart_count": 0,
        "exit_code": 0,
        "termination_reason": None,
        "message": "Healthy - ready 1/1",
        "resources": {
            "cpu_request_m": 4000,
            "cpu_limit_m": 8000,
            "cpu_usage_m": 1200,
            "mem_request_mb": 8192,
            "mem_limit_mb": 16384,
            "mem_usage_mb": 6553,  # 40% of limit
        },
        "previous_logs": "clickhouse-server initialized and listening on 0.0.0.0:9000 (native) and 8123 (http)",
        "events": [
            {
                "type": "Normal",
                "reason": "Started",
                "message": "Started container clickhouse-server",
                "count": 1,
            }
        ],
    },
    {
        "name": "spark-worker-02",
        "namespace": "platform-bigdata",
        "node": "k8s-worker-02",
        "phase": "Running",
        "status": "Running",
        "restart_count": 1,
        "exit_code": 0,
        "termination_reason": None,
        "message": "Healthy - ready 1/1",
        "resources": {
            "cpu_request_m": 2000,
            "cpu_limit_m": 4000,
            "cpu_usage_m": 1900,
            "mem_request_mb": 4096,
            "mem_limit_mb": 8192,
            "mem_usage_mb": 7650,  # 93.4% of limit (Near-OOM warning!)
        },
        "previous_logs": "spark worker running executor threads. memory usage high for batch id #9842",
        "events": [
            {
                "type": "Normal",
                "reason": "Started",
                "message": "Started container spark-worker",
                "count": 1,
            }
        ],
    },
]

# Simulated Longhorn Volume Inventory
MOCK_LONGHORN_VOLUMES = [
    {
        "volume_name": "pvc-clickhouse-analytics-01",
        "size_gb": 500,
        "robustness": "Degraded",
        "state": "attached",
        "node": "k8s-storage-02",
        "replicas": [
            {"node": "k8s-storage-01", "mode": "RW", "healthy": True},
            {"node": "k8s-storage-02", "mode": "ERR", "healthy": False, "error": "Disk I/O latency timeout"},
            {"node": "k8s-storage-03", "mode": "RW", "healthy": True},
        ],
    },
    {
        "volume_name": "pvc-kafka-data-01",
        "size_gb": 200,
        "robustness": "Healthy",
        "state": "attached",
        "node": "k8s-storage-01",
        "replicas": [
            {"node": "k8s-storage-01", "mode": "RW", "healthy": True},
            {"node": "k8s-storage-02", "mode": "RW", "healthy": True},
            {"node": "k8s-storage-03", "mode": "RW", "healthy": True},
        ],
    },
]


class K8sDiagnosticEngine:
    """Diagnostic runner for Kubernetes workloads and Longhorn distributed storage."""

    def __init__(self, kubeconfig_path: str = None):
        self.kubeconfig_path = kubeconfig_path or os.environ.get("KUBECONFIG")
        self.live_mode = False
        self._init_k8s_client()

    def _init_k8s_client(self):
        """Initialize Kubernetes API client if credentials are present."""
        try:
            from kubernetes import client, config
            if self.kubeconfig_path and os.path.exists(self.kubeconfig_path):
                config.load_kube_config(config_file=self.kubeconfig_path)
                self.core_api = client.CoreV1Api()
                self.live_mode = True
                log.info("Kubernetes API client initialized in LIVE mode via kubeconfig")
            elif os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount"):
                config.load_incluster_config()
                self.core_api = client.CoreV1Api()
                self.live_mode = True
                log.info("Kubernetes API client initialized in LIVE in-cluster mode")
            else:
                self.live_mode = False
                log.info("No live cluster detected. Using high-fidelity K8s simulation mode.")
        except ImportError:
            self.live_mode = False
            log.info("kubernetes python package not found. Using high-fidelity simulation mode.")
        except Exception as e:
            self.live_mode = False
            log.warning("Could not connect to live K8s API (%s). Falling back to simulation mode.", e)

    # ================================================================
    # 1. Pod Health Diagnostics
    # ================================================================
    def diagnose_pod_health(self, target_pod: str = None, namespace: str = "platform-bigdata") -> Dict[str, Any]:
        """
        Diagnose pod health and inspect crash/restart details.
        """
        if self.live_mode:
            return self._diagnose_pods_live(target_pod, namespace)
        return self._diagnose_pods_simulated(target_pod, namespace)

    def _diagnose_pods_simulated(self, target_pod: str = None, namespace: str = None) -> Dict[str, Any]:
        """Simulated pod diagnosis for local testing."""
        failing = []
        for pod in MOCK_POD_INVENTORY:
            if target_pod and target_pod.lower() not in pod["name"].lower():
                continue
            if pod["status"] in ("CrashLoopBackOff", "Error", "OOMKilled") or pod["exit_code"] != 0:
                failing.append(pod)

        status = "critical" if any(p["exit_code"] == 137 or p["status"] == "CrashLoopBackOff" for p in failing) else "ok"
        summary_lines = []
        for p in failing:
            summary_lines.append(
                f"Pod {p['name']} ({p['namespace']}) on node {p['node']} in {p['status']} (Restarts: {p['restart_count']}). "
                f"ExitCode: {p['exit_code']} [{p['termination_reason']}]: {p['message']}"
            )

        return {
            "mode": "simulation",
            "status": status,
            "total_inspected": len(MOCK_POD_INVENTORY),
            "failing_pods": failing,
            "summary": "\n".join(summary_lines) if summary_lines else "All inspected pods are running healthy.",
        }

    def _diagnose_pods_live(self, target_pod: str = None, namespace: str = "platform-bigdata") -> Dict[str, Any]:
        """Query live Kubernetes API server for pod states."""
        try:
            pods = self.core_api.list_namespaced_pod(namespace=namespace)
            failing = []
            for pod in pods.items:
                pod_name = pod.metadata.name
                if target_pod and target_pod.lower() not in pod_name.lower():
                    continue

                container_statuses = pod.status.container_statuses or []
                for cs in container_statuses:
                    if cs.state.waiting and cs.state.waiting.reason in ("CrashLoopBackOff", "ImagePullBackOff", "Error"):
                        failing.append({
                            "name": pod_name,
                            "namespace": namespace,
                            "node": pod.spec.node_name,
                            "status": cs.state.waiting.reason,
                            "restart_count": cs.restart_count,
                            "message": cs.state.waiting.message or "Container back-off restart",
                        })
                    elif cs.last_state.terminated and cs.last_state.terminated.exit_code != 0:
                        failing.append({
                            "name": pod_name,
                            "namespace": namespace,
                            "node": pod.spec.node_name,
                            "status": cs.last_state.terminated.reason or "Terminated",
                            "exit_code": cs.last_state.terminated.exit_code,
                            "restart_count": cs.restart_count,
                            "message": cs.last_state.terminated.message or "Non-zero exit",
                        })

            status = "critical" if failing else "ok"
            return {
                "mode": "live",
                "status": status,
                "total_inspected": len(pods.items),
                "failing_pods": failing,
                "summary": f"Detected {len(failing)} failing pod(s) in namespace {namespace}",
            }
        except Exception as e:
            log.error("Failed to query live K8s API: %s", e)
            return {
                "mode": "live_error",
                "status": "warning",
                "total_inspected": 0,
                "failing_pods": [],
                "summary": f"Kubernetes API query failed: {e}",
            }

    # ================================================================
    # 2. Deep Container Crash Logs Extraction (kubectl logs --previous)
    # ================================================================
    def get_pod_logs(
        self,
        target_pod: str = None,
        namespace: str = "platform-bigdata",
        container: str = None,
        previous: bool = True,
        tail_lines: int = 50,
    ) -> Dict[str, Any]:
        """
        Extract logs from previous terminated container instance or current logs.
        Identifies stack traces, OOM markers, and root causes right before crash.
        """
        if self.live_mode:
            return self._get_pod_logs_live(target_pod, namespace, container, previous, tail_lines)
        return self._get_pod_logs_simulated(target_pod, namespace, previous, tail_lines)

    def _get_pod_logs_simulated(
        self, target_pod: str, namespace: str, previous: bool, tail_lines: int
    ) -> Dict[str, Any]:
        pod_item = None
        for p in MOCK_POD_INVENTORY:
            if not target_pod or target_pod.lower() in p["name"].lower():
                if p["status"] in ("CrashLoopBackOff", "Error", "OOMKilled") or p["exit_code"] != 0:
                    pod_item = p
                    break

        if not pod_item and MOCK_POD_INVENTORY:
            pod_item = MOCK_POD_INVENTORY[0]

        if not pod_item:
            return {
                "mode": "simulation",
                "status": "ok",
                "pod": target_pod or "unknown",
                "has_crash_signature": False,
                "detected_signature": None,
                "logs": "No pod found matching query.",
                "summary": "No logs available.",
            }

        raw_logs = pod_item.get("previous_logs", "")
        # Scan for crash signatures
        crash_signatures = [
            "OutOfMemoryError",
            "OOMKilled",
            "SIGSEGV",
            "Fatal error",
            "Panic",
            "NullPointerException",
            "connection refused",
        ]
        detected = []
        for sig in crash_signatures:
            if sig.lower() in raw_logs.lower():
                detected.append(sig)

        status = "critical" if detected or pod_item["exit_code"] != 0 else "ok"
        detected_str = ", ".join(detected) if detected else "None"

        summary = (
            f"Pod: {pod_item['name']} (Previous Logs)\n"
            f"Crash Signatures: {detected_str}\n"
            f"Snippet:\n{raw_logs}"
        )

        return {
            "mode": "simulation",
            "status": status,
            "pod": pod_item["name"],
            "has_crash_signature": len(detected) > 0,
            "detected_signature": detected_str,
            "tail_lines": tail_lines,
            "logs": raw_logs,
            "summary": summary,
        }

    def _get_pod_logs_live(
        self, target_pod: str, namespace: str, container: str, previous: bool, tail_lines: int
    ) -> Dict[str, Any]:
        try:
            kwargs = {"namespace": namespace, "tail_lines": tail_lines, "previous": previous}
            if container:
                kwargs["container"] = container

            log_text = self.core_api.read_namespaced_pod_log(name=target_pod, **kwargs)
            crash_signatures = ["OutOfMemoryError", "OOMKilled", "SIGSEGV", "Fatal error", "Panic", "Exception"]
            detected = [sig for sig in crash_signatures if sig.lower() in log_text.lower()]

            status = "critical" if detected else "ok"
            return {
                "mode": "live",
                "status": status,
                "pod": target_pod,
                "has_crash_signature": len(detected) > 0,
                "detected_signature": ", ".join(detected) if detected else "None",
                "tail_lines": tail_lines,
                "logs": log_text,
                "summary": f"Pod {target_pod} previous logs ({len(detected)} signature(s) detected):\n{log_text[:300]}",
            }
        except Exception as e:
            return {
                "mode": "live_error",
                "status": "warning",
                "pod": target_pod,
                "has_crash_signature": False,
                "detected_signature": None,
                "logs": f"Failed to retrieve pod logs: {e}",
                "summary": f"Could not read pod logs for {target_pod}: {e}",
            }

    # ================================================================
    # 3. Kubernetes Events Inspection (Probe, Scheduling, Eviction)
    # ================================================================
    def get_pod_events(self, target_pod: str = None, namespace: str = "platform-bigdata") -> Dict[str, Any]:
        """
        Inspect Kubernetes events for the given pod or failing pods in namespace.
        Detects Liveness/Readiness probe failures, BackOff, FailedScheduling, Evicted.
        """
        if self.live_mode:
            return self._get_pod_events_live(target_pod, namespace)
        return self._get_pod_events_simulated(target_pod, namespace)

    def _get_pod_events_simulated(self, target_pod: str, namespace: str) -> Dict[str, Any]:
        pod_item = None
        for p in MOCK_POD_INVENTORY:
            if not target_pod or target_pod.lower() in p["name"].lower():
                if p.get("events"):
                    pod_item = p
                    break

        if not pod_item and MOCK_POD_INVENTORY:
            pod_item = MOCK_POD_INVENTORY[0]

        events = pod_item.get("events", []) if pod_item else []
        warnings = [e for e in events if e.get("type") == "Warning"]
        status = "critical" if any(w.get("reason") in ("BackOff", "Unhealthy", "FailedScheduling") for w in warnings) else "ok"

        summary_lines = []
        for e in events:
            summary_lines.append(f"[{e.get('type')}] {e.get('reason')}: {e.get('message')} (x{e.get('count', 1)})")

        return {
            "mode": "simulation",
            "status": status,
            "pod": pod_item["name"] if pod_item else "unknown",
            "events": events,
            "warning_count": len(warnings),
            "summary": "\n".join(summary_lines) if summary_lines else "No warning events found for pod.",
        }

    def _get_pod_events_live(self, target_pod: str, namespace: str) -> Dict[str, Any]:
        try:
            field_selector = f"involvedObject.name={target_pod}" if target_pod else None
            events = self.core_api.list_namespaced_event(namespace=namespace, field_selector=field_selector)
            warnings = []
            all_events = []
            for ev in events.items:
                ev_data = {
                    "type": ev.type,
                    "reason": ev.reason,
                    "message": ev.message,
                    "count": ev.count or 1,
                    "last_timestamp": str(ev.last_timestamp or ""),
                }
                all_events.append(ev_data)
                if ev.type == "Warning":
                    warnings.append(ev_data)

            status = "critical" if warnings else "ok"
            summary_lines = [f"[{e['type']}] {e['reason']}: {e['message']} (x{e['count']})" for e in all_events[:5]]

            return {
                "mode": "live",
                "status": status,
                "pod": target_pod or "all",
                "events": all_events,
                "warning_count": len(warnings),
                "summary": "\n".join(summary_lines) if summary_lines else "No recent events recorded.",
            }
        except Exception as e:
            return {
                "mode": "live_error",
                "status": "warning",
                "pod": target_pod,
                "events": [],
                "warning_count": 0,
                "summary": f"Failed to list events: {e}",
            }

    # ================================================================
    # 4. Pod Resource Limits & Near-OOM Detection
    # ================================================================
    def diagnose_pod_resources(self, target_pod: str = None, namespace: str = "platform-bigdata") -> Dict[str, Any]:
        """
        Evaluate pod CPU and Memory usage against container limits.
        Detects near-OOM risks (>85% warning, >95% critical) before container crashes.
        """
        inspected = []
        for p in MOCK_POD_INVENTORY:
            if target_pod and target_pod.lower() not in p["name"].lower():
                continue
            res = p.get("resources")
            if not res:
                continue

            mem_limit = res.get("mem_limit_mb", 1)
            mem_usage = res.get("mem_usage_mb", 0)
            mem_pct = round((mem_usage / mem_limit) * 100, 1) if mem_limit else 0

            cpu_limit = res.get("cpu_limit_m", 1)
            cpu_usage = res.get("cpu_usage_m", 0)
            cpu_pct = round((cpu_usage / cpu_limit) * 100, 1) if cpu_limit else 0

            if mem_pct >= 95 or p["status"] == "CrashLoopBackOff":
                res_status = "critical"
            elif mem_pct >= 85 or cpu_pct >= 90:
                res_status = "warning"
            else:
                res_status = "ok"

            inspected.append({
                "pod": p["name"],
                "node": p["node"],
                "status": res_status,
                "mem_usage_mb": mem_usage,
                "mem_limit_mb": mem_limit,
                "mem_pct": mem_pct,
                "cpu_usage_m": cpu_usage,
                "cpu_limit_m": cpu_limit,
                "cpu_pct": cpu_pct,
            })

        overall_status = "critical" if any(i["status"] == "critical" for i in inspected) else (
            "warning" if any(i["status"] == "warning" for i in inspected) else "ok"
        )

        lines = []
        for i in inspected:
            lines.append(
                f"Pod {i['pod']}: MEM {i['mem_usage_mb']}MB/{i['mem_limit_mb']}MB ({i['mem_pct']}% limit) | "
                f"CPU {i['cpu_usage_m']}m/{i['cpu_limit_m']}m ({i['cpu_pct']}%) -> status: {i['status'].upper()}"
            )

        return {
            "mode": "simulation",
            "status": overall_status,
            "total_inspected": len(inspected),
            "pods": inspected,
            "summary": "\n".join(lines) if lines else "No pod resource data available.",
        }

    # ================================================================
    # 5. Interactive ChatOps Auto-Remediation: Restart Pod
    # ================================================================
    def restart_pod(
        self, target_pod: str, namespace: str = "platform-bigdata", initiator: str = "ChatOps-Operator"
    ) -> Dict[str, Any]:
        """
        Execute safe pod restart (pod deletion).
        Kubernetes controller (StatefulSet/ReplicaSet) will automatically spawn a fresh instance.
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.info("Executing safe pod restart for %s in %s by %s", target_pod, namespace, initiator)

        if self.live_mode:
            try:
                self.core_api.delete_namespaced_pod(name=target_pod, namespace=namespace)
                msg = f"Pod {target_pod} successfully evicted/restarted via live Kubernetes API."
                log.info(msg)
                return {
                    "success": True,
                    "action": "restart_pod",
                    "mode": "live",
                    "pod": target_pod,
                    "namespace": namespace,
                    "initiator": initiator,
                    "timestamp": ts,
                    "message": msg,
                }
            except Exception as e:
                err_msg = f"Failed to restart pod {target_pod} via K8s API: {e}"
                log.error(err_msg)
                return {
                    "success": False,
                    "action": "restart_pod",
                    "mode": "live_error",
                    "pod": target_pod,
                    "namespace": namespace,
                    "initiator": initiator,
                    "timestamp": ts,
                    "message": err_msg,
                }

        # Simulation mode for testing
        msg = (
            f"[SIMULATED CHATOPS ACTION] Pod '{target_pod}' in namespace '{namespace}' "
            f"signaled for deletion by {initiator}. ReplicaSet/StatefulSet spawning fresh container."
        )
        return {
            "success": True,
            "action": "restart_pod",
            "mode": "simulation",
            "pod": target_pod,
            "namespace": namespace,
            "initiator": initiator,
            "timestamp": ts,
            "message": msg,
        }

    # ================================================================
    # 6. Longhorn Storage Diagnostics
    # ================================================================
    def diagnose_longhorn_storage(self, target_volume: str = None) -> Dict[str, Any]:
        """
        Diagnose Longhorn distributed storage volumes and replica states.
        """
        degraded = []
        for vol in MOCK_LONGHORN_VOLUMES:
            if target_volume and target_volume.lower() not in vol["volume_name"].lower():
                continue
            if vol["robustness"] != "Healthy":
                degraded.append(vol)

        status = "critical" if degraded else "ok"
        summary_lines = []
        for v in degraded:
            healthy_count = sum(1 for r in v["replicas"] if r.get("healthy"))
            total_count = len(v["replicas"])
            summary_lines.append(
                f"Volume {v['volume_name']} is {v['robustness']} ({healthy_count}/{total_count} replicas healthy) on node {v['node']}."
            )

        return {
            "mode": "simulation",
            "status": status,
            "total_volumes": len(MOCK_LONGHORN_VOLUMES),
            "degraded_volumes": degraded,
            "summary": "\n".join(summary_lines) if summary_lines else "All Longhorn volumes are healthy.",
        }


# Quick test runner
if __name__ == "__main__":
    diag = K8sDiagnosticEngine()
    print("--- 1. Kubernetes Pod Health Check ---")
    pod_res = diag.diagnose_pod_health("kafka-broker")
    print("Status :", pod_res["status"].upper())
    print("Summary:\n", pod_res["summary"])

    print("\n--- 2. Deep Crash Logs Retrieval ---")
    log_res = diag.get_pod_logs("kafka-broker-1")
    print("Status :", log_res["status"].upper())
    print("Detected Signature:", log_res["detected_signature"])
    print("Summary:\n", log_res["summary"])

    print("\n--- 3. Kubernetes Events Inspection ---")
    ev_res = diag.get_pod_events("kafka-broker-1")
    print("Status :", ev_res["status"].upper())
    print("Summary:\n", ev_res["summary"])

    print("\n--- 4. Pod Resource Limits vs Usage ---")
    res_diag = diag.diagnose_pod_resources()
    print("Status :", res_diag["status"].upper())
    print("Summary:\n", res_diag["summary"])

    print("\n--- 5. Pod Restart Remediation ---")
    action_res = diag.restart_pod("kafka-broker-1", initiator="Telegram-Operator-Helmi")
    print("Success:", action_res["success"])
    print("Message:", action_res["message"])

    print("\n--- 6. Longhorn Storage Health Check ---")
    storage_res = diag.diagnose_longhorn_storage()
    print("Status :", storage_res["status"].upper())
    print("Summary:\n", storage_res["summary"])
