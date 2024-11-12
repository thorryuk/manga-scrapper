import os, requests, json, time
from dotenv import load_dotenv, set_key
from pathlib import Path
from tqdm import tqdm

# Load environment variables
load_dotenv()
BASE_URL = "https://api.mangadex.org"
IMAGE_URL = "https://uploads.mangadex.org"
DIRECTORY = Path(__file__).parent
# -------------------------- #

def print_json(data):
    print(json.dumps(data, indent=4))

def create_folder_structure(*folder_names):
    path = DIRECTORY / "download" / Path(*folder_names)
    path.mkdir(parents=True, exist_ok=True)
    print(f'Folder {" / ".join(folder_names)} created successfully')

def authenticate(grant_type="password", refresh_token=None):
    creds = {
        "grant_type": grant_type,
        "client_id": os.getenv("CLIENT_ID"),
        "client_secret": os.getenv("CLIENT_SECRET")
    }
    if grant_type == "password":
        creds["username"] = os.getenv("USERNAME")
        creds["password"] = os.getenv("PASSWORD")
    elif grant_type == "refresh_token" and refresh_token:
        creds["refresh_token"] = refresh_token

    response = requests.post(
        "https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token",
        data=creds
    )
    tokens = response.json()
    return tokens.get("access_token"), tokens.get("refresh_token")

def api_search_manga(title):
    response = requests.get(f"{BASE_URL}/manga", params={"title": title})
    return response.json().get("data", [])

def api_get_manga_aggregate(manga_id):
    chapters = []
    response = requests.get(f"{BASE_URL}/manga/{manga_id}/aggregate", params={"translatedLanguage[]": "en"})
    for volume in response.json().get('volumes').values():
        for chapter in volume['chapters'].values():
            chapters.append({
                "volume": volume['volume'],
                "chapter": chapter['chapter'],
                "id": chapter['id']
            })
    return chapters

def api_get_chapter_images(chapters):
    with tqdm(total=len(chapters), desc="Fetching chapter images") as pbar:
        for chapter in chapters:
            try:
                response = requests.get(f"{BASE_URL}/at-home/server/{chapter['id']}", timeout=10)
                response.raise_for_status()
                chapter['images'] = response.json().get('chapter', [])
                chapter['image_url'] = response.json().get('baseUrl', [])
            except requests.RequestException as e:
                print(f"Error fetching images for chapter {chapter['chapter']}: {e}")
                chapter['images'] = None  # Set to None or empty if an error occurs
            pbar.update(1)  # Update progress bar after each chapter image fetch
            time.sleep(2)  # Pause to avoid rate-limiting

    return chapters

def process():
    dataset = {}

    title = input("Enter the title of the manga you want to search for: ").strip()
    manga_list = api_search_manga(title)

    # Display search results
    for idx, manga in enumerate(manga_list, start=1):
        print(f"{idx}. {manga['attributes']['title']['en']} (ID: {manga['id']})")

    # Select manga for download
    try:
        selection = int(input("Enter the number of the manga you want to download (or 0 to skip): "))
        if 1 <= selection <= len(manga_list):
            selected_manga_id = manga_list[selection - 1]['id']
            manga_data = api_get_manga_aggregate(selected_manga_id)
            chapters_with_images = api_get_chapter_images(manga_data)
            dataset['title'] = manga_list[selection - 1]['attributes']['title']['en']
            dataset['detail'] = chapters_with_images
        elif selection == 0:
            dataset['message'] = "No manga selected for download."
        else:
            dataset['message'] = "Invalid selection. Please enter a number within the range."
    except ValueError:
        dataset["message"] = "Invalid input. Please enter a valid number."

    return dataset

def generate_json(data):
    json_data = []

    # Initialize progress bar for generating JSON data
    with tqdm(total=len(data['detail']), desc="Generating JSON data") as pbar:
        for detail in data['detail']:
            dt = {}
            image_url = []
            directory_path = f"{data['title']}/{detail['chapter']}"
            image_hash = detail['images']['hash']
            url = detail['image_url']
            for image in detail['images']['data']:
                image_path = f"{url}/data/{image_hash}/{image}"
                image_url.append(image_path)
            dt['directory_path'] = directory_path
            dt['image_path'] = image_url
            json_data.append(dt)
            pbar.update(1)  # Update progress bar after processing each chapter

    return json_data

def download_images(data):
    for entry in data:
        directory_path = entry['directory_path']
        image_urls = entry['image_path']

        # Create the directory if it doesn't exist
        create_folder_structure(directory_path)

        # Set up the progress bar
        with tqdm(total=len(image_urls), desc=f"Downloading images to {directory_path}", unit="image") as pbar:
            for url in image_urls:
                # Extract the name from the last part of the URL
                image_name = url.split('/')[-1]
                image_name = f"{image_name.split('-')[0]}.png"
                file_path = os.path.join(f"download/{directory_path}", f"{image_name}")

                # Download and save the image
                try:
                    response = requests.get(url)
                    if response.status_code == 200:
                        with open(file_path, 'wb') as file:
                            file.write(response.content)
                        pbar.set_postfix(file=image_name, status="Downloaded")
                    else:
                        pbar.set_postfix(file=image_name, status="Failed")
                except Exception as e:
                    pbar.set_postfix(file=image_name, status=f"Error: {e}")

                # Update the progress bar
                pbar.update(1)

if __name__ == "__main__":
    get_manga = process()
    image_data = generate_json(get_manga)
    donwload = download_images(image_data)