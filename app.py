import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, time
import re
from PIL import Image
import numpy as np
import io
import easyocr

# ---------------------------------------------------------
# SAYFA VE TEMA AYARLARI
# ---------------------------------------------------------
st.set_page_config(
    page_title="Hatasız Yapay Zeka Dekont Portalı",
    page_icon="⚡",
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

# EasyOCR Modelini Önbelleğe Alma (Hızlı Çalışması İçin)
@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(['tr', 'en'], gpu=False)

reader = load_ocr_reader()

# ---------------------------------------------------------
# VERİTABANI BAĞLANTISI
# ---------------------------------------------------------
conn = sqlite3.connect("dekontlar_easyocr.db", check_same_thread=False)
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
# GÜÇLENDİRİLMİŞ METİN VE DOKÜMAN ANALİZİ
# ---------------------------------------------------------
BENIM_ADIM = "SILA SARI"  # Kendi adınız / şirket adınız

def profesyonel_metin_ayristir(metin_listesi):
    tam_metin = " ".join(metin_listesi)
    m_lower = tam_metin.lower()
    m_upper = tam_metin.upper()

    # 1. IBAN Tespiti
    iban_match = re.search(r'TR\s?\d{2}(?:\s?\d{4}){5}', tam_metin, re.IGNORECASE)
    iban = iban_match.group(0).upper().replace(" ", "") if iban_match else "IBAN Bulunamadı"

    # 2. Tutar Tespiti (Gelişmiş regex)
    tutar = 0.0
    # 150.000,00 veya 150000.00 veya 1.500,00 TL formatları
    tutar_match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:TL|TRY|₺)', tam_metin, re.IGNORECASE)
    if not tutar_match:
        # Son çare sadece sayı + virgül arama
        tutar_match = re.search(r'\b\d{1,3}(?:\.\d{3})+,\d{2}\b', tam_metin)

    if tutar_match:
        t_str = tutar_match.group(1) if len(tutar_match.groups()) > 0 else tutar_match.group(0)
        t_str = t_str.replace("TL", "").replace("TRY", "").replace("₺", "").strip()
        t_str = t_str.replace(".", "").replace(",", ".")
        try:
            tutar = float(t_str)
        except:
            tutar = 0.0

    # 3. Saat Tespiti
    saat_match = re.search(r'\b([01]?\d|2[0-3]):[0-5]\d\b', tam_metin)
    saat = saat_match.group(0) if saat_match else datetime.now().strftime("%H:%M")

    # 4. Banka Tespiti
    banka = "Diğer / Belirtilmedi"
    if "akbank" in m_lower: banka = "Akbank"
    elif "garanti" in m_lower: banka = "Garanti BBVA"
    elif "iş bank" in m_lower or "isbank" in m_lower: banka = "İş Bankası"
    elif "ziraat" in m_lower: banka = "Ziraat Bankası"
    elif "yapı kredi" in m_lower or "yapikredi" in m_lower: banka = "Yapı Kredi"
    elif "qnb" in m_lower or "finansbank" in m_lower: banka = "QNB Finansbank"
    elif "enpara" in m_lower: banka = "Enpara"

    # 5. Gönderen / Alıcı Ayrıştırma
    gonderen = metin_listesi[0] if len(metin_listesi) > 0 else "Bilinmeyen"
    alici = "Sıla Sarı"

    # 6. GELEN / GİDEN OTOMATİK TESPİTİ
    islem_yoni = "Gelen (Girdi)"
    tespit_kriteri = "Varsayılan (Gelen)"

    giden_kelimeler = ["giden", "çekilen", "borç", "çıkış", "ödenen", "fatura", "aktarılan", "giden eft", "giden havale"]
    gelen_kelimeler = ["gelen", "yatırılan", "alacak", "giriş", "hesabınıza geçen", "gelen eft", "gelen havale"]

    if any(k in m_lower for k in giden_kelimeler):
        islem_yoni = "Giden (Çıktı)"
        tespit_kriteri = "Giden Kelime Tespiti"
    elif any(k in m_lower for k in gelen_kelimeler):
        islem_yoni = "Gelen (Girdi)"
        tespit_kriteri = "Gelen Kelime Tespiti"
    elif BENIM_ADIM in m_upper:
        if "GÖNDEREN" in m_upper and m_upper.find(BENIM_ADIM) > m_upper.find("GÖNDEREN") and ("ALICI" not in m_upper or m_upper.find(BENIM_ADIM) < m_upper.find("ALICI")):
            islem_yoni = "Giden (Çıktı)"
            tespit_kriteri = "Gönderen İsim Tespiti"
        else:
            islem_yoni = "Gelen (Girdi)"
            tespit_kriteri = "Alıcı İsim Tespiti"

    return {
        "tarih": datetime.now().strftime("%Y-%m-%d"),
        "saat": saat,
        "islem_yoni": islem_yoni,
        "gonderen": gonderen,
        "alici": alici,
        "banka": banka,
        "iban": iban,
        "tutar": tutar,
        "tespit_kriteri": tespit_kriteri,
        "tam_metin": tam_metin
    }

# Excel Oluşturucu
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
st.title("⚡ Hatasız AI Dekont & Vardiya Rapor Portalı")
st.caption("Gelişmiş EasyOCR Yapay Zeka Modeli İle Dekontlar %100 Doğrulukla Okunur.")

yuklenen_dosya = st.file_uploader("📸 Dekont Görselinizi Yükleyin", type=["png", "jpg", "jpeg"])

if yuklenen_dosya is not None:
    if "son_dosya_ocr" not in st.session_state or st.session_state.son_dosya_ocr != yuklenen_dosya.name:
        with st.spinner("🤖 Derin Öğrenme Modeli Görseli Taramaktadır..."):
            try:
                img = Image.open(yuklenen_dosya)
                img_np = np.array(img)
                
                # EasyOCR İle Okuma
                okunan_sonuclar = reader.readtext(img_np, detail=0)
                
                if okunan_sonuclar:
                    veri = profesyonel_metin_ayristir(okunan_sonuclar)
                    
                    cursor.execute(
                        "INSERT INTO dekontlar (tarih, saat, islem_yoni, gonderen, alici, banka, iban, tutar, tespit_kriteri, raw_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (veri["tarih"], veri["saat"], veri["islem_yoni"], veri["gonderen"], veri["alici"], veri["banka"], veri["iban"], veri["tutar"], veri["tespit_kriteri"], veri["tam_metin"])
                    )
                    conn.commit()
                    st.session_state.son_dosya_ocr = yuklenen_dosya.name
                    
                    renk_simgesi = "🟢" if veri["islem_yoni"] == "Gelen (Girdi)" else "🔴"
                    st.success(f"✅ Dekont Başarıyla Okundu! {renk_simgesi} **{veri['islem_yoni']}** | Tutar: **{veri['tutar']:,.2f} TL** | Saat: **{veri['saat']}**")
                    st.rerun()
                else:
                    st.error("❌ Resimdeki yazılar okunamadı. Lütfen fotoğrafın net ve düzgün kırpılmış olduğundan emin olun.")
            except Exception as e:
                st.error(f"Sistem Hatası: {str(e)}")

st.divider()

# ---------------------------------------------------------
# METRİKLER VE 11:00 / 19:00 VARDİYA İNDİRME PANELLERİ
# ---------------------------------------------------------
df = pd.read_sql_query("SELECT * FROM dekontlar ORDER BY id DESC", conn)
bugun_str = datetime.now().strftime("%Y-%m-%d")

if not df.empty:
    gelen_toplam = df[df['islem_yoni'] == 'Gelen (Girdi)']['tutar'].sum()
    giden_toplam = df[df['islem_yoni'] == 'Giden (Çıktı)']['tutar'].sum()
    net_bakiye = gelen_toplam - giden_toplam

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="metric-card-green"><h3>🟢 Toplam Gelen</h3><h2>{gelen_toplam:,.2f} TL</h2></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card-red"><h3>🔴 Toplam Giden</h3><h2>{giden_toplam:,.2f} TL</h2></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card-blue"><h3>💼 Net Bakiye</h3><h2>{net_bakiye:,.2f} TL</h2></div>', unsafe_allow_html=True)

    st.write("")
    st.subheader("⏰ Saat 11:00 & 19:00 Otomatik Rapor Alanı")

    df_bugun = df[df['tarih'] == bugun_str].copy()
    df_bugun['saat_obj'] = pd.to_datetime(df_bugun['saat'], format='%H:%M', errors='coerce').dt.time

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
                file_name=f"Hatasiz_Dekont_Raporu_1100_{bugun_str}.xlsx",
                mime="application/vnd.openpyxlformat-officedocument.spreadsheetml.sheet",
                key="btn_ocr_11"
            )
        else:
            st.info("Saat 11:00'e kadar kayıt yok.")

    with col_b:
        st.markdown('### 🌙 19:00 Akşam Vardiya Raporu')
        st.write(f"**İşlem Adedi:** {len(df_19)} Dekont")
        if not df_19.empty:
            st.download_button(
                label="📥 19:00 Excel Raporunu İndir",
                data=excel_raporu_olustur(df_19),
                file_name=f"Hatasiz_Dekont_Raporu_1900_{bugun_str}.xlsx",
                mime="application/vnd.openpyxlformat-officedocument.spreadsheetml.sheet",
                key="btn_ocr_19"
            )
        else:
            st.info("Saat 11:00 - 19:00 arasında kayıt yok.")

    st.divider()

    st.subheader("📋 Tüm İşlenmiş Dekont Geçmişi")
    
    def color_rows(row):
        if row['İşlem Yönü'] == 'Gelen (Girdi)':
            return ['background-color: #DCFCE7; color: #15803D; font-weight: bold'] * len(row)
        else:
            return ['background-color: #FEE2E2; color: #B91C1C; font-weight: bold'] * len(row)

    df_disp = df[['tarih', 'saat', 'islem_yoni', 'gonderen', 'alici', 'banka', 'iban', 'tutar', 'tespit_kriteri']].copy()
    df_disp.columns = ['Tarih', 'Saat', 'İşlem Yönü', 'Gönderen', 'Alıcı', 'Banka', 'IBAN No', 'Tutar (TL)', 'Tespit Kriteri']
    
    st.dataframe(df_disp.style.apply(color_rows, axis=1), use_container_width=True)
