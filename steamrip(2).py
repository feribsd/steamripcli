#!/home/feribsd/steamrip-scraper/bin/python
import re
import time
import cloudscraper
from bs4 import BeautifulSoup

BANNER = r"""
 ____ _____ _____    _    __  __ ____  ___ ____        ____ _     ___
/ ___|_   _| ____|  / \  |  \/  |  _ \|_ _|  _ \      / ___| |   |_ _|
\___ \ | | |  _|   / _ \ | |\/| | |_) || || |_) |____| |   | |    | |
 ___) || | | |___ / ___ \| |  | |  _ < | ||  __/_____| |___| |___ | |
|____/ |_| |_____/_/   \_\_|  |_|_| \_\___|_|         \____|_____|___|

         [ SteamRIP CLI Scraper ]  -  grab your links fast
"""

scraper = cloudscraper.create_scraper()
BASE_URL = "https://steamrip.com"


def search_steamrip(query, pages=2):
    results = []
    for page in range(1, pages + 1):
        response = scraper.get(BASE_URL, params={"s": query, "paged": page})
        soup = BeautifulSoup(response.text, "html.parser")
        posts = soup.select("div.post-element")
        if not posts:
            break
        for post in posts:
            title_tag = post.select_one("h2.thumb-title a")
            if not title_tag:
                continue
            href = title_tag["href"]
            url = href if href.startswith("http") else f"{BASE_URL}/{href}"
            results.append({"title": title_tag.get_text(strip=True), "url": url})
        time.sleep(1)
    return results


def get_direct_fileditch_url(fileditch_url):
    response = scraper.get(fileditch_url)
    soup = BeautifulSoup(response.text, "html.parser")
    dl_btn = soup.select_one("a#dl-btn")
    if dl_btn and dl_btn.get("href"):
        return dl_btn["href"]
    return None


def get_direct_gofile_url(gofile_url):
    match = re.search(r'gofile\.io/d/([a-zA-Z0-9]+)', gofile_url)
    if not match:
        return None
    content_id = match.group(1)

    token_resp = scraper.post("https://api.gofile.io/accounts")
    if token_resp.status_code != 200:
        return None
    token_data = token_resp.json()
    if token_data.get("status") != "ok":
        return None
    token = token_data["data"]["token"]

    headers = {"Authorization": f"Bearer {token}"}
    content_resp = scraper.get(
        f"https://api.gofile.io/contents/{content_id}",
        headers=headers,
        params={"wt": "4fd6sg89d7s6"}
    )
    if content_resp.status_code != 200:
        return None

    content_data = content_resp.json()
    if content_data.get("status") != "ok":
        return None

    children = content_data["data"].get("children", {})
    links = []
    for child in children.values():
        if child.get("type") == "file":
            links.append({
                "name": child.get("name"),
                "url": child.get("link"),
            })
    return links


def resolve_buzzheavier_shortlink(url):
    """Follow bzzhr.to short links to get the real buzzheavier.com URL."""
    resp = scraper.get(url, allow_redirects=True)
    return resp.url


def get_direct_buzzheavier_url(buzzheavier_url):
    # Resolve short link first if needed
    if "bzzhr.to" in buzzheavier_url:
        buzzheavier_url = resolve_buzzheavier_shortlink(buzzheavier_url)

    match = re.search(r'buzzheavier\.com/([a-zA-Z0-9]+)', buzzheavier_url)
    if not match:
        return None
    file_id = match.group(1)

    download_url = f"https://buzzheavier.com/{file_id}/download"
    alt_url = f"https://buzzheavier.com/{file_id}/download?alt=true"

    headers = {
        "HX-Request": "true",
        "HX-Current-URL": buzzheavier_url,
        "Referer": buzzheavier_url
    }

    resp = scraper.get(download_url, headers=headers, allow_redirects=False)

    if resp.status_code in (301, 302, 303, 307, 308):
        direct = resp.headers.get("Location")
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        a = soup.find("a", href=True)
        direct = a["href"] if a else None

    return {"primary": direct, "alt": alt_url}


def get_game_info(game_url):
    response = scraper.get(game_url)
    soup = BeautifulSoup(response.text, "html.parser")

    info = {}

    for li in soup.select("div.plus ul li"):
        text = li.get_text(strip=True)
        if ":" in text:
            key, _, value = text.partition(":")
            info[key.strip()] = value.strip()

    reqs = {}
    for li in soup.select("div.checklist ul li"):
        text = li.get_text(strip=True)
        if ":" in text:
            key, _, value = text.partition(":")
            reqs[key.strip()] = value.strip()
    if reqs:
        info["System Requirements"] = reqs

    downloads = []
    for btn in soup.select("a.shortc-button"):
        href = btn.get("href", "")
        if not href:
            continue
        if href.startswith("//"):
            href = "https:" + href

        host_label = "Unknown"
        for sibling in btn.find_all_previous(["strong", "a"], limit=5):
            text = sibling.get_text(strip=True)
            if text and sibling.name == "strong" and "DOWNLOAD" not in text.upper():
                host_label = text
                break

        if "fileditch" in href:
            print(f"  Resolving FileDitch link...")
            direct = get_direct_fileditch_url(href)
            downloads.append({
                "host": host_label,
                "page": href,
                "url": direct or href,
                "direct": direct is not None
            })

        elif "gofile.io" in href:
            print(f"  Resolving GoFile link...")
            files = get_direct_gofile_url(href)
            if files:
                for f in files:
                    downloads.append({
                        "host": host_label,
                        "page": href,
                        "url": f["url"],
                        "name": f.get("name"),
                        "direct": True
                    })
            else:
                downloads.append({"host": host_label, "page": href, "url": href, "direct": False})

        elif "buzzheavier.com" in href or "bzzhr.to" in href:
            print(f"  Resolving BuzzHeavier link...")
            result = get_direct_buzzheavier_url(href)
            if result:
                downloads.append({
                    "host": host_label,
                    "page": href,
                    "url": result["primary"] or href,
                    "alt": result["alt"],
                    "direct": result["primary"] is not None
                })
            else:
                downloads.append({"host": host_label, "page": href, "url": href, "direct": False})

        else:
            downloads.append({"host": host_label, "page": href, "url": href, "direct": False})

    info["Downloads"] = downloads
    return info


def print_game_info(info):
    skip = {"Downloads", "System Requirements"}
    print("\n--- GAME INFO ---")
    for key, val in info.items():
        if key not in skip:
            print(f"  {key}: {val}")

    reqs = info.get("System Requirements", {})
    if reqs:
        print("\n--- SYSTEM REQUIREMENTS ---")
        for key, val in reqs.items():
            print(f"  {key}: {val}")

    downloads = info.get("Downloads", [])
    if not downloads:
        print("\n  No download links found.")
        return

    print("\n--- DOWNLOAD LINKS ---")
    for d in downloads:
        host = d["host"]
        if d["direct"]:
            print(f"  [{host}] ✓ {d['url']}")
            if d.get("alt"):
                print(f"  [{host}] ✓ Alt: {d['alt']}")
        else:
            print(f"  [{host}] ⚠ Needs captcha: {d['url']}")


def main():
    print(BANNER)

    while True:
        query = input("\nSearch for a game (or 'q' to quit): ").strip()
        if query.lower() == "q":
            break

        results = search_steamrip(query)
        if not results:
            print("No results found.")
            continue

        print(f"\nFound {len(results)} result(s):")
        for i, r in enumerate(results):
            print(f"  [{i+1}] {r['title']}")

        choice = input("\nEnter number to select (or 0 to search again): ").strip()
        if not choice.isdigit():
            print("Please enter a number.")
            continue
        if int(choice) == 0:
            continue

        idx = int(choice) - 1
        if idx >= len(results):
            print("Invalid choice.")
            continue

        chosen = results[idx]
        print(f"\nFetching info for: {chosen['title']}")
        time.sleep(1)

        info = get_game_info(chosen["url"])
        print_game_info(info)


if __name__ == "__main__":
    main()
