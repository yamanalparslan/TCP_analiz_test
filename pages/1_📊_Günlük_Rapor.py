import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import os

# Üst dizindeki veritabani.py modülüne erişim sağla
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import veritabani

st.set_page_config(page_title="Günlük Raporlar", page_icon="📊", layout="wide")

st.title("📊 Günlük Performans ve Üretim Raporu")
st.markdown("Seçilen tarihe göre tüm cihazların üretim ve verimlilik özetini içerir.")

# Veritabanından mevcut cihaz listesini ve ayarları al
ayarlar = veritabani.tum_ayarlari_oku()
slave_ids_raw = ayarlar.get('slave_ids', '1,2,3')
# ID listesini temizle ve listeye çevir
slave_ids = [int(x.strip()) for x in slave_ids_raw.split(',') if x.strip().isdigit()]

# Raporlama Arayüzü
col_date, col_empty = st.columns([1, 2])
with col_date:
    secilen_tarih = st.date_input("Rapor Tarihi Seçin:", datetime.now())

tarih_str = secilen_tarih.strftime('%Y-%m-%d')

# Rapor Verilerini Hazırla
rapor_listesi = []

for s_id in slave_ids:
    # Veritabanı fonksiyonlarını kullanarak verileri hesapla
    uretim = veritabani.gunluk_uretim_hesapla(tarih_str, slave_id=s_id)
    istatistik = veritabani.tarih_araliginda_ortalamalar(tarih_str, tarih_str, slave_id=s_id)
    hatalar = veritabani.hata_sayilarini_getir(tarih_str, tarih_str, slave_id=s_id)
    
    # Eğer o güne ait ölçüm varsa listeye ekle
    if istatistik and istatistik.get('toplam_olcum', 0) > 0:
        rapor_listesi.append({
            "Cihaz ID": s_id,
            "Üretim (kWh)": uretim['uretim_kwh'] if uretim else 0,
            "Ort. Güç (W)": round(istatistik['ort_guc'], 2),
            "Maks. Güç (W)": istatistik['max_guc'],
            "Ort. Voltaj (V)": round(istatistik['ort_voltaj'], 1),
            "Ort. Sıcaklık (°C)": round(istatistik['ort_sicaklik'], 1),
            "Hata (189/193)": f"{hatalar['hata_189_sayisi']} / {hatalar['hata_193_sayisi']}" if hatalar else "0/0",
            "Çalışma (Saat)": uretim['calisma_suresi_saat'] if uretim else 0
        })

# Tabloyu Göster
if rapor_listesi:
    df_rapor = pd.DataFrame(rapor_listesi)
    
    # Özet Kartları
    total_kwh = df_rapor["Üretim (kWh)"].sum()
    total_errors = sum([int(x.split('/')[0].strip()) + int(x.split('/')[1].strip()) for x in df_rapor["Hata (189/193)"]])
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam Üretim", f"{total_kwh:.2f} kWh")
    c2.metric("Aktif Cihaz Sayısı", len(df_rapor))
    c3.metric("Toplam Hata Kaydı", total_errors)
    
    st.divider()
    
    # Veri Tablosu
    st.dataframe(df_rapor.set_index("Cihaz ID"), use_container_width=True)
    
    # CSV İndirme Seçeneği
    csv = df_rapor.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Raporu CSV Olarak İndir",
        data=csv,
        file_name=f"gunluk_rapor_{tarih_str}.csv",
        mime="text/csv",
    )
else:
    st.warning(f"⚠️ {tarih_str} tarihinde herhangi bir veri kaydı bulunamadı.")