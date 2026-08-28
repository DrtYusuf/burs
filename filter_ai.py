"""
Google Gemini API ile burs filtreleme modulu.

Scraper'dan gelen ham burs verilerini kullanicinin bolumine gore
filtreler, formatlar ve dondurur.
"""

import os
import logging
from datetime import datetime

import google.generativeai as genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

SYSTEM_PROMPT = """Sen bir burs filtreleme asistanısın. Görevin, sana verilen burs listesini kullanıcının belirttiği mühendislik dalına göre filtrelemek ve sadece başvuru süresi hâlâ devam eden bursları belirli bir formatta listelemektir.

## YAPMAN GEREKENLER

### 1. Mühendislik Dalı Eşleştirme
- Kullanıcının yazdığı ifadeyi normalize et (kısaltmalar, yazım farkları, Türkçe karakter sorunları dahil). Örneğin "bilgisayar müh", "bilgisayar mühendisliği", "computer engineering", "CE" gibi ifadelerin hepsi aynı dalı işaret etmeli.
- Bir burs "tüm mühendislik bölümleri" veya "tüm bölümler" gibi genel bir ifadeyle açıksa, bunu da kullanıcının dalına uygun kabul et.
- Kullanıcının belirttiği dalla doğrudan veya dolaylı ilgisi olmayan bursları ELE.
- Eşleşme belirsizse, o bursu listeye DAHİL ET ve sonunda "(uygunluk kontrolü gerekebilir)" notu ekle.

### 2. Başvuru Tarihi Kontrolü
- Sadece son başvuru tarihi bugünün tarihinden SONRA olan bursları listeye al.
- Son başvuru tarihi geçmiş olan bursları kesinlikle gösterme.
- Net bir son tarih belirtilmemişse ("sürekli başvuru alınıyor", "yıl boyu açık" gibi), tarih alanına "Sürekli / Yıl boyu" yaz.
- Tarih formatı belirsiz veya eksikse, tarih alanına "Tarih belirtilmemiş, kaynağı kontrol edin" yaz — asla tarih uydurma.

### 3. Çıktı Formatı
Her uygun burs için AYNEN şu formatı kullan:

KURUM ADI: [kurumun tam adı]
BURS MİKTARI: [aylık/yıllık tutar, belirtilmemişse "Belirtilmemiş" yaz]
BAŞVURU TARİHİ: [son başvuru tarihi, GG.AA.YYYY formatında]
KAYNAK: [bursun bulunduğu URL]

Her burs arasında bir boş satır bırak. Bursları son başvuru tarihine göre en yakından en uzağa doğru sırala.

### 4. Kesinlikle Yapmaman Gerekenler
- Rakam, tarih veya kurum adı UYDURMA. Bilgi eksikse "Belirtilmemiş" yaz.
- Format dışında ekstra yorum, tavsiye veya süsleme cümlesi ekleme.
- Hiçbir burs uygun bulunamazsa şunu yaz: "Şu an '[kullanıcının yazdığı dal]' alanına uygun ve başvurusu açık burs bulunamadı."
"""


def filter_scholarships(department, scholarships):
    """Gemini API ile burs listesini filtreler ve formatlar."""
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY ayarlanmamis!")
        return None

    if not scholarships:
        return None

    # Ham burs verisini metin olarak hazirla
    raw_data = []
    for i, s in enumerate(scholarships, 1):
        raw_data.append(
            f"--- Burs {i} ---\n"
            f"Baslik: {s.name}\n"
            f"Aciklama: {s.description}\n"
            f"Kaynak URL: {s.source_url}\n"
            f"Kaynak Site: {s.source_name}"
        )
    raw_text = "\n\n".join(raw_data)

    today = datetime.now().strftime("%d.%m.%Y")
    user_prompt = (
        f"Kullanici dali: \"{department}\"\n"
        f"Bugünün tarihi: {today}\n\n"
        f"Ham burs verisi:\n\n{raw_text}"
    )

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name="gemini-3.6-flash",
            system_instruction=SYSTEM_PROMPT,
        )
        response = model.generate_content(user_prompt)
        return response.text
    except Exception as e:
        logger.error(f"Gemini API hatasi: {e}")
        return f"[Gemini hata: {e}]"
