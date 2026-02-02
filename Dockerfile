# 1. Taban İmaj: Hafif ve hızlı Python sürümü
FROM python:3.9-slim

# 2. Çalışma klasörünü ayarla
WORKDIR /app

# 3. Zaman Dilimi Ayarı (Logların yerel saatle tutması için kritik)
# Eğer Linux kullanıyorsan buna gerek yok, docker-compose'dan halledeceğiz.
# Ama Windows için environment variable ekleyelim.
ENV TZ=Europe/Istanbul

# 4. Önce gereksinim dosyasını kopyala ve kur (Cache optimizasyonu)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Projedeki tüm kodları (panel.py, veritabani.py vb.) içeri al
COPY . .

# 6. Streamlit'in portunu dışarı aç
EXPOSE 8501

# 7. Sağlık Kontrolü (Sistem çalışıyor mu diye her 30sn'de bir dürt)
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# 8. Başlatma komutu
ENTRYPOINT ["streamlit", "run", "panel.py", "--server.port=8501", "--server.address=0.0.0.0"]