# SOP: Kernel Panic

## Metadata
- **ID:** sop-kernel-panic
- **Triggers:** kernel panic, not syncing, BUG: unable to handle
- **Severity:** critical
- **Last updated:** 2026-10-23

## Symptoms
- syslog shows "kernel panic" or "not syncing" messages
- Server becomes completely unresponsive
- Network connectivity lost
- Console shows panic stack trace
- System rebooted unexpectedly (check uptime)

## Diagnosis steps (after reboot or from console)
1. Check if system recovered: `uptime` and `dmesg | grep -i panic | tail -20`
2. Review last messages before crash: `journalctl --boot=-1 -p err --no-pager | tail -50`
3. Check for hardware errors: `dmesg | grep -iE "mce|hardware error|ecc|I/O error" | tail -20`
4. Review kernel logs: `journalctl -k --since "1 hour ago" --no-pager`
5. Check for recent kernel updates: `rpm -qa --last kernel` or `dpkg -l | grep linux-image`
6. Verify filesystem integrity: `dmesg | grep -i "ext4\|xfs\|filesystem" | grep -i error`

## Remediation
1. **Immediate:**
   - If server is hung, force reboot via IPMI/iLO/console
   - After reboot, verify all services started: `systemctl --failed`
   - Check if previous kernel version is available: boot into older kernel if crash recurs
2. **Short-term:**
   - Disable suspect kernel modules if identified: blacklist in `/etc/modprobe.d/`
   - If hardware error suspected, run diagnostics: `memtest86`, `smartctl -a /dev/sda`
   - Apply kernel patches if available
3. **Long-term:**
   - Configure kernel crash dump (kdump) for future analysis
   - Review and update firmware/BIOS
   - Plan hardware replacement if recurring hardware errors

## Escalation
- Kernel panic always escalates to senior infra engineer
- If hardware error confirmed, engage hardware vendor support
- If production server, initiate failover immediately

## Post-incident
- Capture full panic stack trace
- Check if known kernel bug: search kernel bugzilla / mailing list
- Document whether kernel update was the trigger
- Verify kdump is configured for future incidents
