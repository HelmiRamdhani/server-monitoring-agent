# SOP: Disk Full

## Metadata
- **ID:** sop-disk-full
- **Triggers:** no space left on device, disk full, write error, cannot write
- **Severity:** critical
- **Last updated:** 2026-10-23

## Symptoms
- syslog shows "No space left on device"
- Applications fail to write files or logs
- Database errors related to write failures
- Monitoring alerts on disk usage > 90%

## Diagnosis steps
1. Check disk usage: `df -h`
2. Find largest directories: `du -sh /var/log/* | sort -rh | head -10`
3. Find large files: `find / -type f -size +500M 2>/dev/null | head -20`
4. Check for deleted-but-open files: `lsof +L1 | head -20`
5. Check inode usage: `df -i`
6. Check log rotation: `logrotate -d /etc/logrotate.conf`

## Remediation
1. **Immediate:**
   - Clear old log files: `find /var/log -name "*.gz" -mtime +30 -delete`
   - Truncate large active logs: `truncate -s 0 /var/log/<large_file>.log`
   - Clear package cache: `apt-get clean` or `yum clean all`
   - Clear journal: `journalctl --vacuum-time=3d`
2. **Short-term:**
   - Compress old logs: `find /var/log -name "*.log" -mtime +7 -exec gzip {} \;`
   - Clear temp files: `rm -rf /tmp/* /var/tmp/*` (verify no active sessions)
   - Check and clear Docker: `docker system prune -a --volumes` (if applicable)
3. **Long-term:**
   - Configure proper log rotation in `/etc/logrotate.d/`
   - Set up automated cleanup cron job
   - Monitor disk growth trends and plan capacity upgrade
   - Separate log partition from root filesystem

## Escalation
- If disk keeps filling after cleanup, investigate runaway process writing logs
- If database partition full, escalate to DBA team immediately
- If root partition < 95% and no identifiable cause, escalate to infrastructure team

## Post-incident
- Record what consumed the disk space
- Verify log rotation is working properly
- Update disk monitoring thresholds if needed
