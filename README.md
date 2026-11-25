# Website DPMD (Dinas Pemberdayaan Masyarakat dan Desa)

Flask + SQLite. Menu: HOME, PROFIL, PPID PELAKSANA, APLIKASI, DOKUMENTASI, KONTAK.
Admin mengunggah dokumen PPID, foto kegiatan, dan daftar aplikasi; publik dapat melihat dan mengunduh tanpa login.

## Menjalankan (uji lokal)
    python -m venv venv
    source venv/bin/activate        # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    export ADMIN_PASSWORD="kata-sandi-kuat"   # Windows: set ADMIN_PASSWORD=...
    python app.py
Buka http://127.0.0.1:5000 , admin di http://127.0.0.1:5000/admin

## Pengaturan
- Data dinas (nama daerah, alamat, telepon, surel, jam layanan) dan teks PROFIL (tugas, visi, misi, bidang):
  ubah di bagian PENGATURAN pada `app.py`. Teks bawaan hanyalah contoh.
- Variabel lingkungan: `ADMIN_USER` (bawaan admin), `ADMIN_PASSWORD` (wajib; minimal 12 karakter),
  `SECRET_KEY` (opsional, mekanisme file key yang ada tetap dipakai), `COOKIE_SECURE` (atur `true` jika HTTPS),
  `DATA_DIR` (lokasi database dan unggahan, bawaan folder `data/`). Website akan berhenti jika `ADMIN_PASSWORD` kosong atau kurang dari 12 karakter.

## Produksi (server sendiri)
    gunicorn -w 2 -b 127.0.0.1:8000 app:app
Letakkan di belakang Nginx/Apache dengan HTTPS. Set `client_max_body_size 25m;` di Nginx.

## Cadangan
Seluruh data ada di folder `data/` (database `dpmd.db` dan folder `uploads/`). Cukup salin folder itu secara berkala.

## Permohonan informasi publik
- Formulir: `/ppid-pelaksana/permohonan`; cek status: `/ppid-pelaksana/status`.
- Petugas menindaklanjuti di panel admin, tab **Permohonan** (lihat detail, foto KTP, lampiran, ubah status, catatan).
- Foto KTP dan lampiran hanya dapat dibuka admin. Pasang website dengan HTTPS karena formulir memuat NIK dan foto KTP.
- Opsional: simpan format baku surat sebagai `static/files/form-permohonan-informasi.docx` agar tombol unduh template muncul.

## Menjalankan dengan waitress (Windows atau Linux)
    pip install -r requirements.txt
    set ADMIN_PASSWORD=kata-sandi-kuat        (Linux/Mac: export ADMIN_PASSWORD=...)
    python serve.py
Alamat bawaan http://127.0.0.1:8000 . Di Windows cukup klik dua kali `jalankan.bat`.
Untuk menerima akses dari jaringan: set HOST=0.0.0.0 dan PORT sesuai kebutuhan, atau letakkan di belakang IIS/Nginx dengan HTTPS.

## Berita dan media sosial
- Admin menerbitkan, mengubah, dan menghapus berita di panel admin, tab **Berita** (judul, tanggal, isi, gambar opsional). Berita tampil di beranda (3 terbaru) dan halaman `/berita`.
- Tautan **Instagram, Facebook, Twitter, YouTube, dan TikTok** diatur di tab **Media sosial**. Kolom yang dikosongkan tidak ditampilkan. Ikon muncul di footer dan halaman Kontak.

## Survei Kepuasan Masyarakat dan kode QR
- Halaman survei: `/survei` (9 unsur sesuai Permenpan RB No. 14 Tahun 2017, tanpa identitas pribadi). Poster QR siap cetak: `/survei/cetak`.
- Di panel admin, tab **Survei**: lihat Indeks Kepuasan Masyarakat (skala 25-100) dan mutu A-D, nilai per unsur, saran masuk, filter periode, unduh data CSV, dan hapus tanggapan spam.
- **Penting:** isi *Alamat website resmi* di tab Survei sebelum mencetak QR. Tanpa itu, QR memakai alamat yang sedang dibuka (misalnya `127.0.0.1`) yang tidak bisa dibuka dari HP lain.
- Kode QR dibuat oleh `qrsvg.py` tanpa pustaka tambahan. Ini QR biasa yang membuka halaman survei, bukan QRIS pembayaran.
- Pertanyaan dan pilihan profil responden dapat diubah di `SKM_UNSUR` dan `SKM_PROFIL` pada `app.py`.

## Logo provinsi di halaman Home
Simpan logo provinsi sebagai `static/img/logo-provinsi.png` (boleh juga `.webp`, `.svg`, `.jpg`). Logo otomatis tampil di kiri logo dinas pada banner Home, di samping nama dinas. Tanpa berkas itu, hanya logo dinas yang tampil.

## Kotak pencarian transparan
Tingkat bening kotak "Cari dokumen publik" diatur pada angka `.25` di aturan `.cari` pada `static/css/style.css` (`rgba(10,40,28,.25)`). Angka lebih kecil = lebih bening.

## Penghitung pengunjung
- Tampil di footer semua halaman publik: total pengunjung (gaya penghitung digital), hari ini, kemarin, bulan ini, dan sedang online.
- Cara hitung: satu pengunjung dihitung sekali per hari. Dikenali dari sidik (hash) IP dan browser yang diacak harian; **IP dan cookie tidak disimpan**. Kunjungan admin, bot, serta unduhan berkas dan gambar tidak dihitung.
- Admin: tab **Statistik** menampilkan grafik 30 hari dan kolom **Angka awal** untuk melanjutkan hitungan dari website lama.
- Di belakang Nginx/IIS, teruskan header `X-Forwarded-For` agar pengunjung berbeda tidak dianggap satu orang.

## Profil: kepala dinas, struktur organisasi, dan kutipan harian
- Admin, tab **Profil**: isi nama, foto, dan sambutan kepala dinas; unggah gambar bagan resmi (opsional); kelola **susunan jabatan** yang otomatis menjadi bagan di halaman Profil. Daftar jabatan bawaan hanyalah contoh, sesuaikan dengan struktur resmi.
- Sambutan tidak tampil di halaman Profil sebelum diisi.
- Admin, tab **Kutipan**: kelola kutipan. Beranda menampilkan satu kutipan per hari, bergilir mengikuti tanggal. Isi awal berupa peribahasa dan kalimat motivasi umum; hapus atau tambah sesuai kebutuhan. Untuk kutipan tokoh, cantumkan sumbernya dengan format `kutipan | nama`.

## Catatan keamanan (pembaruan)
- Login admin dibatasi maksimal 5 percobaan gagal per alamat IP dalam jendela 15 menit; blokir 15 menit (pembatasan dalam memori per proses). Untuk deployment multi-worker, tambahkan limiter berbasis Redis/server.
- Header keamanan ditambahkan: CSP dasar, X-Frame-Options, Permissions-Policy, dan Cross-Origin-Opener-Policy. CSP mengizinkan inline script/style karena template saat ini menggunakannya; ini dapat diperketat setelah inline script dipindahkan.
- Validasi signature foto diperketat: JPG/PNG harus cocok dengan ekstensi; WebP harus memiliki header RIFF dan WEBP.
- Di hosting HTTPS, atur `COOKIE_SECURE=true`. Jangan mengaktifkannya saat uji localhost HTTP biasa.
- Jangan unggah folder `data/`, database, foto KTP, file upload, atau `secret.key` ke repository publik.
