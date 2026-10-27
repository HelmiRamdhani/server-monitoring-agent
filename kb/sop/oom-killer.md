# SOP: Out of Memory (OOM) Killer

## Metadata
- **ID:** sop-oom-killer
- **Triggers:** out of memory, oom-killer, oom_kill, killed process, cannot allocate memory
- **Severity:** critical
- **Last updated:** 2026-10-23

## Symptoms
- syslog contains "Out of memory" or "Killed process" entries
- Server becomes unresponsive or services crash unexpectedly
- High memory utilization before the OOM event
- dmesg shows oom-killer invocation traces

## Diagnosis steps
1. Check current memory: `free -h` and `vmstat 1 5`
2. Find top memory consumers: `ps aux --sort=-%mem | head -15`
3. Check dmesg for OOM details: `dmesg -T | grep -i "out of memory" | tail -20`
4. Check if swap is configured: `swapon --show`
5. Review system memory limits: `cat /proc/meminfo | grep -E "MemTotal|MemFree|SwapTotal|SwapFree"`

## Remediation
1. **Immediate:** Identify and restart killed service: `systemctl restart <service>`
2. **Short-term:**
   - Kill rogue processes: `kill -9 <PID>` (only if confirmed non-essential)
   - Clear page cache: `echo 1 > /proc/sys/vm/drop_caches` (temporary relief)
   - Add emergency swap: `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`
3. **Long-term:**
   - Tune OOM scores: `echo -1000 > /proc/<PID>/oom_score_adj` (protect critical services)
   - Configure `vm.overcommit_memory = 2` in `/etc/sysctl.conf`
   - Upgrade server RAM or add more instances behind load balancer
   - Review application memory leaks

## Escalation
- If OOM recurs within 24h after remediation, escalate to application team
- If multiple services affected, consider failover to standby server

## Post-incident
- Document which process was killed and by how much memory was exceeded
- Record memory snapshot for trend analysis
- Update memory thresholds in monitoring config if needed
