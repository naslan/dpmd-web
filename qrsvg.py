"""Pembuat kode QR sederhana (tanpa pustaka luar). Mode byte, koreksi kesalahan M, versi 1-10.
Cukup untuk alamat web hingga sekitar 213 karakter.  qr_svg("https://...") -> teks SVG."""

# (total codeword, ecc per blok, [(jumlah blok, data codeword per blok), ...]) untuk level M
_VERSI = {
    1: (26, 10, [(1, 16)]), 2: (44, 16, [(1, 28)]), 3: (70, 26, [(1, 44)]), 4: (100, 18, [(2, 32)]),
    5: (134, 24, [(2, 43)]), 6: (172, 16, [(4, 27)]), 7: (196, 18, [(4, 31)]),
    8: (242, 22, [(2, 38), (2, 39)]), 9: (292, 22, [(3, 36), (2, 37)]), 10: (346, 26, [(4, 43), (1, 44)]),
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38],
          8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _kali(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _ecc(data, n):
    gen = [1]
    for i in range(n):
        nxt = [0] * (len(gen) + 1)
        for j, g in enumerate(gen):
            nxt[j] ^= g
            nxt[j + 1] ^= _kali(g, _EXP[i])
        gen = nxt
    sisa = list(data) + [0] * n
    for i in range(len(data)):
        f = sisa[i]
        if f:
            for j in range(1, len(gen)):
                sisa[i + j] ^= _kali(gen[j], f)
    return sisa[len(data):]


def _format_bits(mask):
    data = (0b00 << 3) | mask  # level M = 00
    v = data << 10
    for i in range(14, 9, -1):
        if v & (1 << i):
            v ^= 0x537 << (i - 10)
    return ((data << 10) | v) ^ 0x5412


def _versi_bits(ver):
    v = ver << 12
    for i in range(17, 11, -1):
        if v & (1 << i):
            v ^= 0x1F25 << (i - 12)
    return (ver << 12) | v


def _pilih_versi(n):
    for ver in range(1, 11):
        data_cw = sum(b * d for b, d in _VERSI[ver][2])
        kapasitas = (data_cw * 8 - 4 - (8 if ver < 10 else 16)) // 8
        if n <= kapasitas:
            return ver, data_cw
    raise ValueError("Teks terlalu panjang untuk kode QR (maksimal sekitar 213 karakter)")


def buat_matriks(teks, mask=None):
    data = teks.encode("utf-8")
    ver, data_cw = _pilih_versi(len(data))
    ukuran = 17 + 4 * ver

    # --- aliran bit data
    bits = [0, 1, 0, 0]
    jml_bit = 8 if ver < 10 else 16
    bits += [(len(data) >> i) & 1 for i in range(jml_bit - 1, -1, -1)]
    for byte in data:
        bits += [(byte >> i) & 1 for i in range(7, -1, -1)]
    total_bit = data_cw * 8
    bits += [0] * min(4, total_bit - len(bits))
    while len(bits) % 8:
        bits.append(0)
    cw = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = [0xEC, 0x11]
    i = 0
    while len(cw) < data_cw:
        cw.append(pad[i % 2])
        i += 1

    # --- pecah blok, hitung ECC, interleave
    _total, ecc_n, grup = _VERSI[ver]
    blok, pos = [], 0
    for jumlah, ukur in grup:
        for _ in range(jumlah):
            blok.append(cw[pos:pos + ukur])
            pos += ukur
    ecc_blok = [_ecc(b, ecc_n) for b in blok]
    akhir = []
    for k in range(max(len(b) for b in blok)):
        for b in blok:
            if k < len(b):
                akhir.append(b[k])
    for k in range(ecc_n):
        for e in ecc_blok:
            akhir.append(e[k])
    aliran = []
    for byte in akhir:
        aliran += [(byte >> i) & 1 for i in range(7, -1, -1)]

    # --- peta modul fungsi
    M = [[0] * ukuran for _ in range(ukuran)]
    fungsi = [[False] * ukuran for _ in range(ukuran)]

    def set_f(r, c, v):
        if 0 <= r < ukuran and 0 <= c < ukuran:
            M[r][c] = v
            fungsi[r][c] = True

    def finder(r0, c0):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = r0 + dr, c0 + dc
                if not (0 <= r < ukuran and 0 <= c < ukuran):
                    continue
                dalam = 0 <= dr <= 6 and 0 <= dc <= 6
                v = 1 if dalam and (dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4)) else 0
                set_f(r, c, v)

    finder(0, 0)
    finder(0, ukuran - 7)
    finder(ukuran - 7, 0)
    for k in range(8, ukuran - 8):
        set_f(6, k, 1 - k % 2)
        set_f(k, 6, 1 - k % 2)
    pos_a = _ALIGN[ver]
    for r in pos_a:
        for c in pos_a:
            if (r <= 8 and c <= 8) or (r <= 8 and c >= ukuran - 9) or (r >= ukuran - 9 and c <= 8):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    set_f(r + dr, c + dc, 1 if max(abs(dr), abs(dc)) != 1 else 0)
    set_f(ukuran - 8, 8, 1)  # modul gelap
    # area format & versi dicadangkan
    for k in range(9):
        if not fungsi[8][k]: set_f(8, k, 0)
        if not fungsi[k][8]: set_f(k, 8, 0)
    for k in range(8):
        if not fungsi[8][ukuran - 1 - k]: set_f(8, ukuran - 1 - k, 0)
        if not fungsi[ukuran - 1 - k][8]: set_f(ukuran - 1 - k, 8, 0)
    set_f(ukuran - 8, 8, 1)
    if ver >= 7:
        vb = _versi_bits(ver)
        for k in range(18):
            bit = (vb >> k) & 1
            a, b = k // 3, ukuran - 11 + k % 3
            set_f(a, b, bit)
            set_f(b, a, bit)

    # --- tempatkan data zig-zag
    pola = []
    c = ukuran - 1
    naik = True
    while c > 0:
        if c == 6:
            c -= 1
        rentang = range(ukuran - 1, -1, -1) if naik else range(ukuran)
        for r in rentang:
            for dc in (0, 1):
                if not fungsi[r][c - dc]:
                    pola.append((r, c - dc))
        naik = not naik
        c -= 2
    for idx, (r, c) in enumerate(pola):
        M[r][c] = aliran[idx] if idx < len(aliran) else 0

    mask_fn = [
        lambda r, c: (r + c) % 2 == 0, lambda r, c: r % 2 == 0, lambda r, c: c % 3 == 0,
        lambda r, c: (r + c) % 3 == 0, lambda r, c: (r // 2 + c // 3) % 2 == 0,
        lambda r, c: (r * c) % 2 + (r * c) % 3 == 0, lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
        lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
    ]

    def terapkan(mask):
        T = [row[:] for row in M]
        for r in range(ukuran):
            for c in range(ukuran):
                if not fungsi[r][c] and mask_fn[mask](r, c):
                    T[r][c] ^= 1
        fb = _format_bits(mask)
        # salinan 1 (sekitar finder kiri-atas) dan salinan 2
        for k in range(15):
            bit = (fb >> k) & 1
            if k < 6: T[k][8] = bit
            elif k < 8: T[k + 1][8] = bit
            else: T[ukuran - 15 + k][8] = bit
            if k < 8: T[8][ukuran - 1 - k] = bit
            elif k < 9: T[8][15 - k] = bit
            else: T[8][14 - k] = bit
        return T

    def penalti(T):
        p = 0
        for baris in (T, [list(x) for x in zip(*T)]):
            for row in baris:
                jalan = 1
                for i in range(1, ukuran):
                    if row[i] == row[i - 1]:
                        jalan += 1
                    else:
                        if jalan >= 5: p += jalan - 2
                        jalan = 1
                if jalan >= 5: p += jalan - 2
        for r in range(ukuran - 1):
            for c in range(ukuran - 1):
                if T[r][c] == T[r][c + 1] == T[r + 1][c] == T[r + 1][c + 1]:
                    p += 3
        pola1, pola2 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
        for baris in (T, [list(x) for x in zip(*T)]):
            for row in baris:
                for i in range(ukuran - 10):
                    seg = row[i:i + 11]
                    if seg == pola1 or seg == pola2:
                        p += 40
        gelap = sum(map(sum, T))
        p += (abs(gelap * 20 - ukuran * ukuran * 10) // (ukuran * ukuran)) * 10
        return p

    if mask is not None:
        return terapkan(mask)
    return min((terapkan(m) for m in range(8)), key=penalti)


def qr_svg(teks, modul=8, tepi=4):
    T = buat_matriks(teks)
    n = len(T)
    total = (n + 2 * tepi)
    path = []
    for r in range(n):
        c = 0
        while c < n:
            if T[r][c]:
                awal = c
                while c < n and T[r][c]:
                    c += 1
                path.append(f"M{awal + tepi} {r + tepi}h{c - awal}v1h-{c - awal}z")
            else:
                c += 1
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {total}" width="{total * modul}" '
            f'height="{total * modul}" shape-rendering="crispEdges" role="img" aria-label="Kode QR">'
            f'<rect width="{total}" height="{total}" fill="#fff"/><path d="{"".join(path)}" fill="#000"/></svg>')
