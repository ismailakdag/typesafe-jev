"""Uzun transkript analizi: bolumleme, yontem indeksi, kesme listesi.

Iki cikti uretir:

  1. INDEKS   Konu sinirlari, ogretilen yontemler, alistirmalar, ornekler —
              hepsi zaman damgasiyla. Kitap derlemek icin ham veri.
  2. KESME    Dusuk bilgi yogunluklu, idari ya da tekrar olan bolumler.
              ffmpeg'e verilebilecek "tutulacak araliklar" listesi.

IS BOLUMU (projenin geri kalaniyla ayni):
  - JEV'e sorulan: bu bolumde yontem anlatiliyor mu, konu degisiyor mu,
    bilgi yogunlugu ne, kendi basina anlasilir mi.
  - KODDA kalan: zaman damgalari, parcalama, esikler, birlestirme, kesme
    sinirlarinin cumle ortasina denk gelmemesi.

JEV NE YAPAMAZ: metin uretmez. Bolum SINIRINI bulur ama bolume ISIM koyamaz.
Baslik yazmak ayri bir is — ya sen yazarsin ya bir uretken model.

Kullanim:
  uv run python tools/transkript.py analiz <dosya.txt> [--dakika 2] [--esz 8]
  uv run python tools/transkript.py derle  <dosya.txt>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

CIKTI = Path(__file__).resolve().parent.parent / "data" / "transkript"
CIKTI.mkdir(parents=True, exist_ok=True)

KALIP = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s+(.*)$")


# --------------------------------------------------------------------------- #
# Kod tarafi: ayristirma ve parcalama
# --------------------------------------------------------------------------- #

@dataclass
class Parca:
    no: int
    bas: float          # saniye
    son: float
    metin: str
    kelime: int


def zaman(s: float) -> str:
    return f"{int(s//3600):02d}:{int(s%3600//60):02d}:{int(s%60):02d}"


def cue_oku(dosya: Path) -> list[tuple[float, str]]:
    out = []
    for satir in dosya.read_text(encoding="utf-8", errors="replace").splitlines():
        m = KALIP.match(satir.strip())
        if not m:
            continue
        sa, dk, sn, ms, metin = m.groups()
        t = int(sa) * 3600 + int(dk) * 60 + int(sn) + int(ms) / 1000
        if metin.strip():
            out.append((t, metin.strip()))
    return out


def parcala(cueler: list[tuple[float, str]], dakika: float) -> list[Parca]:
    """Sabit sureli parcalara boler. Sinirlar cue sinirlarina oturur."""
    if not cueler:
        return []
    adim = dakika * 60
    parcalar: list[Parca] = []
    bas = cueler[0][0]
    tampon: list[str] = []
    ilk = bas
    for i, (t, metin) in enumerate(cueler):
        tampon.append(metin)
        son_mu = i == len(cueler) - 1
        if t - ilk >= adim or son_mu:
            gövde = " ".join(tampon)
            parcalar.append(Parca(len(parcalar), ilk, t, gövde, len(gövde.split())))
            tampon, ilk = [], t
    return parcalar


# --------------------------------------------------------------------------- #
# Jev tarafi: parca basina yargilar
# --------------------------------------------------------------------------- #

def sorular() -> dict:
    N = lambda y, t=None, f=None: Noul(  # noqa: E731
        instructions=y, criteria={"true": t, "false": f} if t or f else None)
    return {
        # --- icerik turu -------------------------------------------------- #
        # DARALTILDI: ilk surum parcalarin %66'sinda yaniyordu. Genel tavsiye
        # ile adlandirilabilir prosedur ayrilmali; olcum icin bkz. NOTLAR.md
        "yontem": N("The passage teaches a named, repeatable procedure with identifiable steps.",
                    "A specific technique is named or its steps are laid out, such that the listener could write it down and follow it later",
                    "General advice, encouragement, principles or commentary — nothing with nameable steps"),
        "adim_listesi": N("The passage enumerates steps, keys, rules or points as a list."),
        "ilke": N("The passage states a general principle, law or rule about how something works."),
        "tanim": N("The passage defines a term or names a concept."),
        "ornek_hikaye": N("The passage tells a story, anecdote or concrete example."),
        "arastirma": N("The passage cites research, a study, a survey or a statistic."),
        "alistirma": N("The passage asks the listener to do an exercise, write something down, or take an action."),
        "soru_sorusu": N("The passage poses a question to the listener."),
        "alinti": N("The passage quotes a named person."),

        # --- deger --------------------------------------------------------- #
        "yeni_icerik": N("The passage introduces material not present in `onceki_bolum`.",
                         "New idea, method or example appears",
                         "It restates or rephrases what `onceki_bolum` already covered"),
        "tekrar": N("The passage repeats something already said in `onceki_bolum`."),
        "ozet": N("The passage summarises material covered earlier rather than adding new material."),
        "gecis": N("The passage is mostly a transition: linking sentences with little content of their own."),
        "idari": N("The passage is housekeeping rather than teaching.",
                   "Talk about the tape, the side, the break, the room, the schedule, or how to use the recording",
                   "Actual subject matter is being taught"),
        "tanitim": N("The passage promotes a product, book, seminar or service."),
        "dolgu": N("The passage is padded with filler: false starts, repeated words, hesitation."),

        # --- yapi ----------------------------------------------------------- #
        "konu_degisti": N("The subject of this passage is different from the subject of `onceki_bolum`.",
                          "A new topic begins here",
                          "It continues the same topic"),
        "bolum_acilis": N("The passage opens a new section or module, announcing what is coming."),
        "bolum_kapanis": N("The passage closes a section, wrapping up what was covered."),

        # --- kesme guvenligi -------------------------------------------------- #
        "yarim_baslangic": N("The passage begins in the middle of a sentence or thought."),
        "yarim_bitis": N("The passage ends in the middle of a sentence or thought."),
        "onceki_gerekli": N("Understanding this passage requires having heard `onceki_bolum`."),

        # --- siniflandirma ---------------------------------------------------- #
        "bolum_turu": Choice(
            instructions="What is this passage mainly doing?",
            criteria={
                "yontem": "Teaching a method or technique the listener can apply",
                "teori": "Explaining a principle, idea or how something works",
                "ornek": "Telling a story or working through an example",
                "alistirma": "Directing the listener to do something",
                "ozet": "Reviewing material already covered",
                "idari": "Housekeeping: tape, breaks, logistics",
                "tanitim": "Promoting a product or service",
                "giris": "Opening or framing the material",
            }),

        # --- puanlar ---------------------------------------------------------- #
        "bilgi_yogunlugu": Score(
            instructions="How much substantive content does this passage carry?",
            criteria=["Almost nothing of substance",
                      "One thin point stretched out",
                      "A clear point with some support",
                      "Several distinct points, densely packed"]),
        # YENIDEN CAPALANDI: ilk surumde parcalarin yarisi 3/3 aliyordu, olcek
        # ayirt etmiyordu. Ust seviye artik acik bir talimat sarti ariyor.
        "ogretici_deger": Score(
            instructions="If the listener kept only this passage and threw the rest away, how much would they still be able to do?",
            criteria=["Nothing — it carries no instruction at all",
                      "They would understand an idea but could not act on it",
                      "They could act, but would need the surrounding material to know how",
                      "They could act on it alone: the passage states plainly what to do"]),
        "kendi_basina": Score(
            instructions="How well does this passage stand on its own, without the surrounding material?",
            criteria=["Meaningless out of context",
                      "Needs some context to follow",
                      "Mostly self-contained",
                      "Fully self-contained"]),
    }


SORU_SAYISI = len(sorular())


async def analiz(dosya: Path, dakika: float, eszamanli: int) -> None:
    cueler = cue_oku(dosya)
    parcalar = parcala(cueler, dakika)
    q = sorular()
    print(f"{dosya.name}: {len(cueler)} cue, {zaman(cueler[-1][0])} süre")
    print(f"{len(parcalar)} parça × {SORU_SAYISI} soru, {eszamanli} eşzamanlı\n")

    kilit = asyncio.Semaphore(eszamanli)
    sonuc: dict[int, dict] = {}
    toplam_tok = 0
    t0 = time.perf_counter()

    async with AsyncTypeSafeClient() as client:
        async def calis(p: Parca) -> None:
            nonlocal toplam_tok
            onceki = parcalar[p.no - 1].metin[-1500:] if p.no else "(this is the first passage)"
            async with kilit:
                try:
                    r = await client.system_one(
                        {"bolum": p.metin, "onceki_bolum": onceki}, q)
                except Exception as e:
                    print(f"  parça {p.no}: HATA {e}")
                    return
            toplam_tok += r.usage.input_tokens or 0
            sonuc[p.no] = {
                "no": p.no, "bas": p.bas, "son": p.son, "kelime": p.kelime,
                "metin": p.metin,
                "nouls": {k: round(v.noul, 3) for k, v in r.nouls.items()},
                "choices": {k: {"secim": v.choice, "guven": round(v.confidence, 3)}
                            for k, v in r.choices.items()},
                "scores": {k: {"skor": round(v.score, 2), "guven": round(v.confidence, 3)}
                           for k, v in r.scores.items()},
                "token": r.usage.input_tokens,
            }
            if len(sonuc) % 20 == 0:
                print(f"  {len(sonuc)}/{len(parcalar)} parça · {toplam_tok:,} token")

        await asyncio.gather(*(calis(p) for p in parcalar))

    gecen = time.perf_counter() - t0
    usd = toplam_tok * 0.042 / 1_000_000
    yol = CIKTI / f"{dosya.stem}.json"
    yol.write_text(json.dumps(
        {"kaynak": dosya.name, "dakika": dakika, "soru_sayisi": SORU_SAYISI,
         "parcalar": [sonuc[k] for k in sorted(sonuc)]},
        ensure_ascii=False), encoding="utf-8")

    print(f"\n{len(sonuc)}/{len(parcalar)} parça tamamlandı")
    print(f"{gecen:.0f} saniye · {toplam_tok:,} token · ${usd:.4f}")
    print(f"kaydedildi: {yol}")


# --------------------------------------------------------------------------- #
# Derleme: kod tarafi, cagri yok
# --------------------------------------------------------------------------- #

def atilir(p: dict) -> bool:
    """Kesme kurali. Atilacak: idari, tanitim, ya da dusuk yogunluk + tekrar/gecis.

    Tek yerde duruyor: sunucu bunu ice aktarip ayni karari veriyor ve ayrica
    nedenini yaziyor. Iki kopya olsa zamanla birbirinden ayrilirdi.
    """
    n = lambda a: p["nouls"].get(a, 0)                      # noqa: E731
    s = lambda a: p["scores"].get(a, {}).get("skor", 0)     # noqa: E731
    if n("idari") > 0.6 or n("tanitim") > 0.6:
        return True
    zayif = s("bilgi_yogunlugu") < 1.2 and s("ogretici_deger") < 1.2
    return zayif and (n("tekrar") > 0.5 or n("gecis") > 0.5 or n("dolgu") > 0.5)


def derle_veri(P: list[dict]) -> dict:
    """Parca yargilarindan bolum/indeks/kesme cikarir. Cagri yok, saf kod.

    Esikler burada tek yerde duruyor: hem komut satiri araci hem de eklentinin
    sunucusu bunu cagiriyor, yoksa ikisi zamanla birbirinden ayrilir.
    """
    n = lambda p, a: p["nouls"].get(a, 0)                      # noqa: E731
    s = lambda p, a: p["scores"].get(a, {}).get("skor", 0)     # noqa: E731

    # --- 1. BOLUMLER: konu degisimi sinir, aralar birlestirilir -------------
    # Esikler olcumle secildi: yorumlardan gelen 24 gercek bolume karsi
    # 0.85/0.80 -> %92 duyarlilik, %81 kesinlik. 0.6 ise %49 kesinlik veriyordu.
    sinirlar = [0] + [p["no"] for p in P if n(p, "konu_degisti") > 0.85 or n(p, "bolum_acilis") > 0.80]
    sinirlar = sorted(set(sinirlar))
    bolumler = []
    for i, bas in enumerate(sinirlar):
        son = sinirlar[i + 1] - 1 if i + 1 < len(sinirlar) else len(P) - 1
        if son < bas:
            continue
        dilim = P[bas:son + 1]
        bolumler.append({
            "bas": dilim[0]["bas"], "son": dilim[-1]["son"], "parca": len(dilim),
            "ogretici": max(s(p, "ogretici_deger") for p in dilim),
            "yontem_var": any(n(p, "yontem") > 0.6 for p in dilim),
            "turler": sorted({p["choices"]["bolum_turu"]["secim"] for p in dilim}),
        })
    # cok kisa bolumleri oncekine kat
    birlesik = []
    for b in bolumler:
        if birlesik and b["parca"] <= 1:
            o = birlesik[-1]
            o["son"] = b["son"]; o["parca"] += b["parca"]
            o["ogretici"] = max(o["ogretici"], b["ogretici"])
            o["yontem_var"] = o["yontem_var"] or b["yontem_var"]
        else:
            birlesik.append(dict(b))

    # --- 2. YONTEM INDEKSI --------------------------------------------------
    yontemler = [p for p in P if n(p, "yontem") > 0.85 and s(p, "ogretici_deger") >= 2.3]
    alistirmalar = [p for p in P if n(p, "alistirma") > 0.65]
    ornekler = [p for p in P if n(p, "ornek_hikaye") > 0.7 and s(p, "ogretici_deger") >= 2]
    arastirmalar = [p for p in P if n(p, "arastirma") > 0.65]

    # --- 3. KESME LISTESI ---------------------------------------------------
    tut = [p for p in P if not atilir(p)]
    # Ardisik tutulanlari araliklara birlestir
    araliklar = []
    for p in tut:
        if araliklar and p["no"] == araliklar[-1]["son_no"] + 1:
            araliklar[-1]["son"] = p["son"]; araliklar[-1]["son_no"] = p["no"]
        else:
            araliklar.append({"bas": p["bas"], "son": p["son"], "son_no": p["no"]})

    toplam = P[-1]["son"] - P[0]["bas"]
    tutulan = sum(a["son"] - a["bas"] for a in araliklar)

    return {"bolumler": birlesik, "yontemler": yontemler, "alistirmalar": alistirmalar,
            "ornekler": ornekler, "arastirmalar": arastirmalar, "araliklar": araliklar,
            "toplam": toplam, "tutulan": tutulan}


def derle(dosya: Path) -> None:
    yol = CIKTI / f"{dosya.stem}.json"
    if not yol.exists():
        sys.exit(f"Önce analiz çalıştır: {yol} yok")
    veri = json.loads(yol.read_text(encoding="utf-8"))
    P = veri["parcalar"]
    s = lambda p, a: p["scores"].get(a, {}).get("skor", 0)   # noqa: E731

    d = derle_veri(P)
    birlesik = d["bolumler"]
    yontemler, alistirmalar = d["yontemler"], d["alistirmalar"]
    ornekler, arastirmalar = d["ornekler"], d["arastirmalar"]
    araliklar, toplam, tutulan = d["araliklar"], d["toplam"], d["tutulan"]

    # --- ciktilar -----------------------------------------------------------
    rapor = CIKTI / f"{dosya.stem}-indeks.md"
    sat = [f"# {veri['kaynak']} — indeks\n",
           f"{len(P)} parça · {veri['dakika']} dakikalık dilimler · {SORU_SAYISI} soru\n",
           f"\n## Bölümler ({len(birlesik)})\n",
           "| # | başlangıç | süre | tür | yöntem | öğretici |",
           "|---|---|---|---|---|---|"]
    for i, b in enumerate(birlesik, 1):
        sat.append(f"| {i} | {zaman(b['bas'])} | {(b['son']-b['bas'])/60:.0f} dk | "
                   f"{', '.join(b['turler'][:3])} | {'✓' if b['yontem_var'] else ''} | "
                   f"{b['ogretici']:.1f}/3 |")

    def liste(baslik, kayitlar, alan="ogretici_deger", limit=40):
        sat.append(f"\n## {baslik} ({len(kayitlar)})\n")
        for p in sorted(kayitlar, key=lambda x: -s(x, alan))[:limit]:
            onizleme = " ".join(p["metin"].split()[:18])
            sat.append(f"- **{zaman(p['bas'])}** · {s(p, alan):.1f}/3 — {onizleme}…")

    liste("Öğretilen yöntemler", yontemler)
    liste("Alıştırmalar ve eylem çağrıları", alistirmalar)
    liste("Örnekler ve hikâyeler", ornekler)
    liste("Araştırma ve istatistik atıfları", arastirmalar)
    rapor.write_text("\n".join(sat), encoding="utf-8")

    kesme = CIKTI / f"{dosya.stem}-kesme.json"
    kesme.write_text(json.dumps(
        {"kaynak": veri["kaynak"], "toplam_saniye": toplam, "tutulan_saniye": tutulan,
         "tut": [{"bas": round(a["bas"], 2), "son": round(a["son"], 2)} for a in araliklar]},
        ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"bölüm          : {len(birlesik)}")
    print(f"yöntem         : {len(yontemler)}")
    print(f"alıştırma      : {len(alistirmalar)}")
    print(f"örnek/hikâye   : {len(ornekler)}")
    print(f"araştırma atfı : {len(arastirmalar)}")
    print()
    print(f"kesme: {len(araliklar)} aralık tutuluyor")
    print(f"  {toplam/3600:.2f} saat -> {tutulan/3600:.2f} saat  (%{100*tutulan/toplam:.0f} kalıyor, "
          f"%{100*(1-tutulan/toplam):.0f} atılıyor)")
    print()
    print(f"indeks : {rapor}")
    print(f"kesme  : {kesme}")


# --------------------------------------------------------------------------- #
# Disa aktarma: secilen parcalarin transkript metni
# --------------------------------------------------------------------------- #

def disa(dosya: Path, mod: str) -> None:
    """Ise yarar bulunan parcalarin METNINI bolum bolum yazar.

    Uzerinde calisilacak ham malzeme bu: kendi notunu cikarmak, ozet yazmak,
    derlemek icin. Metin kaynaktan oldugu gibi kopyalanir; arac metin uretmez.
    """
    yol = CIKTI / f"{dosya.stem}.json"
    if not yol.exists():
        sys.exit(f"Once analiz calistir: {yol} yok")
    veri = json.loads(yol.read_text(encoding="utf-8"))
    P = veri["parcalar"]
    n = lambda p, a: p["nouls"].get(a, 0)                      # noqa: E731
    s = lambda p, a: p["scores"].get(a, {}).get("skor", 0)     # noqa: E731

    SUZGEC = {
        # Yalnizca adlandirilabilir prosedur anlatan parcalar
        "yontem": lambda p: n(p, "yontem") > 0.85,
        # Dinleyiciye is dusen parcalar
        "alistirma": lambda p: n(p, "alistirma") > 0.7,
        # Kesme listesinin tuttugu her sey
        "tut": lambda p: not (n(p, "idari") > 0.6 or n(p, "tanitim") > 0.6
                              or (s(p, "bilgi_yogunlugu") < 1.2 and n(p, "tekrar") > 0.5)),
        "hepsi": lambda p: True,
    }
    if mod not in SUZGEC:
        sys.exit("mod: " + ", ".join(SUZGEC))
    sec = SUZGEC[mod]

    sinirlar = sorted({0} | {p["no"] for p in P
                             if n(p, "konu_degisti") > 0.85 or n(p, "bolum_acilis") > 0.80})
    bolum_no = {}
    for i, b in enumerate(sinirlar):
        son = sinirlar[i + 1] if i + 1 < len(sinirlar) else len(P)
        for k in range(b, son):
            bolum_no[k] = i + 1

    sat = [
        f"# {veri['kaynak']} — {mod}",
        "",
        f"Süzgeç: **{mod}** · {veri['dakika']} dakikalık dilimler",
        "",
        "> Metin kaynak transkriptten olduğu gibi alınmıştır; araç metin üretmez.",
    ]
    onceki_bolum = None
    sayi = kelime = 0
    for p in P:
        if not sec(p):
            continue
        b = bolum_no.get(p["no"], 0)
        if b != onceki_bolum:
            sat += ["", f"## Bölüm {b}"]
            onceki_bolum = b
        etiket = []
        if n(p, "yontem") > 0.85:
            etiket.append("yöntem")
        if n(p, "alistirma") > 0.7:
            etiket.append("alıştırma")
        if n(p, "adim_listesi") > 0.7:
            etiket.append("liste")
        if n(p, "arastirma") > 0.7:
            etiket.append("araştırma")
        if n(p, "ornek_hikaye") > 0.7:
            etiket.append("örnek")
        bas = f"**{zaman(p['bas'])}–{zaman(p['son'])}**"
        if etiket:
            bas += "  ·  _" + ", ".join(etiket) + "_"
        bas += f"  ·  öğretici {s(p, 'ogretici_deger'):.1f}/3"
        sat += ["", bas, "", p["metin"]]
        sayi += 1
        kelime += p["kelime"]

    cikti = CIKTI / f"{dosya.stem}-{mod}.md"
    cikti.write_text("\n".join(sat) + "\n", encoding="utf-8")
    toplam = sum(x["kelime"] for x in P)
    print(f"{sayi} parça, {kelime:,} kelime yazıldı")
    print(f"kaynağın %{100 * kelime / toplam:.0f}'i")
    print(cikti)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("komut", choices=["analiz", "derle", "disa"])
    ap.add_argument("dosya", type=Path)
    ap.add_argument("--dakika", type=float, default=2.0)
    ap.add_argument("--esz", type=int, default=8)
    ap.add_argument("--mod", default="yontem",
                    help="disa: yontem | alistirma | tut | hepsi")
    a = ap.parse_args()
    if a.komut == "analiz":
        asyncio.run(analiz(a.dosya, a.dakika, a.esz))
    elif a.komut == "derle":
        derle(a.dosya)
    else:
        disa(a.dosya, a.mod)


if __name__ == "__main__":
    main()
