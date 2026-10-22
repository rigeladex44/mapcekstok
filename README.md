# Bot laporan stok pangkalan

Bot Telegram untuk mengambil stok dan laporan pangkalan dari MyPertamina.

## Menjalankan

Gunakan Python 3.11 atau lebih baru:

```sh
python -m pip install -r requirements.txt
python -m playwright install chromium
python BOT_STOK.py
```

Simpan `BOT_TOKEN`, `ALLOWED_CHAT_ID`, dan `HEADLESS` di `BOT_STOK.env` sesuai contoh. Simpan cadangan konfigurasi dan `accounts.json` sebelum memperbarui. Jadwal otomatis menggunakan 08:05 WIB, terlepas dari zona waktu VPS. Jalankan hanya satu instance polling untuk token yang sama.

## Perbaikan laporan

- Akun yang gagal atau timeout dicoba maksimal tiga kali total, dengan jeda 3 lalu 6 detik. Akun yang berhasil tidak diulang. Setelah batas tersebut, email akun masuk daftar kegagalan tanpa PIN.
- Stok dibaca dari bagian dengan label stok yang terlihat, bukan angka Tabung pertama di halaman. Nilai ambigu atau hilang menggagalkan akun dan memicu retry. Angka ribuan seperti `1.820` dibaca sebagai `1820`.
- Stok merupakan nilai dashboard pada saat akun diperiksa sebelum membuka laporan penjualan, bukan hasil perhitungan stok dari transaksi.
- Kategori yang tidak terbaca ditampilkan sebagai `Tidak Diketahui`. Total laporan yang hilang dan kegagalan filter tanggal menggagalkan akun, bukan dianggap nol.
- Sesi browser dibersihkan ketika timeout; pekerjaan bersamaan untuk chat yang sama ditolak.
- Pengiriman Telegram memecah pesan panjang dan menangani pembatasan laju. Koneksi memakai verifikasi TLS; jika VPS mengalami error sertifikat, perbaiki CA/jam sistemnya.

## Pengujian

```sh
python -m unittest discover -s tests -v
```

Pengujian memakai browser lokal dan halaman HTML buatan, tanpa login ke akun produksi atau mengirim pesan Telegram. Playwright memakai Chromium yang telah diinstal; `TEST_CHROMIUM_PATH` dapat menunjuk executable lain.

Label dan struktur halaman MyPertamina yang sedang aktif perlu divalidasi sebelum penggunaan produksi. Jika label berbeda, sesuaikan `read_stock`; jangan kembali mengambil angka pertama tanpa label. Periksa hasil pada satu akun dan bandingkan dengan dashboard sebelum menjalankan semua akun.

Jangan unggah token atau PIN ke repositori publik. `.gitignore` hanya melindungi file yang belum dilacak; file rahasia yang sudah ada di Git harus ditangani terpisah.
