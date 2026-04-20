import argparse
import csv
import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

import cv2
import numpy as np
import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 10
MAX_BUSINESSES = 10
MAX_IMAGES_PER_SITE = 5

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
    social_links: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    has_booking: bool = False
    has_menu: bool = False
    has_cookie_banner: bool = False
    text_length: int = 0


@dataclass
class BusinessLead:
    website: str
    business_name: str
    contact_page: str | None
    primary_email: str | None
    primary_phone: str | None
    image_count: int
    analyzed_count: int
    best_image_score: int | None
    average_image_score: float | None
    lead_score: int
    lead_tier: str
    reasons: str
    recommendation: str
    outreach_angle: str
    technologies: str
    social_links: str


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_soup(session: requests.Session, url: str) -> tuple[BeautifulSoup, str]:
    response = session.get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser"), response.url


def find_businesses(session: requests.Session, city: str, query: str) -> list[str]:
    search_term = quote_plus(f"{query} {city} website")
    search_url = f"https://www.google.com/search?q={search_term}"
    soup, _ = fetch_soup(session, search_url)

    websites: list[str] = []
    for link in soup.find_all("a"):
        href = link.get("href")
        if not href:
            continue

        parsed_href = extract_google_result_url(href)
        if not parsed_href:
            continue

        if is_blocked_domain(parsed_href):
            continue

        websites.append(normalize_url(parsed_href))

    return list(dict.fromkeys(websites))


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
    parsed = urlparse(url)
    clean_path = parsed.path.rstrip("/") or "/"
    return parsed._replace(query="", fragment="", path=clean_path).geturl()


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

        return ImageAnalysis(
            url=url,
            width=width,
            height=height,
            blur_score=blur_score,
            score=score,
        )
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


def extract_site_profile(session: requests.Session, website: str) -> SiteProfile:
    soup, final_url = fetch_soup(session, website)
    page_text = soup.get_text(" ", strip=True)

    title = clean_text(soup.title.string if soup.title and soup.title.string else "")
    meta_description_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = clean_text(meta_description_tag.get("content", "") if meta_description_tag else "")

    business_name = extract_business_name(soup, final_url, title)
    emails = unique_list(EMAIL_RE.findall(page_text) + extract_mailto_links(soup))
    phones = unique_list(normalize_phone(phone) for phone in PHONE_RE.findall(page_text))
    phones = [phone for phone in phones if phone]

    social_links = unique_list(extract_social_links(soup, final_url))
    technologies = detect_technologies(soup, final_url)
    contact_page = discover_contact_page(soup, final_url)

    text_lower = page_text.lower()
    has_booking = any(word in text_lower for word in ("book", "booking", "reserv", "bestil", "order online"))
    has_menu = any(word in text_lower for word in ("menu", "menukort", "wine list", "drinks"))
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
        text_length=len(page_text),
    )


def extract_business_name(soup: BeautifulSoup, final_url: str, title: str) -> str:
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


def extract_social_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    results: list[str] = []
    for link in soup.find_all("a", href=True):
        href = urljoin(base_url, link["href"])
        netloc = urlparse(href).netloc.lower()
        for domain in SOCIAL_DOMAINS:
            if domain in netloc:
                results.append(href)
                break
    return results


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


def score_business(profile: SiteProfile, image_count: int, analyses: Iterable[ImageAnalysis]) -> BusinessLead:
    analysis_list = list(analyses)
    reasons: list[str] = []
    score = 50

    if image_count <= 3:
        score += 14
        reasons.append("fa billeder pa forsiden")
    elif image_count >= 12:
        score -= 6
        reasons.append("mange billeder tilgaengelige")

    if not analysis_list:
        score += 18
        reasons.append("ingen brugbare billeder kunne analyseres")
        best_image_score = None
        average_image_score = None
    else:
        best_image_score = max(item.score for item in analysis_list)
        average_raw = sum(item.score for item in analysis_list) / len(analysis_list)
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

    if not profile.emails:
        score += 8
        reasons.append("ingen tydelig email")
    else:
        score -= 4

    if not profile.phones:
        score += 6
        reasons.append("ingen tydelig telefon")
    else:
        score -= 2

    if not profile.contact_page:
        score += 8
        reasons.append("ingen tydelig kontakt-side")

    if not profile.meta_description:
        score += 8
        reasons.append("mangler meta-beskrivelse")

    if profile.text_length < 500:
        score += 8
        reasons.append("meget lidt tekstindhold")

    if not profile.social_links:
        score += 6
        reasons.append("ingen synlige sociale links")
    else:
        score -= 3

    if not profile.has_booking:
        score += 5
        reasons.append("ingen booking eller bestilling fundet")

    if not profile.has_menu:
        score += 3
        reasons.append("ingen menu eller produktoversigt fundet")

    if not profile.has_cookie_banner:
        score += 4
        reasons.append("ingen tydelig cookie eller privacy-info")

    lead_score = max(0, min(100, round(score)))
    lead_tier = classify_lead_tier(lead_score)
    recommendation = build_recommendation(lead_tier)
    outreach_angle = build_outreach_angle(profile, average_image_score)

    return BusinessLead(
        website=profile.website,
        business_name=profile.business_name,
        contact_page=profile.contact_page,
        primary_email=profile.emails[0] if profile.emails else None,
        primary_phone=profile.phones[0] if profile.phones else None,
        image_count=image_count,
        analyzed_count=len(analysis_list),
        best_image_score=best_image_score,
        average_image_score=average_image_score,
        lead_score=lead_score,
        lead_tier=lead_tier,
        reasons=", ".join(reasons[:6]),
        recommendation=recommendation,
        outreach_angle=outreach_angle,
        technologies=", ".join(profile.technologies),
        social_links=", ".join(profile.social_links[:3]),
    )


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


def build_outreach_angle(profile: SiteProfile, average_image_score: float | None) -> str:
    angles: list[str] = []

    if average_image_score is None or average_image_score < 60:
        angles.append("forbedre billeder og visuel praesentation")
    if not profile.contact_page or not profile.emails:
        angles.append("forenkle kontakt og lead-konvertering")
    if not profile.meta_description or profile.text_length < 500:
        angles.append("styrke seo og lokal synlighed")
    if not profile.has_booking:
        angles.append("indfoere tydelig booking eller bestillingsflow")

    if not angles:
        return "Vis manuel gennemgang og find en mere specifik vinkel"

    return "; ".join(angles[:3])


def analyze_business(session: requests.Session, website: str, max_images: int) -> tuple[BusinessLead, list[ImageAnalysis]]:
    profile = extract_site_profile(session, website)
    images = extract_images(session, profile.website)
    analyses: list[ImageAnalysis] = []

    for img_url in images[:max_images]:
        analysis = analyze_image(session, img_url)
        if analysis:
            analyses.append(analysis)

    lead = score_business(profile, len(images), analyses)
    return lead, analyses


def save_results_to_csv(leads: list[BusinessLead], filepath: str) -> None:
    fieldnames = [
        "business_name",
        "website",
        "contact_page",
        "primary_email",
        "primary_phone",
        "image_count",
        "analyzed_count",
        "best_image_score",
        "average_image_score",
        "lead_score",
        "lead_tier",
        "reasons",
        "recommendation",
        "outreach_angle",
        "technologies",
        "social_links",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for lead in leads:
            writer.writerow(
                {
                    "business_name": lead.business_name,
                    "website": lead.website,
                    "contact_page": lead.contact_page,
                    "primary_email": lead.primary_email,
                    "primary_phone": lead.primary_phone,
                    "image_count": lead.image_count,
                    "analyzed_count": lead.analyzed_count,
                    "best_image_score": lead.best_image_score,
                    "average_image_score": lead.average_image_score,
                    "lead_score": lead.lead_score,
                    "lead_tier": lead.lead_tier,
                    "reasons": lead.reasons,
                    "recommendation": lead.recommendation,
                    "outreach_angle": lead.outreach_angle,
                    "technologies": lead.technologies,
                    "social_links": lead.social_links,
                }
            )


def print_summary(leads: list[BusinessLead]) -> None:
    if not leads:
        print("Ingen virksomheder blev fundet.")
        return

    print("\n=== PROFESSIONEL LEADLISTE ===")
    for index, lead in enumerate(sorted(leads, key=lambda item: item.lead_score, reverse=True), start=1):
        print(f"\n{index}. {lead.business_name} ({lead.website})")
        print(f"   Tier: {lead.lead_tier} | Lead score: {lead.lead_score}/100")
        print(f"   Email: {lead.primary_email or '-'} | Telefon: {lead.primary_phone or '-'}")
        print(f"   Kontakt-side: {lead.contact_page or '-'}")
        print(f"   Billeder: {lead.image_count} fundet, {lead.analyzed_count} analyseret")
        print(f"   Gennemsnitlig billede-score: {lead.average_image_score}")
        print(f"   Signal: {lead.reasons}")
        print(f"   Naeste pitch: {lead.outreach_angle}")
        print(f"   Anbefaling: {lead.recommendation}")


def run_ai_lead_engine(city: str, query: str, max_businesses: int, max_images: int, output_csv: str | None) -> None:
    session = build_session()

    try:
        businesses = find_businesses(session, city=city, query=query)
    except requests.RequestException as exc:
        print(f"Kunne ikke hente virksomheder: {exc}")
        return

    if not businesses:
        print("Ingen virksomheder blev fundet i sogningen.")
        return

    leads: list[BusinessLead] = []
    for website in businesses[:max_businesses]:
        print(f"\nScanner: {website}")
        try:
            business_lead, analyses = analyze_business(session, website, max_images=max_images)
        except requests.RequestException as exc:
            print(f"  Springer over side pa grund af fejl: {exc}")
            continue

        leads.append(business_lead)
        for analysis in analyses:
            print(
                f"  Billede: {analysis.url} | "
                f"{analysis.width}x{analysis.height} | "
                f"blur={analysis.blur_score:.1f} | "
                f"score={analysis.score}"
            )

    print_summary(leads)

    if output_csv and leads:
        save_results_to_csv(leads, output_csv)
        print(f"\nCSV gemt i: {output_csv}")


def clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


def normalize_phone(phone: str) -> str | None:
    compact = re.sub(r"[^\d+]", "", phone)
    digit_count = len(re.sub(r"\D", "", compact))
    if digit_count < 8:
        return None
    return compact


def unique_list(values: Iterable[str]) -> list[str]:
    cleaned = [value for value in values if value]
    return list(dict.fromkeys(cleaned))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find potentielle kunder og score deres hjemmeside som salgslead."
    )
    parser.add_argument("--city", default="Esbjerg", help="By der skal soges i")
    parser.add_argument("--query", default="restaurant", help="Type virksomhed, fx restaurant eller frisor")
    parser.add_argument("--max-businesses", type=int, default=MAX_BUSINESSES, help="Maks antal websites at scanne")
    parser.add_argument("--max-images", type=int, default=MAX_IMAGES_PER_SITE, help="Maks antal billeder per website")
    parser.add_argument("--output-csv", default="lead_results.csv", help="CSV-fil til resultater")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_ai_lead_engine(
        city=args.city,
        query=args.query,
        max_businesses=args.max_businesses,
        max_images=args.max_images,
        output_csv=args.output_csv,
    )
