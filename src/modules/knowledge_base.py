"""
Knowledge Base Engine for The Workplace Brain.
Loads SOP docs, architecture, and incident history from local files.
Matches incoming incidents to relevant KB entries using keyword and pattern matching.
Supports feedback loop: can update KB with new incident resolutions.
"""

import os
import re
import json
import glob
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("agent.kb")


class KnowledgeBase:
    """
    Knowledge base engine that loads and queries:
    - SOP documents (Markdown with YAML frontmatter)
    - Architecture definitions (YAML)
    - Incident history (JSON files)
    """

    def __init__(self, kb_dir: str = None):
        if kb_dir is None:
            kb_dir = Path(__file__).resolve().parent.parent.parent / "kb"
        self.kb_dir = Path(kb_dir)
        self.sop_dir = self.kb_dir / "sop"
        self.arch_dir = self.kb_dir / "architecture"
        self.history_dir = self.kb_dir / "incident_history"

        self.sops = []
        self.architecture = {}
        self.incidents = []

        self._load_all()

    def _load_all(self):
        """Load all KB entries into memory."""
        self._load_sops()
        self._load_architecture()
        self._load_incident_history()
        log.info("KB loaded: %d SOPs, %d architecture entries, %d incidents",
                 len(self.sops), len(self.architecture), len(self.incidents))

    def _load_sops(self):
        """Load all SOP Markdown files from the sop/ directory."""
        self.sops = []
        if not self.sop_dir.exists():
            log.warning("SOP directory not found: %s", self.sop_dir)
            return

        for filepath in sorted(self.sop_dir.glob("*.md")):
            try:
                entry = self._parse_sop_file(filepath)
                if entry:
                    self.sops.append(entry)
                    log.debug("Loaded SOP: %s (%s)", entry["id"], entry["title"])
            except Exception as e:
                log.error("Error loading SOP %s: %s", filepath, e)

    def _parse_sop_file(self, filepath: Path) -> dict:
        """
        Parse a SOP Markdown file.
        Supports two formats:
          1. YAML frontmatter between --- markers
          2. Markdown metadata with bold keys: - **ID:** value, - **Triggers:** value, etc.
        Extracts metadata (id, triggers, severity) and full content.
        """
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        entry = {
            "id": "",
            "title": filepath.stem,
            "triggers": [],
            "severity": "warning",
            "content": content,
            "filepath": str(filepath),
        }

        # Strategy 1: Parse YAML frontmatter (--- ... ---)
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            try:
                frontmatter = yaml.safe_load(fm_match.group(1))
                if frontmatter:
                    entry["id"] = frontmatter.get("ID", filepath.stem)
                    entry["triggers"] = frontmatter.get("Triggers", [])
                    if isinstance(entry["triggers"], str):
                        entry["triggers"] = [t.strip() for t in entry["triggers"].split(",")]
                    entry["severity"] = frontmatter.get("Severity", "warning")
                    entry["title"] = frontmatter.get("title", filepath.stem)
            except yaml.YAMLError as e:
                log.warning("YAML parse error in %s: %s", filepath, e)

        # Strategy 2: Parse Markdown metadata (- **Key:** value)
        # Used when SOP files have ## Metadata section with bold-key list items
        if not entry["id"] or not entry["triggers"]:
            # Extract ID: - **ID:** sop-oom-killer
            id_match = re.search(r"-\s+\*\*ID:\*\*\s*(.+)", content)
            if id_match:
                entry["id"] = id_match.group(1).strip()

            # Extract Triggers: - **Triggers:** out of memory, oom-killer, ...
            trig_match = re.search(r"-\s+\*\*Triggers?:\*\*\s*(.+)", content)
            if trig_match:
                raw_triggers = trig_match.group(1).strip()
                entry["triggers"] = [t.strip() for t in raw_triggers.split(",") if t.strip()]

            # Extract Severity: - **Severity:** critical
            sev_match = re.search(r"-\s+\*\*Severity:\*\*\s*(.+)", content)
            if sev_match:
                raw_sev = sev_match.group(1).strip().lower()
                # Handle compound severity like "warning -> critical (if >10 attempts)"
                # Take the first severity keyword found
                for sev_keyword in ["critical", "error", "warning", "info"]:
                    if sev_keyword in raw_sev:
                        entry["severity"] = sev_keyword
                        break

        # Extract title from first markdown heading if no frontmatter title
        if not entry["title"] or entry["title"] == filepath.stem:
            h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if h1_match:
                entry["title"] = h1_match.group(1).strip()

        log.debug("Parsed SOP: id=%s, title=%s, triggers=%s, severity=%s",
                  entry["id"], entry["title"], entry["triggers"], entry["severity"])

        return entry

    def _load_architecture(self):
        """Load architecture YAML files."""
        self.architecture = {}
        if not self.arch_dir.exists():
            log.warning("Architecture directory not found: %s", self.arch_dir)
            return

        for filepath in sorted(self.arch_dir.glob("*.yaml")) + sorted(self.arch_dir.glob("*.yml")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data:
                        key = filepath.stem
                        self.architecture[key] = data
                        log.debug("Loaded architecture: %s", key)
            except Exception as e:
                log.error("Error loading architecture %s: %s", filepath, e)

    def _load_incident_history(self):
        """Load all incident history JSON files."""
        self.incidents = []
        if not self.history_dir.exists():
            log.warning("Incident history directory not found: %s", self.history_dir)
            return

        for filepath in sorted(self.history_dir.glob("*.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                    entry["_filepath"] = str(filepath)
                    self.incidents.append(entry)
                    log.debug("Loaded incident: %s", entry.get("incident_id", filepath.stem))
            except Exception as e:
                log.error("Error loading incident %s: %s", filepath, e)

    def lookup(self, incident_text: str, incident_patterns: list = None,
               server_name: str = None) -> dict:
        """
        Match an incident to KB entries.

        Args:
            incident_text: raw log line or alert message
            incident_patterns: list of pattern names that triggered (e.g., ["OOM killer"])
            server_name: hostname if known

        Returns:
            {
                "matched_sops": [list of SOP dicts with relevance score],
                "similar_incidents": [list of past incidents sorted by similarity],
                "architecture_context": dict with server info if found,
                "escalation_target": str or None,
            }
        """
        results = {
            "matched_sops": [],
            "similar_incidents": [],
            "architecture_context": None,
            "escalation_target": None,
        }

        combined_text = (incident_text or "").lower()
        if incident_patterns:
            combined_text += " " + " ".join(p.lower() for p in incident_patterns)

        # --- Match SOPs ---
        for sop in self.sops:
            score = 0
            matched_triggers = []

            for trigger in sop.get("triggers", []):
                trigger_lower = trigger.lower()
                if trigger_lower in combined_text:
                    score += 10
                    matched_triggers.append(trigger)

            # Also check if pattern keywords appear in the SOP title
            title_words = sop.get("title", "").lower().split()
            for word in title_words:
                if len(word) > 3 and word in combined_text:
                    score += 3

            if score > 0:
                results["matched_sops"].append({
                    "id": sop["id"],
                    "title": sop["title"],
                    "severity": sop["severity"],
                    "relevance_score": score,
                    "matched_triggers": matched_triggers,
                    "content_preview": sop["content"][:500],
                    "filepath": sop["filepath"],
                })

        results["matched_sops"].sort(key=lambda x: x["relevance_score"], reverse=True)

        # --- Match similar incidents ---
        for inc in self.incidents:
            score = 0
            signatures = inc.get("pattern_signatures", [])

            for sig in signatures:
                if sig.lower() in combined_text:
                    score += 15

            # Match on server name
            if server_name and inc.get("server", "").lower() == server_name.lower():
                score += 5

            # Match on title keywords
            inc_title = inc.get("title", "").lower()
            inc_words = [w for w in inc_title.split() if len(w) > 3]
            for word in inc_words:
                if word in combined_text:
                    score += 5

            if score > 0:
                results["similar_incidents"].append({
                    "incident_id": inc.get("incident_id"),
                    "title": inc.get("title"),
                    "date": inc.get("date"),
                    "severity": inc.get("severity"),
                    "root_cause": inc.get("root_cause"),
                    "resolution": inc.get("resolution"),
                    "similarity_score": score,
                    "pattern_signatures": signatures,
                })

        results["similar_incidents"].sort(key=lambda x: x["similarity_score"], reverse=True)

        # --- Architecture context ---
        arch_data = self.architecture.get("servers", {})
        servers = arch_data.get("servers", []) if isinstance(arch_data, dict) else []
        for srv in servers:
            if server_name and srv.get("hostname") == server_name:
                results["architecture_context"] = srv
                results["escalation_target"] = srv.get("escalation")
                break

        # Try to find escalation target from service_escalation if server not matched
        if not results["escalation_target"]:
            service_esc = arch_data.get("service_escalation", {}) if isinstance(arch_data, dict) else {}
            for service, team in service_esc.items():
                if service.lower() in combined_text:
                    results["escalation_target"] = team
                    break

        log.info("KB lookup: %d SOPs matched, %d similar incidents found",
                 len(results["matched_sops"]), len(results["similar_incidents"]))

        return results

    def add_incident(self, incident_data: dict) -> str:
        """
        Add a new incident to the KB (feedback loop).
        Creates a JSON file in incident_history/ directory.

        Args:
            incident_data: dict with incident details

        Returns:
            Filepath of the saved incident
        """
        self.history_dir.mkdir(parents=True, exist_ok=True)

        inc_id = incident_data.get("incident_id")
        if not inc_id:
            inc_id = f"INC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            incident_data["incident_id"] = inc_id

        filename = f"{inc_id}.json"
        filepath = self.history_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(incident_data, f, indent=2, ensure_ascii=False)

        # Add to in-memory list
        incident_data["_filepath"] = str(filepath)
        self.incidents.append(incident_data)

        log.info("Incident added to KB: %s -> %s", inc_id, filepath)
        return str(filepath)

    def get_incident_analytics(self, days: int = 7) -> dict:
        """
        Aggregate incidents occurring within the last N days for periodic reporting (weekly/monthly).

        Args:
            days: number of days to look back (7 for weekly, 30 for monthly)

        Returns:
            dict with:
                - period_days: int
                - total_incidents: int
                - by_severity: dict {severity: count}
                - by_server: dict {server: count}
                - top_root_causes: list of (cause, count)
                - top_sops_used: list of (sop_id, count)
                - status_counts: dict {status: count} (e.g. resolved, investigating)
                - incidents: list of incident dicts within period
        """
        from datetime import timedelta

        now = datetime.now()
        cutoff_date = now - timedelta(days=days)

        period_incidents = []
        by_severity = {}
        by_server = {}
        root_causes = {}
        sops_used = {}
        status_counts = {"resolved": 0, "investigating": 0, "open": 0}

        for inc in self.incidents:
            date_str = inc.get("date")
            inc_dt = None
            if date_str:
                for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        inc_dt = datetime.strptime(date_str[:19], fmt)
                        break
                    except ValueError:
                        continue

            # If date couldn't be parsed or is within cutoff
            if inc_dt and inc_dt < cutoff_date:
                continue

            period_incidents.append(inc)

            # Severity tally
            sev = inc.get("severity", "warning").lower()
            by_severity[sev] = by_severity.get(sev, 0) + 1

            # Server tally
            srv = inc.get("server", "unknown")
            by_server[srv] = by_server.get(srv, 0) + 1

            # Root cause tally
            rc = inc.get("root_cause", "")
            if rc and rc.lower() not in ("tbd", "unknown", "tbd - requires manual review", ""):
                root_causes[rc] = root_causes.get(rc, 0) + 1

            # SOP tally
            sop = inc.get("sop_used")
            if sop and sop not in ("N/A", "unknown", ""):
                sops_used[sop] = sops_used.get(sop, 0) + 1

            # Status tally
            status = inc.get("status")
            if status:
                status_counts[status] = status_counts.get(status, 0) + 1
            else:
                # Infer from root cause
                if rc and rc.lower() not in ("tbd", "unknown", "tbd - requires manual review", ""):
                    status_counts["resolved"] += 1
                else:
                    status_counts["investigating"] += 1

        # Sort top root causes and SOPs
        sorted_root_causes = sorted(root_causes.items(), key=lambda x: x[1], reverse=True)[:5]
        sorted_sops = sorted(sops_used.items(), key=lambda x: x[1], reverse=True)[:5]

        analytics = {
            "period_days": days,
            "cutoff_date": cutoff_date.strftime("%Y-%m-%d"),
            "total_incidents": len(period_incidents),
            "by_severity": by_severity,
            "by_server": by_server,
            "top_root_causes": sorted_root_causes,
            "top_sops_used": sorted_sops,
            "status_counts": status_counts,
            "incidents": period_incidents,
        }

        log.info("Incident analytics (past %d days): %d total incidents", days, len(period_incidents))
        return analytics

    def get_sop_content(self, sop_id: str) -> str:
        """Retrieve full SOP content by ID."""
        for sop in self.sops:
            if sop["id"] == sop_id:
                return sop["content"]
        return ""

    def reload(self):
        """Reload KB from disk (useful after updates)."""
        self._load_all()
        log.info("KB reloaded")
