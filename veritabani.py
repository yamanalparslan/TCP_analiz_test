import sqlite3
import os
from datetime import datetime

# --- VERİTABANI YOL AYARLARI ---
# Hata Düzeltme: Dosyanın 'data' klasörü içinde oluşmasını garanti ediyoruz.

# Docker içinde miyiz kontrolü (/app/data genellikle Docker volume yoludur)
if os.path.exists("/app/data"):
    DB_NAME = "/app/data/solar_log.db"
else:
    # Yerel bilgisayarda test ediliyorsa 'data' klasörü yoksa oluştur
    if not os.path.exists("data"):
        os.makedirs("data")
    DB_NAME = os.path.join("data", "solar_log.db")

def init_db():
    # Debug için yol bilgisini yazdıralım
    print(f"📂 Veritabanı Bağlanıyor: {DB_NAME}")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Ölçümler Tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS olcumler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slave_id INTEGER, 
            zaman TIMESTAMP,
            guc REAL,
            voltaj REAL,
            akim REAL,
            sicaklik REAL,
            hata_kodu INTEGER DEFAULT 0,
            hata_kodu_193 INTEGER DEFAULT 0
        )
    """)

    # 2. Ayarlar Tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ayarlar (
            anahtar TEXT PRIMARY KEY,
            deger TEXT,
            aciklama TEXT,
            guncelleme_zamani TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # MIGRATION: Eski ayarlar tablosuna yeni kolonlar ekle
    try:
        ayarlar_sutunlar = [row[1] for row in cursor.execute("PRAGMA table_info(ayarlar)")]
        if 'aciklama' not in ayarlar_sutunlar:
            cursor.execute("ALTER TABLE ayarlar ADD COLUMN aciklama TEXT")
        if 'guncelleme_zamani' not in ayarlar_sutunlar:
            cursor.execute("ALTER TABLE ayarlar ADD COLUMN guncelleme_zamani TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except:
        pass

    # 3. Varsayılan Ayarları Ekle
    varsayilan_ayarlar = [
        ('refresh_rate', '2', 'Veri çekme sıklığı (saniye)'),
        ('guc_scale', '1.0', 'Güç çarpanı'),
        ('volt_scale', '0.1', 'Voltaj çarpanı'),
        ('akim_scale', '0.1', 'Akım çarpanı'),
        ('isi_scale', '1.0', 'Sıcaklık çarpanı'),
        ('guc_addr', '70', 'Güç register adresi'),
        ('volt_addr', '71', 'Voltaj register adresi'),
        ('akim_addr', '72', 'Akım register adresi'),
        ('isi_addr', '73', 'Sıcaklık register adresi'),
        ('target_ip', '10.35.14.10', 'Modbus IP adresi'),
        ('target_port', '502', 'Modbus Port'),
        ('slave_ids', '1,2,3', 'İnverter ID listesi')
    ]
    
    for anahtar, deger, aciklama in varsayilan_ayarlar:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO ayarlar (anahtar, deger, aciklama)
                VALUES (?, ?, ?)
            """, (anahtar, deger, aciklama))
        except:
            cursor.execute("""
                INSERT OR IGNORE INTO ayarlar (anahtar, deger)
                VALUES (?, ?)
            """, (anahtar, deger))
    
    # MIGRATION: hata_kodu_193 kolonu yoksa ekle
    try:
        mevcut_sutunlar = [row[1] for row in cursor.execute("PRAGMA table_info(olcumler)")]
        if 'hata_kodu_193' not in mevcut_sutunlar:
            cursor.execute("ALTER TABLE olcumler ADD COLUMN hata_kodu_193 INTEGER DEFAULT 0")
    except:
        pass
        
    conn.commit()
    conn.close()

def ayar_oku(anahtar, varsayilan=None):
    """Veritabanından ayar oku"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT deger FROM ayarlar WHERE anahtar = ?', (anahtar,))
        sonuc = cursor.fetchone()
        conn.close()
        if sonuc:
            return sonuc[0]
        return varsayilan
    except Exception as e:
        print(f"⚠️ Ayar okuma hatası ({anahtar}): {e}")
        return varsayilan

def ayar_yaz(anahtar, deger):
    """Veritabanına ayar yaz"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO ayarlar (anahtar, deger, guncelleme_zamani)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (anahtar, str(deger)))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️ Ayar yazma hatası ({anahtar}): {e}")
        return False

def tum_ayarlari_oku():
    """Tüm ayarları dict olarak döndür"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT anahtar, deger FROM ayarlar')
        ayarlar = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return ayarlar
    except:
        return {
            'refresh_rate': '2', 'guc_scale': '1.0', 'volt_scale': '0.1',
            'akim_scale': '0.1', 'isi_scale': '1.0', 'guc_addr': '70',
            'volt_addr': '71', 'akim_addr': '72', 'isi_addr': '73',
            'target_ip': '10.35.14.10', 'target_port': '502', 'slave_ids': '1,2,3'
        }

def veri_ekle(slave_id, data):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    simdi = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    hk_189 = data.get('hata_kodu', 0)
    hk_193 = data.get('hata_kodu_193', 0)
    cursor.execute("""
        INSERT INTO olcumler (slave_id, zaman, guc, voltaj, akim, sicaklik, hata_kodu, hata_kodu_193)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (slave_id, simdi, data['guc'], data['voltaj'], data['akim'], data['sicaklik'], hk_189, hk_193))
    conn.commit()
    conn.close()

def son_verileri_getir(slave_id, limit=100):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT zaman, guc, voltaj, akim, sicaklik, hata_kodu, hata_kodu_193
        FROM olcumler WHERE slave_id = {slave_id}
        ORDER BY zaman DESC LIMIT {limit}
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows[::-1]

def tum_cihazlarin_son_durumu():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT slave_id, MAX(zaman) as son_zaman, guc, voltaj, akim, sicaklik, hata_kodu, hata_kodu_193
        FROM olcumler GROUP BY slave_id ORDER BY slave_id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def db_temizle():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM olcumler')
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()