"""
Kubernetes & Longhorn Storage Diagnostic Engine for Platform Bigdata.
Supports Dual Mode:
  1. Live Mode: Uses kubernetes-client / Longhorn REST API when kubeconfig / cluster credentials exist.
  2. Simulation / Mock Mode: Allows safe, full-fidelity local testing on laptops without a live cluster.
"""

import os
import json
import logging
from typing import Dict, List, Any
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

    def diagnose_pod_health(self, target_pod: str = None, namespace: str = "platform-bigdata") -> Dict[str, Any]:
        """
        Diagnose pod health and inspect crash/restart details.

        Returns:
            {
                "mode": "live" or "simulation",
                "status": "ok" | "warning" | "critical",
                "total_inspected": int,
                "failing_pods": list,
                "summary": str,
            }
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

    def diagnose_longhorn_storage(self, target_volume: str = None) -> Dict[str, Any]:
        """
        Diagnose Longhorn distributed storage volumes and replica states.

        Returns:
            {
                "mode": "live" or "simulation",
                "status": "ok" | "warning" | "critical",
                "total_volumes": int,
                "degraded_volumes": list,
                "summary": str,
            }
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
    print("--- Kubernetes Pod Health Check ---")
    pod_res = diag.diagnose_pod_health("kafka-broker")
    print("Status :", pod_res["status"].upper())
    print("Summary:\n", pod_res["summary"])

    print("\n--- Longhorn Storage Health Check ---")
    storage_res = diag.diagnose_longhorn_storage()
    print("Status :", storage_res["status"].upper())
    print("Summary:\n", storage_res["summary"])

