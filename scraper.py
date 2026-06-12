"""
Burs ve kredi duyurularini cesitli kaynaklardan tarayan modul.
"""

import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import logging

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), "seen_scholarships.json")


@dataclass
class Scholarship:
    name: str
    grades: str  # "1, 2, 3, 4" veya "Tum siniflar"
    departments: str  # "Tum bolumler" veya spesifik bolumler
    amount: str  # "Aylik 2.000 TL" gibi
    source_url: str = ""
    date_found: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    def to_dict(self):
        return {
            "name": self.name,
            "grades": self.grades,
            "departments": self.departments,
            "amount": self.amount,
            "source_url": self.source_url,
            "date_found": self.date_found,
        }

    def unique_key(self):
        return f"{self.name}|{self.grades}|{self.amount}"


def load_seen():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)


def _headers():
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "tr-TR,tr;q=0.9",
    }


def scrape_bfrk():
    """T.C. Basbakanlik Burs ve Kredi (KYK) sayfasindan bilgi cekmek."""
    scholarships = []
    try:
        url = "https://www.kyk.gov.tr/sayfalar/burs-kredi"
        resp = requests.get(url, headers=_headers(), timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        articles = soup.select("div.content-area article, div.post-content, div.entry-content")
        if not articles:
            articles = soup.select("div.container div.row div, main div")

        for article in articles[:10]:
            title_el = article.find(["h2", "h3", "h4", "a"])
            if title_el:
                title = title_el.get_text(strip=True)
                if any(kw in title.lower() for kw in ["burs", "kredi", "ogrenci"]):
                    link = ""
                    a_tag = title_el if title_el.name == "a" else title_el.find("a")
                    if a_tag and a_tag.get("href"):
                        link = a_tag["href"]
                        if link.startswith("/"):
                            link = "https://www.kyk.gov.tr" + link

                    scholarships.append(Scholarship(
                        name=title,
                        grades="Tum siniflar (1-4)",
                        departments="Tum bolumler",
                        amount="KYK tarafindan belirlenir",
                        source_url=link,
                    ))
    except Exception as e:
        logger.warning(f"KYK sayfasi taranamadi: {e}")

    return scholarships


def scrape_turkiye_burslari():
    """Turkiye Burslari sayfasindan bilgi cekmek."""
    scholarships = []
    try:
        url = "https://www.turkiyeburslari.gov.tr/"
        resp = requests.get(url, headers=_headers(), timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        items = soup.select("div.news-item, div.announcement, article, div.card")
        for item in items[:10]:
            title_el = item.find(["h2", "h3", "h4", "a"])
            if title_el:
                title = title_el.get_text(strip=True)
                if any(kw in title.lower() for kw in ["burs", "basvuru", "program"]):
                    link = ""
                    a_tag = title_el if title_el.name == "a" else title_el.find("a")
                    if a_tag and a_tag.get("href"):
                        link = a_tag["href"]
                        if link.startswith("/"):
                            link = "https://www.turkiyeburslari.gov.tr" + link

                    scholarships.append(Scholarship(
                        name=title,
                        grades="Tum siniflar (1-4)",
                        departments="Tum bolumler",
                        amount="Programa gore degisir",
                        source_url=link,
                    ))
    except Exception as e:
        logger.warning(f"Turkiye Burslari sayfasi taranamadi: {e}")

    return scholarships


def scrape_bfrk_gov():
    """BFRK (Burs Fonu Raportoru Kurumu) sayfasini taramak."""
    scholarships = []
    try:
        url = "https://www.gsb.gov.tr/AnaSayfa/Haber"
        resp = requests.get(url, headers=_headers(), timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        items = soup.select("div.news-item, div.haber-liste, article, li.list-group-item")
        for item in items[:15]:
            title_el = item.find(["h2", "h3", "h4", "a", "span"])
            if title_el:
                title = title_el.get_text(strip=True)
                if any(kw in title.lower() for kw in ["burs", "kredi", "ogrenci", "kyk"]):
                    link = ""
                    a_tag = title_el if title_el.name == "a" else title_el.find("a")
                    if a_tag and a_tag.get("href"):
                        link = a_tag["href"]
                        if link.startswith("/"):
                            link = "https://www.gsb.gov.tr" + link

                    scholarships.append(Scholarship(
                        name=title,
                        grades="Tum siniflar (1-4)",
                        departments="Tum bolumler",
                        amount="Duyuruda belirtilir",
                        source_url=link,
                    ))
    except Exception as e:
        logger.warning(f"GSB sayfasi taranamadi: {e}")

    return scholarships


def scrape_burslari_net():
    """burslari.net sitesinden burs ilanlarini cekmek."""
    scholarships = []
    try:
        url = "https://www.burslari.net/"
        resp = requests.get(url, headers=_headers(), timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        items = soup.select("article, div.post, div.entry, div.card")
        for item in items[:15]:
            title_el = item.find(["h2", "h3", "h4"])
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not any(kw in title.lower() for kw in ["burs", "kredi", "ogrenci", "lisans"]):
                continue

            link = ""
            a_tag = title_el.find("a") or title_el.find_parent("a")
            if a_tag and a_tag.get("href"):
                link = a_tag["href"]

            body = item.get_text(" ", strip=True).lower()

            grades = "Tum siniflar (1-4)"
            for g in ["1. sinif", "2. sinif", "3. sinif", "4. sinif", "hazirlik"]:
                if g in body:
                    grades = body[body.index(g):body.index(g)+50].split(".")[0]
                    break

            departments = "Tum bolumler"
            if "tum bolum" in body or "tum fakulte" in body:
                departments = "Tum bolumler"
            elif "muhendislik" in body or "tip" in body or "hukuk" in body:
                dept_list = []
                for d in ["muhendislik", "tip", "hukuk", "isletme", "iktisat",
                           "bilgisayar", "fen", "edebiyat", "egitim", "mimarlik"]:
                    if d in body:
                        dept_list.append(d.capitalize())
                if dept_list:
                    departments = ", ".join(dept_list)

            amount = "Belirtilmemis"
            import re
            amount_match = re.search(r'(\d{1,3}[.,]?\d{0,3})\s*(tl|lira)', body)
            if amount_match:
                amount = f"Aylik {amount_match.group(0).upper()}"

            scholarships.append(Scholarship(
                name=title,
                grades=grades,
                departments=departments,
                amount=amount,
                source_url=link,
            ))
    except Exception as e:
        logger.warning(f"burslari.net taranamadi: {e}")

    return scholarships


def scrape_all():
    """Tum kaynaklari tarar ve yeni burslari dondurur."""
    seen = load_seen()
    all_scholarships = []

    scrapers = [
        scrape_bfrk,
        scrape_turkiye_burslari,
        scrape_bfrk_gov,
        scrape_burslari_net,
    ]

    for scraper in scrapers:
        try:
            results = scraper()
            all_scholarships.extend(results)
        except Exception as e:
            logger.error(f"Scraper hatasi ({scraper.__name__}): {e}")

    new_scholarships = []
    for s in all_scholarships:
        key = s.unique_key()
        if key not in seen:
            seen.add(key)
            new_scholarships.append(s)

    save_seen(seen)

    logger.info(f"Toplam {len(all_scholarships)} burs bulundu, {len(new_scholarships)} yeni.")
    return new_scholarships
