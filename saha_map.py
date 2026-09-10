#!/usr/bin/env python3
"""
saha_map.py

shift / microagi egocentric veri arzi icin Istanbul hedef saha listesi cikarir.

Mantik:
  microagi'nin isi fabrikaya ozel manipulasyon gorevleri icin robot fine-tune etmek.
  Dolayisiyla her egocentric saat esit degildir. Kategoriler, endustriyel
  manipulasyon primitiflerine transfer degerine gore agirliklandirilir.

Kullanim:
  export GOOGLE_PLACES_API_KEY="..."
  python3 saha_map.py --out saha_listesi.csv
  python3 saha_map.py --out saha_listesi.csv --max-pages 3   # daha genis tarama

Maliyet notu:
  Varsayilan ayarda ~64 sorgu x 2 sayfa = ~128 istek.
  Places API Text Search (New) ucretsiz aylik kredinin cok altinda kalir.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.rating",
    "places.userRatingCount",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.businessStatus",
    "places.primaryTypeDisplayName",
    "nextPageToken",
])

# ---------------------------------------------------------------------------
# 1) KATEGORI TAKSONOMISI
#    agirlik  = endustriyel manipulasyona transfer degeri (0-1)
#    primitif = bu iste baskin olan manipulasyon primitifi
# ---------------------------------------------------------------------------

KATEGORILER = [
    # (arama terimi, agirlik, baskin primitif)
    ("konfeksiyon atolyesi",      1.00, "deforme malzeme manipulasyonu"),
    ("torna tesviye atolyesi",    1.00, "hassas hizalama + alet kullanimi"),
    ("mobilya atolyesi",          0.95, "iki elli montaj + alet kullanimi"),
    ("oto tamir servisi",         0.90, "kisitli alanda alet kullanimi"),
    ("elektronik tamir",          0.90, "ince motor manipulasyon"),
    ("beyaz esya servisi",        0.88, "sokme-takma dizisi"),
    ("kuyumcu atolyesi",          0.85, "ince motor manipulasyon"),
    ("ayakkabi imalathanesi",     0.85, "deforme malzeme + yapistirma"),
    ("paketleme ve depo",         0.85, "kavra-yerlestir + siniflandirma"),
    ("matbaa",                    0.80, "besleme + istifleme"),
    ("kuru temizleme",            0.80, "katlama + deforme malzeme"),
    ("firin ve pastane",          0.70, "iki elli sekillendirme"),
    ("cam ve cerceve",            0.70, "hassas yerlestirme"),
    ("temizlik sirketi",          0.70, "yuzey kaplama + genel ev isi"),
    ("oto yikama",                0.60, "yuzey kaplama"),
    ("kafe",                      0.50, "tekrarli hazirlik dizisi"),
]

# ---------------------------------------------------------------------------
# 2) ILCE / KUME LISTESI
#    Istanbul'da el isciligi yogunlugunun kumelendigi bolgeler
# ---------------------------------------------------------------------------

BOLGELER = [
    "Merter Istanbul",
    "Osmanbey Sisli Istanbul",
    "Ikitelli OSB Istanbul",
    "Perpa Okmeydani Istanbul",
    "Persembe Pazari Karakoy Istanbul",
    "Bayrampasa Istanbul",
    "Zeytinburnu Istanbul",
    "Modoko Umraniye Istanbul",
]

# Varsayilan olarak en yuksek agirlikli 8 kategori x 8 bolge taranir.
VARSAYILAN_KATEGORI_SAYISI = 8


def api_key():
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not key:
        sys.exit(
            "HATA: GOOGLE_PLACES_API_KEY tanimli degil.\n"
            "  export GOOGLE_PLACES_API_KEY='...'\n"
            "Anahtari console.cloud.google.com > Places API (New) uzerinden alabilirsin."
        )
    return key


def text_search(query, key, page_token=None, page_size=20):
    """Places API Text Search (New). (results, next_page_token) doner."""
    payload = {
        "textQuery": query,
        "languageCode": "tr",
        "regionCode": "TR",
        "pageSize": page_size,
    }
    if page_token:
        payload["pageToken"] = page_token

    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detay = e.read().decode("utf-8", errors="ignore")[:300]
        print(f"  ! HTTP {e.code} :: {query} :: {detay}", file=sys.stderr)
        return [], None
    except Exception as e:
        print(f"  ! hata :: {query} :: {e}", file=sys.stderr)
        return [], None

    return data.get("places", []), data.get("nextPageToken")


def skorla(agirlik, telefon, website, yorum_sayisi):
    """
    Skor, savunulabilir ve seffaf olsun diye 3 bilesenden olusur:
      0.70  kategori transfer agirligi   -> veri degeri
      0.15  telefon var mi               -> erisilebilirlik
      0.15  web sitesi var mi            -> kurumsallik / karar verici bulma kolayligi
    Yorum sayisi skora girmez, bilgi amacli tasinir:
      atolyelerde dusuk yorum = kotu isletme degil, sadece tuketiciye kapali is.
    """
    s = 0.70 * agirlik
    s += 0.15 if telefon else 0.0
    s += 0.15 if website else 0.0
    return round(s, 3)


def topla(kategoriler, bolgeler, max_pages, key, bekleme=2.0):
    gorulen = {}
    toplam_istek = 0

    for terim, agirlik, primitif in kategoriler:
        for bolge in bolgeler:
            query = f"{terim} {bolge}"
            token = None
            for sayfa in range(max_pages):
                sonuclar, token = text_search(query, key, page_token=token)
                toplam_istek += 1
                for p in sonuclar:
                    pid = p.get("id")
                    if not pid or pid in gorulen:
                        continue
                    if p.get("businessStatus") not in (None, "OPERATIONAL"):
                        continue
                    loc = p.get("location") or {}
                    tel = p.get("nationalPhoneNumber") or ""
                    web = p.get("websiteUri") or ""
                    gorulen[pid] = {
                        "place_id": pid,
                        "isletme": (p.get("displayName") or {}).get("text", ""),
                        "kategori": terim,
                        "primitif": primitif,
                        "bolge": bolge.replace(" Istanbul", ""),
                        "adres": p.get("formattedAddress", ""),
                        "lat": loc.get("latitude", ""),
                        "lng": loc.get("longitude", ""),
                        "telefon": tel,
                        "website": web,
                        "puan": p.get("rating", ""),
                        "yorum_sayisi": p.get("userRatingCount", ""),
                        "google_tipi": (p.get("primaryTypeDisplayName") or {}).get("text", ""),
                        "transfer_agirligi": agirlik,
                        "skor": skorla(agirlik, tel, web, p.get("userRatingCount")),
                    }
                print(f"  {query} [s{sayfa+1}] -> {len(sonuclar)} sonuc, toplam {len(gorulen)}")
                if not token:
                    break
                time.sleep(bekleme)  # nextPageToken aktiflesme suresi
    return list(gorulen.values()), toplam_istek


def yaz(kayitlar, path):
    if not kayitlar:
        print("Kayit yok, CSV yazilmadi.")
        return
    kayitlar.sort(key=lambda r: (-r["skor"], r["bolge"], r["isletme"]))
    alanlar = list(kayitlar[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=alanlar)
        w.writeheader()
        w.writerows(kayitlar)
    print(f"\n{len(kayitlar)} isletme -> {path}")


def ozet(kayitlar):
    if not kayitlar:
        return
    print("\n--- kategori bazinda ---")
    from collections import Counter
    c = Counter(r["kategori"] for r in kayitlar)
    for k, n in c.most_common():
        print(f"  {n:4d}  {k}")
    print("\n--- bolge bazinda ---")
    c = Counter(r["bolge"] for r in kayitlar)
    for k, n in c.most_common():
        print(f"  {n:4d}  {k}")
    print("\n--- en yuksek skorlu 10 ---")
    for r in kayitlar[:10]:
        print(f"  {r['skor']:.3f}  {r['isletme'][:38]:38s}  {r['bolge']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="saha_listesi.csv")
    ap.add_argument("--max-pages", type=int, default=2, help="sorgu basina sayfa (20 sonuc/sayfa)")
    ap.add_argument("--kategori-sayisi", type=int, default=VARSAYILAN_KATEGORI_SAYISI)
    ap.add_argument("--tum-kategoriler", action="store_true")
    args = ap.parse_args()

    key = api_key()
    kats = KATEGORILER if args.tum_kategoriler else KATEGORILER[: args.kategori_sayisi]

    print(f"{len(kats)} kategori x {len(BOLGELER)} bolge x {args.max_pages} sayfa taraniyor...\n")
    kayitlar, istek = topla(kats, BOLGELER, args.max_pages, key)
    yaz(kayitlar, args.out)
    ozet(kayitlar)
    print(f"\nToplam API istegi: {istek}")


if __name__ == "__main__":
    main()
