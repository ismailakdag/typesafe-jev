"""Transkript derlemesinin degismezleri. Cagri yapmaz, para harcamaz.

Yakalamak istedigimiz sey: bir soru eklenip gruplamaya yazilmayi unutulursa
arayuzde sessizce kaybolur, ya da kesme kuralinin iki kopyasi birbirinden
ayrilirsa atilan listesi kesme araliklariyla celisir. Ikisi de goze carpmaz.

    uv run python tools/test_transkript.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from server import transkript as S  # noqa: E402
import transkript as arac  # noqa: E402

gecti = kaldi = 0


def ok(ad: str, kosul: bool, ek: str = "") -> None:
    global gecti, kaldi
    if kosul:
        gecti += 1
        print(f"  ok   {ad}")
    else:
        kaldi += 1
        print(f"  KALDI {ad}" + (f" — {ek}" if ek else ""))


# --- 1. soru dokumu butun sorulari kapsiyor mu ----------------------------- #
print("\n1. soru dökümü")
q = arac.sorular()
gruplanan = [a for _, _, adlar in S.GRUPLAR for a in adlar]
ok("her soru bir gruba ait", set(gruplanan) == set(q),
   f"eksik: {sorted(set(q) - set(gruplanan))}, fazla: {sorted(set(gruplanan) - set(q))}")
ok("soru iki gruba birden girmemiş", len(gruplanan) == len(set(gruplanan)))
ok("sayı tutuyor", len(gruplanan) == arac.SORU_SAYISI == 26, str(len(gruplanan)))

d = S.soru_dokumu()
hepsi = [s for g in d["gruplar"] for s in g["sorular"]]
ok("her sorunun metni var", all(s["soru"] for s in hepsi))
ok("Noul'ların ölçütü var",
   all(s.get("evet") and s.get("hayir") for s in hepsi if s["tur"] == "Noul" and q[s["ad"]].criteria))
ok("Score'ların seviyeleri var", all(s.get("seviyeler") for s in hepsi if s["tur"] == "Score"))
ok("Choice'un seçenekleri var", all(s.get("secenekler") for s in hepsi if s["tur"] == "Choice"))

# --- 2. esikler arayuzdeki sekmelerle ortusuyor mu ------------------------- #
print("\n2. eşikler")
SEKME = {"bolumler", "yontemler", "alistirmalar", "ornekler", "arastirmalar", "kesme"}
ok("her liste için kural yazılmış", set(S.ESIKLER) == SEKME,
   f"eksik: {sorted(SEKME - set(S.ESIKLER))}")

# --- 3. gercek veride derleme degismezleri --------------------------------- #
print("\n3. derleme (gerçek veri)")
kaynak = S.CIKTI / "lawofattraction.json"
if not kaynak.exists():
    print(f"  atlandı — {kaynak.name} yok")
else:
    P = json.loads(kaynak.read_text(encoding="utf-8"))["parcalar"]
    r = S.derle(P)

    ok("tümü = bütün parçalar", len(r["tumu"]) == len(P))
    ok("atılan + tutulan = tümü",
       len(r["atilan"]) + len(r["kesme"]["tutulan_no"]) == len(P),
       f'{len(r["atilan"])} + {len(r["kesme"]["tutulan_no"])} != {len(P)}')

    atilan_no = {p["no"] for p in r["atilan"]}
    ok("atılan ile tutulan kesişmiyor", not (atilan_no & set(r["kesme"]["tutulan_no"])))

    # Kesme araliklarinin toplam suresi, tutulan parcalarin suresine esit olmali:
    # iki kod yolu (arac.atilir ve derle_veri'nin araliklari) ayni karari veriyor mu?
    tutulan_sure = sum(p["son"] - p["bas"] for p in P if p["no"] in set(r["kesme"]["tutulan_no"]))
    ok("kesme aralıkları atılma kuralıyla tutarlı",
       abs(tutulan_sure - r["kesme"]["tutulan_sn"]) < 1.5,
       f'{tutulan_sure:.1f} vs {r["kesme"]["tutulan_sn"]}')

    ok("her atılanın nedeni yazılı", all(p["neden"] for p in r["atilan"]))
    ok("metinler kırpılmamış",
       all(len(p["metin"].split()) == p["kelime"] for p in r["tumu"]))

    # Bolum metni, icindeki parcalarin metinlerinin toplami olmali.
    b = r["bolumler"][0]
    icinde = sum(len(p["metin"].split()) for p in r["tumu"] if p["no"] in b["parca_no"])
    ok("bölüm metni parçalarının toplamı", len(b["metin"].split()) == icinde,
       f'{len(b["metin"].split())} vs {icinde}')
    ok("bölümler bütün süreyi kaplıyor",
       abs(r["bolumler"][0]["t"] - r["tumu"][0]["t"]) < 1
       and abs(r["bolumler"][-1]["son"] - r["tumu"][-1]["son"]) < 1)

    ok("listelerde sınır yok (kırpılmamış)",
       len(r["yontemler"]) == sum(1 for p in P
                                  if p["nouls"].get("yontem", 0) > 0.85
                                  and p["scores"].get("ogretici_deger", {}).get("skor", 0) >= 2.3))

    # --- 4. tahmin olcume ne kadar yakin ---------------------------------- #
    print("\n4. tahmin doğruluğu")
    gercek = sum(p["token"] for p in P)
    cue = [{"t": p["bas"], "metin": p["metin"]} for p in P]
    t = S.tahmin(cue, 2.0)
    sapma = abs(t["token"] - gercek) / gercek
    ok(f"tahmin %10 içinde (sapma %{sapma * 100:.1f})", sapma < 0.10,
       f'{t["token"]} vs {gercek}')

print(f"\n{gecti} geçti, {kaldi} kaldı")
sys.exit(1 if kaldi else 0)
