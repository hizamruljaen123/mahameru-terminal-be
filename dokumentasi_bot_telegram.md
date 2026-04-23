# 🤖 DOKUMENTASI BOT TELEGRAM: ASETPEDIA INTELLIGENCE

Bot Telegram Asetpedia dirancang untuk memberikan intelijen finansial (Saham, Crypto, Forex, Komoditi) secara instan langsung ke grup Anda. Bot ini beroperasi dalam mode **Restricted** (hanya membalas di grup yang diizinkan) dan **Tag-Aware** (hanya merespons jika di-mention).

---

## 📋 Daftar Perintah (Menu)

### 1. `/update [SIMBOL]` - Intelijen Entitas Terpadu
Memberikan laporan komprehensif mengenai aset tertentu dalam satu balasan.
- **Input**: Kode ticker (contoh: `AAPL`, `BTC-USD`, `BBCA.JK`, `GOLD`).
- **Output**:
    - 📊 **Grafik Intraday**: Grafik harga real-time (Dark Mode).
    - 📋 **Tabel OHLCV**: Daftar 20 data harga terakhir (Open, High, Low, Close, Volume).
    - 📰 **Berita Terkini**: Headline berita intelijen terbaru terkait aset tersebut.
- **Cara Pakai**: `@AsetpediaBot /update NVDA`

### 2. `/analyze [SIMBOL]` - AI Technical Verdict
Menjalankan mesin AI Multi-Agent untuk memberikan analisis teknis mendalam.
- **Input**: Kode ticker.
- **Output**: Vonis akhir dari AI (STRONG BUY / HOLD / SELL) beserta alasan teknis berdasarkan indikator RSI, MACD, dan Bollinger Bands.
- **Cara Pakai**: `@AsetpediaBot /analyze BTC`

### 3. `/market_pulse` - Ringkasan Pasar Global
Memberikan gambaran cepat mengenai kondisi pasar dunia saat ini.
- **Output**: Daftar top gainers dan pergerakan persentase dari berbagai kategori (Indices, Cryptocurrency, Forex, dan Commodities).
- **Cara Pakai**: `@AsetpediaBot /market_pulse`

### 4. `/get_id` - Informasi Identitas Chat
Digunakan untuk keperluan konfigurasi keamanan bot.
- **Output**: Menampilkan ID Chat/Grup saat ini. ID ini harus dimasukkan ke dalam file `.env` pada variabel `TELEGRAM_CHAT_ID` agar bot terkunci hanya untuk grup tersebut.
- **Cara Pakai**: `/get_id` (Bisa dijalankan tanpa tag).

---

## 🔐 Fitur Keamanan & Interaksi

### A. Mode Balas Langsung (Direct Reply)
Bot akan selalu membalas (*reply*) langsung ke pesan Anda. Hal ini memudahkan pelacakan di grup yang ramai sehingga jawaban tidak tertukar dengan permintaan user lain.

### B. Mode Tag (Mention)
Di dalam grup, Anda **wajib** men-tag username bot (contoh: `@UsernameBot`) di awal perintah agar bot merespons. Ini mencegah bot memproses percakapan normal anggota grup.

### C. Restriksi Grup (Chat ID Lockdown)
Bot hanya akan melayani perintah (kecuali `/get_id`) jika pesan berasal dari ID grup yang telah didaftarkan di file `.env`. Pesan dari grup lain atau orang asing akan diabaikan secara otomatis.

---

> [!TIP]
> **Tips Pencarian Simbol**:
> - Saham Indonesia: Tambahkan `.JK` (contoh: `TLKM.JK`)
> - Crypto: Tambahkan `-USD` (contoh: `ETH-USD`)
> - Forex: Gunakan format 6 huruf (contoh: `USDIDR=X` atau `EURUSD=X`)

---
*Dihasilkan oleh Asetpedia Documentation Engine - 2026*
