import streamlit as st
import pandas as pd
import requests
import base64
from PIL import Image
import json
import io
from datetime import datetime

st.set_page_config(page_title="AI Dekont Portalı", page_icon="⚡", layout="wide")

st.title("⚡ Garanti Çalışan AI Dekont Okuma Portalı")
st.caption("Doğrudan Google REST API bağlantısı ile sıfır kütüphane hatası.")

# Sol Menü API Key
with st.sidebar:
    st.header("🔑 Yapay Zeka Bağlantısı")
    api_key = st.text_input("Google Gemini API Key:", type="password", help="aistudio.google.com adresinden ücretsiz alabilirsiniz.")
    st.info("💡 API anahtarınız doğrudan Google resmi API'sine gönderilir.")

if not api_key:
    st.warning("⚠️ Lütfen sol menüden Google Gemini API anahtarınızı girin.")
    st.stop()

if "dekont_listesi" not in st.session_state:
    st.session_state.dekont_listesi = []

yuklenen_dosyalar = st.file_uploader("📸 Dekont Görselinizi Yükleyin", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

def gemini_api_ile_oku(image_bytes, mime_type, key):
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    # Google Gemini REST API Endpoint
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
    
    prompt_text = """
    Bu bir Türk bankası dekontudur. Görseldeki metinleri dikkatlice oku ve aşağıdaki JSON formatında ver:
    SADECE JSON YAZ, BAŞKA HİÇBİR AÇIKLAMA YAZMA.

    {
        "dekont_tipi": "FAST, EFT veya Havale",
        "banka": "Banka Adı",
        "yon": "Gelen veya Giden",
        "islem_tarihi": "DD.MM.YYYY",
        "islem_saati": "HH:MM:SS",
        "tutar": 0.00,
        "para_birimi": "TL",
        "gonderen": "Gönderen Adı",
        "gonderen_iban": "TR...",
        "alici": "Alıcı Adı",
        "alici_iban": "TR...",
        "aciklama": "Açıklama",
        "referans_no": "Referans No"
    }
    """
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64_image
                    }
                }
            ]
        }]
    }
    
    headers = {'Content-Type': 'application/json'}
    res = requests.post(url, headers=headers, json=payload, timeout=30)
    
    if res.status_code != 200:
        raise Exception(f"API Hatası (Kod {res.status_code}): {res.text}")
        
    res_data = res.json()
    raw_text = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
    
    if "```json" in raw_text:
        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        raw_text = raw_text.split("```")[1].strip()
        
    return json.loads(raw_text)

if yuklenen_dosyalar and st.button("🚀 Dekontları Taramayı Başlat"):
    for dosya in yuklenen_dosyalar:
        if not any(d.get("_dosya_adi") == dosya.name for d in st.session_state.dekont_listesi):
            with st.spinner(f"🔍 {dosya.name} taranıyor..."):
                try:
                    bytes_data = dosya.getvalue()
                    mime_type = f"image/{dosya.type.split('/')[-1]}"
                    if "jpeg" in mime_type or "jpg" in mime_type:
                        mime_type = "image/jpeg"
                    elif "png" in mime_type:
                        mime_type = "image/png"
                        
                    result = gemini_api_ile_oku(bytes_data, mime_type, api_key)
                    result["_dosya_adi"] = dosya.name
                    st.session_state.dekont_listesi.append(result)
                    st.success(f"✅ {dosya.name} başarıyla okundu!")
                except Exception as e:
                    st.error(f"❌ HATA ({dosya.name}): {str(e)}")

# SONUÇLARI GOSTER
if st.session_state.dekont_listesi:
    df = pd.DataFrame(st.session_state.dekont_listesi)
    
    kolonlar = {
        "dekont_tipi": "Dekont Tipi", "banka": "Banka", "yon": "Yön",
        "islem_tarihi": "İşlem Tarihi", "islem_saati": "İşlem Saati",
        "tutar": "Tutar", "para_birimi": "Para Birimi", "gonderen": "Gönderen",
        "gonderen_iban": "Gönderen IBAN", "alici": "Alıcı",
        "alici_iban": "Alıcı IBAN", "aciklama": "Açıklama", "referans_no": "Dekont / Referans No"
    }
    
    df_disp = df.rename(columns=kolonlar)
    mevcut = [v for k, v in kolonlar.items() if v in df_disp.columns]
    
    st.subheader("📋 Okunan Dekontlar")
    st.dataframe(df_disp[mevcut], use_container_width=True)
    
    # Excel çıktı
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_disp[mevcut].to_excel(writer, sheet_name='Dekontlar', index=False)
    
    st.download_button(
        "📥 Excel Olarak İndir",
        data=output.getvalue(),
        file_name=f"Dekont_Raporu_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openpyxlformat-officedocument.spreadsheetml.sheet"
    )
