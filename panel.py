import streamlit as st
import time
import pandas as pd
from datetime import datetime
from pymodbus.client import ModbusTcpClient
import veritabani 

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
    .save-success {
        background-color: #1e4d2b;
        color: #4ade80;
        padding: 10px;
        border-radius: 5px;
        border-left: 4px solid #4ade80;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
def parse_id_list(id_string):
    ids = set()
    parts = id_string.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                for i in range(start, end + 1):
                    ids.add(i)
            except: pass
        else:
            try:
                ids.add(int(part))
            except: pass
    return sorted(list(ids))

@st.cache_resource
def get_modbus_client(ip, port):
    return ModbusTcpClient(ip, port=port, timeout=1) 

def read_device(client, slave_id, config):
    try:
        if not client.connected: client.connect()
        
        # 1. Standart Veriler
        r_guc = client.read_holding_registers(config['guc_addr'], 1, slave=slave_id)
        if r_guc.isError(): return None, "No Response"
        val_guc = r_guc.registers[0] * config['guc_scale']

        r_volt = client.read_holding_registers(config['volt_addr'], 1, slave=slave_id)
        val_volt = 0 if r_volt.isError() else r_volt.registers[0] * config['volt_scale']

        r_akim = client.read_holding_registers(config['akim_addr'], 1, slave=slave_id)
        val_akim = 0 if r_akim.isError() else r_akim.registers[0] * config['akim_scale']

        r_isi = client.read_holding_registers(config['isi_addr'], 1, slave=slave_id)
        val_isi = 0 if r_isi.isError() else r_isi.registers[0] * config['isi_scale']

        # 2. Hata Kodları
        hata_kodu_189 = 0
        try:
            r_hata = client.read_holding_registers(189, 2, slave=slave_id)
            if not r_hata.isError():
                hata_kodu_189 = (r_hata.registers[0] << 16) | r_hata.registers[1]
        except: pass

        hata_kodu_193 = 0
        try:
            time.sleep(0.02) 
            r_hata2 = client.read_holding_registers(193, 2, slave=slave_id)
            if not r_hata2.isError():
                hata_kodu_193 = (r_hata2.registers[0] << 16) | r_hata2.registers[1]
        except: pass

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

    except Exception as e:
        return None, str(e)

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
    target_ids = parse_id_list(id_input)
    st.write(f"📡 İzlenecek ID'ler: {target_ids}")
    
    st.divider()
    
    st.header("⏳ Zamanlayıcı")
    refresh_rate = st.number_input(
        "Veri Çekme Sıklığı (Saniye)", 
        value=float(mevcut_ayarlar.get('refresh_rate', 2)), 
        min_value=1.0, 
        step=0.5
    )
    
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
        
        st.session_state.ayarlar_kaydedildi = True
        st.rerun()
    
    # Kayıt başarılı mesajı
    if st.session_state.ayarlar_kaydedildi:
        st.markdown('<div class="save-success">✅ Ayarlar kaydedildi! Collector 30 saniye içinde güncellenecek.</div>', unsafe_allow_html=True)
        time.sleep(3)
        st.session_state.ayarlar_kaydedildi = False

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
    st.markdown(f'<div class="chart-title" style="background:#332a00; color:#FFD700;">☀️ ID:{selected_id} - Güç</div>', unsafe_allow_html=True)
    chart_guc = st.empty()
with row1_c2:
    st.markdown(f'<div class="chart-title" style="background:#001e33; color:#29B6F6;">⚡ ID:{selected_id} - Voltaj</div>', unsafe_allow_html=True)
    chart_volt = st.empty()
with row2_c1:
    st.markdown(f'<div class="chart-title" style="background:#0a260e; color:#66BB6A;">📈 ID:{selected_id} - Akım</div>', unsafe_allow_html=True)
    chart_akim = st.empty()
with row2_c2:
    st.markdown(f'<div class="chart-title" style="background:#2e0a0a; color:#EF5350;">🌡️ ID:{selected_id} - Sıcaklık</div>', unsafe_allow_html=True)
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
    status_bar.success(f"✅ Sistem Aktif")
    
    while st.session_state.monitoring:
        for dev_id in target_ids:
            data, err = read_device(client, dev_id, config)
            if data:
                veritabani.veri_ekle(dev_id, data)
        
        ui_refresh()
        time.sleep(2) 
        st.rerun()
else:
    ui_refresh()
    status_bar.info("Sistem Beklemede. Grafikleri görmek için BAŞLAT'a basın.")