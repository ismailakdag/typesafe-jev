"""TypeSafe / Jev baglanti testi.

Calistir:  uv run python smoke_test.py
Gerekli:   .env icinde TYPESAFE_API_KEY
"""

import os
import sys
import time

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

load_dotenv()

if not os.getenv("TYPESAFE_API_KEY"):
    sys.exit("TYPESAFE_API_KEY yok. .env.example dosyasini .env olarak kopyala ve anahtari gir.")

STATE = (
    "Merhaba, 3 gundur Stripe hesabimi baglamaya calisiyorum ve surekli hata veriyor. "
    "Satis kaybediyorum, lutfen acilen bakar misiniz?"
)

QUESTIONS = {
    "department": Choice(
        instructions="Bu destek talebine hangi ekip bakmali?",
        criteria={
            "billing": "Odeme, fatura veya abonelik sorunlari",
            "technical": "Hata, entegrasyon veya API sorunlari",
            "sales": "Fiyatlandirma veya hesap acma sorulari",
        },
    ),
    "frustration": Score(
        instructions="Musterinin ne kadar sinirli oldugunu degerlendir.",
        criteria=[
            "Sakin, sadece durumu bildiriyor",
            "Rahatsiz ama kibar",
            "Cok ofkeli, sert bir dil kullaniyor",
        ],
    ),
    "is_urgent": Noul(
        instructions="Mesaj aciliyet veya zaman baskisi ifade ediyor.",
        criteria={
            "true": "Musteri hemen cozum istiyor ya da is kaybindan bahsediyor",
            "false": "Zaman baskisi yok, bilgi amacli bir mesaj",
        },
    ),
}


def main() -> None:
    with TypeSafeClient() as client:
        started = time.perf_counter()
        result = client.system_one(STATE, QUESTIONS)
        elapsed_ms = (time.perf_counter() - started) * 1000

    print(f"model: {result.model}   sure: {elapsed_ms:.0f} ms")
    print(f"usage: {result.usage.input_tokens} in / {result.usage.output_tokens} out")
    print()

    for name, answer in result.choices.items():
        print(f"[choice] {name}: {answer.choice}  (confidence {answer.confidence:.3f})")
        for label, probability in sorted(answer.probabilities.items(), key=lambda item: -item[1]):
            print(f"           {label:<12} {probability:.3f}")

    for name, answer in result.scores.items():
        print(f"[score]  {name}: {answer.score:.3f}  (confidence {answer.confidence:.3f})")
        for level, probability in sorted(answer.probabilities.items()):
            print(f"           {level} {answer.legend[level]:<40} {probability:.3f}")

    for name, answer in result.nouls.items():
        print(f"[noul]   {name}: {answer.noul:.3f}")

    # Maliyet: 1M girdi tokeni 0.042 USD, cikti tokenlari ucretsiz.
    if result.usage.input_tokens:
        print(f"\ntahmini maliyet: ${result.usage.input_tokens * 0.042 / 1_000_000:.8f}")


if __name__ == "__main__":
    main()
