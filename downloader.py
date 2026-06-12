"""
downloader.py  —  FG Downloader backend
Handles: FitGirl page scraping, link resolution, sequential file downloading.
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    )
}

# ─────────────────────────────────────────────────────────────────────────────
# Scraping & Searching
# ─────────────────────────────────────────────────────────────────────────────

def search_game(query: str):
    """
    Search FitGirl repacks.
    Returns: list of dicts: [{"title": "...", "url": "..."}, ...]
    """
    search_url = f"https://fitgirl-repacks.site/?s={query.replace(' ', '+')}"
    res = requests.get(search_url, headers=HEADERS, timeout=20)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, 'html.parser')
    results = []
    
    for article in soup.find_all('article'):
        title_tag = article.find('h1', class_='entry-title')
        if title_tag and title_tag.find('a'):
            a_tag = title_tag.find('a')
            results.append({"title": a_tag.text.strip(), "url": a_tag['href']})
            
    return results

def fetch_links(url: str):
    """
    Fetch a FitGirl Repacks page and extract mirror links and thumbnail.
    Returns: (game_title, safe_title, thumb_url, providers)
    providers is a dict: {"FuckingFast": [...links...], "DataNodes": [...links...]}
    """
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')

    title_tag = soup.find('h1', class_='entry-title')
    game_title = title_tag.text.strip() if title_tag else "FitGirl_Repack"
    safe_title = re.sub(r'[\\/*?:"<>|]', "", game_title).strip()

    providers = {"FuckingFast": [], "DataNodes": []}
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        is_ff = href.startswith('https://fuckingfast.co/')
        is_dn = 'datanodes' in href.lower()
        
        if not (is_ff or is_dn): continue
        
        filename = ""
        if '#' in href:
            filename = unquote(href.split('#')[1])
        else:
            filename = a.text.strip()

        if not filename or filename.lower() in ('fuckingfast', 'datanodes', ''):
            continue

        if is_ff:
            providers["FuckingFast"].append({"url": href, "filename": filename})
        elif is_dn:
            providers["DataNodes"].append({"url": href, "filename": filename})

    for prov in providers:
        seen = set()
        unique = []
        for lnk in providers[prov]:
            if lnk['url'] not in seen:
                seen.add(lnk['url'])
                unique.append(lnk)
        providers[prov] = unique

    return game_title, safe_title, providers

def group_files(links: list):
    base_files = []
    optional_files = []
    selective_files = []
    for lnk in links:
        fname = lnk['filename'].lower()
        if 'selective' in fname:
            selective_files.append(lnk)
        elif 'optional' in fname:
            optional_files.append(lnk)
        else:
            base_files.append(lnk)
    return base_files, optional_files, selective_files

# ─────────────────────────────────────────────────────────────────────────────
# Link Resolution
# ─────────────────────────────────────────────────────────────────────────────

def resolve_direct_link(url: str, provider: str) -> str:
    """
    Visit a filehoster page and extract the direct CDN download URL.
    """
    if provider == "FuckingFast":
        res = requests.get(url, headers=HEADERS, timeout=20)
        res.raise_for_status()

        match = re.search(r'window\.open\("([^"]+)"\)', res.text)
        if not match:
            raise ValueError(f"Direct link not found on: {url}")
        direct_link = match.group(1)
        try:
            ff_id = urlparse(url).path.rstrip('/').split('/')[-1]
            requests.post(f"https://fuckingfast.co/f/{ff_id}/dl", headers=HEADERS, timeout=8)
        except: pass
        return direct_link

    elif provider == "DataNodes":
        s = requests.Session()
        s.headers.update(HEADERS)
        res = s.get(url, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        form = soup.find('form')
        if not form: raise ValueError("DataNodes form not found (Cloudflare?)")
        
        data = {}
        for inp in form.find_all('input'):
            if inp.get('name'):
                data[inp.get('name')] = inp.get('value', '')
        
        # Give some time for 'timer' if it exists
        time.sleep(1.5)
        res2 = s.post(url, data=data, timeout=20)
        soup2 = BeautifulSoup(res2.text, 'html.parser')
        dl_btn = soup2.find('a', id='downloadbtn') or soup2.find('a', class_='btn-download')
        
        if dl_btn and dl_btn.get('href'):
            return dl_btn['href']
        
        # If it uses an anchor with regex
        match = re.search(r'href="(https://[^"]+datanodes[^"]+)"', res2.text)
        if match: return match.group(1)
            
        raise ValueError("Could not extract DataNodes direct link.")

    raise ValueError(f"Unknown provider: {provider}")

# ─────────────────────────────────────────────────────────────────────────────
# Downloading
# ─────────────────────────────────────────────────────────────────────────────

def download_file(
    url: str,
    provider: str,
    output_path: str,
    progress_cb=None,
    cancel_check=None,
    pause_event=None
):
    """
    Resolve and download a file.
    Returns: (success: bool, message: str)
    """
    try:
        direct_link = resolve_direct_link(url, provider)
    except Exception as e:
        return False, f"Resolver: {str(e)}"

    try:
        dl_headers = {**HEADERS, 'Referer': url}
        with requests.get(direct_link, headers=dl_headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            total_size_str = r.headers.get('content-length')
            total_size = int(total_size_str) if total_size_str else 0

            if (os.path.exists(output_path)
                    and total_size > 0
                    and os.path.getsize(output_path) == total_size):
                if progress_cb:
                    progress_cb(total_size, total_size, 0.0, 0.0)
                return True, "already_exists"

            start_time = time.perf_counter()
            downloaded = 0

            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65_536):
                    if cancel_check and cancel_check():
                        return False, "cancelled"
                    if pause_event and not pause_event.is_set():
                        while not pause_event.is_set():
                            if cancel_check and cancel_check():
                                return False, "cancelled"
                            time.sleep(0.2)
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = time.perf_counter() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0.0
                        if progress_cb:
                            progress_cb(downloaded, total_size, speed, elapsed)
        return True, "ok"
    except Exception as e:
        return False, str(e)
