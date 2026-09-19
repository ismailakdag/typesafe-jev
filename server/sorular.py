"""Jev'e sorulan yargilar.

Tasarim notlari:
  - Her soru TEK ve DAR bir yargi sorar. Genis sorular literal okunup yanlis
    cevaplanir; bolmek hem dogrulugu hem hata ayiklamayi kolaylastirir.
  - Kodun kesin olarak bildigi hicbir sey sorulmaz (fiyat, m2, aidat, asansor
    alani, mesafe). Bunlar yapilandirilmis alanlarda zaten var.
  - Hepsi TEK cagrida, ayni state uzerinde, paralel calisir: 22 soru icin 22 degil
    1 istek gider, gecikme tek bir cagri kadardir.
  - Maliyet acisindan OLCULEN gercek: state (ilan metni + alanlar + profil) ~1.380
    token; her soru instructions ve criteria metniyle birlikte ~100 token ekliyor.
    Yani 22 soruda maliyetin ~%60'i sorularin kendi metni. Soru eklemek bedava
    degil; ucuz. Kisaltilacak yer once uzun criteria aciklamalaridir.
  - Choice sorularinda her zaman bir "belirsiz" cikisi var; model uygun secenek
    yoksa en yakinini zorlamak yerine bilmedigini soyleyebilsin.
"""

from __future__ import annotations

from typing import Any

from typesafe_sdk import Choice, Noul, Score


def sorular() -> dict[str, Any]:
    return {
        # ------------------------------------------------------------------ #
        # Noul — bagimsiz kosullar. Birden fazlasi ayni anda dogru olabilecegi
        # icin her biri ayri soru; tek bir Choice'a sikistirilmiyor.
        # ------------------------------------------------------------------ #
        "kiracili_ima": Noul(
            instructions="İlan metni, dairenin şu anda kiracılı olduğunu veya alıcıya kiracıyla birlikte teslim edileceğini söylüyor ya da ima ediyor.",
            criteria={
                "true": "Metinde kiracı, kira kontratı, kiracılı teslim, gelir getiren gibi ifadeler geçiyor",
                "false": "Metin boş veya sıfır olduğunu söylüyor ya da kiracı konusuna hiç değinmiyor",
            },
        ),
        "celiskili_bilgi": Noul(
            instructions="`yapilandirilmis_alanlar` içindeki bilgilerle `aciklama` metni birbiriyle çelişiyor.",
            criteria={
                "true": "En az bir konuda alanlar ile açıklama birbirini tutmuyor; örneğin alanlarda 'Kullanım Durumu: Boş' yazarken açıklamada kiracıdan söz edilmesi, ya da oda sayısı veya kat bilgisinin farklı verilmesi",
                "false": "Açıklama, yapılandırılmış alanlarla tutarlı ya da o konulara hiç değinmiyor",
            },
        ),
        "metin_yetersiz": Noul(
            instructions="Açıklama metni, dairenin durumu hakkında karar vermeye yetecek bilgi içermiyor; yalnızca genel reklam cümlelerinden oluşuyor.",
        ),
        "tadilat_gerekli": Noul(
            instructions="İlan metni, dairenin tadilat, yenileme veya onarım gerektirdiğini söylüyor.",
            criteria={
                "true": "Tadilat gerekli, yenilenmeli, badana boya ister, tadilatlık gibi ifadeler var",
                "false": "Daire bakımlı veya yeni yapılmış olarak anlatılıyor ya da konuya değinilmiyor",
            },
        ),
        "yatirimlik_dili": Noul(
            instructions="İlan, oturmak isteyen birine değil, kira getirisi veya değer artışı arayan bir yatırımcıya hitap ediyor.",
            criteria={
                "true": "Kira getirisi, yatırımlık, değerlenir, kazandırır gibi vurgu var",
                "false": "Anlatım oturmak için gelen bir alıcıya yönelik",
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
            instructions="İlan metni takas, trampa veya araç/arsa karşılığı değişim teklifinden söz ediyor.",
        ),
        "abartili_pazarlama": Noul(
            instructions="Metin, doğrulanabilir bilgi vermeden abartılı övgü sıfatlarıyla dolu.",
            criteria={
                "true": "Eşsiz, muhteşem, rüya gibi türünden sıfatlar somut bilgi olmadan kullanılmış",
                "false": "Övgü varsa bile somut bilgiyle desteklenmiş",
            },
        ),
        "iletisim_yonlendirme": Noul(
            instructions="İlan, önemli bilgileri yazmak yerine alıcıyı telefonla aramaya yönlendiriyor.",
            criteria={
                "true": "Detaylı bilgi için arayınız benzeri bir yönlendirme var ve bilgiler eksik bırakılmış",
                "false": "Bilgiler metinde verilmiş",
            },
        ),
        "masraf_aliciya": Noul(
            instructions="İlan metni komisyon, tapu masrafı veya benzeri bir bedelin alıcıya ait olduğunu belirtiyor.",
        ),
        "sifir_kullanilmamis": Noul(
            instructions="İlan, dairenin hiç kullanılmamış veya sıfır olduğunu söylüyor.",
            criteria={
                "true": "Sıfır daire, hiç oturulmamış, ilk sahibinden gibi ifadeler var",
                "false": "Daire kullanılmış olarak anlatılıyor ya da konuya değinilmiyor",
            },
        ),
        "manzara_iddiasi": Noul(
            instructions="İlan metni belirli bir manzaradan söz ediyor (deniz, göl, doğa, şehir manzarası gibi).",
        ),

        # ------------------------------------------------------------------ #
        # Choice — birbirini disliyan secenekler. Her birinde "belirsiz" cikisi var.
        # ------------------------------------------------------------------ #
        "satici_dili": Choice(
            instructions="`aciklama` metninin diline bakarak ilanı kimin yazdığını belirle. `yapilandirilmis_alanlar.kimden` etiketini değil, metnin kendisini esas al.",
            criteria={
                "ev_sahibi": "Dairede oturan veya sahibi olan kişinin kendi ağzından anlatımı",
                "emlak_ofisi": "Kurumsal emlak pazarlama dili, portföy veya danışman anlatımı",
                "belirsiz": "Metinden hangisi olduğu anlaşılmıyor",
            },
        ),
        "ilan_odagi": Choice(
            instructions="Açıklama metni ağırlıklı olarak neyi anlatıyor?",
            criteria={
                "konum": "Çevre, ulaşım, yakındaki yerler",
                "daire_ozellikleri": "Dairenin kendi iç özellikleri, oda düzeni, malzeme",
                "site_olanaklari": "Site içi ortak olanaklar, güvenlik, sosyal alanlar",
                "yatirim": "Getiri, değer artışı, yatırım fırsatı",
                "belirsiz": "Baskın bir odak yok ya da metin çok kısa",
            },
        ),
        "hedef_kitle": Choice(
            instructions="Metnin anlatımı öncelikle kime sesleniyor?",
            criteria={
                "aile": "Çocuklu veya kalabalık aileye yönelik vurgular",
                "ogrenci_bekar": "Tek kişi, öğrenci veya bekâra yönelik vurgular",
                "yatirimci": "Kira getirisi ve değer artışı arayan alıcıya yönelik",
                "belirsiz": "Belirli bir kitleye seslenmiyor",
            },
        ),
        "teslim_durumu": Choice(
            instructions="Açıklama metnine göre daire alıcıya hangi durumda teslim edilecek? Yapılandırılmış alanı değil, metnin söylediğini esas al.",
            criteria={
                "bos_hazir": "Boş ve hemen taşınmaya hazır",
                "kiracili": "İçinde kiracı var, kiracıyla teslim",
                "insaat_halinde": "Henüz tamamlanmamış, teslim ileri bir tarihte",
                "belirsiz": "Metin teslim durumuna değinmiyor",
            },
        ),

        # ------------------------------------------------------------------ #
        # Score — sirali, somut seviyeler. Her seviye kendi basina anlasilir
        # olmali; "orta" gibi goreli ifadeler kullanilmiyor.
        # ------------------------------------------------------------------ #
        "profile_uygunluk": Score(
            instructions="İlanın, `alici_profili` içinde tarif edilen kullanım ve önceliklere uygunluğu. Sadece açıklama ve yapılandırılmış alanlardaki bilgiye dayan.",
            criteria=[
                "Alıcının önceliklerine açıkça aykırı",
                "Zayıf uyum: birkaç önceliği karşılıyor",
                "İyi uyum: önceliklerin çoğunu karşılıyor",
                "Tarif edilen kullanıma birebir uyuyor",
            ],
        ),
        "ulasim_erisilebilirlik": Score(
            instructions="Açıklamaya göre toplu taşıma ve ana yollara erişim kolaylığı.",
            criteria=[
                "Ulaşımdan hiç söz edilmiyor",
                "Sadece araçla erişimden söz ediliyor",
                "Otobüs veya minibüs hattından söz ediliyor",
                "Raylı sistem, istasyon veya ana arter yakınlığı somut mesafeyle verilmiş",
            ],
        ),
        "site_olanaklari": Score(
            instructions="Açıklamada anlatılan site ve bina olanaklarının kapsamı.",
            criteria=[
                "Site veya ortak olanaktan söz edilmiyor",
                "Temel düzeyde: güvenlik veya otopark var",
                "Güvenlik, otopark ve en az bir sosyal alan var",
                "Havuz, spor salonu, çocuk alanı gibi birden çok sosyal olanak var",
            ],
        ),
        "konum_vaadi_somutlugu": Score(
            instructions="Açıklamadaki konum ve ulaşım iddialarının ne kadar somut yazıldığını değerlendir. İddiaların doğru olup olmadığını değil, ne kadar doğrulanabilir olduğunu puanla.",
            criteria=[
                "Konumdan hiç söz edilmiyor",
                "Sadece merkezi konumda, her yere yakın gibi genel ifadeler var",
                "Bazı yerlere mesafe verilmiş ama belirsiz",
                "Adı verilmiş yerlere somut mesafe veya süre belirtilmiş",
            ],
        ),
        "bilgi_doygunlugu": Score(
            instructions="İlan metninin karar vermeye yetecek somut bilgi sunma derecesi.",
            criteria=[
                "Neredeyse hiç bilgi yok",
                "Birkaç dağınık bilgi var",
                "Dairenin çoğu yönü anlatılmış",
                "Daire, bina ve çevre ayrıntılı ve somut biçimde anlatılmış",
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
