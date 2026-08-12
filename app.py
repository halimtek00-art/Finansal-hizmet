import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# Sayfa Ayarları (Mobil ve Masaüstü Uyumlu)
st.set_page_config(
    page_title="Dekont & Muhasebe Portalı",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# VERİTABANI BAĞLANTISI (SQLite)
# ---------------------------------------------------------
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
        tutar REAL
    )
''')
conn.commit()

# ---------------------------------------------------------
# ARAYÜZ VE FORM
# ---------------------------------------------------------
st.title("💳 Dekont & Transfer Takip Portalı")

# Sol Panel - Yeni Dekont Ekleme
with st.sidebar:
    st.header("➕ Yeni Dekont Kaydı")
    
    with st.form("dekont_formu", clear_on_submit=True):
        gonderen = st.text_input("Gönderen Adı Soyadı")
        alici = st.text_input("Alıcı Adı Soyadı", value="Sıla Sarı")
        banka = st.selectbox("Banka", ["Akbank", "Garanti BBVA", "İş Bankası", "Ziraat Bankası", "Yapı Kredi", "QNB Finansbank", "Diğer"])
        iban = st.text_input("Banka / IBAN No", placeholder="TR97 0006 ...")
        tarih = st.date_input("İşlem Tarihi", datetime.now())
        saat = st.time_input("İşlem Saati")
        tutar = st.number_input("Tutar (TL)", min_value=0.0, step=1000.0, format="%.2f")
        
        kaydet = st.form_submit_button("💾 Dekontu Kaydet")
        
        if kaydet:
            if gonderen and iban and tutar > 0:
                cursor.execute(
                    "INSERT INTO dekontlar (tarih, saat, gonderen, alici, banka, iban, tutar) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(tarih), str(saat), gonderen, alici, banka, iban, tutar)
                )
                conn.commit()
                st.success("✅ Dekont başarıyla veritabanına eklendi!")
                st.rerun()
            else:
                st.error("⚠️ Lütfen gönderen, IBAN ve tutar alanlarını doldurun.")

# ---------------------------------------------------------
# VERİ OKUMA VE ÖZET METRİKLER
# ---------------------------------------------------------
df = pd.read_sql_query("SELECT * FROM dekontlar ORDER BY id DESC", conn)

if not df.empty:
    # Üst İstatistik Kartları
    col1, col2, col3 = st.columns(3)
    col1.metric("Toplam İşlem Hacmi", f"{df['tutar'].sum():,.2f} TL")
    col2.metric("Toplam Dekont Sayısı", f"{len(df)} Adet")
    col3.metric("Farklı IBAN Sayısı", f"{df['iban'].nunique()} Hesap")

    st.divider()

    # IBAN Bazlı Toplam Bakiye Tablosu
    st.subheader("📊 IBAN Bazlı Toplam Bakiye Özeti")
    iban_summary = df.groupby(['alici', 'banka', 'iban'])['tutar'].agg(['sum', 'count']).reset_index()
    iban_summary.columns = ['Alıcı', 'Banka', 'IBAN', 'Toplam Gelen (TL)', 'İşlem Adedi']
    st.dataframe(iban_summary, use_container_width=True)

    st.divider()

    # Tüm Dekont Hareketleri
    st.subheader("📋 Tüm Dekont Kayıtları")
    st.dataframe(
        df[['tarih', 'saat', 'gonderen', 'alici', 'banka', 'iban', 'tutar']],
        column_config={
            "tutar": st.column_config.NumberColumn("Tutar (TL)", format="%.2f TL"),
            "gonderen": "Gönderen",
            "alici": "Alıcı",
            "banka": "Banka",
            "iban": "IBAN",
            "tarih": "Tarih",
            "saat": "Saat"
        },
        use_container_width=True
    )

    # Excel İndirme Butonu
    csv_data = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Tüm Verileri Excel / CSV Olarak İndir",
        data=csv_data,
        file_name=f"dekont_raporu_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
else:
    st.info("👋 Henüz hiç dekont eklenmedi. Sol taraftaki menüyü kullanarak ilk dekontunuzu ekleyin.")
