"""
Internetten burs arayan modul.

Strateji:
  1. Bilinen burs sitelerini dogrudan tarar (burslarburada, bursiyer, vb.)
  2. Google arama sonuclarini tarar (genis sorgu seti)
  3. Sonuclari relevance skoruna gore siralar
  4. Tekrarlari URL ve baslik benzerligi ile eler
"""

import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from datetime import datetime
import re
import logging
from urllib.parse import quote_plus, urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from typing import Optional, List

logger = logging.getLogger(__name__)

CURRENT_YEAR = datetime.now().year

# --- Veri modeli ---

@dataclass
class Scholarship:
    name: str
    description: str
    source_url: str
    source_name: str
    score: float = 0.0


# --- HTTP yardimcilari ---

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})


def _get(url: str, timeout: int = 12) -> Optional[requests.Response]:
    try:
        resp = _SESSION.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.debug(f"GET basarisiz {url}: {e}")
        return None


def _soup(resp: requests.Response) -> BeautifulSoup:
    return BeautifulSoup(resp.text, "html.parser")


# ============================================================
# 1) DOGRUDAN SITE TARAYICILARI
# ============================================================

def _scrape_burslarburada(department: str) -> List[Scholarship]:
    """burslarburada.com guncel burs ilanlarini tarar."""
    results = []
    for page in range(1, 4):
        url = f"https://www.burslarburada.com/burslar/page/{page}/"
        resp = _get(url)
        if not resp:
            break
        soup = _soup(resp)

        articles = soup.select("article, div.post-item, div.burs-item, div.entry, li.post-item")
        if not articles:
            # Fallback: herhangi bir baslikli link
            articles = soup.find_all("h2") + soup.find_all("h3")

        for art in articles:
            a = art.find("a", href=True) if art.name != "a" else art
            if not a:
                a = art.find_parent("a", href=True)
            if not a:
                continue

            title = a.get_text(strip=True)
            href = a["href"]
            if not href.startswith("http"):
                href = urljoin(url, href)

            if len(title) < 5:
                continue

            snippet = ""
            p = art.find("p")
            if p:
                snippet = p.get_text(strip=True)[:300]

            results.append(Scholarship(
                name=title,
                description=snippet,
                source_url=href,
                source_name="burslarburada.com",
            ))
        if len(results) >= 30:
            break

    return results


def _scrape_bursiyer(department: str) -> List[Scholarship]:
    """bursiyer.com guncel burs ilanlarini tarar."""
    results = []
    for page in range(1, 4):
        url = f"https://www.bursiyer.com/burs-ilanlari/page/{page}/"
        resp = _get(url)
        if not resp:
            break
        soup = _soup(resp)

        articles = soup.select("article, div.post, div.entry-content, li.post-item")
        if not articles:
            articles = soup.find_all("h2") + soup.find_all("h3")

        for art in articles:
            a = art.find("a", href=True) if art.name != "a" else art
            if not a:
                a = art.find_parent("a", href=True)
            if not a:
                continue

            title = a.get_text(strip=True)
            href = a["href"]
            if not href.startswith("http"):
                href = urljoin(url, href)

            if len(title) < 5:
                continue

            snippet = ""
            p = art.find("p")
            if p:
                snippet = p.get_text(strip=True)[:300]

            results.append(Scholarship(
                name=title,
                description=snippet,
                source_url=href,
                source_name="bursiyer.com",
            ))
        if len(results) >= 30:
            break

    return results


def _scrape_tobbetu_burs(department: str) -> List[Scholarship]:
    """turkiyeburslari.gov.tr ana sayfa duyurularini tarar."""
    results = []
    url = "https://www.turkiyeburslari.gov.tr/tr/sayfa/duyurular"
    resp = _get(url)
    if not resp:
        return results
    soup = _soup(resp)

    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin(url, href)

        lower = title.lower()
        if any(kw in lower for kw in ["burs", "basvuru", "program", "scholarship"]) and len(title) > 10:
            results.append(Scholarship(
                name=title,
                description="",
                source_url=href,
                source_name="turkiyeburslari.gov.tr",
            ))

    return results


def _scrape_kyk(department: str) -> List[Scholarship]:
    """KYK (kyk.gov.tr) burs/kredi duyurularini tarar."""
    results = []
    url = "https://www.kyk.gov.tr/sayfalar/duyurular"
    resp = _get(url)
    if not resp:
        return results
    soup = _soup(resp)

    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin(url, href)

        lower = title.lower()
        if any(kw in lower for kw in ["burs", "kredi", "basvuru", "ogrenci"]) and len(title) > 10:
            results.append(Scholarship(
                name=title,
                description="",
                source_url=href,
                source_name="kyk.gov.tr",
            ))

    return results


# Tum dogrudan tarayicilar
DIRECT_SCRAPERS = [
    _scrape_burslarburada,
    _scrape_bursiyer,
    _scrape_tobbetu_burs,
    _scrape_kyk,
]


# ============================================================
# 2) GOOGLE ARAMA (genis sorgu seti)
# ============================================================

def _build_queries(department: str) -> List[str]:
    """Bolume gore genis sorgu seti olusturur."""
    dep = department.lower().strip()
    y = CURRENT_YEAR

    queries = [
        # Bolume ozel
        f"{dep} burs basvurusu {y}",
        f"{dep} ogrencilerine burs {y}",
        f"{dep} lisans burs imkanlari",
        f"{dep} yuksek lisans burs {y}",
        f"{dep} bursu veren vakiflar",
        # Genel
        f"universite ogrencilerine burs veren kurumlar {y}",
        f"ozel sektor burs programlari {y}",
        f"vakif burslari basvuru {y}",
        f"belediye burs basvurusu {y}",
        f"devlet burslari {y} lisans",
        f"kyk burs kredi basvuru {y}",
    ]
    return queries


def _google_search(query: str, num_results: int = 10) -> List[dict]:
    """Google'da arama yapar ve sonuclari dondurur."""
    results = []
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={num_results}&hl=tr"
    resp = _get(url, timeout=15)
    if not resp:
        return results

    soup = _soup(resp)

    for g in soup.select("div.g, div[data-sokoban-container]"):
        a_tag = g.find("a", href=True)
        title_el = g.find("h3")
        snippet_el = (
            g.find("div", class_="VwiC3b")
            or g.find("span", class_="aCOpRe")
            or g.find("div", {"data-sncf": True})
        )

        if a_tag and title_el:
            href = a_tag["href"]
            if href.startswith("/url?q="):
                href = href.split("/url?q=")[1].split("&")[0]
            if not href.startswith("http"):
                continue

            title = title_el.get_text(strip=True)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            results.append({
                "title": title,
                "url": href,
                "snippet": snippet,
            })

    return results


def _google_search_all(department: str) -> List[Scholarship]:
    """Tum sorgulari paralel calistirir."""
    queries = _build_queries(department)
    all_results: List[Scholarship] = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_google_search, q): q for q in queries}
        for future in as_completed(futures):
            try:
                results = future.result()
            except Exception:
                continue
            for r in results:
                combined = (r["title"] + " " + r["snippet"]).lower()
                if not any(kw in combined for kw in
                           ["burs", "kredi", "ogrenci", "basvuru", "scholarship", "vakif"]):
                    continue

                domain = urlparse(r["url"]).netloc.replace("www.", "")
                all_results.append(Scholarship(
                    name=r["title"],
                    description=r["snippet"],
                    source_url=r["url"],
                    source_name=domain,
                ))

    return all_results


# ============================================================
# 3) SAYFA DETAY CEKME
# ============================================================

def _scrape_page_details(url: str) -> str:
    """Bir sayfanin iceriginden burs ile ilgili detaylari cikarir."""
    resp = _get(url, timeout=10)
    if not resp:
        return ""

    soup = _soup(resp)
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)

    keywords = [
        "basvuru", "son tarih", "ucret", "miktar", "sart", "kosul",
        "kimler basvurabilir", "burs tutari", "deadline", "tl", "lira",
        "son basvuru", "kontenjan", "deger", "destek", "ay", "yil",
    ]

    relevant_parts = []
    sentences = re.split(r'[.!?\n]', text)
    for sentence in sentences:
        lower = sentence.lower().strip()
        if len(lower) < 15 or len(lower) > 400:
            continue
        if any(kw in lower for kw in keywords):
            relevant_parts.append(sentence.strip())
        if len(relevant_parts) >= 5:
            break

    return " | ".join(relevant_parts) if relevant_parts else ""


# ============================================================
# 4) SKORLAMA
# ============================================================

def _score(s: Scholarship, department: str) -> float:
    """Bir burs sonucunu relevance skoruyla degerlendirir."""
    text = (s.name + " " + s.description).lower()
    dep_lower = department.lower()
    score = 0.0

    # Bolum adi eslesmesi (en onemli)
    dep_words = dep_lower.split()
    matched_words = sum(1 for w in dep_words if w in text)
    score += (matched_words / max(len(dep_words), 1)) * 40

    # Yil eslesmesi
    if str(CURRENT_YEAR) in text:
        score += 15
    if str(CURRENT_YEAR - 1) in text:
        score += 5

    # Anahtar kelime yogunlugu
    important_kw = ["basvuru", "burs", "destek", "vakif", "hibe", "kontenjan"]
    kw_count = sum(1 for kw in important_kw if kw in text)
    score += kw_count * 3

    # Detay zenginligi
    if s.description:
        desc_len = len(s.description)
        if desc_len > 100:
            score += 5
        if desc_len > 200:
            score += 5

    # Bilinen guvenilir kaynaklar
    trusted = ["turkiyeburslari.gov.tr", "kyk.gov.tr", "burslarburada.com",
                "bursiyer.com", "tuba.gov.tr", "tubitak.gov.tr", "yok.gov.tr"]
    if any(t in s.source_name for t in trusted):
        score += 10

    return score


# ============================================================
# 5) DEDUPLICATION
# ============================================================

def _deduplicate(scholarships: List[Scholarship]) -> List[Scholarship]:
    """URL ve baslik benzerligine gore tekrarlari eler."""
    seen_urls: set = set()
    seen_titles: List[str] = []
    unique: List[Scholarship] = []

    for s in scholarships:
        # URL normalizasyonu
        normalized_url = s.source_url.rstrip("/").lower()
        if normalized_url in seen_urls:
            continue

        # Baslik benzerligi kontrolu
        is_dup = False
        name_lower = s.name.lower()
        for prev_title in seen_titles:
            ratio = SequenceMatcher(None, name_lower, prev_title).ratio()
            if ratio > 0.75:
                is_dup = True
                break

        if is_dup:
            continue

        seen_urls.add(normalized_url)
        seen_titles.append(name_lower)
        unique.append(s)

    return unique


# ============================================================
# ANA FONKSIYON
# ============================================================

def search_scholarships(department: str) -> List[Scholarship]:
    """Belirli bir bolum icin internetten burs arar.

    1. Bilinen siteleri dogrudan tarar (paralel)
    2. Google uzerinden arar (paralel sorgular)
    3. Sonuclari skorlar, siralar, tekrarlari eler
    4. En iyi sonuclarin detaylarini zenginlestirir
    """
    all_scholarships: List[Scholarship] = []

    # --- Paralel tarama: dogrudan siteler + google ---
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = []

        # Dogrudan site tarayicilarini baslat
        for scraper_fn in DIRECT_SCRAPERS:
            futures.append(pool.submit(scraper_fn, department))

        # Google aramayi baslat
        futures.append(pool.submit(_google_search_all, department))

        for future in as_completed(futures):
            try:
                results = future.result()
                all_scholarships.extend(results)
            except Exception as e:
                logger.warning(f"Tarayici hatasi: {e}")

    logger.info(f"Toplam {len(all_scholarships)} ham sonuc bulundu.")

    # Skorla
    for s in all_scholarships:
        s.score = _score(s, department)

    # Sirala (yuksek skor once)
    all_scholarships.sort(key=lambda s: s.score, reverse=True)

    # Tekrarlari ele
    unique = _deduplicate(all_scholarships)

    # En iyi 20 sonucun detaylarini zenginlestir
    top = unique[:20]

    def _enrich(s: Scholarship) -> Scholarship:
        if len(s.description) < 50:
            details = _scrape_page_details(s.source_url)
            if details:
                s.description = details
        return s

    with ThreadPoolExecutor(max_workers=5) as pool:
        enriched = list(pool.map(_enrich, top))

    logger.info(f"'{department}' icin {len(enriched)} burs sonucu donduruldu.")
    return enriched
