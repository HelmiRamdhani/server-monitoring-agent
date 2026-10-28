# SOP: Service APM Latency & SLO Error Budget Degradation

## Metadata
- **ID:** sop-service-slo-latency-degraded
- **Triggers:** opentelemetry, otel, latency, slo, burnrate, burn rate, p99, 5xx, service degraded
- **Severity:** critical
- **Last updated:** 2026-10-28
- **Escalation Target:** platform-bigdata-sre

## Symptoms
- OpenTelemetry traces indicate service latency $p99$ exceeds SLO objective ($>200\text{ ms}$).
- Elevated HTTP 5xx error rate ($>1.0\%$) or service throughput degradation.
- Multi-window Error Budget Burn Rate exceeds $14.4\times$ (P1 SRE incident).

## Diagnosis steps
1. **Analisis Distributed Trace (OpenTelemetry Call Graph)**:
   - Query OTLP traces to find the critical path bottleneck:
     `otel-collector query traces --service <service>`
   - Inspect downstream child spans (SQL queries, gRPC calls, Redis latency).
2. **Inspeksi Metrik Host & Pod**:
   - Check CPU throttling: `kubectl top pod -l app=<service> -n platform-bigdata`
   - Check container memory working set against `resources.limits.memory`.
3. **Pemeriksaan eBPF Kernel Network**:
   - Trace TCP retransmissions: `bpftrace -e 'tracepoint:tcp:tcp_retransmit_skb'`

## Remediation
1. **Immediate (Traffic Spike):**
   - Scale deployment replicas: `kubectl scale deployment <service-name> --replicas=<num> -n platform-bigdata`
2. **Short-term (Container Stalled / Lock):**
   - Use the Telegram ChatOps `[Restart Pod]` action button to perform safe rolling restart.
3. **Downstream Database Bottleneck:**
   - Enable circuit breaker or rate limiting on caller service to prevent cascading failures.

