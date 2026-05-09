import requests
import time
import random
from bs4 import BeautifulSoup
from requests.exceptions import (
    ConnectionError,
    Timeout,
    TooManyRedirects,
    RequestException
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

PARKING_KEYWORDS = [
    "domain for sale",
    "buy this domain",
    "this domain is for sale",
    "parked free",
    "domain parking",
]

SPAMMY_TLDS = {
    "tk", "ml", "ga", "cf",
    "xyz", "top", "click",        
    "loan", "win", "download", 
    "icu", "rest", "buzz",   
}

def extract_tld(domain):
    if not domain:
        return ""
    parts = domain.lower().rsplit(".",1)
    if len(parts) == 2:
        return parts[1]
    return ""
    
def _empty_result(error_code, domain=None):
    tld = extract_tld(domain) if domain else ""
    return {
        "http_status": None,
        "final_url": None,
        "response_time_ms": None,
        "html_size": None,
        "title": None,
        "is_parked": False,
        "tld": tld,
        "spammy_tld": tld in SPAMMY_TLDS,
        "error": error_code
    }

def extract_title(html):
    try:
        soup = BeautifulSoup(html, 'lxml')
        title_tag = soup.find('title')
        if title_tag and title_tag.text:
            return title_tag.text.strip()[:200]
        return None
    except Exception:
        return None

def detect_parking(html):
    if not html:
        return False
    html_lower = html.lower()
    return any(keyword in html_lower for keyword
    in PARKING_KEYWORDS)

def check_domain(domain, max_attempts=3):
    url = f'https://{domain}'
    last_error = None

    for attempt in range(max_attempts):
        try:
            start = time.time()
            response = requests.get(
                url, 
                timeout=10, 
                allow_redirects=True, 
                headers=HEADERS
         )
            elapsed_ms = round((time.time() - start) * 1000)
            html = response.text

            return {
                "http_status": response.status_code,
                "final_url": response.url,
                "response_time_ms": elapsed_ms,
                "html_size": len(html),
                "title": extract_title(html),
                "is_parked": detect_parking(html),
                "tld": extract_tld(domain),
                "spammy_tld": extract_tld(domain) in SPAMMY_TLDS,
                "error": None
            }
    
        except (Timeout, ConnectionError) as e:
            last_error = type(e).__name__.lower()
            if attempt < max_attempts - 1:
                sleep_time = (2 ** attempt) + random.uniform(0, 0.5)
                time.sleep(sleep_time)
            continue

        except TooManyRedirects:
            return _empty_result("too_many_redirects", domain)
        except RequestException as e:
            return _empty_result(f'request_error:{type(e).__name__}', domain)
        except Exception as e:
            return _empty_result(f'unknown: {type(e).__name__}', domain)
        
    return _empty_result(last_error or "unknown", domain)