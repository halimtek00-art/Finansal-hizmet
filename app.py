import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import re
from PIL import Image
import pytesseract

# Sayfa Ayarları
st.set_page_config(
    page_title="Gerçek Dekont Okuyucu",
    page_icon="🧾",
    layout="wide"
)

# SQLite Veritabanı
conn = sqlite3.connect("dekontlar.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS dekontlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TEXT,
        saat TEXT,
        gonderen TEXT,
        alici TEXT,
        banka TEXT,
        iban TEXT,
        tutar REAL,
        raw_text TEXT
    )
''')
conn.commit()

# --- GELİŞMİŞ METİN AYRIŞTIRMA (REGEX) ---
def metinden_veri_ayikla(metin):
    # 1. IBAN Bulma (TR ile başlayan 26 haneli yapı)
    iban_match = re.search(r'TR\s?\d{2}(?:\s?\d{4}){5}', metin, re.IGNORECASE)
    iban = iban_match.group(0).upper().replace(" ", "") if iban_match else "IBAN Bulunamadı"

    # 2. Tutar Bulma (Örn: 150.000,00 TL / 1.500 TL / 4500.50 TL)
    tutar = 0.0
    tutar_match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:TL|TRY|₺)', metin, re.IGNORECASE)
    if tutar_match:
        t_str = tutar_match.group(1).replace(".", "").replace(",", ".")
        try:
            tutar = float(t_str)
        except:
            tutar = 0.0

    # 3. Saat Bulma (Örn: 21:57 veya 09:15)
    saat_match = re.search(r'\b([01]?\d|2[0-3]):[0-5]\d\b', metin)
    saat = saat_match.group(0) if saat_match else datetime.now().strftime("%H:%M")

    # 4. Banka Algılama
    m_lower = metin.lower()
    banka = "Diğer / Belirtilmedi"
    if "akbank" in m_lower: banka = "Akbank"
    elif "garanti" in m_lower: banka = "Garanti BBVA"
    elif "iş bank" in m_lower or "isbank" in m_lower: banka = "İş Bankası"
    elif "ziraat" in m_lower: banka = "Ziraat Bankası"
    elif "yapı kredi" in m_lower or "yapikredi" in m_lower: banka = "Yapı Kredi"
    elif "qnb" in m_lower or "finansbank" in m_lower: banka = "QNB Finansbank"

    # 5. Gönderen / Alıcı Satır Taraması
    satirlar = [s.strip() for s in metin.split('\n') if len(s.strip()) > 2]
    gonderen = "Algılanamadı"
    alici = "Sıla Sarı" # Varsayılan alıcı hedefi

    for s in satirlar:
        if "gönderen" in s.lower() or "gonderen" in s.lower() or "hesap sahibi" in s.lower():
            gonderen = s
            break
    if gonderen == "Algılanamadı" and len(satirlar) > 0:
        gonderen = satirlar[0]

    return {
        "tarih": datetime.now().strftime("%Y-%m-%d"),
        "saat": saat,
        "gonderen": gonderen,
        "alici": alici,
        "banka": banka,
        "iban": iban,
        "tutar": tutar
    }

# --- ARAYÜZ ---
st.title("🧾 Gerçek Otomatik Dekont Okuyucu")
st.write("Dekont ekran görüntüsünü yükleyin. Sistem içerikteki **gerçek** metni okuyup veritabanına işleyecektir.")

yuklenen_dosya = st.file_uploader(
    "📸 Dekont Görseli Yükleyin (PNG, JPG, JPEG)", 
    type=["png", "jpg", "jpeg"]
)

if yuklenen_dosya is not None:
    if "son_islenen" not in st.session_state or st.session_state.son_islenen != yuklenen_dosya.name:
        with st.spinner("🔍 Görsel üzerindeki yazılar Tesseract OCR ile taranıyor..."):
            try:
                img = Image.open(yuklenen_dosya)
                # Gerçek OCR Okuma
                okunan_metin = pytesseract.image_to_string(img, lang="tur")
                
                if not okunan_metin.strip():
                    st.error("❌ Görselden hiçbir metin okunamadı. Lütfen resmin net ve okunabilir olduğundan emin olun.")
                else:
                    veri = metinden_veri_ayikla(okunan_metin)
                    
                    # Veritabanına Gerçek Veriyi Ekle
                    cursor.execute(
                        "INSERT INTO dekontlar (tarih, saat, gonderen, alici, banka, iban, tutar, raw_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (veri["tarih"], veri["saat"], veri["gonderen"], veri["alici"], veri["banka"], veri["iban"], veri["tutar"], okunan_metin)
                    )
                    conn.commit()
                    st.session_state.son_islenen = yuklenen_dosya.name
                    st.success(f"✅ Dekont Taranıp Kaydedildi! Tutar: {veri['tutar']:,.2f} TL | IBAN: {veri['iban']}")
                    st.rerun()

            except Exception as e:
                st.error(f"⚠️ Görsel okunurken bir sistem hatası oluştu: {str(e)}")
                st.info("Lütfen GitHub deponuza 'packages.txt' dosyasını eklediğinizden ve Streamlit'in yeniden başlatıldığından emin olun.")

st.divider()

# --- VERİ LİSTELEME VE TOPLAMLAR ---
df = pd.read_sql_query("SELECT * FROM dekontlar ORDER BY id DESC", conn)

if not df.empty:
    col1, col2, col3 = st.columns(3)
    col1.metric("Toplam Biriken Tutar", f"{df['tutar'].sum():,.2f} TL")
    col2.metric("Okunan Dekont Sayısı", f"{len(df)} Adet")
    col3.metric("Farklı IBAN Sayısı", f"{df['iban'].nunique()} Hesap")

    st.subheader("📊 IBAN Bazlı Biriken Toplamlar")
    iban_summary = df.groupby(['alici', 'banka', 'iban'])['tutar'].agg(['sum', 'count']).reset_index()
    iban_summary.columns = ['Alıcı', 'Banka', 'IBAN No', 'Biriken Toplam (TL)', 'İşlem Adedi']
    st.dataframe(iban_summary, use_container_width=True)

    st.subheader("📋 Okunan Dekont Geçmişi")
    st.dataframe(
        df[['tarih', 'saat', 'gonderen', 'alici', 'banka', 'iban', 'tutar']], 
        column_config={
            "tutar": st.column_config.NumberColumn("Tutar (TL)", format="%.2f TL")
        },
        use_container_width=True
    )
    
    # Görselden Okunan Ham Metni İnceleme Alanı (Hata Kontrolü İçin)
    with st.expander("🔍 Son Okunan Dekontların Ham Metin İçeriklerini Gör"):
        st.dataframe(df[['id', 'gonderen', 'raw_text']], use_container_width=True)
else:
    st.info("Henüz dekont yüklenmedi. Yukarıdaki alandan gerçek bir dekont görseli yükleyebilirsiniz.")
