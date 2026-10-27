# SOP: Service Crash

## Metadata
- **ID:** sop-service-crash
- **Triggers:** segfault, core dumped, killed process, service failed, crashed
- **Severity:** critical
- **Last updated:** 2026-10-23

## Symptoms
- syslog shows "segfault" or "core dumped" messages
- Service status shows as failed: `systemctl status <service>` returns failed
- Application endpoints returning errors or timing out
- Possible cascading failures on dependent services

## Diagnosis steps
1. Check service status: `systemctl status <service>` and `journalctl -u <service> --since "30 min ago"`
2. Check for core dumps: `coredumpctl list` (if systemd-coredump is installed)
3. Review recent logs: `journalctl -u <service> -n 100 --no-pager`
4. Check system resources at crash time: `dmesg | grep -i "killed\|oom\|segfault" | tail -20`
5. Verify service dependencies: `systemctl list-dependencies <service>`
6. Check for recent config changes: `find /etc -newer /tmp/marker -name "*.conf" 2>/dev/null`

## Remediation
1. **Immediate:**
   - Restart service: `systemctl restart <service>`
   - Verify it stays up: `systemctl status <service>` (wait 60 seconds)
   - If crashes repeatedly, stop: `systemctl stop <service>` to prevent crash loop
2. **Short-term:**
   - Rollback recent changes if identified: `git -C /etc checkout <previous_commit>` (if etc in git)
   - Check for corrupted config: `<service> --test-config` or equivalent
   - Clear corrupted cache/data if applicable
3. **Long-term:**
   - Configure auto-restart with backoff in systemd unit file
   - Set up crash dump collection for analysis
   - Review and fix root cause from core dump analysis
   - Add health check endpoint and auto-restart on failure

## Escalation
- If service crashes more than 3 times in 10 min, escalate to on-call engineer
- If critical business service, initiate failover to standby
- If root cause is infrastructure (storage, network), engage infra team

## Post-incident
- Analyze core dump if available (gdb /addr2line)
- Document what triggered the crash (config change, deploy, resource exhaustion)
- Add crash signature to incident history for future pattern matching
- Verify service stability for at least 1 hour
