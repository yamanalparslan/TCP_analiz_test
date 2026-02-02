import time
import logging
from pymodbus.client import ModbusTcpClient
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
    print("=" * 60)
    
    ayar_kontrol_sayaci = 0
    
    while True:
        start_time = time.time()
        
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
