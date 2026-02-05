import streamlit as st
import pandas as pd
import time
import sys
import os

# Üst dizindeki modülleri (veritabani.py) görebilmesi için yol ayarı
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import veritabani

st.set_page_config(page_title="Aktif Alarmlar", page_icon="⚠️", layout="wide")

st.title("⚠️ Aktif Donanım Arızaları")
st.markdown("Cihazlardan gelen hata kodlarının (Register 189 & 193) detaylı dökümü.")

# --- ALARM HARİTALARI ---
FAULT_MAP_189 = {
    0:  "DC Overcurrent Fault [1-1]",
    1:  "DC Overcurrent Fault [1-2]",
    2:  "DC Overcurrent Fault [2-1]",
    3:  "DC Overcurrent Fault [2-2]",
    4:  "DC Overcurrent Fault [3-1]",
    5:  "DC Overcurrent Fault [3-2]",
    6:  "DC Overcurrent Fault [4-1]",
    7:  "DC Overcurrent Fault [4-2]",
    8:  "DC Overcurrent Fault [5-1]",
    9:  "DC Overcurrent Fault [5-2]",
    10: "DC Overcurrent Fault [6-1]",
    11: "DC Overcurrent Fault [6-2]",
    12: "DC Overcurrent Fault [7-1]",
    13: "DC Overcurrent Fault [7-2]",
    14: "DC Overcurrent Fault [8-1]",
    15: "DC Overcurrent Fault [8-2]",
    16: "DC Overcurrent Fault [9-1]",
    17: "DC Overcurrent Fault [9-2]",
    18: "DC Overcurrent Fault [10-1]",
    19: "DC Overcurrent Fault [10-2]",
    20: "DC Overcurrent Fault [11-1]",
    21: "DC Overcurrent Fault [11-2]",
    22: "DC Overcurrent Fault [12-1]",
    23: "DC Overcurrent Fault [12-2]"
}

FAULT_MAP_193 = {
    0: "PV Overvoltage[1]",
    1: "PV Overvoltage[2]",
    2: "PV Overvoltage[3]",
    3: "PV Overvoltage[4]",
    4: "PV Overvoltage[5]",
    5: "PV Overvoltage[6]",
    6: "PV Overvoltage[7]",
    7: "PV Overvoltage[8]",
    8: "PV Overvoltage[9]",
    9: "PV Overvoltage[10]",
    10: "PV Overvoltage[11]",
    11: "PV Overvoltage[12]"
}

def active_fault_checker(hata_kodu, fault_map):
    active_faults = []
    for bit_index in range(32): 
        if (hata_kodu >> bit_index) & 1:
            mesaj = fault_map.get(bit_index, f"Bilinmeyen Hata (Bit {bit_index})")
            active_faults.append(mesaj)
    return active_faults

# --- VERİLERİ ÇEK VE GÖSTER ---
summary_data = veritabani.tum_cihazlarin_son_durumu()

if not summary_data:
    st.info("Henüz veri yok.")
else:
    toplam_hata = 0
    
    # 2 Kolonlu Düzen
    col1, col2 = st.columns(2)
    
    for row in summary_data:
        dev_id = row[0]
        hata_189 = row[6] if len(row) > 6 else 0
        hata_193 = row[7] if len(row) > 7 else 0
        
        device_has_error = (hata_189 > 0) or (hata_193 > 0)
        
        if device_has_error:
            with st.expander(f"🔴 ID: {dev_id} - ARIZA TESPİT EDİLDİ", expanded=True):
                # 189 Hataları
                if hata_189 > 0:
                    st.markdown("**Register 189 Hataları:**")
                    for err in active_fault_checker(hata_189, FAULT_MAP_189):
                        st.error(f"🛑 {err}")
                        toplam_hata += 1
                
                # 193 Hataları
                if hata_193 > 0:
                    st.divider()
                    st.markdown("**Register 193 Hataları:**")
                    for err in active_fault_checker(hata_193, FAULT_MAP_193):
                        st.warning(f"⚠️ {err}")
                        toplam_hata += 1
        else:
            with st.expander(f"✅ ID: {dev_id} - Sistem Stabil", expanded=False):
                st.write("Aktif arıza kaydı bulunmamaktadır.")

    if toplam_hata == 0:
        st.success("🎉 Harika! Sistemde şu an hiç aktif arıza yok.")

# Otomatik Yenileme Butonu
if st.button("🔄 Yenile"):
    st.rerun()