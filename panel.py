#!/usr/bin/env python3
"""
panel.py  -  saha_map.py çıktısını operasyon paneline çevirir.

Çalıştırma:
    streamlit run panel.py

Panelin tezi:
    1 milyon saat bir hacim problemi değil, kapsama problemi.
    Kapı kapı gezmek hacmi optimize eder, taksonomi kapsamayı optimize eder.
"""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="shift | İstanbul Saha Haritası", layout="wide")

CSV = "saha_listesi.csv"

# ---------------------------------------------------------------------------
# Gösterim eşlemeleri.
# CSV'deki değerler ASCII, ekranda Türkçe görünsün diye burada çevriliyor.
# Böylece scraper'ı baştan çalıştırmaya gerek kalmıyor.
# ---------------------------------------------------------------------------

KATEGORI_AD = {
    "ayakkabi imalathanesi": "Ayakkabı imalathanesi",
    "beyaz esya servisi": "Beyaz eşya servisi",
    "cam ve cerceve": "Cam ve çerçeve",
    "elektronik tamir": "Elektronik tamir",
    "firin ve pastane": "Fırın ve pastane",
    "kafe": "Kafe",
    "konfeksiyon atolyesi": "Konfeksiyon atölyesi",
    "kuru temizleme": "Kuru temizleme",
    "kuyumcu atolyesi": "Kuyumcu atölyesi",
    "matbaa": "Matbaa",
    "mobilya atolyesi": "Mobilya atölyesi",
    "oto tamir servisi": "Oto tamir servisi",
    "oto yikama": "Oto yıkama",
    "paketleme ve depo": "Paketleme ve depo",
    "temizlik sirketi": "Temizlik şirketi",
    "torna tesviye atolyesi": "Torna tesviye atölyesi",
}

BOLGE_AD = {
    "Bayrampasa": "Bayrampaşa",
    "Ikitelli OSB": "İkitelli OSB",
    "Merter": "Merter",
    "Modoko Umraniye": "Modoko / Ümraniye",
    "Osmanbey Sisli": "Osmanbey / Şişli",
    "Perpa Okmeydani": "Perpa / Okmeydanı",
    "Persembe Pazari Karakoy": "Perşembe Pazarı / Karaköy",
    "Zeytinburnu": "Zeytinburnu",
}

PRIMITIF_AD = {
    "besleme + istifleme": "Besleme + istifleme",
    "deforme malzeme + yapistirma": "Deforme malzeme + yapıştırma",
    "deforme malzeme manipulasyonu": "Deforme malzeme manipülasyonu",
    "hassas hizalama + alet kullanimi": "Hassas hizalama + alet kullanımı",
    "hassas yerlestirme": "Hassas yerleştirme",
    "iki elli montaj + alet kullanimi": "İki elli montaj + alet kullanımı",
    "iki elli sekillendirme": "İki elli şekillendirme",
    "ince motor manipulasyon": "İnce motor manipülasyon",
    "katlama + deforme malzeme": "Katlama + deforme malzeme",
    "kavra-yerlestir + siniflandirma": "Kavra-yerleştir + sınıflandırma",
    "kisitli alanda alet kullanimi": "Kısıtlı alanda alet kullanımı",
    "sokme-takma dizisi": "Sökme-takma dizisi",
    "tekrarli hazirlik dizisi": "Tekrarlı hazırlık dizisi",
    "yuzey kaplama": "Yüzey kaplama",
    "yuzey kaplama + genel ev isi": "Yüzey kaplama + genel ev işi",
}

SUTUN_AD = {
    "isletme": "İşletme",
    "kategori": "Kategori",
    "primitif": "Primitif",
    "bolge": "Bölge",
    "adres": "Adres",
    "telefon": "Telefon",
    "website": "Web sitesi",
    "skor": "Skor",
}


@st.cache_data
def yukle(path):
    df = pd.read_csv(path)
    for c in ("lat", "lng", "skor", "transfer_agirligi"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["telefon"] = df["telefon"].fillna("")
    df["website"] = df["website"].fillna("")
    df["kategori"] = df["kategori"].map(lambda x: KATEGORI_AD.get(x, x))
    df["bolge"] = df["bolge"].map(lambda x: BOLGE_AD.get(x, x))
    df["primitif"] = df["primitif"].map(lambda x: PRIMITIF_AD.get(x, x))
    return df


try:
    df = yukle(CSV)
except FileNotFoundError:
    st.error(f"{CSV} bulunamadı. Önce `python3 saha_map.py --out {CSV}` çalıştır.")
    st.stop()

st.title("İstanbul egocentric veri arz haritası")
st.caption(
    "Kategoriler, endüstriyel manipülasyon primitiflerine transfer değerine göre "
    "ağırlıklandırıldı. Skor = 0,70 × transfer ağırlığı + 0,15 telefon + 0,15 web sitesi."
)

# --------------------------------------------------------------- filtreler
with st.sidebar:
    st.header("Filtre")
    bolgeler = st.multiselect("Bölge", sorted(df["bolge"].unique()), default=sorted(df["bolge"].unique()))
    kategoriler = st.multiselect("Kategori", sorted(df["kategori"].unique()), default=sorted(df["kategori"].unique()))
    min_skor = st.slider("Minimum skor", 0.0, 1.0, 0.60, 0.05)
    sadece_tel = st.checkbox("Sadece telefonu olanlar", value=True)

    st.divider()
    st.header("Saha varsayımları")
    st.caption("Hepsi varsayım. Gerçek kriterler girildiğinde model yeniden kalibre olur.")
    kapasite = st.number_input("Haftalık ziyaret kapasitesi", 10, 500, 75, 5)
    donusum = st.slider("Ziyaret → evet dönüşümü (%)", 1, 50, 12, 1)
    saat_isletme = st.number_input("İşletme başına haftalık saat", 1, 40, 6)
    kabul_orani = st.slider("Kabul oranı (%)", 10, 100, 45, 5)

f = df[
    df["bolge"].isin(bolgeler)
    & df["kategori"].isin(kategoriler)
    & (df["skor"] >= min_skor)
]
if sadece_tel:
    f = f[f["telefon"].astype(str).str.len() > 3]

# --------------------------------------------------------------- üst metrikler
# Bağlayıcı kısıt liste büyüklüğü değil, haftalık ziyaret kapasitesi.
ziyaret = min(len(f), kapasite)
evet = ziyaret * donusum / 100
ham = evet * saat_isletme
kabul = ham * kabul_orani / 100

c1, c2, c3, c4 = st.columns(4)
c1.metric("Havuzdaki hedef", f"{len(f):,}")
c2.metric("Haftalık ziyaret", f"{ziyaret:,}")
c3.metric("Haftalık ham saat", f"{ham:,.0f}")
c4.metric("Haftalık kabul saat", f"{kabul:,.0f}")

if kabul > 0:
    st.caption(
        f"100 kabul edilmiş saat: ~{100 / kabul:.1f} hafta.  |  "
        f"1.000 saat: ~{1000 / kabul:.0f} hafta.  |  "
        f"Havuz, {len(f) / kapasite:.0f} haftalık ziyaret kapasitesine denk geliyor."
    )
st.caption(
    "Bağlayıcı kısıt liste büyüklüğü değil, haftalık ziyaret kapasitesi. "
    "Model bu yüzden havuzu değil kapasiteyi baz alıyor."
)

st.divider()

# --------------------------------------------------------------- kapsama matrisi
st.subheader("Kapsama matrisi")
st.caption(
    "Boş ve açık hücreler eksik veri değil, toplanmamış primitif demek. "
    "Asıl hedefleme buradan çıkar."
)
pivot = f.pivot_table(index="kategori", columns="bolge", values="place_id", aggfunc="count").fillna(0).astype(int)
pivot.index.name = "Kategori"
pivot.columns.name = "Bölge"
st.dataframe(pivot.style.background_gradient(cmap="Greens", axis=None), use_container_width=True)
st.caption(
    "Not: sorgu başına 2 sayfa çekildi, hücre başına tavan 40. "
    "Bu matris bolluğu değil kıtlığı ölçmekte güvenilir."
)

# --------------------------------------------------------------- harita ve dağılım
sol, sag = st.columns([3, 2])
with sol:
    st.subheader("Harita")
    harita = f[["lat", "lng"]].dropna().rename(columns={"lng": "lon"})
    if len(harita):
        st.map(harita, size=30)
    else:
        st.info("Koordinat yok.")

with sag:
    st.subheader("Primitif dağılımı")
    prim = f.groupby("primitif")["place_id"].count().sort_values(ascending=False)
    st.bar_chart(prim)

st.divider()

# --------------------------------------------------------------- günlük rota
st.subheader("Günlük saha rotası")
r1, r2 = st.columns([1, 2])
with r1:
    gunluk = st.number_input("Gün başına ziyaret", 5, 60, 15)
with r2:
    secili_bolge = st.selectbox("Bölge seç", sorted(f["bolge"].unique()) if len(f) else ["-"])

rota = f[f["bolge"] == secili_bolge].sort_values("skor", ascending=False).head(gunluk)
st.dataframe(
    rota[["isletme", "kategori", "primitif", "adres", "telefon", "skor"]].rename(columns=SUTUN_AD),
    use_container_width=True,
    hide_index=True,
)
st.download_button(
    "Rotayı CSV indir",
    rota.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"rota_{secili_bolge}.csv",
    mime="text/csv",
)

st.divider()
st.subheader("Tüm liste")
st.dataframe(
    f.sort_values("skor", ascending=False)[
        ["isletme", "kategori", "primitif", "bolge", "adres", "telefon", "website", "skor"]
    ].rename(columns=SUTUN_AD),
    use_container_width=True,
    hide_index=True,
)
st.download_button(
    "Tüm listeyi CSV indir",
    f.to_csv(index=False).encode("utf-8-sig"),
    file_name="saha_listesi_filtreli.csv",
    mime="text/csv",
)
