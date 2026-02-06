import streamlit as st
import time
import pandas as pd
from datetime import datetime
from pymodbus.client import ModbusTcpClient
import veritabani
import utils 

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Solar Monitor",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

# DB Başlat
veritabani.init_db()

# --- CSS TASARIMI ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #E0E0E0; }
    div[data-testid="stMetric"] {
        background-color: #1E1E1E; border: 1px solid #333;
        padding: 10px; border-radius: 8px;
    }
    .chart-title {
        font-size: 1rem; font-weight: 700; margin-bottom: 0px;
        padding: 5px 10px; border-radius: 5px 5px 0 0; display: inline-block; width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
# parse_id_list artık utils.py'de

@st.cache_resource
def get_modbus_client(ip, port):
    return ModbusTcpClient(ip, port=port, timeout=2) 

def read_device_with_retry(client, slave_id, config, max_retries=3):
    """
    Modbus cihazından veri okur, başarısız olursa retry yapar.
    
    Args:
        client: Modbus client
        slave_id: Cihaz ID'si
        config: Adres konfigürasyonu
        max_retries: Maksimum deneme sayısı
        
    Returns:
        tuple: (data dict veya None, error message veya None)
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Bağlantı kontrolü
            if not client.connected:
                client.connect()
                if not client.connected:
                    last_error = "Bağlantı kurulamadı"
                    if attempt < max_retries - 1:
                        time.sleep(0.5)
                        continue
                    return None, last_error
            
            # 1. Standart Veriler
            r_guc = client.read_holding_registers(address=config['guc_addr'], count=1, slave=slave_id)
            if r_guc.isError():
                last_error = f"Güç okunamadı (ID:{slave_id})"
                if attempt < max_retries - 1:
                    time.sleep(0.3)
                    continue
                return None, last_error
            val_guc = r_guc.registers[0] * config['guc_scale']

            r_volt = client.read_holding_registers(address=config['volt_addr'], count=1, slave=slave_id)
            val_volt = 0 if r_volt.isError() else r_volt.registers[0] * config['volt_scale']

            r_akim = client.read_holding_registers(address=config['akim_addr'], count=1, slave=slave_id)
            val_akim = 0 if r_akim.isError() else r_akim.registers[0] * config['akim_scale']

            r_isi = client.read_holding_registers(address=config['isi_addr'], count=1, slave=slave_id)
            val_isi = 0 if r_isi.isError() else r_isi.registers[0] * config['isi_scale']

            # 2. Hata Kodları
            hata_kodu_189 = 0
            try:
                r_hata = client.read_holding_registers(address=189, count=2, slave=slave_id)
                if not r_hata.isError():
                    hata_kodu_189 = (r_hata.registers[0] << 16) | r_hata.registers[1]
            except:
                pass  # Hata kodları opsiyonel

            hata_kodu_193 = 0
            try:
                time.sleep(0.02) 
                r_hata2 = client.read_holding_registers(address=193, count=2, slave=slave_id)
                if not r_hata2.isError():
                    hata_kodu_193 = (r_hata2.registers[0] << 16) | r_hata2.registers[1]
            except:
                pass  # Hata kodları opsiyonel

            # Başarılı okuma
            return {
                "slave_id": slave_id,
                "guc": val_guc,
                "voltaj": val_volt,
                "akim": val_akim,
                "sicaklik": val_isi,
                "hata_kodu": hata_kodu_189,    
                "hata_kodu_193": hata_kodu_193, 
                "timestamp": datetime.now()
            }, None

        except ConnectionError as e:
            last_error = f"Bağlantı hatası: {str(e)}"
            if attempt < max_retries - 1:
                time.sleep(0.5)
                # Yeniden bağlanmayı dene
                try:
                    client.close()
                    client.connect()
                except:
                    pass
        except Exception as e:
            last_error = f"Okuma hatası: {str(e)}"
            if attempt < max_retries - 1:
                time.sleep(0.3)
    
    return None, last_error

# Geriye dönük uyumluluk için
def read_device(client, slave_id, config):
    return read_device_with_retry(client, slave_id, config, max_retries=3)

# --- STATE ---
if 'monitoring' not in st.session_state: 
    st.session_state.monitoring = False
if 'ayarlar_kaydedildi' not in st.session_state:
    st.session_state.ayarlar_kaydedildi = False

# --- YAN MENÜ ---
with st.sidebar:
    st.header("🏭 PULSAR Ayarları")
    
    # Veritabanından mevcut ayarları yükle
    mevcut_ayarlar = veritabani.tum_ayarlari_oku()
    
    target_ip = st.text_input("IP Adresi", value=mevcut_ayarlar.get('target_ip', '10.35.14.10'))
    target_port = st.number_input("Port", value=int(mevcut_ayarlar.get('target_port', 502)), step=1)
    
    st.info("Virgül veya tire ile ayırın (Örn: 1, 2, 5-8)")
    id_input = st.text_input("İnverter ID Listesi", value=mevcut_ayarlar.get('slave_ids', '1,2,3'))
    target_ids, id_errors = utils.parse_id_list(id_input)
    
    if id_errors:
        st.warning(f"⚠️ Bazı ID'ler parse edilemedi: {', '.join(id_errors)}")
    
    st.write(f"📡 İzlenecek ID'ler: {utils.format_id_list_display(target_ids)}")
    
    st.divider()
    
    st.header("⏳ Zamanlayıcı")
    
    # Slider için seçenekler (dakika cinsinden gösterim)
    interval_options = {
        "1 dakika": 60,
        "10 dakika": 600,
        "30 dakika": 1800,
        "1 saat": 3600
    }
    
    # Mevcut değeri bul
    current_refresh = float(mevcut_ayarlar.get('refresh_rate', 60))
    # En yakın seçeneği bul
    current_label = "1 dakika"
    for label, value in interval_options.items():
        if value == current_refresh:
            current_label = label
            break
    
    # Slider ile seçim
    selected_interval = st.select_slider(
        "Veri Toplama Sıklığı",
        options=list(interval_options.keys()),
        value=current_label
    )
    
    refresh_rate = interval_options[selected_interval]
    st.info(f"⏱️ Seçilen: {selected_interval} ({refresh_rate} saniye)")
    
    st.markdown("---")
    st.header("🗺️ Adres Haritası")
    with st.expander("Detaylı Adres Ayarları"):
        c_guc_adr = st.number_input("Güç Adresi", value=int(mevcut_ayarlar.get('guc_addr', 70)))
        c_guc_sc = st.number_input("Güç Çarpan", value=float(mevcut_ayarlar.get('guc_scale', 1.0)), step=0.1, format="%.2f")
        
        c_volt_adr = st.number_input("Voltaj Adresi", value=int(mevcut_ayarlar.get('volt_addr', 71)))
        c_volt_sc = st.number_input("Voltaj Çarpan", value=float(mevcut_ayarlar.get('volt_scale', 0.1)), step=0.1, format="%.2f")
        
        c_akim_adr = st.number_input("Akım Adresi", value=int(mevcut_ayarlar.get('akim_addr', 72)))
        c_akim_sc = st.number_input("Akım Çarpan", value=float(mevcut_ayarlar.get('akim_scale', 0.1)), step=0.1, format="%.2f")
        
        c_isi_adr = st.number_input("Isı Adresi", value=int(mevcut_ayarlar.get('isi_addr', 73)))
        c_isi_sc = st.number_input("Isı Çarpan", value=float(mevcut_ayarlar.get('isi_scale', 1.0)), step=0.1, format="%.2f")
    
    config = {
        'guc_addr': c_guc_adr, 'guc_scale': c_guc_sc,
        'volt_addr': c_volt_adr, 'volt_scale': c_volt_sc,
        'akim_addr': c_akim_adr, 'akim_scale': c_akim_sc,
        'isi_addr': c_isi_adr, 'isi_scale': c_isi_sc,
    }

    # AYARLARI KAYDET BUTONU
    st.markdown("---")
    if st.button("💾 AYARLARI KALICI OLARAK KAYDET", type="primary"):
        # Tüm ayarları veritabanına yaz
        veritabani.ayar_yaz('target_ip', target_ip)
        veritabani.ayar_yaz('target_port', target_port)
        veritabani.ayar_yaz('slave_ids', id_input)
        veritabani.ayar_yaz('refresh_rate', refresh_rate)
        veritabani.ayar_yaz('guc_addr', c_guc_adr)
        veritabani.ayar_yaz('guc_scale', c_guc_sc)
        veritabani.ayar_yaz('volt_addr', c_volt_adr)
        veritabani.ayar_yaz('volt_scale', c_volt_sc)
        veritabani.ayar_yaz('akim_addr', c_akim_adr)
        veritabani.ayar_yaz('akim_scale', c_akim_sc)
        veritabani.ayar_yaz('isi_addr', c_isi_adr)
        veritabani.ayar_yaz('isi_scale', c_isi_sc)
        
        st.success("✅ Ayarlar kaydedildi! Collector 30 saniye içinde güncellenecek.")
        st.rerun()

    # Yenileme süresi ayarı
    st.markdown("---")
    st.header("⏱️ Yenileme Ayarları")
    
    # Session state'te varsayılan değer
    if 'refresh_interval' not in st.session_state:
        st.session_state.refresh_interval = 30
    
    # Slider
    refresh_interval = st.select_slider(
        "Otomatik Yenileme Süresi",
        options=[5, 10, 15, 30, 60, 120],
        value=st.session_state.refresh_interval,
        format_func=lambda x: f"{x} saniye"
    )
    
    # Session state'i güncelle
    st.session_state.refresh_interval = refresh_interval
    
    st.caption(f"Panel {refresh_interval} saniyede bir yenilenecek")
    
    st.markdown("---")
    st.header("🎛️ Sistem Kontrolü")
    
    if st.button("▶️ SİSTEMİ BAŞLAT"):
        st.session_state.monitoring = True
        st.rerun()
    if st.button("⏹️ DURDUR"):
        st.session_state.monitoring = False
        st.rerun()

    st.markdown("---")
    st.header("🗑️ Veri Yönetimi")
    if st.button("Tüm Verileri Sil"):
        if veritabani.db_temizle():
            st.success("Temizlendi!")
            time.sleep(1)
            st.rerun()

# --- ANA EKRAN ---
st.title("⚡ Güneş Enerjisi Santrali İzleme")

# Hızlı Özet
st.subheader("📋 Canlı Filo Durumu")
table_spot = st.empty()

# Grafik Seçimi
st.markdown("---")
col_sel, col_info = st.columns([1, 3])
with col_sel:
    selected_id = st.selectbox("📊 Detaylı Grafik İçin Cihaz Seç:", target_ids)
with col_info:
    st.info("⚠️ Detaylı arıza kodlarını görmek için sol menüden **alarmlar** sayfasına gidin.")

# Grafik Yer Tutucuları
row1_c1, row1_c2 = st.columns(2)
row2_c1, row2_c2 = st.columns(2)

with row1_c1:
    st.markdown(f"**☀️ ID:{int(selected_id)} - Güç**")
    chart_guc = st.empty()
with row1_c2:
    st.markdown(f"**⚡ ID:{int(selected_id)} - Voltaj**")
    chart_volt = st.empty()
with row2_c1:
    st.markdown(f"**📈 ID:{int(selected_id)} - Akım**")
    chart_akim = st.empty()
with row2_c2:
    st.markdown(f"**🌡️ ID:{int(selected_id)} - Sıcaklık**")
    chart_isi = st.empty()

# --- DURUM ÇUBUĞU ---
status_bar = st.empty()

def ui_refresh():
    # 1. TABLO GÜNCELLEME
    summary_data = veritabani.tum_cihazlarin_son_durumu()
    if summary_data:
        df_sum = pd.DataFrame([row[:6] for row in summary_data], columns=["ID", "Son Zaman", "Güç (W)", "Voltaj (V)", "Akım (A)", "Isı (C)"])
        df_sum["Son Zaman"] = pd.to_datetime(df_sum["Son Zaman"]).dt.strftime('%H:%M:%S')
        table_spot.dataframe(df_sum.set_index("ID"), use_container_width=True)

    # 2. GRAFİK GÜNCELLEME
    detail_data = veritabani.son_verileri_getir(selected_id, limit=100)
    if detail_data:
        try:
            df_det = pd.DataFrame(detail_data, columns=["timestamp", "guc", "voltaj", "akim", "sicaklik", "hata_kodu", "hata_kodu_193"])
        except:
            df_det = pd.DataFrame(detail_data, columns=["timestamp", "guc", "voltaj", "akim", "sicaklik", "hata_kodu"])
            
        df_det["timestamp"] = pd.to_datetime(df_det["timestamp"])
        df_det = df_det.set_index("timestamp")
        
        chart_guc.line_chart(df_det["guc"], color="#FFD700")
        chart_volt.line_chart(df_det["voltaj"], color="#29B6F6")
        chart_akim.line_chart(df_det["akim"], color="#66BB6A")
        chart_isi.line_chart(df_det["sicaklik"], color="#EF5350")

# --- ANA DÖNGÜ ---
if st.session_state.monitoring:
    client = get_modbus_client(target_ip, target_port)
    status_bar.success(f"✅ Sistem Aktif - Otomatik yenileme: {st.session_state.refresh_interval} saniye")
    
    # Veri toplama
    for dev_id in target_ids:
        data, err = read_device(client, dev_id, config)
        if data:
            veritabani.veri_ekle(dev_id, data)
        elif err:
            status_bar.warning(f"⚠️ ID {dev_id} okunamadı: {err}")
    
    # UI güncelleme
    ui_refresh()
    
    # Otomatik yenileme (kullanıcının seçtiği süre)
    time.sleep(st.session_state.refresh_interval)
    st.rerun()
else:
    ui_refresh()
    status_bar.info("Sistem Beklemede. Grafikleri görmek için BAŞLAT'a basın.")