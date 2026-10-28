# Server Monitoring Agent & Incident Co-Pilot
**Platform Bigdata — Enterprise Multilayer Observability (Observe → Reason → Act)**

Platform AIOps Incident Co-Pilot enterprise yang mengintegrasikan seluruh layer infrastruktur: **Host/VM** (psutil & syslog), **Container** (cgroup & Docker), **Kubernetes Pod** (CrashLoop, previous logs & events), **Distributed Storage** (Longhorn volume integrity), dan **Service APM** (OpenTelemetry traces p99, Google SRE SLI/SLO burn rate, serta eBPF kernel probes). Terhubung langsung dengan Telegram ChatOps interaktif (@hlm_alert_bot).

## Arsitektur Komponen

```
Ingress (Webhook / Polling) → Knowledge Base SOP → Multilayer Diagnosis (18 Checks) → AI RCA → Delivery (PDF & Telegram ChatOps) → Feedback Loop
```

| Komponen | File | Deskripsi |
|----------|------|-----------|
| Config loader | `src/modules/config_loader.py` | Load YAML config + setup logging |
| Server monitor | `src/modules/server_monitor.py` | Kumpulkan metrik via psutil (CPU, RAM, Disk, Uptime) |
| Syslog parser | `src/modules/syslog_parser.py` | Baca syslog lokal + regex pattern matching |
| Knowledge Base | `src/modules/knowledge_base.py` | Repositori 8 SOP Markdown, topologi & histori insiden |
| Diagnosis engine | `src/modules/diagnosis_engine.py` | 18 pemeriksaan read-only lintas seluruh layer |
| K8s diagnostics | `src/modules/k8s_diagnostics.py` | Pod crash logs (--previous), events probe & restart pod |
| APM & OTel engine | `src/modules/apm_otel_diagnostics.py` | OTel traces p99, SRE SLO burn rate (14.4x), eBPF probes |
| Webhook receiver | `src/modules/webhook_receiver.py` | HTTP Ingress 8080 (Prometheus, Zabbix, Jira, OTLP) |
| Feedback loop | `src/modules/feedback_loop.py` | Audit trail insiden, resolusi tiket & update KB |
| Report generator | `src/modules/report_generator.py` | Generate PDF Snapshot, Weekly & Monthly ReportLab |
| Notifier | `src/modules/notifier.py` | Kirim Telegram ChatOps (@hlm_alert_bot), Email & Teams |
| Main agent | `src/main.py` | Orkestrasi alur kerja 6-tahap |

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Konfigurasi

Copy config example dan edit:

```bash
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml`:

```yaml
server:
  host: "localhost"
  label: "Server-01"

thresholds:
  cpu_warning: 75
  cpu_critical: 90
  memory_warning: 80
  memory_critical: 92
  disk_warning: 80
  disk_critical: 90

syslog:
  log_files:
    - "/var/log/syslog"
    - "/var/log/auth.log"
  tail_lines: 500
  patterns:
    - name: "SSH failed login"
      regex: "Failed password|Invalid user"
      severity: "warning"

email:
  enabled: true
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  smtp_user: "your-email@gmail.com"
  smtp_password: "your-app-password"
  from_addr: "your-email@gmail.com"
  to_addrs:
    - "ops-team@company.com"

teams:
  enabled: true
  webhook_url: "https://your-tenant.webhook.office.com/..."
```

### 3. Jalankan agent

**Run sekali:**

```bash
python src/main.py
```

**Run dengan config custom:**

```bash
python src/main.py --config /path/to/config.yaml
```

**Run continuous (scheduled):**

```bash
python src/main.py --loop
```

Agent akan jalan setiap `interval_minutes` (default 30 menit) dan terus loop sampai dihentikan dengan Ctrl+C.

**Run laporan berkala (Weekly / Monthly):**

```bash
# Laporan Mingguan (agregasi 7 hari terakhir + KPI & SLA)
python src/main.py --report-period weekly

# Laporan Bulanan (agregasi 30 hari terakhir + KPI & SLA)
python src/main.py --report-period monthly
```

**Run built-in scheduler untuk laporan berkala:**

```bash
python src/main.py --schedule-reports
```

Agent akan otomatis menjadwalkan laporan mingguan setiap hari Senin jam 08:00 dan laporan bulanan setiap tanggal 1 jam 07:00.

**Run event-driven webhook server (Prometheus / Zabbix / Jira):**

```bash
python src/main.py --webhook
```

---

## Setup Cron Job / Task Scheduler untuk Laporan Berkala

### 1. Linux Crontab (`crontab -e`)

```bash
# Laporan MINGGUAN: Setiap hari Senin jam 08:00 pagi
0 8 * * 1 cd /path/to/server-monitoring-agent && /usr/bin/python3 src/main.py --report-period weekly >> output/cron_weekly.log 2>&1

# Laporan BULANAN: Setiap tanggal 1 jam 07:00 pagi
0 7 1 * * cd /path/to/server-monitoring-agent && /usr/bin/python3 src/main.py --report-period monthly >> output/cron_monthly.log 2>&1
```

### 2. Windows Task Scheduler (PowerShell)

```powershell
# Jadwal Mingguan (Setiap Senin jam 08:00)
$ActionWeekly = New-ScheduledTaskAction -Execute "python.exe" `
    -Argument "src/main.py --report-period weekly" `
    -WorkingDirectory "C:\path\to\server-monitoring-agent"
$TriggerWeekly = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "08:00AM"
Register-ScheduledTask -TaskName "ServerMonitoring_WeeklyReport" -Action $ActionWeekly -Trigger $TriggerWeekly

# Jadwal Bulanan (Tanggal 1 setiap bulan jam 07:00)
$ActionMonthly = New-ScheduledTaskAction -Execute "python.exe" `
    -Argument "src/main.py --report-period monthly" `
    -WorkingDirectory "C:\path\to\server-monitoring-agent"
$TriggerMonthly = New-ScheduledTaskTrigger -Daily -At "07:00AM"
Register-ScheduledTask -TaskName "ServerMonitoring_MonthlyReport" -Action $ActionMonthly -Trigger $TriggerMonthly
```

## Log file patterns

Agent sudah pre-configure beberapa pattern insiden:

| Pattern | Severity | Contoh log |
|---------|----------|-----------|
| SSH failed login | warning | `Failed password for root from 1.2.3.4` |
| Service crash | critical | `segfault at ... core dumped` |
| Out of memory | critical | `Out of memory: Kill process ...` |
| Disk full | critical | `No space left on device` |
| Kernel panic | critical | `kernel panic - not syncing` |
| Connection refused | warning | `Connection refused` |
| General error | error | `[ERROR] ...` |

Tambahkan pattern sendiri di `config.yaml` di bawah `syslog.patterns`.

## Notifikasi Telegram (ChatOps Bot)

Agent dilengkapi dengan integrasi Telegram Bot interaktif (format alert enterprise Clarissa-style dengan 4 tombol inline keyboard untuk mitigasi cepat).

Panduan lengkap setup bot dan chat ID:
👉 [Panduan Setup Notifikasi Telegram](docs/TELEGRAM_SETUP_GUIDE.md)

Uji coba notifikasi:
```bash
python scripts/test_telegram_bot.py --mock
```

## Output

- **PDF report**: `output/report_YYYYMMDD_HHMMSS.pdf`
- **Agent log**: `output/agent.log`

Report PDF berisi:
1. Header dengan timestamp dan nama tim
2. Informasi server (hostname, OS, uptime, cores, total memory/disk)
3. Tabel metrik dengan status (OK / WARNING / CRITICAL)
4. Tabel alert threshold
5. Ringkasan insiden dari syslog (total, per severity, per kategori)
6. Detail top 10 insiden kritis

## Windows notes

Pada Windows, syslog diganti dengan Event Log. Untuk membaca Event Log, install tambahan:

```bash
pip install python-win32
```

Dan ubah log file path di config ke Event Log source. Atau gunakan tools seperti `wevtutil` untuk export ke text lalu di-parse.

## License

MIT - Bebas digunakan dan dimodifikasi.
