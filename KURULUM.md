# Kurulum

sahibinden ilanlarını tarayıcıda yakalayıp TypeSafe (Jev) ile eleyen yerel bir araç.
Her şey kendi bilgisayarında çalışır; veri dışarı çıkmaz. Tek istisna: değerlendirme
sırasında ilan metni TypeSafe API'sine gider.

Kurulum 5 dakika. Sırayla git.

---

## 1. Gerekenler

- **Windows** (macOS/Linux'ta da çalışır, komutlar biraz değişir)
- **Google Chrome**
- **uv** — Python'u da kendisi indiriyor, ayrıca Python kurmana gerek yok

`uv` kurulu değilse PowerShell aç ve şunu çalıştır:

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

Bittiğinde **PowerShell penceresini kapat ve yenisini aç.** Kurulum `uv`'yi PATH'e
ekliyor ama açık pencereler bunu görmez.

Kontrol:

```powershell
uv --version
```

---

## 2. Klasörü aç

Zip'i istediğin yere çıkar, örneğin `C:\typesafe-jev`. Yol Türkçe karakter
içermesin, işleri kolaylaştırır.

---

## 3. Sunucuyu başlat

Klasördeki **`basla.cmd`** dosyasına çift tıkla.

İlk açılışta `uv` bağımlılıkları indirir, yarım dakika sürebilir. Şunu görmelisin:

```
  Ilan Eleme  -  http://127.0.0.1:8765
  Tarayicida bu adresi ac. Durdurmak icin Ctrl+C.
```

Bu pencere açık kaldığı sürece araç çalışır. Kapatmak için `Ctrl+C`.

---

## 4. Chrome eklentisini yükle

1. Chrome'da `chrome://extensions` adresine git
2. Sağ üstten **Geliştirici modu**'nu aç
3. **Paketlenmemiş öğe yükle** → zip'i çıkardığın klasördeki **`extension`** klasörünü seç

"Ilan Yakala" göründüyse tamam.

> Eklenti dosyaları değişirse aynı sayfadaki **↻** düğmesine bas, sonra açık
> sahibinden sekmelerini **F5** ile yenile.

---

## 5. API anahtarı al ve gir

1. https://console.typesafe.ai/keys adresinden bir anahtar oluştur
2. `http://127.0.0.1:8765` adresini aç
3. Sağ üstte **Ayarlar** → anahtarı yapıştır → **Kaydet** → **Doğrula**

"Çalışıyor. Modeller: jev-latest, jev-preview" yazıyorsa hazırsın.

Anahtar klasördeki `.env` dosyasına yazılır, başka hiçbir yere gitmez.

**Maliyet:** bir ilan ≈ 3.500 token ≈ **0,00015 dolar**. Yani 1000 ilan ≈ 15 sent.

---

## 6. Kullan

**Tek ilanı anında değerlendir**
Bir sahibinden ilanına gir. Sağ altta panel çıkar → **Değerlendir**.
Sonuç: favoriye değer / emin değil / değmez, uygunluk yüzdesi, kırmızı bayraklar,
ve o çağrının süresi, token'ı, maliyeti.

**Nasıl karar verdiğini izle**
Değerlendirmeden sonra **"Nasıl karar verdi? ▸"**. Sorular eş zamanlı dolar,
sonra kod kapıları sırayla açılır, ağırlıklı skor terim terim birikir.
Gösterim hızı 1x / 2x / 5x / 10x.

**Arşive kaydet**
Aynı panelden. Aynı ilanı sonra tekrar kaydedersen üzerine yazmaz, yeni sürüm
ekler — fiyat düşerse görürsün.

**Toplu eleme**
`http://127.0.0.1:8765` → soldan kesin sınırları ve profilini gir →
**Elemeyi çalıştır**. Önce kod filtresi (anlık ve bedava), kalanlar Jev'e gider.

**Arşivi yönet**
Eklenti araç çubuğu düğmesi → ara, detay aç, ilana git, sil.

**Kendi sorularını ekle**
Panelde **Sorular**. Yerleşik sorular değişmez; kendi sorularını
evet/hayır, dereceli veya seçenekli olarak eklersin. Evet/hayır sorusunu
"kırmızı bayrak" yaparsan tek başına eleyebilir; dereceli soruya ağırlık
verirsen skora katılır. **Varsayılana dön** yalnızca senin eklediklerini siler.

---

## Sorun giderme

**`uv` bulunamadı**
Kurulu ama terminalin eski. Yeni bir pencere aç. Ya da mevcut pencerede:
```powershell
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ';' + [Environment]::GetEnvironmentVariable("Path","User")
```

**"Sunucu ZATEN CALISIYOR" diyor**
Başka bir pencerede açık. Tarayıcıdan adresi açman yeterli. Gerçekten durdurmak için:
```powershell
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8765 -State Listen).OwningProcess -Force
```

**Panelde "sunucuya ulaşılamadı"**
`basla.cmd` çalışmıyor. Başlat.

**Panel ilan sayfasında çıkmıyor**
Eklenti yüklü mü? `chrome://extensions` → yenile → sayfayı F5 yap.
Panel yalnızca ilan **detay** sayfalarında çıkar, arama listesinde çıkmaz.

**"TYPESAFE_API_KEY tanımlı değil"**
Adım 5'i yap.

---

## Not

Eklenti hiçbir şeyi kendiliğinden yapmaz: gezmez, sayfa açmaz, arka planda istek
atmaz. Yalnızca sen bakarken, sen tıklayınca, o anki sayfayı okur. Otomatik
değerlendirme seçeneği kapalı gelir.
