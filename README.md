# typesafe-jev

sahibinden ilanlarını tarayıcıda yakalayıp TypeSafe (Jev) ile eleyen yerel araç.

Üç parça:

| Parça | Ne yapar |
|---|---|
| `extension/` | Chrome eklentisi — gezdiğin ilanı tek tıkla yapılandırır, sayfada anlık karar verir |
| `server/` | Yerel arşiv + eleme sunucusu (`127.0.0.1:8765`), veri makineden çıkmaz |
| `tools/` | Kaydedilmiş bir sayfa üzerinde çıkarımı siteye dokunmadan test eden koşum |

## Başlatma

```
basla.cmd
```

Çift tıklamak da yeter. `uv` PATH'te değilse bilinen kurulum yerine bakar.

Elle başlatmak istersen:

```
uv run python -m server.app
```

Sonra `http://127.0.0.1:8765`.

> **`uv` bulunamadı diyorsa:** büyük ihtimalle kurulu ama terminalin eski.
> `C:\Users\<kullanıcı>\.local\bin` kullanıcı PATH'ine kurulumda ekleniyor,
> o an açık olan terminaller bunu görmez. **Yeni bir terminal aç.** Ya da
> mevcut pencerede bir kez:
> ```
> $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ';' + [Environment]::GetEnvironmentVariable("Path","User")
> ```

## Eklentiyi kurma

`chrome://extensions` → Geliştirici modu → **Paketlenmemiş öğe yükle** → `extension/`

Eklenti dosyaları değiştiğinde aynı sayfadan **↻ yenile**.

## API anahtarı

Panelde **Ayarlar** → anahtarı yapıştır → **Kaydet** → **Doğrula**.
`.env` dosyasına yazılır, git'e girmez, yanıtlarda maskelenir.

## Kullanım

- **Sayfada anlık karar** — ilan sayfasındaki panelden *Değerlendir*. Tek çağrı,
  8 soru, sonuç + süre + token + maliyet.
- **Arşive kaydet** — aynı panelden. Aynı ilan tekrar kaydedilirse üzerine
  yazılmaz, yeni sürüm eklenir (fiyat geçmişi).
- **Toplu eleme** — panelde kesin sınırları ve profili ayarla, *Elemeyi çalıştır*.
  Önce kod filtresi (bedava, ~0.02 ms), kalanlar Jev'e gider.
- **Arşiv yönetimi** — eklenti popup'ından ara, detay aç, ilana git, sil.

## Ölçülen maliyet

Bir ilan, 8 soru, tek çağrı:

| | |
|---|---|
| süre | ~750 ms |
| girdi tokeni | ~2.200 |
| maliyet | ~$0.00009 |
| 1000 ilan | ~$0.09 |

Fiyat girdi tokeni başına olduğu için **soru sayısı değil, metin uzunluğu**
maliyeti belirler: ilan bir kez gönderilir, 8 soru onun üstüne çok az ekler.
Gerçek sayılar `data/kullanim.json` defterinde birikir.

## İş bölümü

Sayısal ve kesin olan her şey **kodda**: fiyat, m², aidat, mesafe, poligon.
Jev'e yalnızca metinden çıkan yargılar sorulur: çelişki, abartı, satıcı dili,
profile uygunluk. Nihai karar yine kodda — kırmızı bayraklar ayrı koşul,
tercihler ağırlıklı skor.
