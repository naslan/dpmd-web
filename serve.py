"""Menjalankan website DPMD dengan waitress (cocok untuk Windows maupun Linux).

Jalankan:  python serve.py
Pengaturan opsional lewat variabel lingkungan: HOST (bawaan 127.0.0.1), PORT (bawaan 8000).
Gunakan HOST=0.0.0.0 bila server harus menerima akses langsung dari jaringan.
"""
import os

from waitress import serve

from app import app

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"DPMD berjalan di http://{host}:{port}  (hentikan dengan Ctrl+C)")
    serve(app, host=host, port=port, threads=4, max_request_body_size=26 * 1024 * 1024)
