"""Simple URL fetcher to support paste-OR-URL input for job postings."""
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Sites that block scrapers heavily; we'll suggest user paste manually
HARD_SITES = {"linkedin.com", "indeed.com", "glassdoor.com"}


def is_hard_site(url: str) -> bool:
    host = urlparse(url).netloc.lower().replace("www.", "")
    return any(host == d or host.endswith("." + d) for d in HARD_SITES)


def fetch_job_text(url: str, timeout: float = 12.0) -> str:
    """Fetch a URL and extract reasonably clean text content. Raises on failure."""
    if is_hard_site(url):
        raise RuntimeError(
            f"This site ({urlparse(url).netloc}) blocks automated fetching. "
            "Open the listing in your browser and paste the job description text instead."
        )

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Strip boilerplate tags
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    # Prefer <main> or <article> if present, else use body text
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text(separator="\n")

    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())

    if len(text) < 200:
        raise RuntimeError("Couldn't extract useful text from this URL. Paste the job description manually.")

    return text[:20000]
