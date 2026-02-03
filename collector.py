import time
import logging
from pymodbus.client import ModbusTcpClient
from datetime import datetime
import veritabani

def load_config():
    """Veritabanından ayarları yükle"""
    ayarlar = veritabani.tum_ayarlari_oku()
    return {
        'target_ip': ayarlar.get('target_ip', '10.35.14.10'),
        'target_port': int(ayarlar.get('target_port', 502)),
        'refresh_rate': float(ayarlar.get('refresh_rate', 2)),
        'slave_ids': [int(x.strip()) for x in ayarlar.get('slave_ids', '1,2,3').split(',')],
        'start_addr': int(ayarlar.get('guc_addr', 70)),
        'guc_scale': float(ayarlar.get('guc_scale', 1.0)),
        'volt_scale': float(ayarlar.get('volt_scale', 0.1)),
        'akim_scale': float(ayarlar.get('akim_scale', 0.1)),
        'isi_scale': float(ayarlar.get('isi_scale', 1.0)),
        'veri_saklama_gun': int(ayarlar.get('veri_saklama_gun', 365)),
        'alarm_registers': [
            {'addr': 189, 'key': 'hata_kodu', 'count': 2},
            {'addr': 193, 'key': 'hata_kodu_193', 'count': 1}
        ]
    }

def read_device(client, slave_id, config):
    try:
        if not client.connected: 
            client.connect()
            time.sleep(0.1)
        
        rr = client.read_holding_registers(config['start_addr'], count=4, slave=slave_id)
        if rr.isError(): 
            return None

        veriler = {
            "guc": rr.registers[0] * config['guc_scale'],
            "voltaj": rr.registers[1] * config['volt_scale'],
            "akim": rr.registers[2] * config['akim_scale'],
            "sicaklik": rr.registers[3] * config['isi_scale']
        }

        for reg in config['alarm_registers']:
            try:
                time.sleep(0.05)
                r_hata = client.read_holding_registers(reg['addr'], count=reg.get('count', 2), slave=slave_id)
                if not r_hata.isError():
                    if reg.get('count', 2) == 2:
                        veriler[reg['key']] = (r_hata.registers[0] << 16) | r_hata.registers[1]
                    else:
                        veriler[reg['key']] = r_hata.registers[0]
                else:
                    veriler[reg['key']] = 0
            except:
                veriler[reg['key']] = 0

        return veriler

    except Exception as e:
        logging.error(f"ID {slave_id} Hata: {e}")
        client.close()
        return None

def otomatik_veri_temizle(config):
    """
    Ayarlara göre eski verileri otomatik temizle
    0 = Sınırsız saklama (temizleme yapma)
    """
    saklama_gun = config.get('veri_saklama_gun', 365)
    
    if saklama_gun == 0:
        return 0  # Sınırsız saklama - temizleme yapma
    
    try:
        silinen = veritabani.eski_verileri_temizle(saklama_gun)
        if silinen > 0:
            print(f"\n🧹 Otomatik Temizlik: {silinen} kayıt silindi ({saklama_gun} günden eski)")
        return silinen
    except Exception as e:
        print(f"\n⚠️ Otomatik temizlik hatası: {e}")
        return 0

def start_collector():
    veritabani.init_db()
    print("=" * 60)
    print("🚀 COLLECTOR BAŞLATILDI (Dinamik Ayar Modu)")
    print("=" * 60)
    
    config = load_config()
    client = ModbusTcpClient(config['target_ip'], port=config['target_port'], timeout=2.0)
    
    print(f"📡 IP: {config['target_ip']}:{config['target_port']}")
    print(f"⏱️  Refresh: {config['refresh_rate']}s")
    print(f"🔢 Slave IDs: {config['slave_ids']}")
    print(f"📊 Çarpanlar: Güç={config['guc_scale']}, V={config['volt_scale']}, A={config['akim_scale']}, °C={config['isi_scale']}")
    
    if config['veri_saklama_gun'] == 0:
        print(f"♾️  Veri Saklama: Sınırsız")
    else:
        print(f"🗄️  Veri Saklama: {config['veri_saklama_gun']} Gün")
    
    print("=" * 60)
    
    ayar_kontrol_sayaci = 0
    temizlik_sayaci = 0
    TEMIZLIK_PERIYODU = 1800  # Her 30 dakikada bir temizlik yap (1800 döngü x 2sn = 3600sn = 60dk)
    
    # İlk başlangıçta bir kere temizlik yap
    otomatik_veri_temizle(config)
    
    while True:
        start_time = time.time()
        
        # Her 10 döngüde bir ayarları kontrol et
        ayar_kontrol_sayaci += 1
        if ayar_kontrol_sayaci >= 10:
            yeni_config = load_config()
            if (yeni_config['target_ip'] != config['target_ip'] or 
                yeni_config['target_port'] != config['target_port']):
                print("\n🔄 IP/Port değişti, bağlantı yenileniyor...")
                client.close()
                client = ModbusTcpClient(yeni_config['target_ip'], port=yeni_config['target_port'], timeout=2.0)
            config = yeni_config
            ayar_kontrol_sayaci = 0
            print(f"\n✅ Ayarlar güncellendi (Refresh: {config['refresh_rate']}s)")
        
        # Otomatik veri temizleme (her 30 dakikada)
        temizlik_sayaci += 1
        if temizlik_sayaci >= TEMIZLIK_PERIYODU:
            otomatik_veri_temizle(config)
            temizlik_sayaci = 0
        
        # Veri toplama
        for dev_id in config['slave_ids']:
            print(f"📡 ID {dev_id}...", end=" ")
            time.sleep(0.5)
            data = read_device(client, dev_id, config)
            if data:
                veritabani.veri_ekle(dev_id, data)
                h189 = data.get('hata_kodu', 0)
                h193 = data.get('hata_kodu_193', 0)
                if h189 == 0 and h193 == 0:
                    durum = "TEMİZ"
                else:
                    durum = f"⚠️ HATA (189:{h189}, 193:{h193})"
                print(f"✅ [OK] {durum}")
            else:
                print(f"❌ [YOK]")
        
        elapsed = time.time() - start_time
        time.sleep(max(0, config['refresh_rate'] - elapsed))

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    start_collector()