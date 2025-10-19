"""
Utility functions for handling reference images.

This module provides shared utilities for processing reference images
from various sources (URLs, base64, file uploads) and converting them
to temporary files for the image generation service.
"""

import pathlib
import tempfile
import base64
import requests
from typing import List, Optional
from io import BytesIO


def process_reference_images(reference_image_paths: List[str], max_images: int = 3) -> List[pathlib.Path]:
    """
    Process reference images from various sources and save to temp files.

    Supports:
    - data: URIs (base64 encoded images)
    - http/https URLs
    - Local file paths

    Args:
        reference_image_paths: List of image sources (URLs, data URIs, or paths)
        max_images: Maximum number of images to process (default: 3)

    Returns:
        List of pathlib.Path objects pointing to temporary files

    Note:
        Caller is responsible for cleaning up temporary files after use.
    """
    temp_paths: List[pathlib.Path] = []

    try:
        for image_source in reference_image_paths[:max_images]:
            if not image_source:
                continue

            temp_path = _process_single_image(image_source)
            if temp_path:
                temp_paths.append(temp_path)

    except Exception as e:
        # Clean up any temp files created so far
        for temp_path in temp_paths:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
        raise Exception(f"Error processing reference images: {str(e)}")

    return temp_paths


def _process_single_image(image_source: str) -> Optional[pathlib.Path]:
    """
    Process a single reference image from any source.

    Args:
        image_source: Image source (URL, data URI, or file path)

    Returns:
        Path to temporary file containing the image data, or None if failed
    """
    # Handle data URI (base64)
    if image_source.startswith('data:'):
        return _process_data_uri(image_source)

    # Handle HTTP/HTTPS URL
    elif image_source.startswith(('http://', 'https://')):
        return _process_url(image_source)

    # Handle local file path
    else:
        return _process_file_path(image_source)


def _process_data_uri(data_uri: str) -> Optional[pathlib.Path]:
    """
    Process a data URI (base64 encoded image).

    Args:
        data_uri: Data URI string (e.g., 'data:image/png;base64,iVBORw0KG...')

    Returns:
        Path to temporary file containing the decoded image data
    """
    try:
        # Parse data URI: data:[<mediatype>][;base64],<data>
        if ';base64,' not in data_uri:
            raise ValueError("Invalid data URI format (missing ';base64,')")

        header, data = data_uri.split(';base64,', 1)

        # Extract media type to determine file extension
        media_type = header.replace('data:', '')
        extension = _get_extension_from_media_type(media_type)

        # Decode base64 data
        image_data = base64.b64decode(data)

        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
            tmp.write(image_data)
            return pathlib.Path(tmp.name)

    except Exception as e:
        print(f"Error processing data URI: {e}")
        return None


def _process_url(url: str) -> Optional[pathlib.Path]:
    """
    Download an image from a URL and save to temp file.

    Args:
        url: HTTP/HTTPS URL to the image

    Returns:
        Path to temporary file containing the downloaded image
    """
    try:
        # Download image with timeout
        response = requests.get(url, timeout=10, stream=True)
        response.raise_for_status()

        # Determine file extension from content type or URL
        content_type = response.headers.get('content-type', '')
        extension = _get_extension_from_media_type(content_type)

        if not extension:
            # Try to get extension from URL
            url_path = url.split('?')[0]  # Remove query params
            if '.' in url_path:
                extension = '.' + url_path.split('.')[-1].lower()
                if extension not in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
                    extension = '.png'  # Default
            else:
                extension = '.png'

        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
            for chunk in response.iter_content(chunk_size=8192):
                tmp.write(chunk)
            return pathlib.Path(tmp.name)

    except Exception as e:
        print(f"Error downloading image from URL {url}: {e}")
        return None


def _process_file_path(file_path: str) -> Optional[pathlib.Path]:
    """
    Process a local file path reference image.

    Args:
        file_path: Path to local image file

    Returns:
        Path object pointing to the file (if it exists and is valid)
    """
    try:
        path = pathlib.Path(file_path)

        # Validate file exists
        if not path.exists() or not path.is_file():
            print(f"File not found or not a file: {file_path}")
            return None

        # Validate file extension
        allowed_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
        if path.suffix.lower() not in allowed_extensions:
            print(f"Invalid file extension: {path.suffix}")
            return None

        # For local files, we can return the path directly
        # No need to copy to temp file
        return path

    except Exception as e:
        print(f"Error processing file path {file_path}: {e}")
        return None


def _get_extension_from_media_type(media_type: str) -> str:
    """
    Get file extension from media type.

    Args:
        media_type: MIME type (e.g., 'image/png')

    Returns:
        File extension with dot (e.g., '.png')
    """
    media_type = media_type.lower().strip()

    extension_map = {
        'image/png': '.png',
        'image/jpeg': '.jpg',
        'image/jpg': '.jpg',
        'image/webp': '.webp',
        'image/gif': '.gif',
    }

    return extension_map.get(media_type, '.png')


def cleanup_temp_images(temp_paths: List[pathlib.Path]) -> None:
    """
    Clean up temporary image files.

    Args:
        temp_paths: List of temporary file paths to delete
    """
    for temp_path in temp_paths:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass  # Ignore cleanup errors
