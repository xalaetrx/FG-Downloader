import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote
from tqdm import tqdm
import msvcrt
import tkinter as tk
from tkinter import filedialog

def main():
    url = input("Enter the FitGirl Repack URL: ").strip()
    if not url:
        print("Invalid URL.")
        return

    print("Fetching page...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching URL: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Try to get the game title for the folder name
    title_tag = soup.find('h1', class_='entry-title')
    game_title = title_tag.text.strip() if title_tag else "FitGirl_Repack"
    safe_title = re.sub(r'[\\/*?:"<>|]', "", game_title)
    
    print(f"Game found: {game_title}")

    # Find FuckingFast links
    ff_links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('https://fuckingfast.co/'):
            # The filename is usually after the hash, e.g., #filename.rar
            filename = ""
            if '#' in href:
                filename = unquote(href.split('#')[1])
            else:
                filename = a.text.strip()
            
            if not filename or filename.lower() == 'fuckingfast':
                continue
            
            ff_links.append({"url": href, "filename": filename})

    if not ff_links:
        print("No FuckingFast links found on this page.")
        return
    
    # Remove duplicates
    unique_links = []
    seen = set()
    for link in ff_links:
        if link['url'] not in seen:
            seen.add(link['url'])
            unique_links.append(link)
            
    ff_links = unique_links

    base_files = []
    optional_files = []

    for link in ff_links:
        fname_lower = link['filename'].lower()
        if 'optional' in fname_lower:
            optional_files.append(link)
        else:
            base_files.append(link)

    print(f"\nFound {len(base_files)} base files.")
    
    selected_optional = []
    if optional_files:
        print(f"\nFound {len(optional_files)} optional files:")
        for i, opt in enumerate(optional_files):
            print(f"[{i + 1}] {opt['filename']}")
        
        choices = input("\nEnter the numbers of the optional files you want to download, separated by commas (or press Enter to skip): ").strip()
        if choices:
            for choice in choices.split(','):
                choice = choice.strip()
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(optional_files):
                        selected_optional.append(optional_files[idx])

    download_queue = base_files + selected_optional
    
    if not download_queue:
        print("No files to download.")
        return

    # Ask for parent directory
    print("\nSelect the download directory:")
    print("Press [Enter] to browse for a folder...")
    print("Press [Space] to use the current directory...")
    
    parent_dir = None
    while True:
        ch = msvcrt.getch()
        if ch in (b'\r', b'\n'):
            print("Opening folder browser...")
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            selected_path = filedialog.askdirectory(title="Select Download Directory")
            root.destroy()
            if selected_path:
                parent_dir = os.path.normpath(selected_path)
                print(f"Selected directory: {parent_dir}")
                break
            else:
                print("No directory selected. Press [Enter] to browse, or [Space] to use the current directory.")
        elif ch == b' ':
            parent_dir = os.getcwd()
            print(f"Using current directory: {parent_dir}")
            break

    # Final output folder
    final_dir = os.path.join(parent_dir, safe_title)

    # Create folder
    if not os.path.exists(final_dir):
        os.makedirs(final_dir)
        
    print(f"\nStarting download of {len(download_queue)} files sequentially to folder '{final_dir}'...")

    for i, item in enumerate(download_queue):
        print(f"\n[{i+1}/{len(download_queue)}] Processing: {item['filename']}")
        download_fucking_fast_file(item['url'], os.path.join(final_dir, item['filename']))

def download_fucking_fast_file(ff_url, output_path):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # Step 1: Fetch the FuckingFast page
    try:
        res = requests.get(ff_url, headers=headers)
        res.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch {ff_url}: {e}")
        return

    # Step 2: Extract direct download link
    # Look for window.open("https://dl.fuckingfast.co/dl/...")
    match = re.search(r'window\.open\("([^"]+)"\)', res.text)
    if not match:
        print("Could not find direct download link in the page.")
        return
        
    direct_link = match.group(1)
    
    # Try to extract the download id for the ping request
    parsed_url = urlparse(ff_url)
    ff_id = parsed_url.path.split('/')[-1]
    
    # Inform server about download start
    try:
        requests.post(f"https://fuckingfast.co/f/{ff_id}/dl", headers=headers)
    except:
        pass
        
    # Step 3: Download the file with progress bar
    try:
        dl_headers = {
            'User-Agent': headers['User-Agent'],
            'Referer': ff_url
        }
        with requests.get(direct_link, headers=dl_headers, stream=True) as r:
            r.raise_for_status()
            total_size_str = r.headers.get('content-length')
            total_size = int(total_size_str) if total_size_str else 0
            
            # Check if file exists and matches size
            if os.path.exists(output_path) and total_size > 0 and os.path.getsize(output_path) == total_size:
                print(f"File '{output_path}' already exists and is fully downloaded. Skipping.")
                return

            with open(output_path, 'wb') as f:
                with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024, desc="Downloading") as pbar:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
        print(f"Successfully downloaded to '{output_path}'")
    except Exception as e:
        print(f"Download failed: {e}")

if __name__ == "__main__":
    main()
