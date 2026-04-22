from __future__ import annotations

import argparse
import csv
import io
import re
import sqlite3
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

import cv2
import numpy as np
import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import NotOpenSSLWarning


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 10
DEFAULT_SERVICE = "hjemmeside, billeder og lokal SEO"
DEFAULT_CITY = "Esbjerg"
DEFAULT_QUERY = "restaurant"
DEFAULT_NICHE = "restaurant"
ALL_BUSINESSES_QUERY = "__all_businesses__"
DEFAULT_OUTPUT_CSV = "lead_results.csv"
DEFAULT_OUTPUT_MD = "lead_report.md"
DEFAULT_OUTPUT_DB = "lead_engine.db"
DEFAULT_MAX_BUSINESSES = 20
DEFAULT_MAX_IMAGES = 5

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s\-]?)?(?:\d[\s\-()]?){6,15}\d")
COMMON_CONTACT_PATHS = ("/kontakt", "/contact", "/om-os", "/about", "/booking", "/menu")
SOCIAL_DOMAINS = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
}
PRIORITY_STATUSES = {
    "A": "new-high-priority",
    "B": "review",
    "C": "backlog",
}
CSV_ALIASES = {
    "name": ["name", "business_name", "company", "company_name", "title"],
    "website": ["website", "domain", "url", "site", "homepage"],
    "city": ["city", "town", "location"],
    "query": ["query", "search_query", "category", "segment", "industry"],
    "rating": ["rating", "maps_rating", "google_rating"],
    "review_count": ["review_count", "reviews", "maps_reviews", "google_reviews"],
    "image_count": ["image_count", "photo_count", "photos", "maps_image_count"],
    "maps_url": ["maps_url", "place_url", "maps_link", "google_maps_url"],
    "facebook": ["facebook", "facebook_url"],
    "instagram": ["instagram", "instagram_url"],
    "linkedin": ["linkedin", "linkedin_url"],
    "tiktok": ["tiktok", "tiktok_url"],
    "youtube": ["youtube", "youtube_url"],
}
NICHE_CONFIGS = {
    "auto_dealer": {
        "keywords": ["bilforhandler", "brugte biler", "nye biler", "vaerksted", "leasing"],
        "expected_socials": ["facebook", "instagram"],
        "needs_booking": False,
        "needs_menu": False,
        "maps_weight": 1.1,
    },
    "real_estate": {
        "keywords": ["ejendomsmaegler", "boliger", "villa", "lejlighed", "salgsvurdering"],
        "expected_socials": ["facebook", "instagram", "linkedin"],
        "needs_booking": False,
        "needs_menu": False,
        "maps_weight": 0.8,
    },
    "lawyer": {
        "keywords": ["advokat", "juridisk", "raadgivning", "kontakt"],
        "expected_socials": ["linkedin", "facebook"],
        "needs_booking": False,
        "needs_menu": False,
        "maps_weight": 0.8,
    },
    "accountant": {
        "keywords": ["revisor", "bogholderi", "regnskab", "raadgivning"],
        "expected_socials": ["linkedin", "facebook"],
        "needs_booking": False,
        "needs_menu": False,
        "maps_weight": 0.8,
    },
    "dentist": {
        "keywords": ["tandlaege", "implantat", "behandling", "book tid"],
        "expected_socials": ["facebook"],
        "needs_booking": True,
        "needs_menu": False,
        "maps_weight": 1.0,
    },
    "cafe": {
        "keywords": ["cafe", "kaffe", "brunch", "menu", "booking"],
        "expected_socials": ["instagram", "facebook"],
        "needs_booking": False,
        "needs_menu": True,
        "maps_weight": 1.2,
    },
    "retail": {
        "keywords": ["butik", "shop", "produkter", "aabningstider"],
        "expected_socials": ["instagram", "facebook"],
        "needs_booking": False,
        "needs_menu": False,
        "maps_weight": 1.0,
    },
    "photographer": {
        "keywords": ["fotograf", "bryllup", "portraet", "galleri", "booking"],
        "expected_socials": ["instagram", "facebook"],
        "needs_booking": True,
        "needs_menu": False,
        "maps_weight": 1.1,
    },
    "plumber": {
        "keywords": ["vvs", "blaikkenslager", "installation", "kontakt", "service"],
        "expected_socials": ["facebook"],
        "needs_booking": False,
        "needs_menu": False,
        "maps_weight": 0.9,
    },
    "electrician": {
        "keywords": ["elektriker", "el-installation", "service", "kontakt"],
        "expected_socials": ["facebook"],
        "needs_booking": False,
        "needs_menu": False,
        "maps_weight": 0.9,
    },
    "carpenter": {
        "keywords": ["toemrer", "renovering", "byggeri", "kontakt"],
        "expected_socials": ["facebook", "instagram"],
        "needs_booking": False,
        "needs_menu": False,
        "maps_weight": 0.9,
    },
    "restaurant": {
        "keywords": ["restaurant", "menu", "booking", "take away", "mad", "drinks"],
        "expected_socials": ["facebook", "instagram"],
        "needs_booking": True,
        "needs_menu": True,
        "maps_weight": 1.2,
    },
    "salon": {
        "keywords": ["frisor", "salon", "hair", "beauty", "booking", "behandling"],
        "expected_socials": ["instagram", "facebook"],
        "needs_booking": True,
        "needs_menu": False,
        "maps_weight": 1.1,
    },
    "clinic": {
        "keywords": ["klinik", "tandlaege", "behandling", "book", "kontakt"],
        "expected_socials": ["facebook"],
        "needs_booking": True,
        "needs_menu": False,
        "maps_weight": 0.9,
    },
    "gym": {
        "keywords": ["fitness", "gym", "membership", "hold", "book"],
        "expected_socials": ["instagram", "facebook", "youtube"],
        "needs_booking": False,
        "needs_menu": False,
        "maps_weight": 1.0,
    },
    "hotel": {
        "keywords": ["hotel", "rooms", "booking", "stay", "restaurant"],
        "expected_socials": ["instagram", "facebook"],
        "needs_booking": True,
        "needs_menu": False,
        "maps_weight": 1.2,
    },
    "default": {
        "keywords": [],
        "expected_socials": ["facebook"],
        "needs_booking": False,
        "needs_menu": False,
        "maps_weight": 1.0,
    },
}

warnings.filterwarnings("ignore", category=NotOpenSSLWarning)


@dataclass
class ImageAnalysis:
    url: str
    width: int
    height: int
    blur_score: float
    score: int


@dataclass
class SiteProfile:
    website: str
    business_name: str
    title: str
    meta_description: str
    contact_page: str | None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    social_links: dict[str, str] = field(default_factory=dict)
    technologies: list[str] = field(default_factory=list)
    has_booking: bool = False
    has_menu: bool = False
    has_cookie_banner: bool = False
    text_length: int = 0
    matched_keywords: list[str] = field(default_factory=list)


@dataclass
class BusinessLead:
    business_name: str
    website: str
    domain: str
    city: str
    search_query: str
    niche: str
    contact_page: str | None
    primary_email: str | None
    primary_phone: str | None
    image_count: int
    analyzed_count: int
    best_image_score: int | None
    average_image_score: float | None
    lead_score: int
    lead_tier: str
    crm_status: str
    reasons: str
    recommendation: str
    outreach_angle: str
    technologies: str
    social_links: str
    matched_keywords: str
    pitch_subject: str
    pitch_body: str
    next_action: str
    maps_name: str | None = None
    maps_rating: float | None = None
    maps_review_count: int | None = None
    maps_image_count: int | None = None
    maps_place_url: str | None = None
    source_type: str = "search"


@dataclass
class LeadSource:
    website: str | None
    source_type: str
    row: dict[str, str] = field(default_factory=dict)


@dataclass
class ScanAttempt:
    source_type: str
    input_name: str
    search_city: str
    search_query: str
    discovered_website: str | None
    discovery_status: str
    detail: str
    lead_score: int | None = None
    lead_tier: str | None = None
    kept_as_lead: bool = False


@dataclass
class ScanReport:
    leads: list[BusinessLead]
    attempts: list[ScanAttempt]


@dataclass
class ScanConfig:
    city: str = DEFAULT_CITY
    query: str = DEFAULT_QUERY
    niche: str = DEFAULT_NICHE
    max_businesses: int = DEFAULT_MAX_BUSINESSES
    max_images: int = DEFAULT_MAX_IMAGES
    service_offer: str = DEFAULT_SERVICE
    min_score: int = 0
    output_csv: str | None = DEFAULT_OUTPUT_CSV
    output_md: str | None = DEFAULT_OUTPUT_MD
    output_db: str | None = DEFAULT_OUTPUT_DB
    input_websites: str | None = None
    websites_arg: str | None = None
    source_csv: str | None = None


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_soup(session: requests.Session, url: str) -> tuple[BeautifulSoup, str]:
    response = session.get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser"), response.url


def get_niche_config(niche: str) -> dict[str, Any]:
    return NICHE_CONFIGS.get(niche.lower(), NICHE_CONFIGS["default"])


def find_businesses(session: requests.Session, city: str, query: str) -> list[str]:
    results: list[str] = []
    for phrase in build_discovery_phrases(city=city, query=query):
        for search_fn in (search_google_phrase, search_bing_phrase, search_duckduckgo_phrase):
            try:
                found = search_fn(session, phrase)
            except requests.RequestException:
                found = []
            results.extend(found)

        deduped = list(dict.fromkeys(results))
        if len(deduped) >= 10:
            return deduped

    return list(dict.fromkeys(results))


def build_discovery_phrases(city: str, query: str) -> list[str]:
    clean_city = clean_text(city)
    clean_query = clean_text(query)

    if not clean_query or clean_query == ALL_BUSINESSES_QUERY:
        broad_phrases = [
            f"virksomheder i {clean_city}",
            f"lokale virksomheder {clean_city}",
            f"businesses in {clean_city}",
            f"firmaer i {clean_city}",
            f"site:.dk {clean_city}",
        ]
        return list(dict.fromkeys(phrase for phrase in broad_phrases if clean_text(phrase)))

    phrases = [
        f"{clean_query} {clean_city} website",
        f"{clean_query} {clean_city}",
        f"{clean_query} i {clean_city}",
        f"bedste {clean_query} {clean_city}",
        f"{clean_query} {clean_city} kontakt",
        f"{clean_query} {clean_city} booking",
    ]

    if clean_city:
        phrases.append(f"{clean_query} naer {clean_city}")
    else:
        phrases.extend(
            [
                f"{clean_query} website",
                f"bedste {clean_query}",
                f"{clean_query} kontakt",
            ]
        )

    return list(dict.fromkeys(phrase for phrase in phrases if clean_text(phrase)))


def search_google(session: requests.Session, city: str, query: str) -> list[str]:
    phrase = f"{query} {city} website"
    return search_google_phrase(session, phrase)


def search_bing(session: requests.Session, city: str, query: str) -> list[str]:
    phrase = f"{query} {city} website"
    return search_bing_phrase(session, phrase)


def extract_google_result_url(href: str) -> str | None:
    if href.startswith("http"):
        return href
    if not href.startswith("/url?"):
        return None

    query_params = parse_qs(urlparse(href).query)
    result_url = query_params.get("q", [None])[0]
    if not result_url or not result_url.startswith("http"):
        return None
    return result_url


def is_blocked_domain(url: str) -> bool:
    blocked_fragments = (
        "google.",
        "youtube.com",
        "facebook.com",
        "instagram.com",
        "tripadvisor.",
        "yelp.",
        "linkedin.com",
        "tiktok.com",
        "wikipedia.org",
    )
    netloc = urlparse(url).netloc.lower()
    return any(fragment in netloc for fragment in blocked_fragments)


def normalize_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    clean_path = parsed.path.rstrip("/") or "/"
    return parsed._replace(query="", fragment="", path=clean_path).geturl()


def load_websites_from_file(filepath: str) -> list[str]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Filen findes ikke: {filepath}")

    websites: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        website = clean_text(line)
        if website and not website.startswith("#"):
            websites.append(normalize_url(website))
    return list(dict.fromkeys(websites))


def parse_websites_arg(raw_value: str) -> list[str]:
    values = [clean_text(part) for part in raw_value.split(",")]
    return list(dict.fromkeys(normalize_url(value) for value in values if value))


def load_csv_rows(filepath: str) -> list[dict[str, str]]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Filen findes ikke: {filepath}")

    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return [
            {clean_text(key).lower(): clean_text(value or "") for key, value in row.items()}
            for row in reader
        ]


def load_csv_rows_from_text(raw_text: str) -> list[dict[str, str]]:
    buffer = io.StringIO(raw_text)
    reader = csv.DictReader(buffer)
    return [
        {clean_text(key).lower(): clean_text(value or "") for key, value in row.items()}
        for row in reader
    ]


def get_csv_value(row: dict[str, str], key: str) -> str:
    for alias in CSV_ALIASES[key]:
        if row.get(alias):
            return row[alias]
    return ""


def prepare_csv_sources(rows: list[dict[str, str]]) -> list[LeadSource]:
    sources: list[LeadSource] = []
    for row in rows:
        website = get_csv_value(row, "website")
        normalized_website = normalize_url(website) if website else None
        if normalized_website:
            row["website"] = normalized_website
        sources.append(LeadSource(website=normalized_website, source_type="csv", row=row))
    return sources


def discover_website_for_source(
    session: requests.Session,
    source: LeadSource,
    fallback_city: str,
    fallback_query: str,
) -> str | None:
    if source.website:
        return source.website

    row = source.row
    name = get_csv_value(row, "name")
    city = get_csv_value(row, "city") or fallback_city
    query = get_csv_value(row, "query") or fallback_query

    social_candidates = extract_candidate_websites_from_social_links(extract_social_links_from_row(row))
    if social_candidates:
        return social_candidates[0]

    if not name:
        return None

    search_phrases = [
        f"{name} {city} official website",
        f"{name} {city}",
        f"{name} {query} {city}",
    ]
    for phrase in search_phrases:
        for search_fn in (search_google_phrase, search_bing_phrase, search_duckduckgo_phrase):
            try:
                results = search_fn(session, phrase)
            except requests.RequestException:
                results = []
            if results:
                return results[0]

    return None


def search_google_phrase(session: requests.Session, phrase: str) -> list[str]:
    search_url = f"https://www.google.com/search?q={quote_plus(phrase)}"
    soup, _ = fetch_soup(session, search_url)
    websites: list[str] = []
    for link in soup.find_all("a"):
        href = link.get("href")
        if not href:
            continue
        parsed_href = extract_google_result_url(href)
        if not parsed_href or is_blocked_domain(parsed_href):
            continue
        websites.append(normalize_url(parsed_href))
    return list(dict.fromkeys(websites))


def search_bing_phrase(session: requests.Session, phrase: str) -> list[str]:
    search_url = f"https://www.bing.com/search?q={quote_plus(phrase)}"
    soup, _ = fetch_soup(session, search_url)
    websites: list[str] = []
    for link in soup.select("li.b_algo h2 a, a"):
        href = link.get("href")
        if not href or not href.startswith("http"):
            continue
        if is_blocked_domain(href):
            continue
        websites.append(normalize_url(href))
    return list(dict.fromkeys(websites))


def search_duckduckgo_phrase(session: requests.Session, phrase: str) -> list[str]:
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(phrase)}"
    soup, _ = fetch_soup(session, search_url)
    websites: list[str] = []
    for link in soup.select("a.result__a, a[href]"):
        href = link.get("href")
        if not href:
            continue
        parsed_href = extract_duckduckgo_result_url(href)
        if not parsed_href or is_blocked_domain(parsed_href):
            continue
        websites.append(normalize_url(parsed_href))
    return list(dict.fromkeys(websites))


def extract_duckduckgo_result_url(href: str) -> str | None:
    if href.startswith("http"):
        return href
    if not href.startswith("//duckduckgo.com/l/?") and not href.startswith("/l/?"):
        return None

    query_params = parse_qs(urlparse(href).query)
    result_url = query_params.get("uddg", [None])[0]
    if not result_url or not result_url.startswith("http"):
        return None
    return result_url


def extract_candidate_websites_from_social_links(social_links: dict[str, str]) -> list[str]:
    candidates: list[str] = []
    blocked_domains = tuple(SOCIAL_DOMAINS.keys())
    for _, social_url in social_links.items():
        parsed = urlparse(social_url)
        if any(domain in parsed.netloc.lower() for domain in blocked_domains):
            continue
        if social_url.startswith("http"):
            candidates.append(normalize_url(social_url))
    return list(dict.fromkeys(candidates))


def extract_images(session: requests.Session, website: str) -> list[str]:
    soup, final_url = fetch_soup(session, website)
    images: list[str] = []

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        img_url = urljoin(final_url, src)
        if img_url.startswith("http"):
            images.append(img_url)
    return list(dict.fromkeys(images))


def analyze_image(session: requests.Session, url: str) -> ImageAnalysis | None:
    try:
        response = session.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            return None

        height, width = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        score = score_image(width=width, height=height, blur_score=blur_score)
        return ImageAnalysis(url=url, width=width, height=height, blur_score=blur_score, score=score)
    except (requests.RequestException, cv2.error):
        return None


def score_image(*, width: int, height: int, blur_score: float) -> int:
    score = 100
    if width < 800:
        score -= 25
    if height < 600:
        score -= 15
    if blur_score < 80:
        score -= 30
    elif blur_score < 150:
        score -= 15
    return max(score, 0)


def extract_site_profile(
    session: requests.Session,
    website: str,
    query: str,
    city: str,
    niche: str,
    source_row: dict[str, str] | None = None,
) -> SiteProfile:
    soup, final_url = fetch_soup(session, website)
    page_text = soup.get_text(" ", strip=True)

    contact_page = discover_contact_page(soup, final_url)
    extra_text = ""
    if contact_page:
        try:
            contact_soup, _ = fetch_soup(session, contact_page)
            extra_text = contact_soup.get_text(" ", strip=True)
        except requests.RequestException:
            extra_text = ""

    combined_text = f"{page_text} {extra_text}".strip()
    text_lower = combined_text.lower()
    title = clean_text(soup.title.string if soup.title and soup.title.string else "")
    meta_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = clean_text(meta_tag.get("content", "") if meta_tag else "")
    business_name = extract_business_name(soup, final_url, title, source_row=source_row)

    emails = unique_list(EMAIL_RE.findall(combined_text) + extract_mailto_links(soup))
    phones = [phone for phone in unique_list(normalize_phone(phone) for phone in PHONE_RE.findall(combined_text)) if phone]
    social_links = merge_social_links(
        extract_social_links(soup, final_url),
        extract_social_links_from_row(source_row or {}),
    )
    technologies = detect_technologies(soup, final_url)
    matched_keywords = extract_matched_keywords(text_lower, query=query, city=city, niche=niche)

    has_booking = any(word in text_lower for word in ("book", "booking", "reserv", "bestil", "order online"))
    has_menu = any(word in text_lower for word in ("menu", "menukort", "wine list", "drinks", "priser"))
    has_cookie_banner = any(word in text_lower for word in ("cookie", "cookies", "gdpr", "privacy"))

    return SiteProfile(
        website=final_url,
        business_name=business_name,
        title=title,
        meta_description=meta_description,
        contact_page=contact_page,
        emails=emails,
        phones=phones,
        social_links=social_links,
        technologies=technologies,
        has_booking=has_booking,
        has_menu=has_menu,
        has_cookie_banner=has_cookie_banner,
        text_length=len(combined_text),
        matched_keywords=matched_keywords,
    )


def extract_business_name(
    soup: BeautifulSoup,
    final_url: str,
    title: str,
    source_row: dict[str, str] | None = None,
) -> str:
    if source_row:
        name = get_csv_value(source_row, "name")
        if name:
            return name

    og_site_name = soup.find("meta", attrs={"property": "og:site_name"})
    if og_site_name and og_site_name.get("content"):
        return clean_text(og_site_name["content"])

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return clean_text(h1.get_text(" ", strip=True))

    if title:
        title_parts = re.split(r"\s+[|\-–]\s+", title)
        if title_parts:
            return clean_text(title_parts[0])

    return urlparse(final_url).netloc.replace("www.", "")


def extract_mailto_links(soup: BeautifulSoup) -> list[str]:
    results: list[str] = []
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if href.lower().startswith("mailto:"):
            email = href.split(":", 1)[1].split("?", 1)[0]
            if email:
                results.append(email)
    return results


def extract_social_links(soup: BeautifulSoup, base_url: str) -> dict[str, str]:
    results: dict[str, str] = {}
    for link in soup.find_all("a", href=True):
        href = urljoin(base_url, link["href"])
        netloc = urlparse(href).netloc.lower()
        for domain, label in SOCIAL_DOMAINS.items():
            if domain in netloc and label not in results:
                results[label] = href
    return results


def extract_social_links_from_row(row: dict[str, str]) -> dict[str, str]:
    results: dict[str, str] = {}
    for platform in ("facebook", "instagram", "linkedin", "tiktok", "youtube"):
        value = get_csv_value(row, platform)
        if value:
            results[platform] = value
    return results


def merge_social_links(*sources: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for source in sources:
        for key, value in source.items():
            if value and key not in merged:
                merged[key] = value
    return merged


def detect_technologies(soup: BeautifulSoup, final_url: str) -> list[str]:
    technologies: list[str] = []
    html = str(soup).lower()
    generator = soup.find("meta", attrs={"name": "generator"})
    if generator and generator.get("content"):
        technologies.append(clean_text(generator["content"]))

    checks = {
        "WordPress": ("wp-content", "wordpress"),
        "Shopify": ("cdn.shopify.com", "shopify"),
        "Wix": ("static.wixstatic.com", "wix"),
        "Squarespace": ("squarespace",),
    }
    for label, needles in checks.items():
        if any(needle in html or needle in final_url.lower() for needle in needles):
            technologies.append(label)
    return unique_list(technologies)


def discover_contact_page(soup: BeautifulSoup, base_url: str) -> str | None:
    for link in soup.find_all("a", href=True):
        href = urljoin(base_url, link["href"])
        anchor_text = clean_text(link.get_text(" ", strip=True)).lower()
        href_lower = href.lower()
        if any(path in href_lower for path in COMMON_CONTACT_PATHS):
            return href
        if any(word in anchor_text for word in ("kontakt", "contact", "about", "om os", "booking")):
            return href
    return None


def extract_matched_keywords(text_lower: str, query: str, city: str, niche: str) -> list[str]:
    query_keywords = [clean_text(part).lower() for part in re.split(r"\W+", query) if part.strip()]
    niche_keywords = get_niche_config(niche).get("keywords", [])
    candidate_keywords = query_keywords + niche_keywords + [city.lower(), "kontakt", "booking", "menu"]
    return [keyword for keyword in candidate_keywords if keyword and keyword in text_lower]


def parse_optional_int(value: str) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def parse_optional_float(value: str) -> float | None:
    if not value:
        return None
    cleaned = value.replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    return float(match.group()) if match else None


def score_business(
    profile: SiteProfile,
    image_count: int,
    analyses: list[ImageAnalysis],
    service_offer: str,
    city: str,
    query: str,
    niche: str,
    source_type: str,
    source_row: dict[str, str] | None = None,
) -> BusinessLead:
    config = get_niche_config(niche)
    reasons: list[str] = []
    score = 50

    if image_count <= 3:
        score += 14
        reasons.append("fa billeder pa websitet")
    elif image_count >= 12:
        score -= 6
        reasons.append("mange billeder pa websitet")

    if not analyses:
        score += 18
        reasons.append("ingen brugbare billeder kunne analyseres")
        best_image_score = None
        average_image_score = None
    else:
        best_image_score = max(item.score for item in analyses)
        average_raw = sum(item.score for item in analyses) / len(analyses)
        average_image_score = round(average_raw, 1)
        if average_raw < 50:
            score += 20
            reasons.append("lav billedkvalitet")
        elif average_raw < 70:
            score += 10
            reasons.append("middel billedkvalitet")
        else:
            score -= 10
            reasons.append("fornuftig billedkvalitet")

    contact_signals = int(bool(profile.emails)) + int(bool(profile.phones)) + int(bool(profile.contact_page))
    if contact_signals == 0:
        score += 16
        reasons.append("svag kontaktstruktur")
    elif contact_signals == 1:
        score += 8
        reasons.append("begranset kontaktinfo")
    else:
        score -= 4

    if not profile.meta_description:
        score += 8
        reasons.append("mangler meta-beskrivelse")
    if profile.text_length < 500:
        score += 8
        reasons.append("meget lidt tekstindhold")

    social_penalty = score_social_presence(profile.social_links, niche=niche)
    score += social_penalty
    if social_penalty > 0:
        reasons.append("svag social tilstedevaerelse")
    elif social_penalty < 0:
        reasons.append("stabil social tilstedevaerelse")

    if config["needs_booking"] and not profile.has_booking:
        score += 8
        reasons.append("mangler tydelig booking")
    elif profile.has_booking:
        score -= 3

    if config["needs_menu"] and not profile.has_menu:
        score += 6
        reasons.append("mangler menu eller prisoversigt")
    elif profile.has_menu:
        score -= 2

    if not profile.has_cookie_banner:
        score += 3
        reasons.append("ingen tydelig privacy eller cookie-info")

    if profile.matched_keywords:
        score += 6
        reasons.append("starkt match med sokriterier")
    else:
        score -= 5
        reasons.append("svagt match med sokriterier")

    maps_name = None
    maps_rating = None
    maps_review_count = None
    maps_image_count = None
    maps_place_url = None
    if source_row:
        maps_name = get_csv_value(source_row, "name") or None
        maps_place_url = get_csv_value(source_row, "maps_url") or None
        maps_image_count = parse_optional_int(get_csv_value(source_row, "image_count"))
        maps_rating = parse_optional_float(get_csv_value(source_row, "rating"))
        maps_review_count = parse_optional_int(get_csv_value(source_row, "review_count"))
        score += score_maps_signals(
            maps_image_count=maps_image_count,
            maps_rating=maps_rating,
            maps_review_count=maps_review_count,
            weight=float(config["maps_weight"]),
            reasons=reasons,
        )

    lead_score = max(0, min(100, round(score)))
    lead_tier = classify_lead_tier(lead_score)
    recommendation = build_recommendation(lead_tier)
    outreach_angle = build_outreach_angle(profile, average_image_score, niche=niche)
    pitch_subject = build_pitch_subject(profile)
    pitch_body = build_pitch_body(profile, outreach_angle, service_offer)
    next_action = build_next_action(lead_tier, profile)

    return BusinessLead(
        business_name=profile.business_name,
        website=profile.website,
        domain=urlparse(profile.website).netloc.replace("www.", ""),
        city=city,
        search_query=query,
        niche=niche,
        contact_page=profile.contact_page,
        primary_email=profile.emails[0] if profile.emails else None,
        primary_phone=profile.phones[0] if profile.phones else None,
        image_count=image_count,
        analyzed_count=len(analyses),
        best_image_score=best_image_score,
        average_image_score=average_image_score,
        lead_score=lead_score,
        lead_tier=lead_tier,
        crm_status=PRIORITY_STATUSES[lead_tier],
        reasons=", ".join(reasons[:8]),
        recommendation=recommendation,
        outreach_angle=outreach_angle,
        technologies=", ".join(profile.technologies),
        social_links=", ".join(f"{k}:{v}" for k, v in profile.social_links.items()),
        matched_keywords=", ".join(profile.matched_keywords),
        pitch_subject=pitch_subject,
        pitch_body=pitch_body,
        next_action=next_action,
        maps_name=maps_name,
        maps_rating=maps_rating,
        maps_review_count=maps_review_count,
        maps_image_count=maps_image_count,
        maps_place_url=maps_place_url,
        source_type=source_type,
    )


def score_social_presence(social_links: dict[str, str], niche: str) -> int:
    expected = get_niche_config(niche)["expected_socials"]
    present_count = len(social_links)
    expected_missing = len([platform for platform in expected if platform not in social_links])
    score_delta = 0
    if expected_missing:
        score_delta += expected_missing * 4
    if present_count >= 3:
        score_delta -= 6
    elif present_count == 2:
        score_delta -= 3
    elif present_count == 0:
        score_delta += 6
    return score_delta


def score_maps_signals(
    maps_image_count: int | None,
    maps_rating: float | None,
    maps_review_count: int | None,
    weight: float,
    reasons: list[str],
) -> int:
    score = 0
    if maps_image_count is not None:
        if maps_image_count == 0:
            score += round(20 * weight)
            reasons.append("ingen billeder pa maps")
        elif maps_image_count <= 3:
            score += round(12 * weight)
            reasons.append("fa billeder pa maps")
        elif maps_image_count >= 15:
            score -= round(5 * weight)
            reasons.append("mange billeder pa maps")

    if maps_rating is not None and maps_review_count is not None:
        if maps_rating >= 4.2 and maps_review_count >= 20 and (maps_image_count is None or maps_image_count <= 3):
            score += round(10 * weight)
            reasons.append("staerk maps-profil men svag billeddaekning")
        elif maps_rating < 3.8 and maps_review_count >= 20:
            score -= round(4 * weight)
    return score


def classify_lead_tier(score: int) -> str:
    if score >= 75:
        return "A"
    if score >= 55:
        return "B"
    return "C"


def build_recommendation(lead_tier: str) -> str:
    if lead_tier == "A":
        return "Kontakt hurtigt med et konkret forbedringsforslag"
    if lead_tier == "B":
        return "Relevant lead, men kraever mere manuel vurdering"
    return "Lav prioritet lige nu"


def build_outreach_angle(profile: SiteProfile, average_image_score: float | None, niche: str) -> str:
    angles: list[str] = []
    if average_image_score is None or average_image_score < 60:
        angles.append("forbedre billeder og visuel praesentation")
    if not profile.contact_page or not profile.emails:
        angles.append("forenkle kontakt og lead-konvertering")
    if not profile.meta_description or profile.text_length < 500:
        angles.append("styrke seo og lokal synlighed")
    if get_niche_config(niche)["needs_booking"] and not profile.has_booking:
        angles.append("indfoere tydelig booking eller bestillingsflow")
    if not profile.social_links:
        angles.append("loefte social proof og platform-tilstedevaerelse")
    return "; ".join(angles[:3]) if angles else "vis manuel gennemgang og find en mere specifik vinkel"


def build_pitch_subject(profile: SiteProfile) -> str:
    return f"Ide til at skaffe flere kunder via {profile.business_name}s hjemmeside"


def build_pitch_body(profile: SiteProfile, outreach_angle: str, service_offer: str) -> str:
    return (
        f"Hej {profile.business_name},\n\n"
        f"Jeg kiggede kort pa jeres online tilstedevaerelse og lagde maerke til nogle muligheder for at {outreach_angle}. "
        f"Jeg arbejder med {service_offer}, og jeg tror, der er et par hurtige forbedringer, som kan styrke "
        f"baade det visuelle indtryk og hvor nemt det er for nye kunder at tage kontakt.\n\n"
        "Hvis det har interesse, kan jeg sende 3 konkrete forslag til forbedringer pa jeres nuvaerende setup.\n\n"
        "Bedste hilsner\n"
        "[Dit navn]"
    )


def build_next_action(lead_tier: str, profile: SiteProfile) -> str:
    if lead_tier == "A" and profile.emails:
        return "Send personlig email med 3 konkrete forbedringer"
    if lead_tier == "A" and profile.phones:
        return "Ring og folg op med kort email bagefter"
    if lead_tier == "B":
        return "Lav manuel gennemgang og prioriter efter branche-fit"
    return "Gem i pipeline og genbesog senere"


def analyze_business(
    session: requests.Session,
    source: LeadSource,
    max_images: int,
    service_offer: str,
    city: str,
    query: str,
    niche: str,
) -> tuple[BusinessLead, list[ImageAnalysis]]:
    profile = extract_site_profile(
        session,
        source.website,
        query=query,
        city=city,
        niche=niche,
        source_row=source.row,
    )
    images = extract_images(session, profile.website)
    analyses: list[ImageAnalysis] = []
    for img_url in images[:max_images]:
        analysis = analyze_image(session, img_url)
        if analysis:
            analyses.append(analysis)

    lead = score_business(
        profile=profile,
        image_count=len(images),
        analyses=analyses,
        service_offer=service_offer,
        city=city,
        query=query,
        niche=niche,
        source_type=source.source_type,
        source_row=source.row,
    )
    return lead, analyses


def collect_sources(config: ScanConfig, session: requests.Session) -> list[LeadSource]:
    if config.source_csv:
        return prepare_csv_sources(load_csv_rows(config.source_csv))
    if config.websites_arg:
        return [LeadSource(website=url, source_type="manual") for url in parse_websites_arg(config.websites_arg)]
    if config.input_websites:
        return [LeadSource(website=url, source_type="manual") for url in load_websites_from_file(config.input_websites)]

    found = find_businesses(session, city=config.city, query=config.query)
    return [LeadSource(website=url, source_type="search") for url in found]


def run_scan_report(config: ScanConfig) -> ScanReport:
    session = build_session()
    try:
        sources = collect_sources(config, session)
    except (FileNotFoundError, requests.RequestException) as exc:
        print(str(exc))
        return ScanReport(leads=[], attempts=[])

    if not sources:
        print("Ingen virksomheder blev fundet. Proev --source-csv, --websites eller --input-websites.")
        return ScanReport(leads=[], attempts=[])

    leads: list[BusinessLead] = []
    attempts: list[ScanAttempt] = []
    scanned = 0
    for source in sources:
        if scanned >= config.max_businesses:
            break

        input_name = get_csv_value(source.row, "name") or source.website or "ukendt"
        search_city = get_csv_value(source.row, "city") or config.city
        search_query = get_csv_value(source.row, "query") or config.query
        resolved_website = discover_website_for_source(
            session,
            source,
            fallback_city=config.city,
            fallback_query=config.query,
        )
        if not resolved_website:
            print(f"\nSpringer over kilde uden website: {get_csv_value(source.row, 'name') or source.row or 'ukendt'}")
            attempts.append(
                ScanAttempt(
                    source_type=source.source_type,
                    input_name=input_name,
                    search_city=search_city,
                    search_query=search_query,
                    discovered_website=None,
                    discovery_status="ikke-fundet",
                    detail="Kunne ikke finde et brugbart website for kandidaten",
                )
            )
            continue

        source.website = resolved_website
        scanned += 1
        print(f"\nScanner: {source.website}")
        try:
            lead, analyses = analyze_business(
                session=session,
                source=source,
                max_images=config.max_images,
                service_offer=config.service_offer,
                city=get_csv_value(source.row, "city") or config.city,
                query=get_csv_value(source.row, "query") or config.query,
                niche=config.niche,
            )
        except requests.RequestException as exc:
            print(f"  Springer over side pa grund af fejl: {exc}")
            attempts.append(
                ScanAttempt(
                    source_type=source.source_type,
                    input_name=input_name,
                    search_city=search_city,
                    search_query=search_query,
                    discovered_website=resolved_website,
                    discovery_status="fundet-men-fejl",
                    detail=str(exc),
                )
            )
            continue

        kept = lead.lead_score >= config.min_score
        if lead.lead_score >= config.min_score:
            leads.append(lead)
        attempts.append(
            ScanAttempt(
                source_type=source.source_type,
                input_name=input_name,
                search_city=search_city,
                search_query=search_query,
                discovered_website=resolved_website,
                discovery_status="fundet",
                detail="Scannet succesfuldt",
                lead_score=lead.lead_score,
                lead_tier=lead.lead_tier,
                kept_as_lead=kept,
            )
        )
        for analysis in analyses:
            print(
                f"  Billede: {analysis.url} | "
                f"{analysis.width}x{analysis.height} | "
                f"blur={analysis.blur_score:.1f} | "
                f"score={analysis.score}"
            )

    leads = sorted(leads, key=lambda item: item.lead_score, reverse=True)
    print_summary(leads)
    persist_outputs(leads, config)
    return ScanReport(leads=leads, attempts=attempts)


def run_scan(config: ScanConfig) -> list[BusinessLead]:
    return run_scan_report(config).leads


def preview_discovery(config: ScanConfig) -> list[ScanAttempt]:
    session = build_session()
    try:
        sources = collect_sources(config, session)
    except (FileNotFoundError, requests.RequestException) as exc:
        print(str(exc))
        return []

    if not sources:
        return []

    attempts: list[ScanAttempt] = []
    scanned = 0
    for source in sources:
        if scanned >= config.max_businesses:
            break

        input_name = get_csv_value(source.row, "name") or source.website or "ukendt"
        search_city = get_csv_value(source.row, "city") or config.city
        search_query = get_csv_value(source.row, "query") or config.query
        resolved_website = discover_website_for_source(
            session,
            source,
            fallback_city=config.city,
            fallback_query=config.query,
        )

        if resolved_website:
            scanned += 1
            attempts.append(
                ScanAttempt(
                    source_type=source.source_type,
                    input_name=input_name,
                    search_city=search_city,
                    search_query=search_query,
                    discovered_website=resolved_website,
                    discovery_status="fundet",
                    detail="Klar til scoring",
                )
            )
        else:
            attempts.append(
                ScanAttempt(
                    source_type=source.source_type,
                    input_name=input_name,
                    search_city=search_city,
                    search_query=search_query,
                    discovered_website=None,
                    discovery_status="ikke-fundet",
                    detail="Ingen brugbar hjemmeside fundet endnu",
                )
            )

    return attempts


def persist_outputs(leads: list[BusinessLead], config: ScanConfig) -> None:
    if not leads:
        return
    if config.output_csv:
        save_results_to_csv(leads, config.output_csv)
        print(f"\nCSV gemt i: {config.output_csv}")
    if config.output_md:
        save_results_to_markdown(leads, config.output_md, config=config)
        print(f"Markdown rapport gemt i: {config.output_md}")
    if config.output_db:
        save_results_to_sqlite(leads, config.output_db)
        print(f"SQLite database gemt i: {config.output_db}")


def save_results_to_csv(leads: list[BusinessLead], filepath: str) -> None:
    fieldnames = list(asdict(leads[0]).keys())
    with open(filepath, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for lead in leads:
            writer.writerow(asdict(lead))


def save_results_to_markdown(leads: list[BusinessLead], filepath: str, config: ScanConfig) -> None:
    lines = [
        "# Lead Report",
        "",
        f"- City: {config.city}",
        f"- Query: {config.query}",
        f"- Niche: {config.niche}",
        f"- Service offer: {config.service_offer}",
        f"- Leads found: {len(leads)}",
        "",
    ]
    for index, lead in enumerate(leads, start=1):
        lines.extend(
            [
                f"## {index}. {lead.business_name}",
                "",
                f"- Website: {lead.website}",
                f"- Domain: {lead.domain}",
                f"- Lead tier: {lead.lead_tier}",
                f"- Lead score: {lead.lead_score}/100",
                f"- CRM status: {lead.crm_status}",
                f"- Source type: {lead.source_type}",
                f"- Email: {lead.primary_email or '-'}",
                f"- Phone: {lead.primary_phone or '-'}",
                f"- Maps rating: {lead.maps_rating if lead.maps_rating is not None else '-'}",
                f"- Maps reviews: {lead.maps_review_count if lead.maps_review_count is not None else '-'}",
                f"- Maps images: {lead.maps_image_count if lead.maps_image_count is not None else '-'}",
                f"- Contact page: {lead.contact_page or '-'}",
                f"- Socials: {lead.social_links or '-'}",
                f"- Matched keywords: {lead.matched_keywords or '-'}",
                f"- Outreach angle: {lead.outreach_angle}",
                f"- Reasons: {lead.reasons}",
                f"- Recommendation: {lead.recommendation}",
                f"- Next action: {lead.next_action}",
                "",
                "### Outreach Draft",
                "",
                f"**Subject:** {lead.pitch_subject}",
                "",
                "```text",
                lead.pitch_body,
                "```",
                "",
            ]
        )
    Path(filepath).write_text("\n".join(lines), encoding="utf-8")


def save_results_to_sqlite(leads: list[BusinessLead], filepath: str) -> None:
    conn = sqlite3.connect(filepath)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                domain TEXT PRIMARY KEY,
                business_name TEXT NOT NULL,
                website TEXT NOT NULL,
                city TEXT,
                search_query TEXT,
                niche TEXT,
                contact_page TEXT,
                primary_email TEXT,
                primary_phone TEXT,
                image_count INTEGER,
                analyzed_count INTEGER,
                best_image_score INTEGER,
                average_image_score REAL,
                lead_score INTEGER,
                lead_tier TEXT,
                crm_status TEXT,
                reasons TEXT,
                recommendation TEXT,
                outreach_angle TEXT,
                technologies TEXT,
                social_links TEXT,
                matched_keywords TEXT,
                pitch_subject TEXT,
                pitch_body TEXT,
                next_action TEXT,
                maps_name TEXT,
                maps_rating REAL,
                maps_review_count INTEGER,
                maps_image_count INTEGER,
                maps_place_url TEXT,
                source_type TEXT
            )
            """
        )
        for lead in leads:
            row = asdict(lead)
            fields = ", ".join(row.keys())
            placeholders = ", ".join(f":{key}" for key in row.keys())
            updates = ", ".join(f"{key}=excluded.{key}" for key in row.keys() if key != "domain")
            conn.execute(
                f"""
                INSERT INTO leads ({fields})
                VALUES ({placeholders})
                ON CONFLICT(domain) DO UPDATE SET {updates}
                """,
                row,
            )
        conn.commit()
    finally:
        conn.close()


def print_summary(leads: list[BusinessLead]) -> None:
    if not leads:
        print("Ingen virksomheder blev fundet.")
        return
    print("\n=== PROFESSIONEL LEADLISTE ===")
    for index, lead in enumerate(leads, start=1):
        print(f"\n{index}. {lead.business_name} ({lead.website})")
        print(f"   Tier: {lead.lead_tier} | Lead score: {lead.lead_score}/100 | CRM: {lead.crm_status}")
        print(f"   Email: {lead.primary_email or '-'} | Telefon: {lead.primary_phone or '-'}")
        print(f"   Kontakt-side: {lead.contact_page or '-'}")
        print(f"   Socials: {lead.social_links or '-'}")
        print(f"   Maps billeder: {lead.maps_image_count if lead.maps_image_count is not None else '-'}")
        print(f"   Signal: {lead.reasons}")
        print(f"   Naeste handling: {lead.next_action}")


def clean_text(value: str) -> str:
    return " ".join(str(value).split()).strip()


def normalize_phone(phone: str) -> str | None:
    compact = re.sub(r"[^\d+]", "", phone)
    digit_count = len(re.sub(r"\D", "", compact))
    if digit_count < 8:
        return None
    return compact


def unique_list(values: Any) -> list[str]:
    cleaned = [value for value in values if value]
    return list(dict.fromkeys(cleaned))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find potentielle kunder og score deres online tilstedevaerelse som salgslead."
    )
    parser.add_argument("--city", default=DEFAULT_CITY)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--niche", default=DEFAULT_NICHE, choices=sorted(NICHE_CONFIGS.keys()))
    parser.add_argument("--max-businesses", type=int, default=DEFAULT_MAX_BUSINESSES)
    parser.add_argument("--max-images", type=int, default=DEFAULT_MAX_IMAGES)
    parser.add_argument("--service-offer", default=DEFAULT_SERVICE)
    parser.add_argument("--min-score", type=int, default=0)
    parser.add_argument("--websites")
    parser.add_argument("--input-websites")
    parser.add_argument("--source-csv", help="CSV med virksomheder, Maps-felter og sociale links")
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-md", default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--output-db", default=DEFAULT_OUTPUT_DB)
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> ScanConfig:
    return ScanConfig(
        city=args.city,
        query=args.query,
        niche=args.niche,
        max_businesses=args.max_businesses,
        max_images=args.max_images,
        service_offer=args.service_offer,
        min_score=args.min_score,
        websites_arg=args.websites,
        input_websites=args.input_websites,
        source_csv=args.source_csv,
        output_csv=args.output_csv,
        output_md=args.output_md,
        output_db=args.output_db,
    )


if __name__ == "__main__":
    run_scan(config_from_args(parse_args()))
