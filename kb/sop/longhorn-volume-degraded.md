# SOP: Longhorn Distributed Storage Volume Degraded

## Metadata
- **ID:** sop-longhorn-volume-degraded
- **Triggers:** LonghornVolumeDegraded, volume degraded, replica faulted, longhorn replica, storage degraded
- **Severity:** critical
- **Last updated:** 2026-10-26

## Symptoms
- Alert `LonghornVolumeDegraded` firing in Prometheus / Alertmanager
- One or more volume replicas in Longhorn dashboard show `Faulted` or `Rebuilding`
- PV read/write latency spikes or I/O wait on affected pods increases

## Diagnosis steps
1. Check Longhorn volume status via CLI or UI:
   `kubectl get volumes.longhorn.io -n longhorn-system <volume-name> -o yaml | grep state`
2. Check replica status across nodes:
   `kubectl get replicas.longhorn.io -n longhorn-system -l longhornvolume=<volume-name>`
3. Check target node disk space:
   `kubectl describe nodes <node-name> | grep -A 5 "Allocated resources"`
4. Check Longhorn manager pod logs:
   `kubectl logs -n longhorn-system -l app=longhorn-manager --tail=100 | grep -i "error"`

## Remediation
1. **Immediate:**
   - Verify if healthy replicas remain (minimum 1 healthy replica to prevent read-only mode)
   - Allow Longhorn auto-rebuilding to provision a replacement replica on another healthy node
2. **Short-term:**
   - If node disk is full, clean evicted pod caches or expand disk
   - Restart affected replica pod if stuck in rebuilding:
     `kubectl delete pod -n longhorn-system -l longhornvolume=<volume-name>`
3. **Long-term:**
   - Review replica count settings (standard is 3 replicas across different racks/nodes)
   - Enable Longhorn recurring volume snapshots and S3/NFS backup schedule

## Escalation
- If volume enters `Faulted` status (all replicas lost), immediately escalate to Infrastructure Storage Lead
- Halt write workloads to prevent filesystem corruption

## Post-incident
- Verify all 3 replicas return to `Healthy` state
- Run filesystem check `e2fsck` / `xfs_repair` if ungraceful detachment occurred
- Document incident in knowledge base

