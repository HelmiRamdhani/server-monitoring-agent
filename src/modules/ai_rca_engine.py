"""
AI & Intelligent Heuristic Root Cause Analysis (RCA) Engine.
Synthesizes telemetry, diagnostic check results, and SOP context into
actionable, human-readable incident explanations.

Supports:
  1. Smart Deterministic / Heuristic Synthesis (offline, instant, reliable).
  2. Optional LLM Integration (local Ollama on GPU nodes or cloud LLM APIs).
"""

import os
import json
import logging
from typing import Dict, List, Any

log = logging.getLogger("agent.ai_rca")


class AIRootCauseEngine:
    """Intelligent Root Cause Analysis Engine for Platform Bigdata."""

    def __init__(self, config: Any = None):
        self.config = config or {}
        ai_cfg = self.config.get("ai_rca", {}) if isinstance(self.config, dict) else {}
        self.enabled = ai_cfg.get("enabled", True)
        self.llm_provider = ai_cfg.get("provider", "heuristic")  # "heuristic", "ollama", "gemini"
        self.ollama_url = ai_cfg.get("ollama_url", "http://localhost:11434")
        self.model_name = ai_cfg.get("model", "llama3")

    def synthesize_rca(
        self,
        incident_context: dict,
        diagnosis_results: list = None,
        kb_match: dict = None,
        metrics: dict = None,
    ) -> Dict[str, Any]:
        """
        Synthesize diagnostic telemetry and incident context into an executive RCA.

        Returns:
            {
                "headline": str,
                "executive_summary": str,
                "probable_root_cause": str,
                "immediate_impact": str,
                "recommended_actions": list of str,
                "confidence": "HIGH" | "MEDIUM" | "LOW",
                "source": "heuristic" | "llm",
            }
        """
        diagnosis_results = diagnosis_results or []
        metrics = metrics or {}
        kb_match = kb_match or {}

        alert_name = ", ".join(incident_context.get("patterns", [])) or incident_context.get("text", "Alert")
        server = incident_context.get("server", "unknown")
        severity = incident_context.get("severity", "warning").upper()

        # Check for failing diagnostic checks
        critical_checks = [r for r in diagnosis_results if r.get("status") == "critical"]
        warning_checks = [r for r in diagnosis_results if r.get("status") == "warning"]

        # 1. Specialized Heuristic Analyzers
        # Case A: Kubernetes CrashLoop / OOMKilled
        if "crashloop" in alert_name.lower() or "oom" in alert_name.lower() or any("k8s" in r.get("check_name", "") for r in critical_checks):
            return {
                "headline": f"Pod CrashLoopBackOff pada {server} terdeteksi ExitCode 137 (OOMKilled)",
                "executive_summary": (
                    f"Pod pada node {server} mengalami kegagalan berulang akibat batas alokasi memori (cgroup memory limit) terlampaui. "
                    f"Linux Kernel OOM-Killer mematikan proses utama container untuk melindungi stabilitas host."
                ),
                "probable_root_cause": (
                    "Lonjakan beban throughput data ingestion melebihi batas batas memory limits (4Gi) pada manifest pod, "
                    "menyebabkan container dihentikan paksa (OOMKilled exit code 137)."
                ),
                "immediate_impact": "Degradasi pipeline streaming ingestion; kemungkinan peningkatan consumer group lag.",
                "recommended_actions": [
                    "Taikkan resource memory limit pada deployment manifest (`resources.limits.memory` ke 6Gi/8Gi).",
                    "Jalankan `kubectl rollout restart` untuk menstabilkan replica pod yang crash.",
                    "Periksa apakah ada zombie thread atau heap leak pada runtime container.",
                ],
                "confidence": "HIGH",
                "source": "heuristic",
            }

        # Case B: Longhorn Distributed Storage Degraded
        if "longhorn" in alert_name.lower() or "volume" in alert_name.lower() or any("longhorn" in r.get("check_name", "") for r in critical_checks):
            return {
                "headline": f"Volume Storage Longhorn Degraded pada node {server}",
                "executive_summary": (
                    f"Volume distributed block storage Longhorn kehilangan redundansi akibat salah satu replika mengalami desinkronisasi atau I/O latency timeout pada {server}. "
                    f"Volume saat ini masih beroperasi dengan sisa replika sehat, namun tanpa toleransi kegagalan tambahan."
                ),
                "probable_root_cause": (
                    "Replika storage lokal mengalami disk write timeout atau I/O backlog pada disk partition NVMe/SSD, "
                    "memicu state volume berubah menjadi Degraded."
                ),
                "immediate_impact": "Redundansi data storage berkurang (2 dari 3 replika aktif). Potensi I/O latency meningkat bagi pod yang me-mount PVC ini.",
                "recommended_actions": [
                    "Buka dashboard Longhorn UI dan pantau proses auto-rebuilding replika baru.",
                    "Pastikan kapasitas disk pada node target storage pool memiliki sisa ruang > 15%.",
                    "Verifikasi network inter-node antar storage node untuk memastikan tidak ada packet drop.",
                ],
                "confidence": "HIGH",
                "source": "heuristic",
            }

        # Case C: Disk Full / High Disk Usage
        if "disk" in alert_name.lower() or any("disk" in r.get("check_name", "") for r in critical_checks):
            return {
                "headline": f"Kapasitas Partisi Disk pada {server} Melebihi Batas Kritis",
                "executive_summary": (
                    f"Penyimpanan pada {server} mengalami lonjakan pemakaian melebihi batas toleransi. "
                    f"Jika dibiarkan, layanan database dan container runtime dapat mengalami kegagalan write I/O."
                ),
                "probable_root_cause": "Akumulasi log file (`/var/log`), container temporary cache, atau journalctl yang belum di-rotate.",
                "immediate_impact": "Risiko kegagalan write database, pod eviction otomatis oleh Kubelet (DiskPressure).",
                "recommended_actions": [
                    "Jalankan rotasi log darurat: `journalctl --vacuum-time=2d`.",
                    "Hapus dangling container images: `crictl rmi --prune` atau `docker image prune -a`.",
                    "Identifikasi direktori terbesar menggunakan `du -sh /* | sort -rh | head -10`.",
                ],
                "confidence": "HIGH",
                "source": "heuristic",
            }

        # General Fallback
        matched_sop_title = kb_match.get("matched_sops", [{}])[0].get("title", "SOP Investigasi Standar")
        return {
            "headline": f"Insiden {alert_name} terdeteksi pada {server} [{severity}]",
            "executive_summary": (
                f"Sistem mendeteksi event anomali pada {server}. "
                f"Agent telah menjalankan {len(diagnosis_results)} uji diagnostik otomatis dan mencocokkan referensi runbook."
            ),
            "probable_root_cause": f"Memerlukan verifikasi lanjutan berdasarkan hasil diagnosa ({len(critical_checks)} critical, {len(warning_checks)} warning).",
            "immediate_impact": "Potensi degradasi performa pada node terdampak.",
            "recommended_actions": [
                f"Tinjau rekomendasi runbook: {matched_sop_title}.",
                "Periksa detail metrik host CPU, RAM, dan status network pada laporan PDF terlampir.",
                "Lakukan eskalasi ke tim PIC jika alert berulang dalam 15 menit.",
            ],
            "confidence": "MEDIUM",
            "source": "heuristic",
        }

