"""Vasita (otomobil) ilanlari icin yargilar.

Otomotivde en sik karsilasilan sorun ILAN ILE VERININ CELISMESI: baslik
"hasar kaydi yok" derken govde semasinda sekiz panel boyali cikabiliyor.
Bu yuzden semadan cikan `hasar` nesnesi state'e konuyor ve modele acikca
"ikisini karsilastir" diye soruluyor — metinden tahmin etmesi beklenmiyor.

Kodun kesin bildigi hicbir sey sorulmuyor: yil, km, motor hacmi, fiyat hepsi
yapilandirilmis alanlarda; karsilastirmalari kod yapar.
"""

from __future__ import annotations

from typing import Any

from typesafe_sdk import Choice, Noul, Score


def sorular_vasita() -> dict[str, Any]:
    return {
        # ------------------------------------------------------------------ #
        # Noul — bagimsiz kosullar
        # ------------------------------------------------------------------ #
        "hasar_celiskisi": Noul(
            instructions=(
                "`baslik` veya `aciklama` aracın hasarsız, orijinal ya da hasar kaydı olmadığını "
                "söylüyor; ama `hasar_semasi` bunu yalanlıyor. İkisini karşılaştır."
            ),
            criteria={
                "true": "Metin hasarsız/orijinal/hasar kaydı yok diyor ama şemada boyalı, lokal boyalı veya değişen panel var",
                "false": "Metin ile şema birbiriyle tutarlı; ya ikisi de temiz ya da metin boyalı/değişen parçaları kabul ediyor",
            },
        ),
        "agir_hasar_imasi": Noul(
            instructions="İlan metni aracın ağır hasar, pert, hasarlı çıkma veya büyük bir kaza geçmişi olduğunu söylüyor ya da ima ediyor.",
            criteria={
                "true": "Pert, ağır hasar kaydı, hasarlı, kaza yapmış gibi ifadeler var",
                "false": "Böyle bir ifade yok",
            },
        ),
        "degisen_parca_beyani": Noul(
            instructions="İlan metni değişen, boyalı veya sökülüp takılmış parçalardan açıkça söz ediyor.",
            criteria={
                "true": "Metin değişen, boyalı, lokal boyalı ya da söküp takılmış parçaları sayıyor veya kabul ediyor",
                "false": "Metin bu konuya hiç değinmiyor ya da hepsinin orijinal olduğunu söylüyor",
            },
        ),
        "tramer_belirsiz": Noul(
            instructions="İlan metni tramer veya hasar kaydı tutarına dair hiçbir bilgi vermiyor.",
            criteria={
                "true": "Tramer tutarından, hasar kaydından veya sorgu sonucundan hiç söz edilmiyor",
                "false": "Tramer tutarı ya da hasar kaydı durumu açıkça belirtilmiş",
            },
        ),
        "ekspertize_acik": Noul(
            instructions="İlan, alıcıyı ekspertiz yaptırmaya veya aracı incelemeye açıkça davet ediyor.",
            criteria={
                "true": "Ekspertize götürebilirsiniz, istediğiniz serviste bakabilirsiniz gibi bir davet var",
                "false": "Böyle bir davet yok",
            },
        ),
        "ticari_kullanim": Noul(
            instructions="Araç ticari olarak kullanılmış görünüyor.",
            criteria={
                "true": "Taksi, ticari plaka, kiralık filo, sürücü kursu, kurye veya benzeri ticari kullanım belirtisi var",
                "false": "Bireysel kullanım anlatılıyor ya da konuya değinilmiyor",
            },
        ),
        "lpg_donusum": Noul(
            instructions="Araçta sonradan takılmış LPG sistemi olduğu belirtiliyor.",
        ),
        "bakim_kaniti_yok": Noul(
            instructions="İlan metni bakım geçmişine dair hiçbir somut bilgi vermiyor.",
            criteria={
                "true": "Bakımdan hiç söz edilmiyor ya da sadece bakımlı denip geçilmiş",
                "false": "Yapılan bakımlar, değişen parçalar veya servis kaydı sayılmış",
            },
        ),
        "km_vurgusu_ispatsiz": Noul(
            instructions="İlan kilometrenin orijinal olduğunu vurguluyor ama bunu destekleyecek somut bir dayanak vermiyor.",
            criteria={
                "true": "Kilometre orijinal deniyor; servis kaydı, fatura veya sorgu gibi bir dayanak gösterilmiyor",
                "false": "Ya böyle bir vurgu yok ya da dayanağı birlikte veriliyor",
            },
        ),
        "acil_satis_baskisi": Noul(
            instructions="Satıcı aciliyet veya zaman baskısı yaratan bir dil kullanıyor.",
            criteria={
                "true": "Acil satılık, fırsat, son fiyat, kaçırmayın gibi baskı ifadeleri var",
                "false": "Sakin, bilgilendirici bir anlatım",
            },
        ),
        "takas_arayisi": Noul(
            instructions="İlan metni takas veya trampa teklifinden söz ediyor.",
        ),
        "masrafsiz_iddiasi": Noul(
            instructions="İlan, araca hiç masraf gerekmediğini veya hiçbir masrafı olmadığını iddia ediyor.",
        ),
        "abartili_pazarlama": Noul(
            instructions="Metin, doğrulanabilir bilgi vermeden abartılı övgü sıfatlarıyla dolu.",
            criteria={
                "true": "Kusursuz, emsalsiz, tertemiz gibi sıfatlar somut bilgi olmadan kullanılmış",
                "false": "Övgü varsa bile somut bilgiyle desteklenmiş",
            },
        ),
        "iletisim_yonlendirme": Noul(
            instructions="İlan, önemli bilgileri yazmak yerine alıcıyı telefonla aramaya yönlendiriyor.",
            criteria={
                "true": "Detay için arayınız benzeri bir yönlendirme var ve bilgiler eksik bırakılmış",
                "false": "Bilgiler metinde verilmiş",
            },
        ),

        # ------------------------------------------------------------------ #
        # Choice — her birinde "belirsiz" cikisi var
        # ------------------------------------------------------------------ #
        "satici_dili": Choice(
            instructions="`aciklama` metninin diline bakarak ilanı kimin yazdığını belirle. `yapilandirilmis_alanlar.kimden` etiketini değil, metnin kendisini esas al.",
            criteria={
                "arac_sahibi": "Aracı kendi kullanan kişinin kendi ağzından anlatımı",
                "galeri": "Galeri, oto ticaret veya kurumsal satıcı dili",
                "belirsiz": "Metinden hangisi olduğu anlaşılmıyor",
            },
        ),
        "hasar_beyani": Choice(
            instructions="İlan metni aracın hasar durumu hakkında ne beyan ediyor? Şemaya değil, metnin kendi iddiasına bak.",
            criteria={
                "tamamen_hasarsiz": "Hiç boya, değişen veya hasar olmadığı iddia ediliyor",
                "kismi_kabul": "Bazı boyalı veya değişen parçalar olduğu kabul ediliyor",
                "hasarli_kabul": "Ciddi hasar veya ağır hasar kaydı kabul ediliyor",
                "belirsiz": "Metin hasar durumuna hiç değinmiyor",
            },
        ),
        "kullanim_profili": Choice(
            instructions="Metne göre araç ağırlıklı olarak nasıl kullanılmış?",
            criteria={
                "sehir_ici": "Kısa mesafe, şehir içi kullanım anlatılıyor",
                "uzun_yol": "Uzun yol, şehirlerarası kullanım anlatılıyor",
                "ticari": "Ticari kullanım anlatılıyor",
                "belirsiz": "Kullanım biçiminden söz edilmiyor",
            },
        ),

        # ------------------------------------------------------------------ #
        # Score — sirali, somut seviyeler
        # ------------------------------------------------------------------ #
        "profile_uygunluk": Score(
            instructions="Aracın, `alici_profili` içinde tarif edilen kullanım ve önceliklere uygunluğu. Sadece açıklama ve yapılandırılmış alanlardaki bilgiye dayan.",
            criteria=[
                "Alıcının önceliklerine açıkça aykırı",
                "Zayıf uyum: birkaç önceliği karşılıyor",
                "İyi uyum: önceliklerin çoğunu karşılıyor",
                "Tarif edilen kullanıma birebir uyuyor",
            ],
        ),
        "aciklama_seffafligi": Score(
            instructions="İlan metninin, aracın eksilerini ve kusurlarını da açıkça söyleme derecesi.",
            criteria=[
                "Sadece olumlu yanlar anlatılmış, hiçbir kusurdan söz edilmiyor",
                "Bir iki kusur geçiştirilerek anılmış",
                "Kusurlar açıkça sayılmış",
                "Kusurlar ayrıntısıyla sayılmış ve ekspertize davet edilmiş",
            ],
        ),
        "bakim_kaniti": Score(
            instructions="Düzenli bakım yapıldığına dair ilan metnindeki kanıtın gücü.",
            criteria=[
                "Bakımdan hiç söz edilmiyor",
                "Bakımlı denmiş ama ayrıntı yok",
                "Yapılan bakım kalemleri sayılmış (yağ, triger, balata, debriyaj gibi)",
                "Yetkili servis kaydı veya faturalı bakım geçmişi belirtilmiş",
            ],
        ),
        "donanim_zenginligi": Score(
            instructions="Açıklamada sayılan donanımın kapsamı.",
            criteria=[
                "Donanımdan hiç söz edilmiyor",
                "Birkaç temel donanım sayılmış",
                "Konfor ve güvenlik donanımları ayrıntılı sayılmış",
                "Üst segment donanımlar sayılmış (adaptif far, şeritte kalma, deri döşeme, cam tavan gibi)",
            ],
        ),
        "satis_aciliyeti": Score(
            instructions="Satıcının aciliyet düzeyi; pazarlık payı olup olmadığının sinyali.",
            criteria=[
                "Acele yok; pazarlık kabul edilmediği belirtilmiş",
                "Normal bir satış ilanı",
                "Acil satılık, takas olur, pazarlık payı var gibi ifadeler var",
            ],
        ),
    }


# Agirlikli skora giren Score sorulari ve agirliklari.
AGIRLIKLAR_VASITA = {
    "profile_uygunluk": 0.35,
    "aciklama_seffafligi": 0.25,
    "bakim_kaniti": 0.25,
    "donanim_zenginligi": 0.10,
    "satis_aciliyeti": 0.05,
}

# Tek basina eleyen kosullar: (soru adi, etiket). Agirlikli skora karismazlar.
BAYRAKLAR_VASITA = [
    ("hasar_celiskisi", "ilan hasar şemasıyla çelişiyor"),
    ("agir_hasar_imasi", "ağır hasar ima ediliyor"),
    ("ticari_kullanim", "ticari kullanım belirtisi"),
]
