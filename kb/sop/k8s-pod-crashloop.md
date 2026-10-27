# SOP: Kubernetes Pod CrashLoopBackOff

## Metadata
- **ID:** sop-k8s-pod-crashloop
- **Triggers:** CrashLoopBackOff, pod crashed, KubePodCrashLooping, container terminated, back-off restarting failed container, exit code 137
- **Severity:** critical
- **Last updated:** 2026-10-26

## Symptoms
- Prometheus alert `KubePodCrashLooping` is firing
- Pod status shows `CrashLoopBackOff` or high restart count (`RESTARTS > 5`)
- Microservice endpoints return 502 Bad Gateway or 503 Service Unavailable
- Big data pipeline consumer group lag increases

## Diagnosis steps
1. Check pod status and restart count:
   `kubectl get pods -n <namespace> -l app=<app-name> -o wide`
2. Inspect pod termination reason and exit code:
   `kubectl describe pod <pod-name> -n <namespace>`
3. Check previous container logs before the crash:
   `kubectl logs <pod-name> -n <namespace> --previous --tail=100`
4. Check recent Kubernetes events for OOM or Eviction:
   `kubectl get events -n <namespace> --sort-by='.metadata.creationTimestamp' | tail -25`
5. Inspect node resource pressure on host where pod was scheduled:
   `kubectl describe node <node-name> | grep -A 5 Conditions`

## Remediation
1. **If Exit Code 137 (OOMKilled):**
   - Increase memory limits in deployment manifest:
     `kubectl set resources deployment/<deployment-name> -n <namespace> --limits=memory=4Gi --requests=memory=2Gi`
   - Trigger rolling update:
     `kubectl rollout restart deployment/<deployment-name> -n <namespace>`
2. **If Exit Code 1 or Configuration Error:**
   - Verify environment variables, mounted ConfigMaps, and Secrets
   - Rollback to previous stable revision:
     `kubectl rollout undo deployment/<deployment-name> -n <namespace>`
3. **If Storage / PVC Lock:**
   - Verify PVC volume attachment in Longhorn UI or via kubectl
   - Delete stuck pod to force reschedule: `kubectl delete pod <pod-name> -n <namespace> --grace-period=0 --force`

## Escalation
- If pod continues crashing across multiple nodes, escalate to Platform / Big Data Engineering team
- Escalate to Application Owner if application configuration or schema migration caused fatal startup crash

## Post-incident
- Record pod restart history and root cause in incident log
- Verify Prometheus alert resolves (`resolved` status received)
- Add memory usage alerting at 80% to avoid sudden OOMKilled events

