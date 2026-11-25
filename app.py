"""
Website Dinas Pemberdayaan Masyarakat dan Desa (DPMD)
Flask + SQLite. Menu: HOME, PROFIL, PPID PELAKSANA, APLIKASI, DOKUMENTASI, KONTAK.

Jalankan:  python app.py   (lalu buka http://127.0.0.1:5000)
Admin:     http://127.0.0.1:5000/admin
"""
import csv
import hashlib
import hmac
import io
import os
import re
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, Response, abort, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from qrsvg import qr_svg

# --------------------------------------------------------------------------
# PENGATURAN: ubah isi bagian ini sesuai data dinas Anda
# --------------------------------------------------------------------------
SITE = {
    "nama": "Dinas Pemberdayaan Masyarakat dan Desa",
    "singkatan": "DPMD",
    "daerah": "Pemerintah Provinsi Sulawesi Selatan",
    "alamat": "Jl. [Bontolangkasa] No. [7-9], [Rappocini], [Kota Makassar], [Kode Pos : 90222]",
    "telepon": "(0411) 873-836",
    "email": "dpmd@sulselprov.go.id",
    "jam": "Senin–Kamis 08.00–16.00, Jumat 08.00–16.30",
    "ppid_kontak": "ppid.dpmd@sulselprov.go.id",
}

PROFIL = {
    "tugas": (
        "Dinas Pemberdayaan Masyarakat dan Desa melaksanakan urusan pemerintahan "
        "di bidang pemberdayaan masyarakat dan desa, meliputi pembinaan pemerintahan "
        "desa, pengelolaan keuangan dan aset desa, kelembagaan dan kerja sama desa, "
        "serta pemberdayaan ekonomi dan sosial budaya masyarakat."
    ),
    "visi": "Terwujudnya desa yang mandiri, partisipatif, dan sejahtera.",
    "misi": [
        "Meningkatkan kapasitas pemerintah desa dalam perencanaan dan tata kelola.",
        "Mendorong transparansi dan akuntabilitas pengelolaan keuangan desa.",
        "Memperkuat kelembagaan masyarakat dan kerja sama antardesa.",
        "Menumbuhkan ekonomi desa melalui BUMDes dan usaha produktif warga.",
        "Menyediakan layanan informasi publik yang terbuka dan mudah diakses.",
    ],
    "bidang": [
        ("Sekretariat", "Perencanaan, keuangan, kepegawaian, umum, dan pelaporan dinas."),
        ("Bidang Pemerintahan Desa", "Pembinaan penyelenggaraan pemerintahan dan administrasi desa."),
        ("Bidang Keuangan dan Aset Desa", "Pendampingan APBDes, pelaporan, dan pengelolaan aset desa."),
        ("Bidang Kelembagaan dan Kerja Sama Desa", "Penguatan BPD, lembaga kemasyarakatan, dan kerja sama desa."),
        ("Bidang Pemberdayaan Masyarakat", "Pemberdayaan ekonomi, sosial budaya, dan teknologi tepat guna."),
    ],
}

KATEGORI = {
    "berkala": "Informasi Berkala",
    "serta-merta": "Informasi Serta Merta",
    "setiap-saat": "Informasi Setiap Saat",
}
KATEGORI_KET = {
    "berkala": "Diumumkan secara rutin, paling singkat 6 bulan sekali: laporan kinerja, laporan keuangan, program dan kegiatan.",
    "serta-merta": "Menyangkut hajat hidup orang banyak dan ketertiban umum; diumumkan segera, misalnya bencana atau gangguan layanan.",
    "setiap-saat": "Tersedia setiap saat dan dapat diminta kapan pun: daftar informasi publik, peraturan, perjanjian dengan pihak ketiga.",
}

EXT_DOKUMEN = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv", "zip"}
EXT_GAMBAR = {"jpg", "jpeg", "png", "webp"}

KATEGORI_PEMOHON = ["Perorangan", "Kelompok Orang", "Badan Hukum"]
CARA_MEMPEROLEH = [
    "Melihat, membaca, mendengarkan, atau mencatat",
    "Mengambil salinan langsung di kantor",
    "Salinan dikirim melalui email",
    "Salinan dikirim melalui pos",
    "Salinan dikirim melalui kurir",
]
STATUS_PERMOHONAN = ["Diterima", "Diproses", "Selesai", "Ditolak"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAGIC_GAMBAR = (b"\xff\xd8\xff", b"\x89PNG")
MAGIC_PDF = (b"%PDF",)
FILE_TEMPLATE = "form-permohonan-informasi.docx"  # letakkan di static/files/ (opsional)

# Media sosial yang dapat diubah admin: (kunci, label, contoh alamat)
SOSMED = [
    ("instagram", "Instagram", "https://www.instagram.com/namaakun"),
    ("facebook", "Facebook", "https://www.facebook.com/namahalaman"),
    ("twitter", "Twitter", "https://twitter.com/namaakun"),
    ("youtube", "YouTube", "https://www.youtube.com/@namakanal"),
    ("tiktok", "TikTok", "https://www.tiktok.com/@namaakun"),
]
MAGIC_FOTO = (b"\xff\xd8\xff", b"\x89PNG", b"RIFF")  # JPG, PNG, WebP
BERITA_PER_HALAMAN = 9

# Penghitung pengunjung: hanya halaman publik berikut yang dihitung (bukan admin, berkas, atau gambar).
HALAMAN_HITUNG = {"home", "profil", "ppid", "aplikasi", "dokumentasi", "kontak", "berita", "berita_detail",
                  "survei", "permohonan", "status_permohonan"}
BOT_RE = re.compile(r"bot|crawl|spider|slurp|headless|preview|monitor|uptime|pingdom|curl|wget|python-requests|"
                    r"httpclient|scrapy|facebookexternalhit|lighthouse|checker", re.I)
ONLINE_DETIK = 300  # dianggap "sedang online" bila aktif dalam 5 menit terakhir

# Survei Kepuasan Masyarakat (SKM) mengikuti 9 unsur pada Permenpan RB No. 14 Tahun 2017.
# Setiap pertanyaan punya 4 pilihan jawaban bernilai 1 sampai 4 (urut dari yang terendah).
SKM_UNSUR = [
    ("u1", "Persyaratan", "Bagaimana pendapat Saudara tentang kesesuaian persyaratan pelayanan dengan jenis pelayanannya?",
     ["Tidak sesuai", "Kurang sesuai", "Sesuai", "Sangat sesuai"]),
    ("u2", "Sistem, mekanisme, dan prosedur", "Bagaimana pemahaman Saudara tentang kemudahan prosedur pelayanan di unit ini?",
     ["Tidak mudah", "Kurang mudah", "Mudah", "Sangat mudah"]),
    ("u3", "Waktu penyelesaian", "Bagaimana pendapat Saudara tentang kecepatan waktu dalam memberikan pelayanan?",
     ["Tidak cepat", "Kurang cepat", "Cepat", "Sangat cepat"]),
    ("u4", "Biaya/tarif", "Bagaimana pendapat Saudara tentang kewajaran biaya/tarif dalam pelayanan?",
     ["Sangat mahal", "Cukup mahal", "Murah", "Gratis"]),
    ("u5", "Produk spesifikasi jenis pelayanan",
     "Bagaimana pendapat Saudara tentang kesesuaian produk pelayanan antara yang tercantum dalam standar pelayanan dengan hasil yang diberikan?",
     ["Tidak sesuai", "Kurang sesuai", "Sesuai", "Sangat sesuai"]),
    ("u6", "Kompetensi pelaksana", "Bagaimana pendapat Saudara tentang kompetensi/kemampuan petugas dalam pelayanan?",
     ["Tidak kompeten", "Kurang kompeten", "Kompeten", "Sangat kompeten"]),
    ("u7", "Perilaku pelaksana", "Bagaimana pendapat Saudara tentang perilaku petugas dalam pelayanan terkait kesopanan dan keramahan?",
     ["Tidak sopan dan ramah", "Kurang sopan dan ramah", "Sopan dan ramah", "Sangat sopan dan ramah"]),
    ("u8", "Penanganan pengaduan, saran, dan masukan", "Bagaimana pendapat Saudara tentang penanganan pengaduan pengguna layanan?",
     ["Tidak ada", "Ada tetapi tidak berfungsi", "Berfungsi kurang maksimal", "Dikelola dengan baik"]),
    ("u9", "Sarana dan prasarana", "Bagaimana pendapat Saudara tentang kualitas sarana dan prasarana?",
     ["Buruk", "Cukup", "Baik", "Sangat baik"]),
]
SKM_PROFIL = [  # (kolom, label, pilihan) - ubah daftar pilihan sesuai kebutuhan
    ("jk", "Jenis kelamin", ["Laki-laki", "Perempuan"]),
    ("umur", "Kelompok umur", ["Di bawah 20 tahun", "20-29 tahun", "30-39 tahun", "40-49 tahun", "50 tahun ke atas"]),
    ("pendidikan", "Pendidikan terakhir", ["SD", "SMP", "SMA/SMK", "D1-D3", "S1/D4", "S2/S3"]),
    ("pekerjaan", "Pekerjaan", ["PNS/TNI/Polri", "Pegawai swasta", "Wirausaha", "Pelajar/Mahasiswa",
                                "Aparatur/perangkat desa", "Lainnya"]),
    ("layanan", "Jenis layanan yang diterima", ["Informasi publik (PPID)", "Pembinaan dan pendampingan desa",
                                                 "Konsultasi atau pengaduan", "Layanan lainnya"]),
]

# --------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "dpmd.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
_pw = os.environ.get("ADMIN_PASSWORD", "")
if not _pw:
    raise RuntimeError("ADMIN_PASSWORD wajib diatur. Website dihentikan agar tidak memakai password bawaan.")
if len(_pw) < 12:
    raise RuntimeError("ADMIN_PASSWORD harus minimal 12 karakter.")
ADMIN_HASH = generate_password_hash(_pw)


def _secret_key():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = os.path.join(DATA_DIR, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app = Flask(__name__)
app.config.update(
    SECRET_KEY=_secret_key(),  # Secret key tetap menggunakan mekanisme yang sudah ada.
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Aktifkan COOKIE_SECURE=true di deployment HTTPS. Default false agar localhost HTTP berfungsi.
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() in ("1", "true", "yes"),
)

# Pembatasan percobaan login (per proses). Untuk deployment multi-worker gunakan rate limiter
# eksternal/Redis agar batasnya berlaku bersama antar-worker.
_LOGIN_ATTEMPTS = {}
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCK_SECONDS = 15 * 60

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS dokumen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judul TEXT NOT NULL, kategori TEXT NOT NULL, tahun INTEGER NOT NULL,
    deskripsi TEXT DEFAULT '', filename TEXT NOT NULL, original_name TEXT NOT NULL,
    ukuran INTEGER DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aplikasi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL, deskripsi TEXT DEFAULT '', url TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS dokumentasi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judul TEXT NOT NULL, tanggal TEXT NOT NULL, keterangan TEXT DEFAULT '',
    filename TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS permohonan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no_reg TEXT DEFAULT '', kategori TEXT NOT NULL, nama TEXT NOT NULL, nik TEXT NOT NULL,
    pekerjaan TEXT DEFAULT '', alamat TEXT NOT NULL, email TEXT NOT NULL, hp TEXT NOT NULL,
    ktp_file TEXT NOT NULL, bidang TEXT DEFAULT '', rincian TEXT NOT NULL,
    berkas_file TEXT DEFAULT '', berkas_nama TEXT DEFAULT '', tujuan TEXT NOT NULL,
    cara TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Diterima', catatan TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS berita (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judul TEXT NOT NULL, isi TEXT NOT NULL, tanggal TEXT NOT NULL,
    gambar TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pengaturan (
    kunci TEXT PRIMARY KEY, nilai TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS survei (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
    jk TEXT NOT NULL, umur TEXT NOT NULL, pendidikan TEXT NOT NULL, pekerjaan TEXT NOT NULL, layanan TEXT NOT NULL,
    u1 INTEGER NOT NULL, u2 INTEGER NOT NULL, u3 INTEGER NOT NULL, u4 INTEGER NOT NULL, u5 INTEGER NOT NULL,
    u6 INTEGER NOT NULL, u7 INTEGER NOT NULL, u8 INTEGER NOT NULL, u9 INTEGER NOT NULL,
    saran TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS statistik_harian (
    tanggal TEXT PRIMARY KEY, pengunjung INTEGER NOT NULL DEFAULT 0, tayangan INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pengunjung_hari (
    tanggal TEXT NOT NULL, kode TEXT NOT NULL, PRIMARY KEY (tanggal, kode)
);
CREATE TABLE IF NOT EXISTS pengunjung_aktif (
    kode TEXT PRIMARY KEY, waktu REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS struktur (
    id INTEGER PRIMARY KEY AUTOINCREMENT, induk_id INTEGER, urutan INTEGER NOT NULL DEFAULT 0,
    jabatan TEXT NOT NULL, nama TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS kutipan (
    id INTEGER PRIMARY KEY AUTOINCREMENT, teks TEXT NOT NULL, penulis TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS pesan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL, email TEXT DEFAULT '', subjek TEXT DEFAULT '',
    isi TEXT NOT NULL, created_at TEXT NOT NULL
);
"""

SEED_APLIKASI = [
    ("Prodeskel", "Pengisian dan pemutakhiran profil desa dan kelurahan.", ""),
    ("Siskeudes", "Aplikasi pengelolaan keuangan desa untuk perencanaan sampai pelaporan.", ""),
    ("Layanan Pengaduan", "Sampaikan keluhan atau saran terkait layanan pemerintah desa.", ""),
]


SEED_KUTIPAN = [
    ("Berat sama dipikul, ringan sama dijinjing.", "Peribahasa"),
    ("Bersatu kita teguh, bercerai kita runtuh.", "Peribahasa"),
    ("Sedikit demi sedikit, lama-lama menjadi bukit.", "Peribahasa"),
    ("Di mana bumi dipijak, di situ langit dijunjung.", "Peribahasa"),
    ("Rajin pangkal pandai, hemat pangkal kaya.", "Peribahasa"),
    ("Sekali merengkuh dayung, dua tiga pulau terlampaui.", "Peribahasa"),
    ("Malu bertanya, sesat di jalan.", "Peribahasa"),
    ("Duduk sama rendah, berdiri sama tinggi.", "Peribahasa"),
    ("Ke bukit sama mendaki, ke lurah sama menurun.", "Peribahasa"),
    ("Bulat air karena pembuluh, bulat kata karena mufakat.", "Peribahasa"),
    ("Desa yang kuat adalah fondasi Indonesia yang kuat.", ""),
    ("Pelayanan terbaik dimulai dari kesediaan untuk mendengar.", ""),
    ("Keterbukaan informasi hari ini adalah kepercayaan masyarakat di hari esok.", ""),
    ("Pemberdayaan berarti membuka jalan agar warga mampu melangkah dengan kekuatannya sendiri.", ""),
    ("Setiap perubahan besar di desa bermula dari satu warga yang mau bergerak.", ""),
    ("Gotong royong bukan sekadar tradisi, melainkan cara kita menyelesaikan pekerjaan besar bersama.", ""),
    ("Anggaran desa adalah amanah; setiap rupiahnya harus dapat dipertanggungjawabkan kepada warga.", ""),
    ("Musyawarah yang baik lahir dari kemauan untuk menghargai perbedaan.", ""),
    ("Melayani dengan ramah adalah bentuk sederhana dari menghormati sesama.", ""),
    ("Potensi desa tumbuh ketika warganya diberi ruang untuk berkarya.", ""),
    ("Kemajuan diukur bukan dari seberapa cepat kita berlari, tetapi dari seberapa banyak warga yang ikut melangkah.", ""),
    ("Data yang akurat membuat keputusan desa tepat sasaran.", ""),
    ("Kerja jujur hari ini menjadi teladan bagi generasi desa esok hari.", ""),
    ("Setiap warga berhak mendapat pelayanan yang cepat, mudah, dan adil.", ""),
    ("Pembangunan yang berhasil adalah yang manfaatnya dirasakan oleh seluruh warga.", ""),
    ("Disiplin kecil yang dilakukan setiap hari menghasilkan pelayanan yang besar.", ""),
    ("Kolaborasi mengubah keterbatasan menjadi kekuatan.", ""),
    ("Mulailah dari yang ada, lakukan dengan sungguh-sungguh, dan ajak warga ikut serta.", ""),
    ("Pemimpin yang baik hadir, mendengar, dan bertindak.", ""),
    ("Transparansi bukan beban, melainkan cara membangun kepercayaan.", ""),
    ("Kebersihan lingkungan dimulai dari halaman rumah sendiri.", ""),
    ("Semangat melayani adalah tenaga terbesar sebuah organisasi.", ""),
]


def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.executescript(SCHEMA)
        if con.execute("SELECT COUNT(*) FROM aplikasi").fetchone()[0] == 0:
            con.executemany("INSERT INTO aplikasi (nama, deskripsi, url) VALUES (?,?,?)", SEED_APLIKASI)

        def sudah(kunci):
            return con.execute("SELECT 1 FROM pengaturan WHERE kunci=?", (kunci,)).fetchone() is not None

        # Contoh awal, hanya sekali. Admin bebas mengubah atau menghapusnya (tidak dibuat ulang).
        if not sudah("kutipan_awal"):
            if con.execute("SELECT COUNT(*) FROM kutipan").fetchone()[0] == 0:
                con.executemany("INSERT INTO kutipan (teks, penulis) VALUES (?,?)", SEED_KUTIPAN)
            con.execute("INSERT INTO pengaturan (kunci, nilai) VALUES ('kutipan_awal', '1')")
        if not sudah("struktur_awal"):
            if con.execute("SELECT COUNT(*) FROM struktur").fetchone()[0] == 0:
                akar = con.execute("INSERT INTO struktur (induk_id, urutan, jabatan) VALUES (NULL, 0, 'Kepala Dinas')").lastrowid
                con.execute("INSERT INTO struktur (induk_id, urutan, jabatan) VALUES (?, 0, 'Sekretaris')", (akar,))
                for i, (bidang, _uraian) in enumerate(PROFIL["bidang"][1:], 1):
                    con.execute("INSERT INTO struktur (induk_id, urutan, jabatan) VALUES (?, ?, ?)",
                                (akar, i, "Kepala " + bidang))
            con.execute("INSERT INTO pengaturan (kunci, nilai) VALUES ('struktur_awal', '1')")


init_db()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# --------------------------------------------------------------------------
# Keamanan dasar: CSRF, login
# --------------------------------------------------------------------------
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.before_request
def lindungi_post():
    if request.method == "POST":
        kirim = request.form.get("csrf", "")
        asli = session.get("csrf", "")
        if not kirim or not asli or not hmac.compare_digest(kirim, asli):
            abort(400)


@app.before_request
def hitung_pengunjung():
    """Catat kunjungan tanpa menyimpan IP atau cookie: pengunjung unik per hari dikenali dari sidik
    (hash) IP + browser yang diacak harian bersama kunci rahasia. Bot dan admin tidak dihitung."""
    if request.method != "GET" or request.endpoint not in HALAMAN_HITUNG or session.get("admin"):
        return
    ua = request.headers.get("User-Agent", "")
    if not ua or BOT_RE.search(ua):
        return
    try:
        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or ""
        hari = datetime.now().strftime("%Y-%m-%d")
        kode = hashlib.sha256(f"{app.config['SECRET_KEY']}|{hari}|{ip}|{ua}".encode()).hexdigest()[:24]
        db = get_db()
        baru = db.execute("INSERT OR IGNORE INTO pengunjung_hari (tanggal, kode) VALUES (?,?)", (hari, kode)).rowcount
        db.execute("INSERT INTO statistik_harian (tanggal, pengunjung, tayangan) VALUES (?,?,1) "
                   "ON CONFLICT(tanggal) DO UPDATE SET pengunjung=pengunjung+?, tayangan=tayangan+1", (hari, baru, baru))
        sekarang = time.time()
        db.execute("INSERT OR REPLACE INTO pengunjung_aktif (kode, waktu) VALUES (?,?)", (kode, sekarang))
        db.execute("DELETE FROM pengunjung_hari WHERE tanggal < ?", (hari,))
        db.execute("DELETE FROM pengunjung_aktif WHERE waktu < ?", (sekarang - 3600,))
        db.commit()
    except sqlite3.Error:
        pass  # penghitung tidak boleh mengganggu halaman


def wajib_login(fn):
    @wraps(fn)
    def bungkus(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return bungkus


@app.after_request
def header_aman(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    resp.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    return resp


# --------------------------------------------------------------------------
# Template helper
# --------------------------------------------------------------------------
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]


@app.template_filter("tgl")
def tgl_id(value):
    try:
        d = datetime.strptime(str(value)[:10], "%Y-%m-%d")
        return f"{d.day} {BULAN[d.month - 1]} {d.year}"
    except ValueError:
        return value


def logo_provinsi():
    """Logo provinsi opsional: simpan sebagai static/img/logo-provinsi.png (atau .webp/.svg/.jpg)."""
    for ext in ("png", "webp", "svg", "jpg", "jpeg"):
        if os.path.exists(os.path.join(app.static_folder, "img", f"logo-provinsi.{ext}")):
            return f"img/logo-provinsi.{ext}"
    return None


def ambil_sosmed(semua=False):
    """Tautan media sosial yang diisi admin. semua=True mengembalikan dict kunci -> nilai (termasuk kosong)."""
    baris = get_db().execute("SELECT kunci, nilai FROM pengaturan").fetchall()
    nilai = {r["kunci"]: r["nilai"] for r in baris}
    if semua:
        return nilai
    return [(k, label, nilai[k]) for k, label, _ in SOSMED if nilai.get(k)]


@app.template_filter("paragraf")
def paragraf(teks):
    """Ubah teks biasa menjadi paragraf HTML yang aman (baris kosong = paragraf baru)."""
    bagian = [b.strip() for b in re.split(r"\n\s*\n", teks or "") if b.strip()]
    return Markup("".join("<p>%s</p>" % escape(b).replace("\n", Markup("<br>")) for b in bagian))


@app.template_filter("ringkas")
def ringkas(teks, n=150):
    t = " ".join((teks or "").split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "..."


def ambil_pengaturan(kunci):
    r = get_db().execute("SELECT nilai FROM pengaturan WHERE kunci=?", (kunci,)).fetchone()
    return r["nilai"] if r else ""


def alamat_publik():
    """Alamat dasar website untuk kode QR: pengaturan admin, atau alamat yang sedang dipakai pengunjung."""
    return (ambil_pengaturan("url_publik") or request.host_url).rstrip("/")


def url_survei():
    return alamat_publik() + url_for("survei")


def mutu_ikm(nilai):
    if nilai >= 88.31:
        return "A", "Sangat baik"
    if nilai >= 76.61:
        return "B", "Baik"
    if nilai >= 65.00:
        return "C", "Kurang baik"
    return "D", "Tidak baik"


def tanggal_filter(teks):
    return teks if teks and re.fullmatch(r"\d{4}-\d{2}-\d{2}", teks) else ""


def kondisi_survei(dari, sampai):
    kondisi, par = "1=1", []
    if dari:
        kondisi += " AND date(created_at) >= ?"
        par.append(dari)
    if sampai:
        kondisi += " AND date(created_at) <= ?"
        par.append(sampai)
    return kondisi, par


def ringkasan_survei(db, dari="", sampai=""):
    """Hitung Indeks Kepuasan Masyarakat: rata-rata nilai tiap unsur, lalu rata-rata unsur dikali 25 (skala 25-100)."""
    kondisi, par = kondisi_survei(dari, sampai)
    kolom = ", ".join(f"AVG({k})" for k, *_ in SKM_UNSUR)
    row = db.execute(f"SELECT COUNT(*), {kolom} FROM survei WHERE {kondisi}", par).fetchone()
    n = row[0]
    hasil = {"n": n, "unsur": [], "ikm": None, "mutu": None, "saran": []}
    if n:
        for i, (k, judul, *_rest) in enumerate(SKM_UNSUR):
            hasil["unsur"].append({"judul": judul, "rata": row[i + 1], "ikm": row[i + 1] * 25})
        hasil["ikm"] = sum(u["rata"] for u in hasil["unsur"]) / len(SKM_UNSUR) * 25
        hasil["mutu"] = mutu_ikm(hasil["ikm"])
        hasil["saran"] = db.execute(
            f"SELECT id, created_at, layanan, saran FROM survei WHERE {kondisi} AND saran <> '' "
            "ORDER BY id DESC LIMIT 30", par).fetchall()
    return hasil


def ringkasan_pengunjung():
    db = get_db()
    sekarang = datetime.now()
    hari = sekarang.strftime("%Y-%m-%d")
    kemarin = (sekarang - timedelta(days=1)).strftime("%Y-%m-%d")

    def satu(tanggal):
        r = db.execute("SELECT pengunjung, tayangan FROM statistik_harian WHERE tanggal=?", (tanggal,)).fetchone()
        return (r["pengunjung"], r["tayangan"]) if r else (0, 0)

    total = db.execute("SELECT COALESCE(SUM(pengunjung),0) p, COALESCE(SUM(tayangan),0) t FROM statistik_harian").fetchone()
    bulan = db.execute("SELECT COALESCE(SUM(pengunjung),0) FROM statistik_harian WHERE tanggal LIKE ?",
                       (hari[:7] + "%",)).fetchone()[0]
    awal = ambil_pengaturan("hitung_awal")
    awal = int(awal) if awal.isdigit() else 0
    online = db.execute("SELECT COUNT(*) FROM pengunjung_aktif WHERE waktu >= ?",
                        (time.time() - ONLINE_DETIK,)).fetchone()[0]
    return {"hari_ini": satu(hari)[0], "tayangan_hari_ini": satu(hari)[1], "kemarin": satu(kemarin)[0],
            "bulan_ini": bulan, "total": total["p"] + awal, "awal": awal, "tayangan_total": total["t"],
            "online": online, "digit": list(str(total["p"] + awal).zfill(6))}


def statistik_30_hari():
    db = get_db()
    baris = {r["tanggal"]: r for r in db.execute(
        "SELECT * FROM statistik_harian WHERE tanggal >= ?",
        ((datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d"),))}
    hasil = []
    for i in range(29, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        r = baris.get(d)
        hasil.append({"tanggal": d, "pengunjung": r["pengunjung"] if r else 0, "tayangan": r["tayangan"] if r else 0})
    return hasil


@app.template_filter("angka")
def angka(n):
    return f"{int(n or 0):,}".replace(",", ".")


def simpan_pengaturan(kunci, nilai):
    db = get_db()
    db.execute("INSERT INTO pengaturan (kunci, nilai) VALUES (?,?) ON CONFLICT(kunci) DO UPDATE SET nilai=excluded.nilai",
               (kunci, nilai))
    db.commit()


def kutipan_hari_ini():
    """Satu kutipan per hari: bergilir mengikuti tanggal, sama untuk semua pengunjung."""
    baris = get_db().execute("SELECT * FROM kutipan ORDER BY id").fetchall()
    return baris[datetime.now().date().toordinal() % len(baris)] if baris else None


def ambil_struktur():
    """Susunan jabatan sebagai pohon bersarang: [{id, jabatan, nama, induk_id, urutan, kedalaman, anak: [...]}]."""
    baris = get_db().execute("SELECT * FROM struktur ORDER BY urutan, id").fetchall()
    ada = {r["id"] for r in baris}
    anak = {}
    for r in baris:
        anak.setdefault(r["induk_id"], []).append(r)

    def bangun(r, kedalaman, dilihat):
        dilihat = dilihat | {r["id"]}
        return {"id": r["id"], "jabatan": r["jabatan"], "nama": r["nama"], "induk_id": r["induk_id"],
                "urutan": r["urutan"], "kedalaman": kedalaman,
                "anak": [bangun(x, kedalaman + 1, dilihat) for x in anak.get(r["id"], []) if x["id"] not in dilihat]}

    return [bangun(r, 0, frozenset()) for r in baris if r["induk_id"] is None or r["induk_id"] not in ada]


def ratakan_struktur(pohon):
    for n in pohon:
        yield n
        yield from ratakan_struktur(n["anak"])


def id_turunan(db, i):
    hasil, antri = set(), [i]
    while antri:
        x = antri.pop()
        for r in db.execute("SELECT id FROM struktur WHERE induk_id=?", (x,)):
            if r["id"] not in hasil:
                hasil.add(r["id"])
                antri.append(r["id"])
    return hasil


@app.template_filter("ukuran")
def ukuran(n):
    n = n or 0
    for satuan in ("B", "KB", "MB"):
        if n < 1024 or satuan == "MB":
            return f"{n:.0f} {satuan}" if satuan == "B" else f"{n:.1f} {satuan}"
        n /= 1024


@app.context_processor
def konteks():
    return {"site": SITE, "KATEGORI": KATEGORI, "csrf_token": csrf_token,
            "tahun_ini": datetime.now().year, "sosmed": ambil_sosmed(),
            "logo_provinsi": logo_provinsi(),
            "pengunjung": ringkasan_pengunjung()}


def cek_file(f, allowed, max_bytes=None, magic=None):
    """Validasi ekstensi, ukuran, dan signature dasar berkas sebelum disimpan."""
    if not f or not f.filename:
        return False
    ext = os.path.splitext(f.filename)[1].lower().lstrip(".")
    if ext not in allowed:
        return False
    f.stream.seek(0, os.SEEK_END)
    n = f.stream.tell()
    f.stream.seek(0)
    if max_bytes and n > max_bytes:
        return False
    if magic:
        head = f.stream.read(12)
        f.stream.seek(0)
        if ext == "webp":
            if not (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
                return False
        elif ext in ("jpg", "jpeg"):
            if not head.startswith(b"\xff\xd8\xff"):
                return False
        elif ext == "png":
            if not head.startswith(b"\x89PNG\r\n\x1a\n"):
                return False
        elif not any(head.startswith(m) for m in magic):
            return False
    return True


def simpan_file(f, allowed, max_bytes=None, magic=None):
    """Simpan unggahan dengan nama acak. Mengembalikan (nama_disimpan, nama_asli, ukuran) atau None."""
    if not cek_file(f, allowed, max_bytes, magic):
        return None
    ext = os.path.splitext(f.filename)[1].lower().lstrip(".")
    nama = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(UPLOAD_DIR, nama)
    f.save(path)
    asli = secure_filename(f.filename) or f"berkas.{ext}"
    return nama, asli, os.path.getsize(path)


def hapus_file(nama):
    try:
        os.remove(os.path.join(UPLOAD_DIR, nama))
    except OSError:
        pass


# --------------------------------------------------------------------------
# Halaman publik
# --------------------------------------------------------------------------
@app.route("/")
def home():
    db = get_db()
    return render_template(
        "home.html",
        dokumen=db.execute("SELECT * FROM dokumen ORDER BY id DESC LIMIT 5").fetchall(),
        berita=db.execute("SELECT * FROM berita ORDER BY tanggal DESC, id DESC LIMIT 3").fetchall(),
        kutipan=kutipan_hari_ini(),
        foto=db.execute("SELECT * FROM dokumentasi ORDER BY tanggal DESC, id DESC LIMIT 3").fetchall(),
        jumlah=db.execute("SELECT COUNT(*) FROM dokumen").fetchone()[0],
    )


@app.route("/profil")
def profil():
    kadis = {k: ambil_pengaturan("kadis_" + k) for k in ("nama", "jabatan", "sambutan", "foto")}
    return render_template("profil.html", p=PROFIL, kadis=kadis, bagan=ambil_pengaturan("struktur_gambar"),
                           pohon=ambil_struktur())


@app.route("/ppid-pelaksana")
def ppid():
    db = get_db()
    kat = request.args.get("kategori", "")
    q = request.args.get("q", "").strip()
    tahun = request.args.get("tahun", "")

    sql, par = "SELECT * FROM dokumen WHERE 1=1", []
    if kat in KATEGORI:
        sql += " AND kategori=?"
        par.append(kat)
    if q:
        sql += " AND (judul LIKE ? OR deskripsi LIKE ?)"
        par += [f"%{q}%", f"%{q}%"]
    if tahun.isdigit():
        sql += " AND tahun=?"
        par.append(int(tahun))
    sql += " ORDER BY tahun DESC, id DESC"

    hitung = {r["kategori"]: r["n"] for r in
              db.execute("SELECT kategori, COUNT(*) AS n FROM dokumen GROUP BY kategori")}
    tahun_list = [r[0] for r in db.execute("SELECT DISTINCT tahun FROM dokumen ORDER BY tahun DESC")]
    return render_template("ppid.html", dokumen=db.execute(sql, par).fetchall(), kat=kat, q=q,
                           tahun=tahun, hitung=hitung, tahun_list=tahun_list,
                           total=sum(hitung.values()), KET=KATEGORI_KET)


@app.route("/aplikasi")
def aplikasi():
    return render_template("aplikasi.html",
                           apps=get_db().execute("SELECT * FROM aplikasi ORDER BY id").fetchall())


@app.route("/dokumentasi")
def dokumentasi():
    return render_template("dokumentasi.html", foto=get_db().execute(
        "SELECT * FROM dokumentasi ORDER BY tanggal DESC, id DESC").fetchall())


@app.route("/kontak", methods=["GET", "POST"])
def kontak():
    if request.method == "POST":
        if request.form.get("website"):  # kolom jebakan untuk bot
            return redirect(url_for("kontak"))
        nama = request.form.get("nama", "").strip()[:100]
        email = request.form.get("email", "").strip()[:150]
        subjek = request.form.get("subjek", "").strip()[:150]
        isi = request.form.get("isi", "").strip()[:3000]
        if not nama or not isi:
            flash("Nama dan pesan wajib diisi.", "galat")
        else:
            db = get_db()
            db.execute("INSERT INTO pesan (nama, email, subjek, isi, created_at) VALUES (?,?,?,?,?)",
                       (nama, email, subjek, isi, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            flash("Pesan terkirim. Petugas kami akan menindaklanjuti.", "ok")
            return redirect(url_for("kontak"))
    return render_template("kontak.html")


@app.route("/berita")
def berita():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM berita").fetchone()[0]
    jumlah_hal = max((total + BERITA_PER_HALAMAN - 1) // BERITA_PER_HALAMAN, 1)
    h = request.args.get("hal", "1")
    hal = min(max(int(h), 1), jumlah_hal) if h.isdigit() else 1
    rows = db.execute("SELECT * FROM berita ORDER BY tanggal DESC, id DESC LIMIT ? OFFSET ?",
                      (BERITA_PER_HALAMAN, (hal - 1) * BERITA_PER_HALAMAN)).fetchall()
    return render_template("berita.html", berita=rows, hal=hal, jumlah_hal=jumlah_hal, total=total)


@app.route("/berita/<int:i>")
def berita_detail(i):
    db = get_db()
    b = db.execute("SELECT * FROM berita WHERE id=?", (i,)).fetchone()
    if not b:
        abort(404)
    lain = db.execute("SELECT id, judul, tanggal FROM berita WHERE id<>? ORDER BY tanggal DESC, id DESC LIMIT 4",
                      (i,)).fetchall()
    return render_template("berita_detail.html", b=b, lain=lain)


@app.route("/survei", methods=["GET", "POST"])
def survei():
    v = request.form if request.method == "POST" else {}
    galat = []
    if request.method == "POST":
        if request.form.get("website"):  # kolom jebakan untuk bot
            return redirect(url_for("survei"))
        nilai = {}
        for kolom, label, pilihan in SKM_PROFIL:
            nilai[kolom] = request.form.get(kolom, "")
            if nilai[kolom] not in pilihan:
                galat.append(f"Pilih {label.lower()}.")
        for kolom, judul, _pertanyaan, _opsi in SKM_UNSUR:
            nilai[kolom] = request.form.get(kolom, "")
            if nilai[kolom] not in ("1", "2", "3", "4"):
                galat.append(f"Beri penilaian untuk: {judul}.")
        if time.time() - session.get("survei_terakhir", 0) < 30:
            galat.append("Survei Anda baru saja terkirim. Tunggu sebentar sebelum mengirim lagi.")
        if not galat:
            kode_unsur = {k for k, *_ in SKM_UNSUR}
            kolom_db = [k for k, *_ in SKM_PROFIL] + [k for k, *_ in SKM_UNSUR]
            db = get_db()
            db.execute(f"INSERT INTO survei (created_at, {', '.join(kolom_db)}, saran) "
                       f"VALUES (?, {', '.join('?' * len(kolom_db))}, ?)",
                       [datetime.now().strftime("%Y-%m-%d %H:%M")]
                       + [int(nilai[k]) if k in kode_unsur else nilai[k] for k in kolom_db]
                       + [request.form.get("saran", "").strip()[:1000]])
            db.commit()
            session["survei_terakhir"] = time.time()
            session["survei_ok"] = True
            return redirect(url_for("survei_selesai"))
    return render_template("survei.html", v=v, galat=galat, UNSUR=SKM_UNSUR, PROFIL=SKM_PROFIL)


@app.route("/survei/terima-kasih")
def survei_selesai():
    if not session.pop("survei_ok", None):
        return redirect(url_for("survei"))
    return render_template("survei_selesai.html")


@app.route("/survei/qr.svg")
def survei_qr():
    try:
        svg = qr_svg(url_survei())
    except ValueError:
        abort(404)
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/survei/cetak")
def survei_cetak():
    return render_template("survei_cetak.html", url=url_survei())


@app.route("/unduh/<int:doc_id>")
def unduh(doc_id):
    row = get_db().execute("SELECT * FROM dokumen WHERE id=?", (doc_id,)).fetchone()
    if not row:
        abort(404)
    return send_from_directory(UPLOAD_DIR, row["filename"], as_attachment=True,
                               download_name=row["original_name"])


@app.route("/media/<path:nama>")
def media(nama):
    ada = get_db().execute("SELECT 1 FROM dokumentasi WHERE filename=? UNION SELECT 1 FROM berita WHERE gambar=? "
                           "UNION SELECT 1 FROM pengaturan WHERE kunci IN ('kadis_foto', 'struktur_gambar') AND nilai=?",
                           (nama, nama, nama)).fetchone()
    if not ada:
        abort(404)
    return send_from_directory(UPLOAD_DIR, nama)


@app.route("/ppid-pelaksana/permohonan", methods=["GET", "POST"])
def permohonan():
    v = request.form if request.method == "POST" else {}
    galat = []
    if request.method == "POST":
        if request.form.get("website"):  # kolom jebakan untuk bot
            return redirect(url_for("permohonan"))

        def isi(k, n):
            return request.form.get(k, "").strip()[:n]

        d = {"kategori": isi("kategori", 40), "nama": isi("nama", 120), "nik": isi("nik", 16),
             "pekerjaan": isi("pekerjaan", 100), "alamat": isi("alamat", 400),
             "email": isi("email", 150), "hp": isi("hp", 20), "bidang": isi("bidang", 120),
             "rincian": isi("rincian", 4000), "tujuan": isi("tujuan", 2000), "cara": isi("cara", 80)}
        ktp, lampiran = request.files.get("ktp"), request.files.get("berkas")

        if d["kategori"] not in KATEGORI_PEMOHON:
            galat.append("Pilih kategori pemohon.")
        if not d["nama"]:
            galat.append("Nama lengkap wajib diisi.")
        if not re.fullmatch(r"\d{16}", d["nik"]):
            galat.append("NIK harus 16 digit angka.")
        if not d["alamat"]:
            galat.append("Alamat domisili wajib diisi.")
        if not EMAIL_RE.match(d["email"]):
            galat.append("Alamat email tidak valid.")
        if not re.fullmatch(r"\+?[\d\s-]{8,18}", d["hp"]):
            galat.append("Nomor HP atau WhatsApp tidak valid.")
        if not cek_file(ktp, {"jpg", "jpeg", "png"}, 1024 * 1024, MAGIC_GAMBAR):
            galat.append("Foto KTP wajib diunggah dalam format JPG atau PNG, maksimal 1 MB.")
        if lampiran and lampiran.filename and not cek_file(lampiran, {"pdf"}, 5 * 1024 * 1024, MAGIC_PDF):
            galat.append("Berkas lampiran harus berformat PDF, maksimal 5 MB.")
        if not d["rincian"]:
            galat.append("Rincian informasi yang dibutuhkan wajib diisi.")
        if not d["tujuan"]:
            galat.append("Tujuan penggunaan informasi wajib diisi.")
        if d["cara"] not in CARA_MEMPEROLEH:
            galat.append("Pilih cara memperoleh informasi.")
        if not request.form.get("setuju"):
            galat.append("Centang pernyataan kebenaran data sebelum mengirim.")

        if not galat:
            f_ktp = simpan_file(ktp, {"jpg", "jpeg", "png"}, 1024 * 1024, MAGIC_GAMBAR)
            f_lamp = simpan_file(lampiran, {"pdf"}, 5 * 1024 * 1024, MAGIC_PDF) if lampiran and lampiran.filename else None
            db = get_db()
            cur = db.execute(
                "INSERT INTO permohonan (kategori, nama, nik, pekerjaan, alamat, email, hp, ktp_file, bidang, rincian, "
                "berkas_file, berkas_nama, tujuan, cara, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (d["kategori"], d["nama"], d["nik"], d["pekerjaan"], d["alamat"], d["email"], d["hp"], f_ktp[0],
                 d["bidang"], d["rincian"], f_lamp[0] if f_lamp else "", f_lamp[1] if f_lamp else "",
                 d["tujuan"], d["cara"], datetime.now().strftime("%Y-%m-%d %H:%M")))
            no_reg = f"PPID-{datetime.now().year}-{cur.lastrowid:04d}"
            db.execute("UPDATE permohonan SET no_reg=? WHERE id=?", (no_reg, cur.lastrowid))
            db.commit()
            session["no_reg_baru"] = no_reg
            return redirect(url_for("permohonan_berhasil"))
    ada_template = os.path.exists(os.path.join(app.static_folder, "files", FILE_TEMPLATE))
    return render_template("permohonan.html", v=v, galat=galat, KAT_PEMOHON=KATEGORI_PEMOHON,
                           CARA=CARA_MEMPEROLEH, bidang=[b[0] for b in PROFIL["bidang"]],
                           ada_template=ada_template, file_template=FILE_TEMPLATE)


@app.route("/ppid-pelaksana/permohonan/berhasil")
def permohonan_berhasil():
    no_reg = session.pop("no_reg_baru", None)
    if not no_reg:
        return redirect(url_for("permohonan"))
    return render_template("permohonan_berhasil.html", no_reg=no_reg)


@app.route("/ppid-pelaksana/status", methods=["GET", "POST"])
def status_permohonan():
    hasil = None
    if request.method == "POST":
        no = request.form.get("no_reg", "").strip().upper()
        email = request.form.get("email", "").strip().lower()
        hasil = get_db().execute("SELECT * FROM permohonan WHERE no_reg=? AND lower(email)=?",
                                 (no, email)).fetchone()
        if not hasil:
            flash("Permohonan tidak ditemukan. Periksa nomor registrasi dan email yang Anda gunakan.", "galat")
    return render_template("status.html", hasil=hasil)


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------
@app.route("/admin/masuk", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        # Gunakan alamat peer langsung; jangan percaya X-Forwarded-For kecuali proxy tepercaya.
        ip = request.remote_addr or "unknown"
        now = time.time()
        state = _LOGIN_ATTEMPTS.get(ip, {"times": [], "locked_until": 0})
        if state.get("locked_until", 0) > now:
            flash("Terlalu banyak percobaan login. Coba kembali beberapa saat lagi.", "galat")
            return render_template("admin_login.html"), 429
        times = [t for t in state.get("times", []) if now - t < _LOGIN_WINDOW_SECONDS]
        u, p = request.form.get("username", ""), request.form.get("password", "")
        if hmac.compare_digest(u, ADMIN_USER) and check_password_hash(ADMIN_HASH, p):
            _LOGIN_ATTEMPTS.pop(ip, None)
            session.clear()
            session["admin"] = True
            return redirect(url_for("admin"))
        times.append(now)
        locked_until = now + _LOGIN_LOCK_SECONDS if len(times) >= _LOGIN_MAX_ATTEMPTS else 0
        _LOGIN_ATTEMPTS[ip] = {"times": times, "locked_until": locked_until}
        flash("Nama pengguna atau kata sandi salah.", "galat")
        if locked_until:
            return render_template("admin_login.html"), 429
    return render_template("admin_login.html")


@app.route("/admin/keluar", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin")
@wajib_login
def admin():
    db = get_db()
    tab = request.args.get("tab", "dokumen")
    data = {
        "dokumen": db.execute("SELECT * FROM dokumen ORDER BY id DESC").fetchall(),
        "aplikasi": db.execute("SELECT * FROM aplikasi ORDER BY id").fetchall(),
        "dokumentasi": db.execute("SELECT * FROM dokumentasi ORDER BY tanggal DESC, id DESC").fetchall(),
        "pesan": db.execute("SELECT * FROM pesan ORDER BY id DESC").fetchall(),
        "berita": db.execute("SELECT * FROM berita ORDER BY tanggal DESC, id DESC").fetchall(),
        "sosmed": ambil_sosmed(semua=True),
        "permohonan": db.execute("SELECT * FROM permohonan ORDER BY id DESC").fetchall(),
        "survei": None,
        "statistik": None,
        "profil": None,
        "kutipan": db.execute("SELECT * FROM kutipan ORDER BY id").fetchall(),
    }
    if tab not in data:
        tab = "dokumen"
    sv = None
    if tab == "survei":
        dari, sampai = tanggal_filter(request.args.get("dari")), tanggal_filter(request.args.get("sampai"))
        sv = ringkasan_survei(db, dari, sampai)
        url = url_survei()
        sv.update(dari=dari, sampai=sampai, url=url, url_publik=ambil_pengaturan("url_publik"),
                  lokal=bool(re.match(r"https?://(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", url)))
    pf = None
    if tab == "profil":
        pf = {"nama": ambil_pengaturan("kadis_nama"), "jabatan": ambil_pengaturan("kadis_jabatan"),
              "sambutan": ambil_pengaturan("kadis_sambutan"), "foto": ambil_pengaturan("kadis_foto"),
              "bagan": ambil_pengaturan("struktur_gambar"), "daftar": list(ratakan_struktur(ambil_struktur()))}
    kh = kutipan_hari_ini() if tab == "kutipan" else None
    return render_template("admin.html", tab=tab, data=data, tahun_ini=datetime.now().year, pf=pf, kh=kh,
                           STATUS=STATUS_PERMOHONAN, SOSMED=SOSMED,
                           hari_ini=datetime.now().strftime("%Y-%m-%d"), sv=sv,
                           st=statistik_30_hari() if tab == "statistik" else None)


@app.route("/admin/dokumen/tambah", methods=["POST"])
@wajib_login
def tambah_dokumen():
    judul = request.form.get("judul", "").strip()
    kategori = request.form.get("kategori", "")
    tahun = request.form.get("tahun", "")
    hasil = simpan_file(request.files.get("berkas"), EXT_DOKUMEN)
    if not judul or kategori not in KATEGORI or not tahun.isdigit() or not hasil:
        flash("Lengkapi judul, kategori, tahun, dan pilih berkas (PDF, Word, Excel, PowerPoint, CSV, atau ZIP).", "galat")
    else:
        db = get_db()
        db.execute("INSERT INTO dokumen (judul, kategori, tahun, deskripsi, filename, original_name, ukuran, created_at) "
                   "VALUES (?,?,?,?,?,?,?,?)",
                   (judul, kategori, int(tahun), request.form.get("deskripsi", "").strip(),
                    hasil[0], hasil[1], hasil[2], datetime.now().strftime("%Y-%m-%d")))
        db.commit()
        flash("Dokumen diterbitkan.", "ok")
    return redirect(url_for("admin", tab="dokumen"))


@app.route("/admin/dokumen/<int:i>/hapus", methods=["POST"])
@wajib_login
def hapus_dokumen(i):
    db = get_db()
    row = db.execute("SELECT filename FROM dokumen WHERE id=?", (i,)).fetchone()
    if row:
        hapus_file(row["filename"])
        db.execute("DELETE FROM dokumen WHERE id=?", (i,))
        db.commit()
        flash("Dokumen dihapus.", "ok")
    return redirect(url_for("admin", tab="dokumen"))


@app.route("/admin/aplikasi/tambah", methods=["POST"])
@wajib_login
def tambah_aplikasi():
    nama = request.form.get("nama", "").strip()
    url = request.form.get("url", "").strip()
    if not nama or (url and not url.startswith(("http://", "https://"))):
        flash("Isi nama aplikasi. Tautan harus diawali http:// atau https://.", "galat")
    else:
        db = get_db()
        db.execute("INSERT INTO aplikasi (nama, deskripsi, url) VALUES (?,?,?)",
                   (nama, request.form.get("deskripsi", "").strip(), url))
        db.commit()
        flash("Aplikasi ditambahkan.", "ok")
    return redirect(url_for("admin", tab="aplikasi"))


@app.route("/admin/aplikasi/<int:i>/hapus", methods=["POST"])
@wajib_login
def hapus_aplikasi(i):
    db = get_db()
    db.execute("DELETE FROM aplikasi WHERE id=?", (i,))
    db.commit()
    flash("Aplikasi dihapus.", "ok")
    return redirect(url_for("admin", tab="aplikasi"))


@app.route("/admin/dokumentasi/tambah", methods=["POST"])
@wajib_login
def tambah_dokumentasi():
    judul = request.form.get("judul", "").strip()
    tanggal = request.form.get("tanggal", "") or datetime.now().strftime("%Y-%m-%d")
    hasil = simpan_file(request.files.get("foto"), EXT_GAMBAR)
    if not judul or not hasil:
        flash("Isi judul kegiatan dan pilih foto (JPG, PNG, atau WebP).", "galat")
    else:
        db = get_db()
        db.execute("INSERT INTO dokumentasi (judul, tanggal, keterangan, filename, created_at) VALUES (?,?,?,?,?)",
                   (judul, tanggal, request.form.get("keterangan", "").strip(), hasil[0],
                    datetime.now().strftime("%Y-%m-%d")))
        db.commit()
        flash("Foto kegiatan ditambahkan.", "ok")
    return redirect(url_for("admin", tab="dokumentasi"))


@app.route("/admin/dokumentasi/<int:i>/hapus", methods=["POST"])
@wajib_login
def hapus_dokumentasi(i):
    db = get_db()
    row = db.execute("SELECT filename FROM dokumentasi WHERE id=?", (i,)).fetchone()
    if row:
        hapus_file(row["filename"])
        db.execute("DELETE FROM dokumentasi WHERE id=?", (i,))
        db.commit()
        flash("Foto dihapus.", "ok")
    return redirect(url_for("admin", tab="dokumentasi"))


@app.route("/admin/permohonan/<int:i>/berkas/<jenis>")
@wajib_login
def admin_berkas(i, jenis):
    kolom = {"ktp": "ktp_file", "lampiran": "berkas_file"}.get(jenis)
    row = get_db().execute("SELECT * FROM permohonan WHERE id=?", (i,)).fetchone()
    if not row or not kolom or not row[kolom]:
        abort(404)
    resp = send_from_directory(UPLOAD_DIR, row[kolom])
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/admin/permohonan/<int:i>/ubah", methods=["POST"])
@wajib_login
def ubah_permohonan(i):
    status = request.form.get("status", "")
    if status not in STATUS_PERMOHONAN:
        abort(400)
    db = get_db()
    db.execute("UPDATE permohonan SET status=?, catatan=? WHERE id=?",
               (status, request.form.get("catatan", "").strip()[:2000], i))
    db.commit()
    flash("Status permohonan diperbarui.", "ok")
    return redirect(url_for("admin", tab="permohonan"))


@app.route("/admin/permohonan/<int:i>/hapus", methods=["POST"])
@wajib_login
def hapus_permohonan(i):
    db = get_db()
    row = db.execute("SELECT ktp_file, berkas_file FROM permohonan WHERE id=?", (i,)).fetchone()
    if row:
        hapus_file(row["ktp_file"])
        if row["berkas_file"]:
            hapus_file(row["berkas_file"])
        db.execute("DELETE FROM permohonan WHERE id=?", (i,))
        db.commit()
        flash("Permohonan dan berkas terkait dihapus.", "ok")
    return redirect(url_for("admin", tab="permohonan"))


@app.route("/admin/pesan/<int:i>/hapus", methods=["POST"])
@wajib_login
def hapus_pesan(i):
    db = get_db()
    db.execute("DELETE FROM pesan WHERE id=?", (i,))
    db.commit()
    flash("Pesan dihapus.", "ok")
    return redirect(url_for("admin", tab="pesan"))


def tanggal_valid(teks):
    try:
        return datetime.strptime(teks, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return datetime.now().strftime("%Y-%m-%d")


def cek_gambar_berita(f):
    """None bila tidak ada gambar yang dipilih, True bila valid, False bila tidak valid."""
    if not f or not f.filename:
        return None
    return cek_file(f, EXT_GAMBAR, 5 * 1024 * 1024, MAGIC_FOTO)


@app.route("/admin/berita/tambah", methods=["POST"])
@wajib_login
def tambah_berita():
    judul = request.form.get("judul", "").strip()[:200]
    isi = request.form.get("isi", "").strip()[:20000]
    gambar = request.files.get("gambar")
    if not judul or not isi:
        flash("Judul dan isi berita wajib diisi.", "galat")
    elif cek_gambar_berita(gambar) is False:
        flash("Gambar harus berformat JPG, PNG, atau WebP dengan ukuran maksimal 5 MB.", "galat")
    else:
        hasil = simpan_file(gambar, EXT_GAMBAR, 5 * 1024 * 1024, MAGIC_FOTO) if cek_gambar_berita(gambar) else None
        db = get_db()
        db.execute("INSERT INTO berita (judul, isi, tanggal, gambar, created_at) VALUES (?,?,?,?,?)",
                   (judul, isi, tanggal_valid(request.form.get("tanggal", "")), hasil[0] if hasil else "",
                    datetime.now().strftime("%Y-%m-%d %H:%M")))
        db.commit()
        flash("Berita diterbitkan.", "ok")
    return redirect(url_for("admin", tab="berita"))


@app.route("/admin/berita/<int:i>/edit", methods=["GET", "POST"])
@wajib_login
def edit_berita(i):
    db = get_db()
    b = db.execute("SELECT * FROM berita WHERE id=?", (i,)).fetchone()
    if not b:
        abort(404)
    if request.method == "POST":
        judul = request.form.get("judul", "").strip()[:200]
        isi = request.form.get("isi", "").strip()[:20000]
        gambar = request.files.get("gambar")
        if not judul or not isi:
            flash("Judul dan isi berita wajib diisi.", "galat")
        elif cek_gambar_berita(gambar) is False:
            flash("Gambar harus berformat JPG, PNG, atau WebP dengan ukuran maksimal 5 MB.", "galat")
        else:
            nama_gambar = b["gambar"]
            if cek_gambar_berita(gambar):
                baru = simpan_file(gambar, EXT_GAMBAR, 5 * 1024 * 1024, MAGIC_FOTO)
                if nama_gambar:
                    hapus_file(nama_gambar)
                nama_gambar = baru[0]
            elif request.form.get("hapus_gambar") and nama_gambar:
                hapus_file(nama_gambar)
                nama_gambar = ""
            db.execute("UPDATE berita SET judul=?, isi=?, tanggal=?, gambar=? WHERE id=?",
                       (judul, isi, tanggal_valid(request.form.get("tanggal", "")), nama_gambar, i))
            db.commit()
            flash("Berita diperbarui.", "ok")
            return redirect(url_for("admin", tab="berita"))
    return render_template("admin_berita_edit.html", b=b)


@app.route("/admin/berita/<int:i>/hapus", methods=["POST"])
@wajib_login
def hapus_berita(i):
    db = get_db()
    row = db.execute("SELECT gambar FROM berita WHERE id=?", (i,)).fetchone()
    if row:
        if row["gambar"]:
            hapus_file(row["gambar"])
        db.execute("DELETE FROM berita WHERE id=?", (i,))
        db.commit()
        flash("Berita dihapus.", "ok")
    return redirect(url_for("admin", tab="berita"))


@app.route("/admin/sosmed", methods=["POST"])
@wajib_login
def simpan_sosmed():
    nilai = {}
    for kunci, label, _ in SOSMED:
        v = request.form.get(kunci, "").strip()[:300]
        if v and not re.fullmatch(r"https?://\S+", v, re.I):
            flash(f"Tautan {label} harus diawali http:// atau https:// dan tidak boleh mengandung spasi.", "galat")
            return redirect(url_for("admin", tab="sosmed"))
        nilai[kunci] = v
    db = get_db()
    db.executemany("INSERT INTO pengaturan (kunci, nilai) VALUES (?,?) "
                   "ON CONFLICT(kunci) DO UPDATE SET nilai=excluded.nilai", list(nilai.items()))
    db.commit()
    flash("Tautan media sosial disimpan.", "ok")
    return redirect(url_for("admin", tab="sosmed"))


@app.route("/admin/survei/alamat", methods=["POST"])
@wajib_login
def simpan_alamat_publik():
    v = request.form.get("url_publik", "").strip().rstrip("/")[:200]
    if v and not re.fullmatch(r"https?://[^\s/]+(/\S*)?", v, re.I):
        flash("Alamat website harus diawali http:// atau https:// (contoh: https://dpmd.contoh.go.id).", "galat")
    else:
        db = get_db()
        db.execute("INSERT INTO pengaturan (kunci, nilai) VALUES ('url_publik', ?) "
                   "ON CONFLICT(kunci) DO UPDATE SET nilai=excluded.nilai", (v,))
        db.commit()
        flash("Alamat website untuk kode QR disimpan.", "ok")
    return redirect(url_for("admin", tab="survei"))


@app.route("/admin/survei/unduh.csv")
@wajib_login
def unduh_survei():
    kondisi, par = kondisi_survei(tanggal_filter(request.args.get("dari")), tanggal_filter(request.args.get("sampai")))
    rows = get_db().execute(f"SELECT * FROM survei WHERE {kondisi} ORDER BY id", par).fetchall()

    def aman(x):  # cegah rumus berbahaya saat dibuka di Excel
        x = str(x)
        return "'" + x if x[:1] in ("=", "+", "-", "@") else x

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["No", "Waktu"] + [label for _k, label, _p in SKM_PROFIL] + [judul for _k, judul, *_ in SKM_UNSUR] + ["Saran"])
    for i, r in enumerate(rows, 1):
        w.writerow([i, r["created_at"]] + [aman(r[k]) for k, _l, _p in SKM_PROFIL]
                   + [r[k] for k, *_ in SKM_UNSUR] + [aman(r["saran"] or "")])
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=survei-kepuasan.csv"})


@app.route("/admin/survei/<int:i>/hapus", methods=["POST"])
@wajib_login
def hapus_survei(i):
    db = get_db()
    db.execute("DELETE FROM survei WHERE id=?", (i,))
    db.commit()
    flash("Tanggapan survei dihapus.", "ok")
    return redirect(url_for("admin", tab="survei"))


@app.route("/admin/statistik/awal", methods=["POST"])
@wajib_login
def simpan_hitung_awal():
    v = request.form.get("hitung_awal", "").strip().replace(".", "").replace(" ", "")
    if v == "":
        v = "0"
    if not v.isdigit() or len(v) > 12:
        flash("Angka awal harus berupa bilangan bulat (tanpa huruf atau tanda minus).", "galat")
    else:
        db = get_db()
        db.execute("INSERT INTO pengaturan (kunci, nilai) VALUES ('hitung_awal', ?) "
                   "ON CONFLICT(kunci) DO UPDATE SET nilai=excluded.nilai", (str(int(v)),))
        db.commit()
        flash("Angka awal pengunjung disimpan.", "ok")
    return redirect(url_for("admin", tab="statistik"))


@app.route("/admin/profil/kadis", methods=["POST"])
@wajib_login
def simpan_kadis():
    foto = request.files.get("foto")
    status = cek_gambar_berita(foto)
    if status is False:
        flash("Foto harus berformat JPG, PNG, atau WebP dengan ukuran maksimal 5 MB.", "galat")
        return redirect(url_for("admin", tab="profil"))
    lama = ambil_pengaturan("kadis_foto")
    if status:
        baru = simpan_file(foto, EXT_GAMBAR, 5 * 1024 * 1024, MAGIC_FOTO)
        if lama:
            hapus_file(lama)
        simpan_pengaturan("kadis_foto", baru[0])
    elif request.form.get("hapus_foto") and lama:
        hapus_file(lama)
        simpan_pengaturan("kadis_foto", "")
    simpan_pengaturan("kadis_nama", request.form.get("nama", "").strip()[:120])
    simpan_pengaturan("kadis_jabatan", request.form.get("jabatan", "").strip()[:160])
    simpan_pengaturan("kadis_sambutan", request.form.get("sambutan", "").strip()[:12000])
    flash("Profil kepala dinas disimpan.", "ok")
    return redirect(url_for("admin", tab="profil"))


@app.route("/admin/profil/bagan", methods=["POST"])
@wajib_login
def simpan_bagan():
    gambar = request.files.get("gambar")
    status = cek_gambar_berita(gambar)
    lama = ambil_pengaturan("struktur_gambar")
    if request.form.get("hapus") and lama:
        hapus_file(lama)
        simpan_pengaturan("struktur_gambar", "")
        flash("Gambar bagan dihapus.", "ok")
    elif status is None:
        flash("Pilih gambar bagan terlebih dahulu.", "galat")
    elif status is False:
        flash("Gambar harus berformat JPG, PNG, atau WebP dengan ukuran maksimal 5 MB.", "galat")
    else:
        baru = simpan_file(gambar, EXT_GAMBAR, 5 * 1024 * 1024, MAGIC_FOTO)
        if lama:
            hapus_file(lama)
        simpan_pengaturan("struktur_gambar", baru[0])
        flash("Gambar bagan disimpan.", "ok")
    return redirect(url_for("admin", tab="profil"))


def _data_struktur():
    jabatan = request.form.get("jabatan", "").strip()[:160]
    nama = request.form.get("nama", "").strip()[:120]
    induk = request.form.get("induk_id", "")
    urut = request.form.get("urutan", "").strip()
    return jabatan, nama, int(induk) if induk.isdigit() else None, min(int(urut), 999) if urut.isdigit() else 0


@app.route("/admin/struktur/tambah", methods=["POST"])
@wajib_login
def tambah_struktur():
    jabatan, nama, induk, urut = _data_struktur()
    db = get_db()
    if not jabatan:
        flash("Nama jabatan wajib diisi.", "galat")
    elif induk is not None and not db.execute("SELECT 1 FROM struktur WHERE id=?", (induk,)).fetchone():
        flash("Atasan yang dipilih tidak ditemukan.", "galat")
    else:
        db.execute("INSERT INTO struktur (induk_id, urutan, jabatan, nama) VALUES (?,?,?,?)", (induk, urut, jabatan, nama))
        db.commit()
        flash("Jabatan ditambahkan.", "ok")
    return redirect(url_for("admin", tab="profil"))


@app.route("/admin/struktur/<int:i>/edit", methods=["GET", "POST"])
@wajib_login
def edit_struktur(i):
    db = get_db()
    n = db.execute("SELECT * FROM struktur WHERE id=?", (i,)).fetchone()
    if not n:
        abort(404)
    terlarang = id_turunan(db, i) | {i}
    if request.method == "POST":
        jabatan, nama, induk, urut = _data_struktur()
        if not jabatan:
            flash("Nama jabatan wajib diisi.", "galat")
        elif induk is not None and (induk in terlarang or not db.execute("SELECT 1 FROM struktur WHERE id=?", (induk,)).fetchone()):
            flash("Atasan tidak valid: sebuah jabatan tidak boleh berada di bawah dirinya sendiri atau bawahannya.", "galat")
        else:
            db.execute("UPDATE struktur SET induk_id=?, urutan=?, jabatan=?, nama=? WHERE id=?", (induk, urut, jabatan, nama, i))
            db.commit()
            flash("Jabatan diperbarui.", "ok")
            return redirect(url_for("admin", tab="profil"))
    pilihan = [x for x in ratakan_struktur(ambil_struktur()) if x["id"] not in terlarang]
    return render_template("admin_struktur_edit.html", n=n, pilihan=pilihan)


@app.route("/admin/struktur/<int:i>/hapus", methods=["POST"])
@wajib_login
def hapus_struktur(i):
    db = get_db()
    n = db.execute("SELECT induk_id FROM struktur WHERE id=?", (i,)).fetchone()
    if n:
        db.execute("UPDATE struktur SET induk_id=? WHERE induk_id=?", (n["induk_id"], i))  # bawahan naik satu tingkat
        db.execute("DELETE FROM struktur WHERE id=?", (i,))
        db.commit()
        flash("Jabatan dihapus. Bawahannya dipindahkan ke atasan di atasnya.", "ok")
    return redirect(url_for("admin", tab="profil"))


@app.route("/admin/kutipan/tambah", methods=["POST"])
@wajib_login
def tambah_kutipan():
    db, jumlah = get_db(), 0
    for baris in request.form.get("kutipan", "").splitlines()[:100]:
        teks, _, penulis = baris.partition("|")
        teks, penulis = teks.strip().strip('"\u201c\u201d'), penulis.strip()
        if teks:
            db.execute("INSERT INTO kutipan (teks, penulis) VALUES (?,?)", (teks[:400], penulis[:100]))
            jumlah += 1
    db.commit()
    flash(f"{jumlah} kutipan ditambahkan." if jumlah else "Tulis minimal satu kutipan.", "ok" if jumlah else "galat")
    return redirect(url_for("admin", tab="kutipan"))


@app.route("/admin/kutipan/<int:i>/hapus", methods=["POST"])
@wajib_login
def hapus_kutipan(i):
    db = get_db()
    db.execute("DELETE FROM kutipan WHERE id=?", (i,))
    db.commit()
    flash("Kutipan dihapus.", "ok")
    return redirect(url_for("admin", tab="kutipan"))


@app.errorhandler(404)
def tidak_ada(_e):
    return render_template("404.html"), 404


@app.errorhandler(413)
def kebesaran(_e):
    flash("Ukuran berkas melebihi batas 25 MB.", "galat")
    return redirect(request.referrer or url_for("home"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
