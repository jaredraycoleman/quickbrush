import requests
import dotenv
import os
import pytest
import pathlib

dotenv.load_dotenv()
API_KEY = os.getenv("QUICKBRUSH_API_KEY")
BASE_URL = "http://localhost:5000/api"
thisdir = pathlib.Path(__file__).parent
savedir = thisdir / "outputs"


def test_generate(api_key=API_KEY):
    url = f"{BASE_URL}/generate"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "text": "A brave knight with silver armor",
        "generation_type": "character",
        "quality": "medium",
        "size": "1024x1024"
    }

    response = requests.post(url, headers=headers, json=data)
    print(f"Generate response status: {response.status_code}")
    print(f"Generate response: {response.json()}")

    assert response.status_code == 200

    # Get the image URL from response
    image_url = response.json().get("image_url")
    if image_url:
        # The image_url is a relative path like "/api/image/{generation_id}"
        # We need to use the full URL and include authentication headers
        full_image_url = f"{BASE_URL.replace('/api', '')}{image_url}"
        print(f"Full image URL: {full_image_url}")

        # Download the image with authentication
        image_response = requests.get(full_image_url, headers=headers)
        print(f"Image download status: {image_response.status_code}")

        if image_response.status_code == 200:
            savedir.mkdir(exist_ok=True)
            image_path = savedir / "generated_knight.webp"
            with open(image_path, "wb") as f:
                f.write(image_response.content)
            print(f"Image saved to {image_path}")
        else:
            print(f"Failed to download image. Response: {image_response.text}")
            assert False, f"Image download failed with status {image_response.status_code}"
    

def test_get_generations(api_key=API_KEY):
    url = f"{BASE_URL}/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.get(url, headers=headers)
    print(response.status_code)
    print(response.json())
    assert response.status_code == 200

def test_bad_api_key():
    with pytest.raises(Exception):
        test_generate(api_key="invalid_key")
        test_get_generations(api_key="invalid_key")

