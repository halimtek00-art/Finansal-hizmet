import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import json
import io
from datetime import datetime

st.set_page_config(page_title="AI Dekont Okuma Portalı", page_icon="⚡", layout="wide")

st.title("⚡ Akıllı Dekont Okuma & Otomatik Takip Portalı")
st.caption("Dekont fotoğrafını yükleyin, yapay zeka tüm detayları sıfır hatayla okusun.")

# API Key Giriş Alanı (Sol Menü)
with st.sidebar:
    st.header("🔑 Yapay Zeka Bağlantısı")
    api_key = st.text_input("Google Gemini API Anahtarınız:", type="password", help="aistudio.google.com adresinden ücretsiz alabilirsiniz.")
    st.info("💡 API anahtarı bir defa girildikten sonra oturum boyunca tüm görselleri ücretsiz okur.")

if not api_key:
    st.warning("⚠️ Lütfen sol menüden Google Gemini API anahtarınızı girin.")
    st.stop()

# Gemini AI Yapılandırması
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-flash')

# Oturum Hafızası
if "dekont_listesi" not in st.session_state:
    st.session_state.dekont_listesi = []

# GÖRSEL YÜKLEME ALANI
yuklenen_dosyalar = st.file_uploader("📸 Dekont Görselini / Fotoğrafını Buraya Sürükleyin", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

if yuklenen_dosyalar:
    for dosya in yuklenen_dosyalar:
        # Dosya daha önce işlenmediyse işle
        if not any(d.get("_dosya_adi") == dosya.name for d in st.session_state.dekont_listesi):
            with st.spinner(f"🔍 {dosya.name} yapay zeka ile taranıyor..."):
                try:
                    img = Image.open(dosya)
                    
                    prompt = """
                    Bu bir Türk bankası dekontu görselidir. Görseldeki metinleri dikkatlice incele ve aşağıdaki verileri eksiksiz ayrıştır.
                    SADECE aşağıdaki JSON formatında çıktı ver, başka hiçbir açıklama yazma:

                    {
                        "dekont_tipi": "FAST, EFT veya Havale",
                        "banka": "Banka Adı (örn: Garanti BBVA, Ziraat, İş Bankası, QNB, Akbank vb.)",
                        "yon": "Gelen veya Giden",
                        "islem_tarihi": "DD.MM.YYYY",
                        "islem_saati": "HH:MM:SS",
                        "tutar": 0.00,
                        "para_birimi": "TL",
                        "gonderen": "Gönderen Ad Soyad / Unvan",
                        "gonderen_iban": "TR...",
                        "alici": "Alıcı Ad Soyad / Unvan",
                        "alici_iban": "TR...",
                        "aciklama": "İşlem Açıklaması",
                        "referans_no": "Referans No / Dekont No"
                    }
                    """
                    
                    response = model.generate_content([prompt, img])
                    text_res = response.text.strip()
                    
                    if "```json" in text_res:
                        text_res = text_res.split("```json")[1].split("```")[0].strip()
                    elif "```" in text_res:
                        text_res = text_res.split("```")[1].strip()
                    
                    veri = json.loads(text_res)
                    veri["_dosya_adi"] = dosya.name
                    st.session_state.dekont_listesi.append(veri)
                    st.toast(f"✅ {dosya.name} başarıyla okundu!", icon="🎉")
                except Exception as e:
                    st.error(f"❌ {dosya.name} okunamadı: {e}")

# OKUNAN VERİLERİ ŞABLONA GÖRE GÖSTERME VE İNDİRME
if st.session_state.dekont_listesi:
    df = pd.DataFrame(st.session_state.dekont_listesi)
    
    # Ekran gösterim kolonları
    gosterim_kolonlari = {
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
    
    df_gosterim = df.copy().rename(columns=gosterim_kolonlari)
    mevcut_kolonlar = [v for k, v in gosterim_kolonlari.items() if v in df_gosterim.columns]
    
    st.subheader("📋 Okunan Dekont Tablosu")
    st.dataframe(df_gosterim[mevcut_kolonlar], use_container_width=True)
    
    # Dosyanızdaki Gruplama Kuralına Uygun Excel Üretme
    def excel_olustur():
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='openpyxl')
        
        # Alıcı IBAN'a göre grupla ve aralara 5 boş satır koy
        grouped_rows = []
        if "alici_iban" in df.columns:
            for iban, group in df.groupby("alici_iban", sort=False):
                for _, row in group.iterrows():
                    row_dict = {gosterim_kolonlari[k]: row[k] for k in gosterim_kolonlari.keys() if k in row}
                    grouped_rows.append(row_dict)
                # 5 boş satır gruplama kuralınız
                for _ in range(5):
                    grouped_rows.append({v: "" for v in gosterim_kolonlari.values()})
        else:
            for _, row in df.iterrows():
                row_dict = {gosterim_kolonlari[k]: row[k] for k in gosterim_kolonlari.keys() if k in row}
                grouped_rows.append(row_dict)
                
        df_excel = pd.DataFrame(grouped_rows)
        df_excel.to_excel(writer, sheet_name='Dekontlar', index=False)
        writer.close()
        return output.getvalue()

    st.download_button(
        label="📥 Okunan Verileri Excel Olarak İndir",
        data=excel_olustur(),
        file_name=f"Dekont_Raporu_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openpyxlformat-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
