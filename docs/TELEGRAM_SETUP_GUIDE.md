# Panduan Setup Notifikasi Telegram (Telegram ChatOps Bot)
**Platform Bigdata — Server Monitoring Agent & Incident Co-Pilot**

Dokumen ini berisi panduan langkah demi langkah untuk mengonfigurasi notifikasi Telegram bot interaktif untuk monitoring server dan alert insiden.

---

## 1. Buat Telegram Bot & Dapatkan `bot_token`

1. Buka aplikasi Telegram di HP atau Desktop.
2. Cari akun resmi **`@BotFather`** (dengan centang biru verified).
3. Ketik perintah:
   ```text
   /newbot
   ```
4. Masukkan **Nama Tampilan Bot** (contoh: `Platform Bigdata Monitoring Bot`).
5. Masukkan **Username Bot** yang berakhiran `bot` (contoh: `platform_bigdata_alert_bot`).
6. BotFather akan memberikan **HTTP API Token**. Simpan token ini dengan aman.
   *Contoh token:* `8626517356:AAEPp5x9DdHC1YAbw0c8eCVjm7HTo6C7FaU`

> **PENTING:** Buka bot baru Anda di Telegram, lalu klik tombol **START** (atau ketik `/start`). Jika bot belum di-start oleh Anda, bot tidak diizinkan oleh Telegram untuk mengirim pesan ke Anda.

---

## 2. Dapatkan `chat_id` (Akun Pribadi atau Grup Tim Ops)

### Opsi A: Untuk Notifikasi ke Akun Pribadi
1. Di Telegram, cari bot **`@getmyid_bot`** atau **`@userinfobot`**.
2. Klik **Start**.
3. Bot akan menampilkan `Your user ID:` (contoh: `6622084716`). Angka ini adalah `chat_id` Anda.

### Opsi B: Untuk Notifikasi ke Grup Tim Ops
1. Buat Grup Telegram baru atau buka grup yang sudah ada.
2. Undang (Invite) bot Anda ke dalam grup tersebut.
3. Undang juga bot **`@getmyid_bot`** ke dalam grup.
4. Perhatikan baris `Current chat ID:` yang biasanya diawali tanda minus `-` (contoh: `-1002345678901`).
5. Hapus `@getmyid_bot` dari grup setelah mendapatkan ID.

---

## 3. Konfigurasi di Monitoring Agent

Buka file konfigurasi **`config/config.yaml`**:

```yaml
telegram:
  enabled: true
  bot_token: "8626517356:AAEPp5x9DdHC1YAbw0c8eCVjm7HTo6C7FaU" # Ganti dengan bot_token Anda
  chat_id: "6622084716"                                      # Ganti dengan chat_id Anda
  send_pdf: false                                             # false = pure text Clarissa-style + tombol; true = kirim lampiran PDF
```

### Opsi Environment Variables (Deployment K8s / Docker / CI-CD)
Jika tidak ingin menuliskan token di file konfigurasi, Anda bisa menggunakan environment variable:
```bash
export TELEGRAM_BOT_TOKEN="8626517356:AAEPp5x9DdHC1YAbw0c8eCVjm7HTo6C7FaU"
export TELEGRAM_CHAT_ID="6622084716"
```

---

## 4. Cara Uji Coba (Testing Script)

Tersedia script simulasi bawaan di `scripts/test_telegram_bot.py` untuk menguji koneksi dan format pesan:

### Live Test (Mengirim Langsung ke Akun/Grup Telegram):
```bash
python scripts/test_telegram_bot.py --token "BOT_TOKEN_ANDA" --chat-id "CHAT_ID_ANDA"
```

### Dry-Run / Mock Test (Tanpa Koneksi Internet / Offline):
```bash
python scripts/test_telegram_bot.py --mock
```

---

## 5. Fitur Pesan & Tombol Interaktif

Setiap insiden terdeteksi akan dikirim dengan format enterprise Clarissa-style:
- **Header:** Identitas `[PLATFORM BIGDATA] Incident Alert` dan timestamp WIB.
- **Context:** Node target, Incident ID, dan trigger error.
- **Diagnostic Snippet:** Blok kode `copy` yang memuat potongan log error riil (contoh: Longhorn replica faulted, OOM kill).
- **Matched SOP:** Tautan/referensi SOP Runbook otomatis dari Knowledge Base.
- **Host Telemetry:** Penggunaan CPU, RAM, Disk, dan Uptime server.
- **4 Tombol Inline Keyboard Interaktif:**
  1. `[Buka SOP Runbook]` → Menampilkan SOP penanganan insiden.
  2. `[Acknowledge]` → Menandai bahwa insiden sedang ditangani teknisi.
  3. `[Restart Pod]` → Eksekusi restart container/pod terkait.
  4. `[Full Telemetry]` → Menampilkan statistik lengkap server.

