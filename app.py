import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, time
import re
from PIL import Image
import pytesseract
import io

# ---------------------------------------------------------
# SAYFA VE TEMA AYARLARI
# ---------------------------------------------------------
st.set_page_config(
    page_title="Tam Otomatik Dekont & Vardiya Portalı",
    page_icon="🤖",
    layout="wide"
)

st.markdown("""
    <style>
    .metric-card-green {
        background-color: #DCFCE7;
        border-left: 5px solid #16A34A;
        padding: 15px;
        border-radius: 8px;
        color: #14532D;
    }
    .metric-card-red {
        background-color: #FEE2E2;
        border-left: 5px solid #DC2626;
        padding: 15px;
        border-radius: 8px;
        color: #7F1D1D;
    }
    .metric-card-blue {
        background-color: #DBEAFE;
        border-left: 5px solid #2563EB;
        padding: 15px;
        border-radius: 8px;
        color: #1E3A8A;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# VERİTABANI BAĞLANTISI
# ---------------------------------------------------------
conn = sqlite3.connect("dekontlar_v4.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS dekontlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TEXT,
        saat TEXT,
        islem_yoni TEXT,
        gonderen TEXT,
        alici TEXT,
        banka TEXT,
        iban TEXT,
        tutar REAL,
        tespit_kriteri TEXT,
        raw_text TEXT
    )
''')
conn.commit()

# ---------------------------------------------------------
# 🤖 KENDİ KENDİNE GELEN / GİDEN AYRIŞTIRMA MANTIĞI
# ---------------------------------------------------------
BENIM_ADIM = "SILA SARI"  # Kendi adınızı veya şirket adınızı buraya yazabilirsiniz

def akilli_metin_ayristir(metin):
    m_upper = metin.upper()
    m_lower = metin.lower()

    # 1. IBAN Tespiti
    iban_match = re.search(r'TR\s?\d{2}(?:\s?\d{4}){5}', metin, re.IGNORECASE)
    iban = iban_match.group(0).upper().replace(" ", "") if iban_match else "IBAN Bulunamadı"

    # 2. Tutar Tespiti
    tutar = 0.0
    tutar_match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:TL|TRY|₺)', metin, re.IGNORECASE)
    if tutar_match:
        t_str = tutar_match.group(1).replace(".", "").replace(",", ".")
        try:
            tutar = float(t_str)
        except:
            tutar = 0.0

    # 3. Saat Tespiti
    saat_match = re.search(r'\b([01]?\d|2[0-3]):[0-5]\d\b', metin)
    saat = saat_match.group(0) if saat_match else datetime.now().strftime("%H:%M")

    # 4. Banka Tespiti
    banka = "Diğer / Belirtilmedi"
    if "akbank" in m_lower: banka = "Akbank"
    elif "garanti" in m_lower: banka = "Garanti BBVA"
    elif "iş bank" in m_lower or "isbank" in m_lower: banka = "İş Bankası"
    elif "ziraat" in m_lower: banka = "Ziraat Bankası"
    elif "yapı kredi" in m_lower or "yapikredi" in m_lower: banka = "Yapı Kredi"

    # 5. Gönderen / Alıcı Ayrıştırma
    satirlar = [s.strip() for s in metin.split('\n') if len(s.strip()) > 2]
    gonderen = satirlar[0] if len(satirlar) > 0 else "Bilinmeyen"
    alici = "Sıla Sarı"

    # 6. 🧠 OTOMATİK GELEN (GİRDİ) / GİDEN (ÇIKTI) KARARI
    islem_yoni = "Gelen (Girdi)" # Varsayılan
    tespit_kriteri = "Metin Analizi"

    gelen_kelimeler = ["gelen transfer", "yatırılan", "alacak", "hesabınıza geçen", "hesaba giriş", "gelen eft", "gelen havale"]
    giden_kelimeler = ["giden transfer", "çekilen", "borç", "hesabınızdan çıkan", "hesaptan çıkış", "giden eft", "giden havale", "ödenen", "fatura ödemesi"]

    # Kelime Kontrolü
    if any(k in m_lower for k in giden_kelimeler):
        islem_yoni = "Giden (Çıktı)"
        tespit_kriteri = "Giden Terim Tespiti"
    elif any(k in m_lower for k in gelen_kelimeler):
        islem_yoni = "Gelen (Girdi)"
        tespit_kriteri = "Gelen Terim Tespiti"
    # İsim Kontrolü (Gelişmiş)
    elif BENIM_ADIM in m_upper:
        # Eğer 'Gönderen' tarafında benim adım geçiyorsa para çıkmıştır
        if "GÖNDEREN" in m_upper and m_upper.find(BENIM_ADIM) > m_upper.find("GÖNDEREN") and ("ALICI" not in m_upper or m_upper.find(BENIM_ADIM) < m_upper.find("ALICI")):
            islem_yoni = "Giden (Çıktı)"
            tespit_kriteri = "Gönderen İsim Eşleşmesi"
        else:
            islem_yoni = "Gelen (Girdi)"
            tespit_kriteri = "Alıcı İsim Eşleşmesi"

    return {
        "tarih": datetime.now().strftime("%Y-%m-%d"),
        "saat": saat,
        "islem_yoni": islem_yoni,
        "gonderen": gonderen,
        "alici": alici,
        "banka": banka,
        "iban": iban,
        "tutar": tutar,
        "tespit_kriteri": tespit_kriteri
    }

# Excel Oluşturucu Yardımcı Fonksiyon
def excel_raporu_olustur(df_subset):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_subset.to_excel(writer, sheet_name='Dekont_Listesi', index=False)
        iban_summary = df_subset.groupby(['alici', 'banka', 'iban', 'islem_yoni'])['tutar'].sum().unstack(fill_value=0).reset_index()
        iban_summary.to_excel(writer, sheet_name='IBAN_Ozet_Bakiye', index=False)
    return buffer.getvalue()

# ---------------------------------------------------------
# ARAYÜZ
# ---------------------------------------------------------
st.title("🤖 Tam Otomatik Dekont & Vardiya Rapor Portalı")
st.caption("Gelen ve giden para ayrımı yapay zeka/OCR metin analizi ile tamamen otomatik yapılmaktadır.")

yuklenen_dosya = st.file_uploader("📸 Dekont Görselini Doğrudan Yükleyin (Manuel Seçim Yapmanıza Gerek Yokdur)", type=["png", "jpg", "jpeg"])

if yuklenen_dosya is not None:
    if "son_dosya_v4" not in st.session_state or st.session_state.son_dosya_v4 != yuklenen_dosya.name:
        with st.spinner("🔍 Dekont taranıyor ve yönü otomatik tespit ediliyor..."):
            try:
                img = Image.open(yuklenen_dosya)
                okunan_metin = pytesseract.image_to_string(img, lang="tur")
                if okunan_metin.strip():
                    veri = akilli_metin_ayristir(okunan_metin)
                    cursor.execute(
                        "INSERT INTO dekontlar (tarih, saat, islem_yoni, gonderen, alici, banka, iban, tutar, tespit_kriteri, raw_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (veri["tarih"], veri["saat"], veri["islem_yoni"], veri["gonderen"], veri["alici"], veri["banka"], veri["iban"], veri["tutar"], veri["tespit_kriteri"], okunan_metin)
                    )
                    conn.commit()
                    st.session_state.son_dosya_v4 = yuklenen_dosya.name
                    
                    renk_simgesi = "🟢" if veri["islem_yoni"] == "Gelen (Girdi)" else "🔴"
                    st.success(f"✅ Otomatik Tespit Edildi: {renk_simgesi} **{veri['islem_yoni']}** | Tutar: **{veri['tutar']:,.2f} TL** ({veri['saat']})")
                    st.rerun()
            except Exception as e:
                st.error(f"Hata oluştu: {str(e)}")

st.divider()

# ---------------------------------------------------------
# OTOMATİK 11:00 VE 19:00 VARDİYA RAPORLARI
# ---------------------------------------------------------
df = pd.read_sql_query("SELECT * FROM dekontlar ORDER BY id DESC", conn)
bugun_str = datetime.now().strftime("%Y-%m-%d")

if not df.empty:
    # Metrik Kartları
    gelen_toplam = df[df['islem_yoni'] == 'Gelen (Girdi)']['tutar'].sum()
    giden_toplam = df[df['islem_yoni'] == 'Giden (Çıktı)']['tutar'].sum()
    net_bakiye = gelen_toplam - giden_toplam

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="metric-card-green"><h3>🟢 Toplam Gelen (Girdi)</h3><h2>{gelen_toplam:,.2f} TL</h2></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card-red"><h3>🔴 Toplam Giden (Çıktı)</h3><h2>{giden_toplam:,.2f} TL</h2></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card-blue"><h3>💼 Net Günlük Bakiye</h3><h2>{net_bakiye:,.2f} TL</h2></div>', unsafe_allow_html=True)

    st.write("")
    st.subheader("⏰ Saat 11:00 & 19:00 Otomatik Rapor İndirme Alanı")

    df_bugun = df[df['tarih'] == bugun_str].copy()
    df_bugun['saat_obj'] = pd.to_datetime(df_bugun['saat'], format='%H:%M', errors='coerce').dt.time

    # Vardiyalar
    df_11 = df_bugun[df_bugun['saat_obj'] <= time(11, 0)]
    df_19 = df_bugun[(df_bugun['saat_obj'] > time(11, 0)) & (df_bugun['saat_obj'] <= time(19, 0))]

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('### ☀️ 11:00 Sabah Vardiya Raporu')
        st.write(f"**İşlem Adedi:** {len(df_11)} Dekont")
        if not df_11.empty:
            st.download_button(
                label="📥 11:00 Excel Raporunu İndir",
                data=excel_raporu_olustur(df_11),
                file_name=f"Otomatik_Dekont_Raporu_1100_{bugun_str}.xlsx",
                mime="application/vnd.openpyxlformat-officedocument.spreadsheetml.sheet",
                key="btn_auto_11"
            )
        else:
            st.info("Saat 11:00'e kadar henüz dekont girilmedi.")

    with col_b:
        st.markdown('### 🌙 19:00 Akşam Vardiya Raporu')
        st.write(f"**İşlem Adedi:** {len(df_19)} Dekont")
        if not df_19.empty:
            st.download_button(
                label="📥 19:00 Excel Raporunu İndir",
                data=excel_raporu_olustur(df_19),
                file_name=f"Otomatik_Dekont_Raporu_1900_{bugun_str}.xlsx",
                mime="application/vnd.openpyxlformat-officedocument.spreadsheetml.sheet",
                key="btn_auto_19"
            )
        else:
            st.info("Saat 11:00 - 19:00 arasında henüz dekont girilmedi.")

    st.divider()

    # Tablo Listesi ve Renklendirme
    st.subheader("📋 Otomatik Ayrıştırılan Tüm Dekont Geçmişi")
    
    def color_rows(row):
        if row['İşlem Yönü'] == 'Gelen (Girdi)':
            return ['background-color: #DCFCE7; color: #15803D; font-weight: bold'] * len(row)
        else:
            return ['background-color: #FEE2E2; color: #B91C1C; font-weight: bold'] * len(row)

    df_disp = df[['tarih', 'saat', 'islem_yoni', 'gonderen', 'alici', 'banka', 'iban', 'tutar', 'tespit_kriteri']].copy()
    df_disp.columns = ['Tarih', 'Saat', 'İşlem Yönü', 'Gönderen', 'Alıcı', 'Banka', 'IBAN No', 'Tutar (TL)', 'Tespit Kriteri']
    
    st.dataframe(df_disp.style.apply(color_rows, axis=1), use_container_width=True)

else:
    st.info("Sisteme henüz dekont yüklenmedi. Fotoğrafı bıraktığınız an yönü otomatik tespit edilecektir.")
