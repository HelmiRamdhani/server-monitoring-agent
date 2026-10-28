"""
Diagnosis Engine for The Workplace Brain.
Runs read-only diagnostic checks across 4 categories:
1. Network checks (ping, curl health endpoint, DNS lookup, port check)
2. System/service checks (systemctl, docker ps, df, kubectl)
3. Log aggregation query (search patterns in log files / ELK / Graylog)
4. Monitoring API query (Zabbix / Prometheus / Grafana API)

All checks are READ-ONLY. No modifications are made to any system.
Results are structured for inclusion in the PDF report.
"""

import os
import re
import time
import socket
import platform
import subprocess
import logging
from typing import Any
from datetime import datetime

import requests

log = logging.getLogger("agent.diagnosis")


class DiagnosisEngine:
    """Runs read-only diagnostic checks based on incident context."""

    def __init__(self, config: Any = None):
        self.config = config
        self.os_type = platform.system()
        self.results = []

    def run_all_checks(self, incident_context: dict, kb_match: dict = None) -> list:
        """
        Run relevant diagnostic checks based on incident context and KB match.

        Args:
            incident_context: dict with at least:
                - text: raw log line or alert text
                - patterns: list of pattern names
                - server: hostname
            kb_match: KB lookup result with matched SOPs and architecture context

        Returns:
            List of diagnosis result dicts:
                {check_type, check_name, command, status, output, duration_ms, timestamp}
        """
        self.results = []
        patterns = incident_context.get("patterns", [])
        text = incident_context.get("text", "").lower()
        server = incident_context.get("server", "localhost")

        # Extract expected services from architecture context for smart port checking
        self._expected_services = []
        if kb_match and kb_match.get("architecture_context"):
            self._expected_services = kb_match["architecture_context"].get("services", [])

        log.info("Starting diagnosis for patterns: %s", patterns)

        # Always run basic network and system checks
        self._run_network_checks(server)
        self._run_system_checks()

        # Run Kubernetes & Cloud-Native Storage checks
        self._run_cloud_native_checks(incident_context)

        # Run OpenTelemetry APM & eBPF Kernel checks
        self._run_apm_ebpf_checks(incident_context)

        # Run log aggregation queries
        self._run_log_query_checks(incident_context)

        # Run monitoring API checks if configured
        self._run_monitoring_api_checks(server)

        log.info("Diagnosis complete: %d checks executed", len(self.results))
        return self.results

    # ================================================================
    # 1. Network checks
    # ================================================================
    def _run_network_checks(self, target: str):
        """Run network diagnostic checks."""

        # Ping check
        self._execute_check(
            check_type="network",
            check_name="ping",
            command=f"ping {'-n' if self.os_type == 'Windows' else '-c'} 3 {target}",
            runner=lambda: self._ping(target),
        )

        # DNS lookup
        self._execute_check(
            check_type="network",
            check_name="dns_lookup",
            command=f"nslookup {target}",
            runner=lambda: self._dns_lookup(target),
        )

        # Port check — only check ports relevant to expected services
        # Map known services to their default ports
        service_port_map = {
            "nginx": 80, "apache": 80, "httpd": 80,
            "sshd": 22, "ssh": 22,
            "postgresql": 5432, "pgbouncer": 5432, "postgres": 5432,
            "mysql": 3306, "mariadb": 3306,
            "redis": 6379, "redis-server": 6379,
            "https": 443, "node-app": 443,
            "docker": 2375,
        }

        expected_services = getattr(self, "_expected_services", [])
        if expected_services:
            # Only check ports for services that are expected on this server
            ports_to_check = set()
            for svc in expected_services:
                svc_lower = svc.lower()
                if svc_lower in service_port_map:
                    ports_to_check.add(service_port_map[svc_lower])
            # Always include SSH
            ports_to_check.add(22)
            ports_to_check = sorted(ports_to_check)
        else:
            # Fallback: check common web/app ports only
            ports_to_check = [22, 80, 443]

        for port in ports_to_check:
            self._execute_check(
                check_type="network",
                check_name=f"port_check_{port}",
                command=f"check port {port} on {target}",
                runner=lambda p=port: self._port_check(target, p),
            )

        # HTTP health check
        self._execute_check(
            check_type="network",
            check_name="http_health",
            command=f"curl -sS -o /dev/null -w '%{{http_code}}' http://{target}/",
            runner=lambda: self._http_health_check(target),
        )

    def _ping(self, target: str) -> str:
        """Execute ping command."""
        if target in ("localhost", "127.0.0.1", platform.node()):
            return "host is local, ping not needed"

        flag = "-n" if self.os_type == "Windows" else "-c"
        try:
            result = subprocess.run(
                ["ping", flag, "3", target],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip() if result.stdout else result.stderr.strip()
        except subprocess.TimeoutExpired:
            return "ping timed out"
        except FileNotFoundError:
            return "ping command not available"
        except Exception as e:
            return f"ping error: {e}"

    def _dns_lookup(self, target: str) -> str:
        """Perform DNS lookup."""
        try:
            ip = socket.gethostbyname(target)
            return f"Resolved: {target} -> {ip}"
        except socket.gaierror:
            return f"DNS resolution failed for {target}"
        except Exception as e:
            return f"DNS error: {e}"

    def _port_check(self, host: str, port: int) -> str:
        """Check if a TCP port is open."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return f"port {port} is OPEN"
            else:
                return f"port {port} is CLOSED"
        except socket.gaierror:
            return f"port {port}: host unresolved"
        except Exception as e:
            return f"port {port}: error - {e}"

    def _http_health_check(self, target: str) -> str:
        """Check HTTP health endpoint."""
        if target in ("localhost", "127.0.0.1"):
            url = "http://localhost/"
        else:
            url = f"http://{target}/"
        try:
            resp = requests.get(url, timeout=5, allow_redirects=True)
            return f"HTTP {resp.status_code} - {resp.reason} (response time: {resp.elapsed.total_seconds():.2f}s)"
        except requests.exceptions.ConnectionError:
            return f"connection refused: {url}"
        except requests.exceptions.Timeout:
            return f"timeout: {url}"
        except Exception as e:
            return f"HTTP check error: {e}"

    # ================================================================
    # 2. System / service checks
    # ================================================================
    def _run_system_checks(self):
        """Run system and service status checks."""

        # Disk usage
        self._execute_check(
            check_type="system",
            check_name="disk_usage",
            command="df -h" if self.os_type != "Windows" else "wmic logicaldisk",
            runner=self._check_disk_usage,
        )

        # Memory usage
        self._execute_check(
            check_type="system",
            check_name="memory_usage",
            command="free -h" if self.os_type != "Windows" else "systeminfo",
            runner=self._check_memory,
        )

        # Top processes by memory
        self._execute_check(
            check_type="system",
            check_name="top_processes_mem",
            command="ps aux --sort=-%mem | head -10",
            runner=self._check_top_processes,
        )

        # Failed services (systemd)
        if self.os_type != "Windows":
            self._execute_check(
                check_type="system",
                check_name="failed_services",
                command="systemctl --failed",
                runner=self._check_failed_services,
            )

        # Docker containers status
        self._execute_check(
            check_type="system",
            check_name="docker_ps",
            command="docker ps -a --format 'table {{.Names}}\t{{.Status}}'",
            runner=self._check_docker,
        )

    def _run_cloud_native_checks(self, incident_context: dict):
        """Run Kubernetes & Longhorn storage diagnostic checks."""
        patterns = [p.lower() for p in incident_context.get("patterns", [])]
        text = incident_context.get("text", "").lower()

        # Check if incident is related to K8s pods, containers, or distributed storage
        is_k8s = any(kw in " ".join(patterns) or kw in text for kw in [
            "pod", "kube", "k8s", "crashloop", "oom", "restart", "container",
        ])
        is_storage = any(kw in " ".join(patterns) or kw in text for kw in [
            "longhorn", "volume", "replica", "storage", "pvc", "disk",
        ])

        try:
            try:
                from modules.k8s_diagnostics import K8sDiagnosticEngine
            except ImportError:
                from src.modules.k8s_diagnostics import K8sDiagnosticEngine

            k8s_engine = K8sDiagnosticEngine()

            if is_k8s:
                # 1. Pod Health Check
                def _run_pod_diag():
                    res = k8s_engine.diagnose_pod_health()
                    return f"status: {res['status'].upper()}\n{res['summary']}"

                self._execute_check(
                    check_type="kubernetes",
                    check_name="k8s_pod_health",
                    command="kubectl get pods -n platform-bigdata",
                    runner=_run_pod_diag,
                )

                # 2. Deep Crash Logs Retrieval (kubectl logs --previous)
                def _run_pod_crash_logs():
                    res = k8s_engine.get_pod_logs()
                    return f"status: {res['status'].upper()}\n{res['summary']}"

                self._execute_check(
                    check_type="kubernetes",
                    check_name="k8s_pod_crash_logs",
                    command="kubectl logs -n platform-bigdata --previous --tail=50",
                    runner=_run_pod_crash_logs,
                )

                # 3. Pod Events Inspection (Probes & Scheduling)
                def _run_pod_events():
                    res = k8s_engine.get_pod_events()
                    return f"status: {res['status'].upper()}\n{res['summary']}"

                self._execute_check(
                    check_type="kubernetes",
                    check_name="k8s_pod_events",
                    command="kubectl get events -n platform-bigdata --sort-by=.metadata.creationTimestamp",
                    runner=_run_pod_events,
                )

                # 4. Pod Resource Limits vs Usage
                def _run_pod_resources():
                    res = k8s_engine.diagnose_pod_resources()
                    return f"status: {res['status'].upper()}\n{res['summary']}"

                self._execute_check(
                    check_type="kubernetes",
                    check_name="k8s_pod_resource_limits",
                    command="kubectl top pods -n platform-bigdata --containers",
                    runner=_run_pod_resources,
                )

            if is_storage:
                def _run_storage_diag():
                    res = k8s_engine.diagnose_longhorn_storage()
                    return f"status: {res['status'].upper()}\n{res['summary']}"

                self._execute_check(
                    check_type="storage",
                    check_name="longhorn_volume_health",
                    command="kubectl get volumes.longhorn.io -n longhorn-system",
                    runner=_run_storage_diag,
                )
        except Exception as e:
            log.warning("Could not execute cloud-native checks: %s", e)

    def _run_apm_ebpf_checks(self, incident_context: dict):
        """Run OpenTelemetry APM, Google SRE SLI/SLO, and eBPF Kernel diagnostic checks."""
        patterns = [p.lower() for p in incident_context.get("patterns", [])]
        text = incident_context.get("text", "").lower()

        is_apm = any(kw in " ".join(patterns) or kw in text for kw in [
            "service", "api", "latency", "slo", "trace", "http", "5xx", "rate", "slow", "checkout", "payment", "burn",
        ])
        is_ebpf = any(kw in " ".join(patterns) or kw in text for kw in [
            "ebpf", "kernel", "retransmit", "drop", "syscall", "network", "tcp", "io",
        ])

        try:
            try:
                from modules.apm_otel_diagnostics import APMOtelDiagnosticEngine
            except ImportError:
                from src.modules.apm_otel_diagnostics import APMOtelDiagnosticEngine

            apm_engine = APMOtelDiagnosticEngine()

            if is_apm:
                # 1. Service APM Latency & Trace Breakdown
                def _run_apm_diag():
                    res = apm_engine.diagnose_service_apm()
                    return f"status: {res['status'].upper()}\n{res['summary']}"

                self._execute_check(
                    check_type="apm",
                    check_name="otel_service_traces",
                    command="otel-collector query traces --service platform-bigdata",
                    runner=_run_apm_diag,
                )

                # 2. Google SRE SLI/SLO & Error Budget Burn Rate
                def _run_slo_diag():
                    res = apm_engine.evaluate_sre_slo()
                    return f"status: {res['status'].upper()}\n{res['summary']}"

                self._execute_check(
                    check_type="sre",
                    check_name="slo_burn_rate",
                    command="sre-slo-engine evaluate --window 1h",
                    runner=_run_slo_diag,
                )

            if is_ebpf:
                # 3. eBPF Kernel Probes & Retransmit Telemetry
                def _run_ebpf_diag():
                    res = apm_engine.diagnose_ebpf_kernel()
                    return f"status: {res['status'].upper()}\n{res['summary']}"

                self._execute_check(
                    check_type="ebpf",
                    check_name="ebpf_kernel_probes",
                    command="bpftrace -e 'tracepoint:tcp:tcp_retransmit_skb'",
                    runner=_run_ebpf_diag,
                )
        except Exception as e:
            log.warning("Could not execute APM / eBPF checks: %s", e)

    def _check_disk_usage(self) -> str:
        """Check disk usage across mounted filesystems."""
        try:
            import psutil
            parts = psutil.disk_partitions()
            lines = []
            for p in parts:
                try:
                    usage = psutil.disk_usage(p.mountpoint)
                    pct = usage.percent
                    status = "OK" if pct < 80 else "WARNING" if pct < 90 else "CRITICAL"
                    lines.append(f"{p.mountpoint}: {pct}% used (status: {status}) - {usage.total // (1024**3)}GB total")
                except PermissionError:
                    continue
            return "\n".join(lines) if lines else "no disk partitions found — status: OK"
        except Exception as e:
            return f"disk check error: {e}"

    def _check_memory(self) -> str:
        """Check memory and swap usage with threshold evaluation."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Evaluate memory status against thresholds
            mem_pct = mem.percent
            if mem_pct >= 92:
                mem_status = "CRITICAL"
            elif mem_pct >= 80:
                mem_status = "WARNING"
            else:
                mem_status = "OK"

            return (
                f"Memory: {mem.percent}% used ({mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB) — status: {mem_status}\n"
                f"Swap: {swap.percent}% used ({swap.used // (1024**3)}GB / {swap.total // (1024**3)}GB)"
            )
        except Exception as e:
            return f"memory check error: {e}"

    def _check_top_processes(self) -> str:
        """List top processes by memory usage."""
        try:
            import psutil
            procs = []
            for p in psutil.process_iter(["name", "memory_percent", "cpu_percent", "pid"]):
                try:
                    info = p.info
                    procs.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            procs.sort(key=lambda x: x.get("memory_percent", 0) or 0, reverse=True)
            lines = ["PID    NAME                MEM%    CPU%"]
            for p in procs[:10]:
                pid = p.get("pid", "?")
                name = (p.get("name", "?") or "?")[:18]
                mem = round(p.get("memory_percent", 0) or 0, 1)
                cpu = round(p.get("cpu_percent", 0) or 0, 1)
                lines.append(f"{pid:<6} {name:<18} {mem:<7} {cpu}")
            return "\n".join(lines)
        except Exception as e:
            return f"process check error: {e}"

    def _check_failed_services(self) -> str:
        """Check for failed systemd services."""
        try:
            result = subprocess.run(
                ["systemctl", "--failed", "--no-legend"],
                capture_output=True, text=True, timeout=5,
            )
            output = result.stdout.strip()
            if not output:
                return "no failed services"
            return output
        except FileNotFoundError:
            return "systemctl not available"
        except subprocess.TimeoutExpired:
            return "systemctl timed out"
        except Exception as e:
            return f"service check error: {e}"

    def _check_docker(self) -> str:
        """Check Docker container status."""
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
                capture_output=True, text=True, timeout=10,
            )
            output = result.stdout.strip()
            if not output:
                return "no containers or docker not running"
            return output[:500]
        except FileNotFoundError:
            return "docker not installed"
        except subprocess.TimeoutExpired:
            return "docker command timed out"
        except Exception as e:
            return f"docker check error: {e}"

    # ================================================================
    # 3. Log aggregation query
    # ================================================================
    def _run_log_query_checks(self, incident_context: dict):
        """Search log files for patterns related to the incident."""
        patterns = incident_context.get("patterns", [])
        text = incident_context.get("text", "")

        # Get log file paths from config
        log_files = []
        if self.config:
            syslog_cfg = self.config.get("syslog")
            if syslog_cfg:
                log_files = syslog_cfg.get("log_files", [])

        if not log_files:
            log_files = ["/var/log/syslog", "/var/log/messages", "/var/log/auth.log"]

        # Build search terms from incident patterns and keywords
        search_terms = []
        for p in patterns:
            # Extract key words from pattern name
            words = [w for w in p.lower().split() if len(w) > 2]
            search_terms.extend(words)

        # Also extract error keywords from incident text
        error_keywords = re.findall(r'\b(?:error|fail|crash|critical|panic|oom|killed|denied|timeout|refused)\w*\b', text, re.IGNORECASE)
        search_terms.extend(list(set(k.lower() for k in error_keywords))[:5])

        if not search_terms:
            return

        for log_file in log_files:
            self._execute_check(
                check_type="log_query",
                check_name=f"search_{os.path.basename(log_file)}",
                command=f"grep -i '{'|'.join(search_terms[:3])}' {log_file} | tail -20",
                runner=lambda lf=log_file, terms=search_terms: self._search_log(lf, terms),
            )

    def _search_log(self, log_file: str, search_terms: list) -> str:
        """Search a log file for specific terms."""
        if not os.path.exists(log_file):
            return f"log file not found: {log_file}"

        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-200:]  # last 200 lines

            matches = []
            for line in lines:
                line_lower = line.lower()
                if any(term in line_lower for term in search_terms):
                    matches.append(line.strip())

            if matches:
                return f"found {len(matches)} matching lines:\n" + "\n".join(matches[:15])
            else:
                return f"no matches found for terms: {search_terms[:5]}"
        except PermissionError:
            return f"permission denied: {log_file}"
        except Exception as e:
            return f"log search error: {e}"

    # ================================================================
    # 4. Monitoring API query
    # ================================================================
    def _run_monitoring_api_checks(self, server: str):
        """Query external monitoring APIs if configured."""
        if not self.config:
            return

        monitoring_cfg = self.config.get("monitoring_api")
        if not monitoring_cfg:
            return

        api_type = monitoring_cfg.get("type", "").lower()

        if api_type == "prometheus":
            self._execute_check(
                check_type="monitoring_api",
                check_name="prometheus_query",
                command=f"query Prometheus for {server}",
                runner=lambda: self._query_prometheus(monitoring_cfg, server),
            )
        elif api_type == "zabbix":
            self._execute_check(
                check_type="monitoring_api",
                check_name="zabbix_query",
                command=f"query Zabbix for {server}",
                runner=lambda: self._query_zabbix(monitoring_cfg, server),
            )
        elif api_type == "grafana":
            self._execute_check(
                check_type="monitoring_api",
                check_name="grafana_query",
                command=f"query Grafana for {server}",
                runner=lambda: self._query_grafana(monitoring_cfg, server),
            )

    def _query_prometheus(self, cfg: Any, server: str) -> str:
        """Query Prometheus API for server metrics."""
        url = cfg.get("url", "http://localhost:9090")
        queries = cfg.get("queries", [
            f'up{{instance="{server}"}}',
            f'node_load1{{instance="{server}"}}',
        ])
        results = []
        for query in queries:
            try:
                resp = requests.get(
                    f"{url}/api/v1/query",
                    params={"query": query},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        for result in data.get("data", {}).get("result", []):
                            value = result.get("value", [0, "N/A"])[1]
                            results.append(f"{query} = {value}")
                    else:
                        results.append(f"{query} = query failed")
                else:
                    results.append(f"{query} = HTTP {resp.status_code}")
            except Exception as e:
                results.append(f"{query} = error: {e}")
        return "\n".join(results) if results else "no Prometheus results"

    def _query_zabbix(self, cfg: Any, server: str) -> str:
        """Query Zabbix API for server metrics."""
        url = cfg.get("url", "http://localhost/zabbix/api_jsonrpc.php")
        token = cfg.get("api_token", "")
        if not token:
            return "Zabbix API token not configured"
        # Simplified: in production, implement proper Zabbix API call
        return f"Zabbix API query for {server} (configured but not fully implemented - add API calls)"

    def _query_grafana(self, cfg: Any, server: str) -> str:
        """Query Grafana API."""
        url = cfg.get("url", "http://localhost:3000")
        token = cfg.get("api_token", "")
        if not token:
            return "Grafana API token not configured"
        try:
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(f"{url}/api/health", headers=headers, timeout=10)
            return f"Grafana health: {resp.status_code} - {resp.text[:200]}"
        except Exception as e:
            return f"Grafana API error: {e}"

    # ================================================================
    # Helper: execute and record a check
    # ================================================================
    def _execute_check(self, check_type: str, check_name: str, command: str, runner):
        """Execute a diagnostic check and record the result."""
        result = {
            "check_type": check_type,
            "check_name": check_name,
            "command": command,
            "status": "unknown",
            "output": "",
            "duration_ms": 0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        start = time.time()
        try:
            output = runner()
            result["output"] = output[:1000]  # truncate for report
            result["status"] = self._determine_status(output)
        except Exception as e:
            result["output"] = f"check failed: {e}"
            result["status"] = "error"

        result["duration_ms"] = round((time.time() - start) * 1000, 0)

        log.debug("  [%s/%s] %s -> %s (%.0fms)",
                  check_type, check_name, result["status"], result["duration_ms"], result["duration_ms"])

        self.results.append(result)

    def _determine_status(self, output: str) -> str:
        """
        Determine check status from output text.

        Priority order:
          1. Explicit status markers (status: CRITICAL, status: WARNING, status: OK) — highest priority
          2. Error conditions (failed, refused, timed out, error, panic, etc.)
          3. Warning conditions (warning, high usage)
          4. Healthy conditions (ok, open, success, up, resolved, no failed, no matches)
          5. Default: info
        """
        output_lower = output.lower()

        # 1. Check for explicit status markers first (from our improved check functions)
        if "status: critical" in output_lower:
            return "critical"
        if "status: warning" in output_lower:
            return "warning"
        if "status: ok" in output_lower:
            return "ok"

        # Clean search results or healthy states (checked before error keywords so "[error]" in search query doesn't trigger false critical)
        if any(kw in output_lower for kw in [
            "no matches", "no failed", "not needed", "no containers", "not installed",
        ]):
            return "ok"

        # 2. Critical error conditions
        if any(kw in output_lower for kw in [
            "error", "failed", "refused", "timed out", "panic",
            "permission denied", "not available", "check failed",
            "connection refused", "dns resolution failed",
        ]):
            return "critical"

        # 3. Warning conditions (only actual warnings, not "no matches")
        if any(kw in output_lower for kw in [
            "warning", "high usage",
        ]):
            return "warning"

        # 4. Healthy / informational conditions (including "closed" for non-expected ports,
        #    and "no matches" which means logs are clean = good)
        if any(kw in output_lower for kw in [
            "ok", "open", "success", "up", "resolved", "no failed",
            "no matches", "not needed", "no containers",
            "no disk", "not installed",
        ]):
            return "ok"

        # 5. Port closed — treat as informational, not critical
        #    (a closed port is expected for services not running on this server)
        if "closed" in output_lower:
            return "info"

        return "info"

    def summarize_results(self) -> dict:
        """Create summary of all diagnosis results."""
        summary = {
            "total_checks": len(self.results),
            "by_status": {},
            "by_type": {},
            "critical_checks": [],
        }

        for r in self.results:
            status = r["status"]
            summary["by_status"][status] = summary["by_status"].get(status, 0) + 1

            ctype = r["check_type"]
            summary["by_type"][ctype] = summary["by_type"].get(ctype, 0) + 1

            if status in ("critical", "warning"):
                summary["critical_checks"].append({
                    "check_name": r["check_name"],
                    "status": r["status"],
                    "output": r["output"][:200],
                })

        return summary
