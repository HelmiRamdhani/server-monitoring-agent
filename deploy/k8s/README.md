# Panduan Deployment Server Monitoring Agent ke Kubernetes

Panduan ini menjelaskan langkah deployment agent ke kluster Kubernetes **Platform Bigdata**.

---

### 📦 1. Build & Push Image Container (ke Harbor / Internal Registry)

```bash
# Build image
docker build -t harbor.internal/platform-bigdata/server-monitoring-agent:v1.0.0 .

# Push image ke registry internal
docker push harbor.internal/platform-bigdata/server-monitoring-agent:v1.0.0
```

---

### ☸️ 2. Deploy ke Kluster Kubernetes

Jalankan perintah berikut menggunakan `kubectl`:

```bash
# Buat namespace jika belum ada
kubectl create namespace monitoring

# 1. Apply RBAC (ServiceAccount & ClusterRole Reader)
kubectl apply -f deploy/k8s/01-rbac.yaml

# 2. Apply ConfigMap
kubectl apply -f deploy/k8s/02-configmap.yaml

# 3. Apply Deployment
kubectl apply -f deploy/k8s/03-deployment.yaml

# 4. Apply Service ClusterIP
kubectl apply -f deploy/k8s/04-service.yaml
```

Verifikasi pod berjalan:
```bash
kubectl get pods -n monitoring -l app=server-monitoring-agent
kubectl logs -n monitoring -l app=server-monitoring-agent -f
```

---

### 🔔 3. Hubungkan Prometheus Alertmanager

Buka file konfigurasi `alertmanager.yml` di kluster Anda, lalu masukkan konfigurasi dari file:
[`deploy/k8s/05-alertmanager-config.yaml`](./05-alertmanager-config.yaml)

URL webhook internal kluster:
```
http://server-monitoring-agent.monitoring.svc.cluster.local:8080/webhook/prometheus
```

Begitu konfigurasi di-reload (`curl -X POST http://alertmanager:9093/-/reload`), setiap ada alert firing di kluster, Alertmanager akan langsung mengirimkan notifikasi ke agent, dan agent akan otomatis melakukan investigasi serta men-generate laporan insiden.

