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
    page_title="Otomatik Vardiyalı Dekont Portalı",
    page_icon="⏰",
    layout="wide"
)

st.markdown("""
    <style>
    .report-card-ready {
        background-color: #DCFCE7;
        border: 2px solid #16A34A;
        padding: 18px;
        border-radius: 10px;
        margin-bottom: 15px;
    }
    .report-card-waiting {
        background-color: #FEF3C7;
        border: 2px solid #D97706;
        padding: 18px;
        border-radius: 10px;
        margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# VERİTABANI BAĞLANTISI
# ---------------------------------------------------------
conn = sqlite3.connect("dekontlar_v3.db", check_same_thread=False)
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
        raw_text TEXT
    )
''')
conn.commit()

# Metin Ayrıştırma Fonksiyonu
def metinden_veri_ayikla(metin, yon="Gelen (Girdi)"):
    iban_match = re.search(r'TR\s?\d{2}(?:\s?\d{4}){5}', metin, re.IGNORECASE)
    iban = iban_match.group(0).upper().replace(" ", "") if iban_match else "IBAN Bulunamadı"

    tutar = 0.0
    tutar_match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:TL|TRY|₺)', metin, re.IGNORECASE)
    if tutar_match:
        t_str = tutar_match.group(1).replace(".", "").replace(",", ".")
        try:
            tutar = float(t_str)
        except:
            tutar = 0.0

    saat_match = re.search(r'\b([01]?\d|2[0-3]):[0-5]\d\b', metin)
    saat = saat_match.group(0) if saat_match else datetime.now().strftime("%H:%M")

    m_lower = metin.lower()
    banka = "Diğer / Belirtilmedi"
    if "akbank" in m_lower: banka = "Akbank"
    elif "garanti" in m_lower: banka = "Garanti BBVA"
    elif "iş bank" in m_lower or "isbank" in m_lower: banka = "İş Bankası"
    elif "ziraat" in m_lower: banka = "Ziraat Bankası"
    elif "yapı kredi" in m_lower or "yapikredi" in m_lower: banka = "Yapı Kredi"

    satirlar = [s.strip() for s in metin.split('\n') if len(s.strip()) > 2]
    gonderen = satirlar[0] if len(satirlar) > 0 else "Bilinmeyen Gönderen"
    alici = "Sıla Sarı"

    return {
        "tarih": datetime.now().strftime("%Y-%m-%d"),
        "saat": saat,
        "islem_yoni": yon,
        "gonderen": gonderen,
        "alici": alici,
        "banka": banka,
        "iban": iban,
        "tutar": tutar
    }

# Excel Oluşturucu Yardımcı Fonksiyon
def excel_raporu_olustur(df_subset, rapor_basligi):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_subset.to_excel(writer, sheet_name='Dekont_Listesi', index=False)
        iban_summary = df_subset.groupby(['alici', 'banka', 'iban', 'islem_yoni'])['tutar'].sum().unstack(fill_value=0).reset_index()
        iban_summary.to_excel(writer, sheet_name='IBAN_Ozet_Bakiye', index=False)
    return buffer.getvalue()

# ---------------------------------------------------------
# ARAYÜZ & DEKONT YÜKLEME
# ---------------------------------------------------------
st.title("💳 Vardiyalı & Saatlik Hazır Dekont Portalı")

with st.sidebar:
    st.header("⚙️ Dekont Yönü")
    islem_yoni = st.radio("Yön Seçin:", ["🟢 Gelen Para (Girdi)", "🔴 Giden Para (Çıktı)"])
    islem_yoni_clean = "Gelen (Girdi)" if "Gelen" in islem_yoni else "Giden (Çıktı)"

yuklenen_dosya = st.file_uploader("📸 Dekont Görseli Sürükleyip Bırakın", type=["png", "jpg", "jpeg"])

if yuklenen_dosya is not None:
    if "son_dosya_v3" not in st.session_state or st.session_state.son_dosya_v3 != yuklenen_dosya.name:
        with st.spinner("🔍 Dekont taranıyor..."):
            try:
                img = Image.open(yuklenen_dosya)
                okunan_metin = pytesseract.image_to_string(img, lang="tur")
                if okunan_metin.strip():
                    veri = metinden_veri_ayikla(okunan_metin, yon=islem_yoni_clean)
                    cursor.execute(
                        "INSERT INTO dekontlar (tarih, saat, islem_yoni, gonderen, alici, banka, iban, tutar, raw_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (veri["tarih"], veri["saat"], veri["islem_yoni"], veri["gonderen"], veri["alici"], veri["banka"], veri["iban"], veri["tutar"], okunan_metin)
                    )
                    conn.commit()
                    st.session_state.son_dosya_v3 = yuklenen_dosya.name
                    st.success(f"✅ Dekont İşlendi! ({veri['saat']} - {veri['tutar']:,.2f} TL)")
                    st.rerun()
            except Exception as e:
                st.error(f"Hata: {str(e)}")

st.divider()

# ---------------------------------------------------------
# OTOMATİK 11:00 VE 19:00 HAZIR RAPOR PANELLERİ
# ---------------------------------------------------------
st.subheader("⏰ Bugünün Otomatik Saat Raporları (11:00 & 19:00)")

df = pd.read_sql_query("SELECT * FROM dekontlar ORDER BY id DESC", conn)
bugun_str = datetime.now().strftime("%Y-%m-%d")
simdiki_saat = datetime.now().time()

if not df.empty:
    df_bugun = df[df['tarih'] == bugun_str].copy()
    
    # Saat Ayrıştırma
    df_bugun['saat_obj'] = pd.to_datetime(df_bugun['saat'], format='%H:%M', errors='coerce').dt.time

    # 1. SABAH 11:00 RAPORU (Saat 11:00 ve Öncesi)
    df_11 = df_bugun[df_bugun['saat_obj'] <= time(11, 0)]
    
    # 2. AKŞAM 19:00 RAPORU (Saat 11:00 ile 19:00 Arası)
    df_19 = df_bugun[(df_bugun['saat_obj'] > time(11, 0)) & (df_bugun['saat_obj'] <= time(19, 0))]

    col_a, col_b = st.columns(2)

    # ☀️ 11:00 Rapor Kartı
    with col_a:
        st.markdown('### ☀️ 11:00 Sabah Vardiya Raporu')
        gelen_11 = df_11[df_11['islem_yoni'] == 'Gelen (Girdi)']['tutar'].sum()
        giden_11 = df_11[df_11['islem_yoni'] == 'Giden (Çıktı)']['tutar'].sum()
        
        st.write(f"**Gelen:** {gelen_11:,.2f} TL | **Giden:** {giden_11:,.2f} TL | **İşlem:** {len(df_11)} Adet")
        
        if not df_11.empty:
            excel_11 = excel_raporu_olustur(df_11, "11:00 Raporu")
            st.download_button(
                label="📥 11:00 Excel Raporunu İndir",
                data=excel_11,
                file_name=f"Dekont_Raporu_1100_{bugun_str}.xlsx",
                mime="application/vnd.openpyxlformat-officedocument.spreadsheetml.sheet",
                key="btn_11"
            )
        else:
            st.info("Saat 11:00'e kadar henüz dekont kaydı girilmedi.")

    # 🌙 19:00 Rapor Kartı
    with col_b:
        st.markdown('### 🌙 19:00 Akşam Vardiya Raporu')
        gelen_19 = df_19[df_19['islem_yoni'] == 'Gelen (Girdi)']['tutar'].sum()
        giden_19 = df_19[df_19['islem_yoni'] == 'Giden (Çıktı)']['tutar'].sum()
        
        st.write(f"**Gelen:** {gelen_19:,.2f} TL | **Giden:** {giden_19:,.2f} TL | **İşlem:** {len(df_19)} Adet")
        
        if not df_19.empty:
            excel_19 = excel_raporu_olustur(df_19, "19:00 Raporu")
            st.download_button(
                label="📥 19:00 Excel Raporunu İndir",
                data=excel_19,
                file_name=f"Dekont_Raporu_1900_{bugun_str}.xlsx",
                mime="application/vnd.openpyxlformat-officedocument.spreadsheetml.sheet",
                key="btn_19"
            )
        else:
            st.info("Saat 11:00 - 19:00 arasında henüz dekont kaydı girilmedi.")

    st.divider()

    # 📋 Tüm Kayıtlar
    st.subheader("📋 Tüm Günlük Dekont Listesi")
    df_display = df[['tarih', 'saat', 'islem_yoni', 'gonderen', 'alici', 'banka', 'iban', 'tutar']].copy()
    df_display.columns = ['Tarih', 'Saat', 'İşlem Yönü', 'Gönderen', 'Alıcı', 'Banka', 'IBAN No', 'Tutar (TL)']
    st.dataframe(df_display, use_container_width=True)

else:
    st.info("Henüz veritabanında kayıt yok. Dekont yüklediğinizde 11:00 ve 19:00 raporları otomatik oluşacaktır.")
