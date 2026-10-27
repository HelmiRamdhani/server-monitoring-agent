# SOP: SSH Brute Force Attack

## Metadata
- **ID:** sop-ssh-brute-force
- **Triggers:** failed password, invalid user, sshd, authentication failure
- **Severity:** warning -> critical (if >10 attempts in 5 min)
- **Last updated:** 2026-10-23

## Symptoms
- syslog shows repeated "Failed password" or "Invalid user" entries from same IP
- `/var/log/auth.log` contains multiple sshd authentication failures
- Possibly accompanied by high CPU from sshd processes

## Diagnosis steps
1. Check failed login count: `grep "Failed password" /var/log/auth.log | wc -l`
2. Identify source IPs: `grep "Failed password" /var/log/auth.log | awk '{print $(NF-3)}' | sort | uniq -c | sort -rn | head -20`
3. Check if fail2ban is running: `systemctl status fail2ban`
4. Verify SSH config: `sshd -T | grep -E "maxauthtries|permitrootlogin|passwordauthentication"`

## Remediation
1. **Immediate:** Block offending IP: `iptables -A INPUT -s <IP> -j DROP`
2. **Short-term:** Enable/adjust fail2ban: `systemctl enable fail2ban && systemctl start fail2ban`
3. **Hardening:**
   - Set `MaxAuthTries 3` in `/etc/ssh/sshd_config`
   - Set `PermitRootLogin no`
   - Consider key-based auth only: `PasswordAuthentication no`
4. **Monitor:** Watch for recurrence in next 30 minutes

## Escalation
- If attacks persist after blocking, escalate to network team to block at firewall level
- If unauthorized access detected (successful login from attacking IP), trigger incident response SOP

## Post-incident
- Document attacker IPs in incident history
- Review fail2ban configuration
- Consider adding IP to permanent blocklist
