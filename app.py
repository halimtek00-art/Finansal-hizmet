import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import json
import io
from datetime import datetime

st.set_page_config(page_title="Görsel Yapay Zeka Dekont Portalı", page_icon="⚡", layout="wide")

st.title("⚡ AI Dekont Okuma & Otomatik Excel Portalı")
st.caption("Excel Şablonunuzla %100 Uyumlu Görsel Yapay Zeka Destekli Otomatik Ayrıştırma")

# 1. API KEY ALANI
api_key = st.sidebar.text_input("Google Gemini API Key", type="password", help="aistudio.google.com adresinden ücretsiz alabilirsiniz.")

if not api_key:
    st.warning("⚠️ Lütfen sol menüden Google Gemini API anahtarınızı girin.")
    st.stop()

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-flash')

# Oturum Hafızası
if "dekont_listesi" not in st.session_state:
    st.session_state.dekont_listesi = []

yuklenen_dosyalar = st.file_uploader("📸 Dekont Görsellerinizi / Fotoğraflarınızı Yükleyin", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

if yuklenen_dosyalar and st.button("🚀 Dekontları Analiz Et ve İşle"):
    for dosya in yuklenen_dosyalar:
        with st.spinner(f"🤖 {dosya.name} yapay zeka ile analiz ediliyor..."):
            try:
                img = Image.open(dosya)
                
                prompt = """
                Bu bir banka dekontu görselidir. Görseldeki bilgileri okuyup SADECE aşağıdaki JSON formatında çıktı ver.
                Ekstra hiçbir açıklama yazma, sadece JSON döndür.

                JSON Formatı:
                {
                    "dekont_tipi": "FAST veya EFT veya Havale",
                    "banka": "Banka Adı",
                    "yon": "Gelen veya Giden",
                    "islem_tarihi": "DD.MM.YYYY",
                    "islem_saati": "HH:MM:SS",
                    "tutar": 0.00,
                    "para_birimi": "TL",
                    "gonderen": "Gönderen Adı Soyadı/Unvanı",
                    "gonderen_iban": "TR...",
                    "alici": "Alıcı Adı Soyadı/Unvanı",
                    "alici_iban": "TR...",
                    "aciklama": "İşlem Açıklaması",
                    "referans_no": "Referans/Dekont No"
                }
                """
                
                response = model.generate_content([prompt, img])
                text_res = response.text.strip()
                if "```json" in text_res:
                    text_res = text_res.split("```json")[1].split("```")[0].strip()
                elif "```" in text_res:
                    text_res = text_res.split("```")[1].strip()
                
                veri = json.loads(text_res)
                st.session_state.dekont_listesi.append(veri)
            except Exception as e:
                st.error(f"{dosya.name} işlenirken hata oluştu: {e}")

    st.success("✅ Tüm dekontlar başarıyla okundu!")

# VERİLERİ GÖSTERME VE ŞABLONA UYGUN EXCEL ÜRETME
if st.session_state.dekont_listesi:
    df_raw = pd.DataFrame(st.session_state.dekont_listesi)
    
    st.subheader("📋 İşlenen Dekont Listesi")
    st.dataframe(df_raw, use_container_width=True)
    
    # Excel Oluşturma (Şablon Kurallarına Göre)
    def sablon_excel_olustur(raw_data):
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='openpyxl')
        
        df = pd.DataFrame(raw_data)
        
        # Kolon isimlerini dosyanızdaki şablonla birebir eşle
        kolon_haritasi = {
            "dekont_tipi": "Dekont Tipi",
            "banka": "Banka",
            "yon": "Yön",
            "islem_tarihi": "İşlem Tarihi",
            "islem_saati": "İşlem Saati",
            "tutar": "Tutar",
            "para_birimi": "Para Birimi",
            "gonderen": "Gönderen",
            "gonderen_iban": "Gönderen IBAN",
            "alici": "Alıcı",
            "alici_iban": "Alıcı IBAN",
            "aciklama": "Açıklama",
            "referans_no": "Dekont / Referans No"
        }
        
        df = df.rename(columns=kolon_haritasi)
        
        # ALICI IBAN GRUPLAMA KURALI:
        # Aynı Alıcı IBAN'a ait dekontları grupla, aralara 5 boş satır koy
        grouped_rows = []
        if "Alıcı IBAN" in df.columns:
            gruplar = df.groupby("Alıcı IBAN", sort=False)
            for iban, group in gruplar:
                for _, row in group.iterrows():
                    grouped_rows.append(row.to_dict())
                # Gruplama kuralınız: her grup sonrasına 5 boş satır
                for _ in range(5):
                    grouped_rows.append({col: "" for col in df.columns})
        else:
            grouped_rows = df.to_dict('records')
            
        df_final = pd.DataFrame(grouped_rows)
        
        # 'Dekontlar' Sayfası
        df_final.to_excel(writer, sheet_name='Dekontlar', index=False)
        
        writer.close()
        return output.getvalue()

    excel_data = sablon_excel_olustur(st.session_state.dekont_listesi)
    
    st.download_button(
        label="📥 Şablona Uygun Excel Dosyasını İndir",
        data=excel_data,
        file_name=f"Dekont_Takip_Raporu_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openpyxlformat-officedocument.spreadsheetml.sheet"
    )
