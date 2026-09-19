# Plan — Fırsat Rozeti

> Durum: **fikir aşaması.** Kod yazılmadı. Bu belge, başlandığında nereden
> devam edileceğini tutuyor.

## Fikir

Seçilmiş alışveriş sitelerinde gezerken ürün sayfalarını sessizce kaydeden bir
tarayıcı eklentisi. Aynı ürünü daha önce başka bir platformda gördüysen ve
buradaki belirgin şekilde ucuzsa büyük bir **FIRSAT** rozeti gösterir.

Kayıt pasif: sen gezerken okur, gezmez, arama yapmaz. İlan Yakala'nın
öğrendiğimiz kalıbının aynısı.

## Neden Jev'in işi

Ürün eşleştirme **anlam** işi:

```
"Apple iPhone 15 128GB Mavi"
"iPhone 15  Mavi  128 GB (Apple Türkiye Garantili)"     → aynı
"iPhone 15 Pro 128GB Mavi"                              → FARKLI
"iPhone 15 128GB Mavi + kılıf + cam"                    → farklı (paket)
"iPhone 15 128GB Mavi — Yenilenmiş"                     → farklı (ikinci el)
```

Regex, tam eşleşme ya da gömme vektörü bunları güvenilir ayıramaz. Fiyat
karşılaştırmasının kendisi ise aritmetik — kodda kalır. Aynı bölünme.

## Mimari

```
[1] YAKALA    içerik betiği, yalnızca izinli alan adlarında
              → {baslik, fiyat, satici, varyant alanlari, url, zaman}

[2] ADAY BUL  KOD: marka + kategori + fiyat bandı + anahtar kelime
              → geçmişten en fazla 5 aday

[3] EŞLE      JEV: adayların HEPSİ tek state'te, tek çağrı
              → hangisi aynı ürün, varyant farkı var mı

[4] KARAR     KOD: fiyat farkı, kaydın tazeliği, kaç kez görüldü
              → FIRSAT / normal / pahalı
```

3. adımda adayları tek tek sormak yerine hepsini bir state'e koyup tek Choice
sorusu sormak önemli: N çağrı yerine 1 çağrı.

## Sorular (taslak)

```
Choice  hangi_aday     → aday_1 / aday_2 / ... / hicbiri
Noul    ayni_model     "İki ilan aynı modeli anlatıyor."
Noul    ayni_varyant   "Fiyatı etkileyen varyant (kapasite, beden, renk) aynı."
Noul    ikinci_el      "İlanlardan biri yenilenmiş, kullanılmış ya da teşhir."
Noul    paket_farki    "İlanlardan biri ek ürünlerle birlikte satılıyor."
Noul    garanti_farki  "Garanti kapsamı ilanlar arasında farklı."
Score   eslesme_guveni 0–3
```

**FIRSAT yalnızca şu koşulda:** `ayni_model` ve `ayni_varyant` yüksek,
`ikinci_el` ve `paket_farki` düşük, `eslesme_guveni` ≥ 2, ve fiyat farkı kodun
eşiğini aşıyor. Şüpheliyse hiçbir şey gösterme — sessiz kalmak yanlış rozetten
iyidir.

## Maliyet (hesap)

- Günde ~100 ürün sayfası
- Sayfa başına 1 çağrı (adaylar tek state'te), ~2.000 token
- 100 × 2.000 = 200 bin token/gün ≈ **$0.0084/gün** ≈ **ayda 25 sent**

Ucuz. **Ama dikkat:** maliyet çağrı sayısıyla büyür, aday sayısıyla değil.
Kod ön elemesi olmadan her yeni ürünü geçmişteki 500 ürünle karşılaştırmaya
kalkarsan iş karesel büyür ve hesap tutmaz. Ön eleme şart.

## Riskler

**1. Yanlış FIRSAT projeyi bitirir.** Bir kez 128 GB'ı 256 GB'la karıştırırsa
kimse rozete bir daha güvenmez. Bu yüzden:

> **Başlamadan önce 50 ürün çifti etiketle** (aynı / farklı). Jev'in cevabıyla
> karşılaştır, yanlış-pozitif oranını ölç. Hedef: yanlış FIRSAT ≈ 0. Kaçırmak
> serbest — göstermediğin fırsat can yakmaz, yanlış gösterdiğin yakar.

Bu, oturum boyunca konuştuğumuz "etiketli değerlendirme seti" ihtiyacının ilk
kez gerçekten pahalıya patladığı yer.

**2. Fiyat bayatlar.** Üç hafta önceki kayıt bugünün karşılaştırması değildir.
Kaydın yaşı kodda kontrol edilmeli; eski kayıtlar ya elenmeli ya "eski fiyat"
diye işaretlenmeli.

**3. Tek görüş yeterli değil.** Bir yerde ucuz görmüş olmak fırsat demek değil —
hatalı etiket, farklı satıcı ya da dolandırıcılık olabilir. Kendi
gözlemlerinin medyanına göre karar ver, kaç kez gördüğünü de göster.

**4. Gizlilik.** Gezdiğin her şeyi kaydetmek çok fazla kişisel veri demek.
Alan adı izin listesi zorunlu (senin de ilk aklına gelen buydu). Veri yerelde
kalır, `data/` altında, depoya girmez.

**5. Kullanım şartları.** Pasif okuma, kazıma değil — İlan Yakala'daki çizgi
burada da geçerli. Gezmeyecek, arama yapmayacak, toplu çekmeyecek.

## İlk adım

Eklenti yazmadan önce:

1. İki platformdan 50 ürün sayfası kaydet (elle, `data/ornek/` gibi)
2. Çiftleri elle etiketle: aynı / farklı / belirsiz
3. Yukarıdaki soru setini oyun alanında (`/oyun`) bu çiftler üzerinde koştur
4. Yanlış-pozitif oranına bak

Oran kabul edilebilirse eklentiyi yaz. Değilse önce soruları düzelt — eklenti
yazmak kolay kısım, güvenilir eşleştirme zor kısım.
