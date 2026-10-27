"""
Feedback Loop Module for The Workplace Brain.
After an incident is resolved, this module:
1. Updates the knowledge base with the new incident resolution
2. Tags the helpdesk ticket as resolved (if ticket API is configured)
3. Generates a post-mortem draft for critical incidents

This closes the loop — the agent learns from every incident.
"""

import os
import json
import logging
from datetime import datetime
from typing import Any

import requests

log = logging.getLogger("agent.feedback")


class FeedbackLoop:
    """Handles post-incident feedback: KB update, ticket resolution, post-mortem."""

    def __init__(self, kb, config: Any = None):
        """
        Args:
            kb: KnowledgeBase instance
            config: Config object with optional ticketing_api section
        """
        self.kb = kb
        self.config = config

    def process_resolution(self, incident_data: dict) -> dict:
        """
        Process the resolution of an incident.

        SAFETY: This method differentiates between two modes:
          - Triage mode (root_cause is "TBD" or empty): Only records the incident
            as "open/investigating" in KB. Does NOT resolve tickets or create
            post-mortems. This prevents premature ticket closure on new alerts.
          - Resolution mode (root_cause is filled): Full processing — updates KB,
            resolves ticket, and creates post-mortem for critical incidents.

        Args:
            incident_data: dict with at least:
                - incident_id (optional, auto-generated if missing)
                - title
                - severity
                - server
                - symptoms (list of str)
                - root_cause
                - resolution
                - sop_used (SOP ID if one was matched)
                - diagnosis_commands_run (list)
                - time_to_resolve
                - follow_up
                - pattern_signatures (list of str for future matching)

        Returns:
            {
                "kb_updated": bool,
                "kb_filepath": str or None,
                "ticket_resolved": bool,
                "post_mortem_created": bool,
                "post_mortem_path": str or None,
                "mode": "triage" or "resolution",
            }
        """
        results = {
            "kb_updated": False,
            "kb_filepath": None,
            "ticket_resolved": False,
            "post_mortem_created": False,
            "post_mortem_path": None,
            "mode": "triage",
        }

        root_cause = incident_data.get("root_cause", "").strip()
        is_resolved = root_cause and root_cause.lower() not in (
            "tbd", "tbd - requires manual review", "unknown", "pending", "",
        )

        if is_resolved:
            results["mode"] = "resolution"
        else:
            results["mode"] = "triage"
            # Mark incident status as open/investigating for KB storage
            incident_data["status"] = "investigating"

        log.info("Processing feedback for incident: %s (mode: %s)",
                 incident_data.get("incident_id", "N/A"), results["mode"])

        # 1. Update KB with new incident (always — records the event)
        results["kb_updated"], results["kb_filepath"] = self._update_kb(incident_data)

        # 2. Tag helpdesk ticket as resolved — ONLY if root cause is confirmed
        if is_resolved:
            results["ticket_resolved"] = self._resolve_ticket(incident_data)
        else:
            log.info("Skipping ticket resolution — incident is still in triage (root_cause: %s)",
                     root_cause or "empty")

        # 3. Create post-mortem — ONLY for confirmed critical resolutions
        if is_resolved and incident_data.get("severity") == "critical":
            results["post_mortem_created"], results["post_mortem_path"] = self._create_post_mortem(incident_data)
        elif not is_resolved and incident_data.get("severity") == "critical":
            log.info("Skipping post-mortem — incident is critical but root cause not yet confirmed")

        log.info("Feedback loop complete: KB=%s, Ticket=%s, PostMortem=%s, Mode=%s",
                 results["kb_updated"], results["ticket_resolved"],
                 results["post_mortem_created"], results["mode"])

        return results

    def _update_kb(self, incident_data: dict) -> tuple:
        """Add incident to KB incident history."""
        try:
            # Clean data for KB storage
            kb_entry = {k: v for k, v in incident_data.items() if not k.startswith("_")}

            # Ensure required fields
            if not kb_entry.get("date"):
                kb_entry["date"] = datetime.now().strftime("%Y-%m-%d")

            if not kb_entry.get("pattern_signatures"):
                # Auto-extract signatures from symptoms and root cause
                text = " ".join(kb_entry.get("symptoms", [])) + " " + kb_entry.get("root_cause", "")
                kb_entry["pattern_signatures"] = self._extract_signatures(text)

            filepath = self.kb.add_incident(kb_entry)
            log.info("Incident added to KB: %s", filepath)
            return True, filepath
        except Exception as e:
            log.error("Failed to update KB: %s", e)
            return False, None

    def _resolve_ticket(self, incident_data: dict) -> bool:
        """Tag helpdesk ticket as resolved via API (if configured)."""
        if not self.config:
            return False

        ticket_cfg = self.config.get("ticketing_api")
        if not ticket_cfg:
            log.info("No ticketing API configured, skipping ticket resolution")
            return False

        ticket_id = incident_data.get("ticket_id")
        if not ticket_id:
            log.info("No ticket ID in incident data, skipping")
            return False

        api_url = ticket_cfg.get("url", "")
        api_token = ticket_cfg.get("token", "")
        api_type = ticket_cfg.get("type", "generic").lower()

        if not api_url or not api_token:
            log.warning("Ticketing API URL or token not configured")
            return False

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

        try:
            if api_type == "jira":
                # Jira transition to "Resolved"
                transition_url = f"{api_url}/rest/api/2/issue/{ticket_id}/transitions"
                # First get available transitions
                resp = requests.get(transition_url, headers=headers, timeout=10)
                if resp.status_code != 200:
                    log.error("Failed to get Jira transitions: %d", resp.status_code)
                    return False

                transitions = resp.json().get("transitions", [])
                resolved_id = None
                for t in transitions:
                    if t.get("name", "").lower() in ("resolved", "done", "closed"):
                        resolved_id = t.get("id")
                        break

                if not resolved_id:
                    log.warning("Could not find 'Resolved' transition for Jira ticket %s", ticket_id)
                    return False

                # Apply transition
                resp = requests.post(
                    transition_url,
                    headers=headers,
                    json={"transition": {"id": resolved_id}},
                    timeout=10,
                )

                if resp.status_code in (200, 204):
                    log.info("Jira ticket %s resolved", ticket_id)
                    return True
                else:
                    log.error("Failed to resolve Jira ticket: %d", resp.status_code)
                    return False

            else:
                # Generic API - POST resolution
                resp = requests.post(
                    f"{api_url}/tickets/{ticket_id}/resolve",
                    headers=headers,
                    json={
                        "status": "resolved",
                        "resolution_notes": incident_data.get("resolution", ""),
                        "resolved_at": datetime.now().isoformat(),
                    },
                    timeout=10,
                )

                if resp.status_code in (200, 202):
                    log.info("Ticket %s resolved via API", ticket_id)
                    return True
                else:
                    log.error("Failed to resolve ticket: %d", resp.status_code)
                    return False

        except requests.exceptions.Timeout:
            log.error("Ticketing API request timed out")
            return False
        except Exception as e:
            log.error("Error resolving ticket: %s", e)
            return False

    def _create_post_mortem(self, incident_data: dict) -> tuple:
        """Generate a post-mortem Markdown document for critical incidents."""
        try:
            output_dir = "output/post_mortems"
            os.makedirs(output_dir, exist_ok=True)

            inc_id = incident_data.get("incident_id", "UNKNOWN")
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"postmortem_{inc_id}_{date_str}.md"
            filepath = os.path.join(output_dir, filename)

            content = self._generate_post_mortem_content(incident_data)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            log.info("Post-mortem created: %s", filepath)
            return True, filepath
        except Exception as e:
            log.error("Failed to create post-mortem: %s", e)
            return False, None

    def _generate_post_mortem_content(self, data: dict) -> str:
        """Generate post-mortem Markdown content from incident data."""
        inc_id = data.get("incident_id", "N/A")
        title = data.get("title", "Untitled incident")
        date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
        severity = data.get("severity", "unknown")
        server = data.get("server", "unknown")
        ttr = data.get("time_to_resolve", "unknown")
        root_cause = data.get("root_cause", "TBD")
        resolution = data.get("resolution", "TBD")
        follow_up = data.get("follow_up", "TBD")
        sop_used = data.get("sop_used", "N/A")
        symptoms = data.get("symptoms", [])
        diagnosis_cmds = data.get("diagnosis_commands_run", [])
        signatures = data.get("pattern_signatures", [])

        symptoms_text = "\n".join(f"- {s}" for s in symptoms) if symptoms else "- TBD"
        cmds_text = "\n".join(f"  - `{c}`" for c in diagnosis_cmds) if diagnosis_cmds else "  - TBD"
        sigs_text = ", ".join(signatures) if signatures else "N/A"

        return f"""# Post-Mortem: {title}

**Incident ID:** {inc_id}
**Date:** {date}
**Severity:** {severity}
**Server:** {server}
**Time to resolve:** {ttr}
**SOP used:** {sop_used}

---

## Summary

{root_cause}

## Symptoms

{symptoms_text}

## Timeline

- **Detection:** {date} - Alert received and agent started processing
- **Diagnosis:** Automated diagnostic checks executed
- **Resolution:** {resolution}

## Root cause

{root_cause}

## Resolution applied

{resolution}

## Diagnosis commands run

{cmds_text}

## Pattern signatures (for future matching)

{sigs_text}

## Follow-up actions

{follow_up}

## Lessons learned

- _To be filled in by team lead after review_
- What went well:
- What went wrong:
- Where we got lucky:
- What we would do differently:

---

_Generated automatically by The Workplace Brain on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}_
"""

    def _extract_signatures(self, text: str) -> list:
        """Extract key pattern signatures from incident text for future matching."""
        import re
        # Common error keywords
        keywords = re.findall(
            r'\b(?:error|fail|crash|critical|panic|oom|killed|denied|timeout|refused|disk|memory|cpu|ssh|nginx|postgres|docker|service|process)\w*\b',
            text.lower()
        )
        # Deduplicate and return top 5
        seen = []
        for kw in keywords:
            if kw not in seen and len(kw) > 3:
                seen.append(kw)
            if len(seen) >= 5:
                break
        return seen
