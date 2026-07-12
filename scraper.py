"""
Tavily API kullanarak internetten burs arayan modul.

Strateji:
  1. Bolume ozel + genel burs sorgulari olusturur
  2. Tavily API ile arama yapar (arama + icerik cikarma tek seferde)
  3. Sonuclari relevance skoruna gore siralar
  4. Tekrarlari baslik benzerligi ile eler
"""

import os
import logging
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from tavily import TavilyClient

logger = logging.getLogger(__name__)

CURRENT_YEAR = datetime.now().year

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")


@dataclass
class Scholarship:
    name: str
    description: str
    source_url: str
    source_name: str
    score: float = 0.0


def _build_queries(department: str) -> List[str]:
    dep = department.strip()
    y = CURRENT_YEAR
    return [
        f"{dep} burs basvurusu {y}",
        f"{dep} ogrencilerine burs veren kurumlar vakiflar {y}",
        f"{dep} lisans yuksek lisans burs imkanlari {y}",
        f"universite ogrencilerine acik burs programlari {y}",
        f"ozel sektor vakif belediye burs basvurusu {y}",
        f"KYK burs kredi basvuru {y}",
        f"turkiye burslari basvuru {y}",
        f"tubitak burs destek programlari {y}",
    ]


def _tavily_search(client: TavilyClient, query: str) -> List[dict]:
    """Tek bir sorgu icin Tavily araması yapar."""
    try:
        response = client.search(
            query=query,
            search_depth="advanced",
            include_answer=False,
            max_results=10,
        )
        return response.get("results", [])
    except Exception as e:
        logger.warning(f"Tavily arama hatasi ({query[:40]}...): {e}")
        return []


def _score(s: Scholarship, department: str) -> float:
    text = (s.name + " " + s.description).lower()
    dep_lower = department.lower()
    score = 0.0

    # Bolum adi eslesmesi
    dep_words = dep_lower.split()
    matched = sum(1 for w in dep_words if w in text)
    score += (matched / max(len(dep_words), 1)) * 40

    # Yil eslesmesi
    if str(CURRENT_YEAR) in text:
        score += 15
    if str(CURRENT_YEAR - 1) in text:
        score += 5

    # Anahtar kelime yogunlugu
    important_kw = ["basvuru", "burs", "destek", "vakif", "hibe", "kontenjan",
                     "son tarih", "burs tutari", "tl"]
    score += sum(3 for kw in important_kw if kw in text)

    # Detay zenginligi
    if s.description and len(s.description) > 100:
        score += 5
    if s.description and len(s.description) > 200:
        score += 5

    # Guvenilir kaynaklar
    trusted = ["turkiyeburslari.gov.tr", "kyk.gov.tr", "tubitak.gov.tr",
                "yok.gov.tr", "tuba.gov.tr"]
    if any(t in s.source_name for t in trusted):
        score += 10

    return score


def _deduplicate(scholarships: List[Scholarship]) -> List[Scholarship]:
    seen_urls: set = set()
    seen_titles: List[str] = []
    unique: List[Scholarship] = []

    for s in scholarships:
        normalized_url = s.source_url.rstrip("/").lower()
        if normalized_url in seen_urls:
            continue

        name_lower = s.name.lower()
        is_dup = any(
            SequenceMatcher(None, name_lower, prev).ratio() > 0.75
            for prev in seen_titles
        )
        if is_dup:
            continue

        seen_urls.add(normalized_url)
        seen_titles.append(name_lower)
        unique.append(s)

    return unique


def search_scholarships(department: str) -> List[Scholarship]:
    """Belirli bir bolum icin Tavily API ile burs arar."""
    if not TAVILY_API_KEY:
        logger.error("TAVILY_API_KEY ayarlanmamis!")
        return []

    client = TavilyClient(api_key=TAVILY_API_KEY)
    queries = _build_queries(department)
    all_scholarships: List[Scholarship] = []
    seen_urls: set = set()

    # Paralel arama
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_tavily_search, client, q): q for q in queries}
        for future in as_completed(futures):
            results = future.result()
            for r in results:
                url = r.get("url", "")
                title = r.get("title", "")
                content = r.get("content", "")

                if url in seen_urls or not title:
                    continue
                seen_urls.add(url)

                # Burs ile ilgisi olmayanlari filtrele
                combined = (title + " " + content).lower()
                if not any(kw in combined for kw in
                           ["burs", "kredi", "ogrenci", "basvuru", "scholarship",
                            "vakif", "destek", "hibe"]):
                    continue

                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace("www.", "")

                all_scholarships.append(Scholarship(
                    name=title,
                    description=content[:500] if content else "",
                    source_url=url,
                    source_name=domain,
                ))

    logger.info(f"Toplam {len(all_scholarships)} ham sonuc bulundu.")

    # Skorla ve sirala
    for s in all_scholarships:
        s.score = _score(s, department)
    all_scholarships.sort(key=lambda s: s.score, reverse=True)

    # Tekrarlari ele
    unique = _deduplicate(all_scholarships)

    result = unique[:20]
    logger.info(f"'{department}' icin {len(result)} burs sonucu donduruldu.")
    return result
