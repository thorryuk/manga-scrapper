import os, requests, json, time
from dotenv import load_dotenv
from pathlib import Path
from tqdm import tqdm
from colorama import init, Fore
from concurrent.futures import ThreadPoolExecutor

# Initialize colorama
init(autoreset=True)

# Load environment variables
load_dotenv()
BASE_URL = "https://api.mangadex.org"
IMAGE_URL = "https://uploads.mangadex.org"
DIRECTORY = Path(__file__).parent

def create_folder_structure(manga_title, chapter):
    path = DIRECTORY / "download" / manga_title / f"chapter {chapter}"
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        tqdm.write(Fore.GREEN + f'\n[INFO] ➜ Folder "{manga_title} / chapter {chapter}" created successfully\n')
    else:
        tqdm.write(Fore.YELLOW + f'\n[INFO] ➜ Folder "{manga_title} / chapter {chapter}" already exists\n')

def api_request(url, params=None, method='get', data=None):
    try:
        response = requests.request(method, url, params=params, data=data, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        tqdm.write(Fore.RED + f'\n[ERROR] ✖ {e}\n')
        return None

def api_search_manga(title):
    tqdm.write(Fore.CYAN + f'\n[INFO] 🔍 Searching for manga with title: "{title}"\n')
    return api_request(f"{BASE_URL}/manga", params={"title": title}).get("data", [])

def api_get_manga_aggregate(manga_id):
    tqdm.write(Fore.CYAN + f'\n[INFO] 📊 Getting aggregate data for manga ID: {manga_id}\n')
    chapters = []
    volumes = api_request(f"{BASE_URL}/manga/{manga_id}/aggregate", params={"translatedLanguage[]": "en"}).get('volumes', {})
    for volume in volumes.values():
        for chapter in volume['chapters'].values():
            chapters.append({"chapter": chapter['chapter'], "id": chapter['id']})
    return chapters

def api_get_chapter_images(chapters):
    tqdm.write(Fore.CYAN + '\n[INFO] 🖼️ Fetching chapter images\n')
    for chapter in tqdm(chapters, desc="Fetching chapter images", colour="blue"):
        chapter['images'] = api_request(f"{BASE_URL}/at-home/server/{chapter['id']}").get('chapter', {})
        time.sleep(2)  # Pause to avoid rate-limiting
    return chapters

def process():
    title = input("Enter the title of the manga you want to search for: ").strip()
    manga_list = api_search_manga(title)
    for idx, manga in enumerate(manga_list, start=1):
        print(f"{idx}. {manga['attributes']['title']['en']} (ID: {manga['id']})")
    try:
        selection = int(input("Enter the number of the manga you want to download (or 0 to skip): "))
        if 1 <= selection <= len(manga_list):
            selected_manga_id = manga_list[selection - 1]['id']
            chapters_with_images = api_get_chapter_images(api_get_manga_aggregate(selected_manga_id))
            return {'title': manga_list[selection - 1]['attributes']['title']['en'], 'detail': chapters_with_images}
        else:
            return {'message': "\n[INFO] ➜ No manga selected for download.\n"}
    except ValueError:
        return {"message": "\n[ERROR] ✖ Invalid input. Please enter a valid number.\n"}

def generate_json(data):
    tqdm.write(Fore.CYAN + '\n[INFO] 📝 Generating JSON data\n')
    json_data = []
    for detail in tqdm(data['detail'], desc="Generating JSON data", colour="green"):
        image_urls = [f"{IMAGE_URL}/{detail['images']['hash']}/{img}" for img in detail['images']['data']]
        json_data.append({'directory_path': f"{data['title']}/chapter {detail['chapter']}", 'image_path': image_urls})
    return json_data

def download_image(url, file_path):
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(file_path, 'wb') as file:
            file.write(response.content)
    except requests.RequestException as e:
        tqdm.write(Fore.RED + f'\n[ERROR] ✖ Failed to download {file_path.name}: {e}\n')

def download_images(data):
    for entry in data:
        manga_title, chapter = entry['directory_path'].split('/')[0], entry['directory_path'].split('/')[-1].split(' ')[1]
        create_folder_structure(manga_title, chapter)
        file_paths = [DIRECTORY / "download" / manga_title / f"chapter {chapter}" / f"{index + 1}.{url.split('.')[-1]}" for index, url in enumerate(entry['image_path'])]

        # Check for missing images
        missing_images = [url for url, file_path in zip(entry['image_path'], file_paths) if not file_path.exists()]
        missing_file_paths = [file_path for file_path in file_paths if not file_path.exists()]

        if missing_images:
            tqdm.write(Fore.CYAN + f'\n[INFO] 🖼️ Downloading missing images for "{manga_title} / chapter {chapter}"\n')
            with ThreadPoolExecutor(max_workers=10) as executor:
                list(tqdm(executor.map(download_image, missing_images, missing_file_paths), total=len(missing_images), desc=f"Downloading images to {manga_title} / chapter {chapter}", unit="image", colour="yellow"))

if __name__ == "__main__":
    try:
        get_manga = process()
        if 'detail' in get_manga:
            image_data = generate_json(get_manga)
            download_images(image_data)
        else:
            tqdm.write(Fore.RED + get_manga.get('message', '\n[ERROR] ✖ An error occurred during processing.\n'))
    except Exception as e:
        tqdm.write(Fore.RED + f'\n[ERROR] ✖ An unexpected error occurred: {e}\n')