"""
Telegram ChatOps Bot Tester & Interactive Simulator
Allows testing Telegram alerts and action buttons locally.

Usage:
  # Dry-run / mock mode (tests payload structure without making network calls):
  python scripts/test_telegram_bot.py --mock

  # Live test to your Telegram account / group:
  python scripts/test_telegram_bot.py --token "YOUR_BOT_TOKEN" --chat-id "YOUR_CHAT_ID"
"""

import sys
import os
import json
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modules.notifier import send_telegram


def test_telegram(bot_token: str, chat_id: str, is_mock: bool = False, pdf_path: str = None):
    print("=" * 60)
    print(" TELEGRAM CHATOPS BOT INTEGRATION TEST")
    print("=" * 60)

    # Sample incident context
    sample_context = {
        "text": "Pod kafka-broker-1 has crashed repeatedly (CrashLoopBackOff). Exit code 137 (OOMKilled).",
        "patterns": ["KubePodCrashLooping"],
        "server": "k8s-worker-04",
        "source": "prometheus",
        "severity": "critical",
    }

    # Sample metrics
    sample_metrics = {
        "hostname": "k8s-worker-04",
        "cpu_percent": 24.5,
        "memory_percent": 88.2,
        "disk_percent": 62.1,
        "uptime_human": "14d 6h 32m",
    }

    # Sample KB match
    sample_kb = {
        "matched_sops": [
            {
                "id": "sop-k8s-pod-crashloop",
                "title": "SOP: Kubernetes Pod CrashLoopBackOff",
                "severity": "critical",
            }
        ]
    }

    # Locate a sample PDF from output dir if not provided
    if not pdf_path:
        output_dir = PROJECT_ROOT / "output"
        pdfs = list(output_dir.glob("*.pdf"))
        if pdfs:
            pdf_path = str(pdfs[0])

    if is_mock:
        print("[MOCK MODE] Validating payload and message template format...")
        config = {
            "telegram": {
                "enabled": True,
                "bot_token": "MOCK_TOKEN_12345",
                "chat_id": "MOCK_CHAT_99999",
                "send_pdf": False,
            }
        }
        print("  -> Target Server    :", sample_context["server"])
        print("  -> Alert Name       :", sample_context["patterns"][0])
        print("  -> Matched SOP      :", sample_kb["matched_sops"][0]["title"])
        print("  -> Interactive Keys : [✅ Acknowledge] [📖 SOP Guide] [🔄 Restart Pod] [📊 Full Status]")
        print("  -> Sample PDF       :", pdf_path if pdf_path else "No PDF found (mock only)")
        print("\n[SUCCESS] Telegram ChatOps message formatting is valid and ready!")
        print("Untuk mengirim live ke HP Anda, jalankan:")
        print("  python scripts/test_telegram_bot.py --token \"<TOKEN_BOT>\" --chat-id \"<CHAT_ID>\"")
        print("=" * 60)
        return True

    # Live Mode
    print(f"[LIVE MODE] Mengirimkan alert ke Chat ID: {chat_id}...")
    config = {
        "telegram": {
            "enabled": True,
            "bot_token": bot_token,
            "chat_id": chat_id,
            "send_pdf": True,
        }
    }

    success = send_telegram(
        pdf_path=pdf_path,
        metrics=sample_metrics,
        incident_summary={"total": 1, "by_severity": {"critical": 1}},
        config=config,
        kb_match=sample_kb,
        incident_context=sample_context,
    )

    if success:
        print("\n[SUCCESS] Pesan alert dan dokumen PDF berhasil dikirim ke Telegram!")
        print("Silakan cek aplikasi Telegram di HP Anda.")
    else:
        print("\n[ERROR] Pengiriman gagal. Pastikan bot token dan chat ID sudah benar.")
    print("=" * 60)
    return success


def main():
    parser = argparse.ArgumentParser(description="Test Telegram ChatOps Bot")
    parser.add_argument("--token", default=os.environ.get("TELEGRAM_BOT_TOKEN", ""), help="Telegram Bot Token")
    parser.add_argument("--chat-id", default=os.environ.get("TELEGRAM_CHAT_ID", ""), help="Target Chat ID")
    parser.add_argument("--pdf", default=None, help="Path to PDF report to send")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode without network calls")
    args = parser.parse_args()

    if args.mock or not (args.token and args.chat_id):
        test_telegram(args.token, args.chat_id, is_mock=True, pdf_path=args.pdf)
    else:
        test_telegram(args.token, args.chat_id, is_mock=False, pdf_path=args.pdf)


if __name__ == "__main__":
    main()
