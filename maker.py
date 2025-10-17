import logging
import pathlib
from typing import Dict, Iterable, List, Literal, Optional, Union
from base64 import b64decode, b64encode
from rembg import remove
from abc import ABC, abstractmethod
from PIL import Image
from openai import OpenAI
import os
from io import BytesIO
import tempfile

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def token_cost(quality: str) -> int:
    """Returns number of tokens consumed per image based on quality."""
    if quality == "low":
        return 1
    if quality == "medium":
        return 3
    if quality == "high":
        return 5
    return 3  # default medium

def convert_for_openai(path: pathlib.Path, format: str) -> pathlib.Path:
    if path.suffix.lower() == f".{format}":
        return path.resolve(strict=True)
    image = Image.open(path)
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{format}") as temp_file:
        image.save(temp_file, format=format.upper())
        return pathlib.Path(temp_file.name)

def remove_background(image_path: pathlib.Path, savepath: pathlib.Path) -> pathlib.Path:
    """
    Remove the background from an image using rembg.

    Args:
        image_path (pathlib.Path): The path to the original image.
        savepath (pathlib.Path): The path where the image with the background removed will be saved.

    Returns:
        pathlib.Path: The path to the image with the background removed.
    """
    output_image: bytes = remove(image_path.read_bytes(), force_return_bytes=True) # type: ignore
    savepath.parent.mkdir(parents=True, exist_ok=True)
    savepath.write_bytes(output_image)
    return savepath.resolve()

IMAGE_SIZE = Literal['256x256', '512x512', '1024x1024', '1536x1024', '1024x1536', 'auto']
BACKGROUND = Literal["transparent", "opaque", "auto"]
QUALITY = Literal["standard", "low", "medium", "high", "auto"]
class ImageGenerator(ABC):
    DEFAULT_IMAGE_SIZE: IMAGE_SIZE = "1024x1024"

    @abstractmethod
    def get_prompt(self, description: str) -> str:
        raise NotImplementedError
    
    @abstractmethod
    def get_description(self, text: str, prompt: str, reference_images: Optional[List[pathlib.Path]] = None) -> str:
        """Extract a description from the provided text. The prompt provides context for the description to be generated (e.g., style change, specific outfit, etc.).

        Args:
            text (str): The text containing the character's description.
            prompt (str): The context prompt for the description.
            reference_images (List[pathlib.Path], optional): Optional list of reference image paths.

        Returns:
            str: A concise description.
        """
        raise NotImplementedError
    
    def generate_image(self,
                       description: str,
                       reference_images: Optional[List[pathlib.Path]] = None,
                       model: str = "gpt-image-1-mini",
                       image_size: IMAGE_SIZE = "1024x1024",
                       quality: QUALITY = "medium",
                       background: BACKGROUND = "transparent") -> bytes:
        """
        Generate an image based on the provided prompt using OpenAI's API.

        Args:
            description (str): The prompt for the character description.
            reference_images (List[pathlib.Path]): Optional list of reference image paths.
            model (str): The OpenAI model to use for generation.
            image_size (IMAGE_SIZE): Size of the generated image.
            quality (QUALITY): Quality level for generation.
            background (BACKGROUND): Background type (transparent, opaque, auto).

        Returns:
            bytes: WebP image data as bytes.
        """
        if not reference_images:
            response = client.images.generate(
                prompt=self.get_prompt(description),
                background=background,
                model=model,
                size=image_size,
                quality=quality
            )
        else:
            # Call OpenAI with file paths
            response = client.images.edit(
                prompt=self.get_prompt(description),
                image=[
                    convert_for_openai(img_path, "png")
                    for img_path in reference_images
                ],
                background=background,
                model=model,
                size=image_size,
                quality=quality
            )

        if not response.data or not response.data[0].b64_json:
            raise ValueError("No image data returned from OpenAI API.")

        image_data = b64decode(response.data[0].b64_json)

        # Convert PNG to WebP format
        with Image.open(BytesIO(image_data)) as img:
            webp_buffer = BytesIO()
            img.save(webp_buffer, format="WEBP", quality=95)
            webp_data = webp_buffer.getvalue()

        return webp_data


class CharacterImageGenerator(ImageGenerator):
    DEFAULT_CONTEXT_PROMPT = "Generate a physical description of a character."
    def get_prompt(self, description: str) -> str:
        prompt = (
            f"Highly stylized digital concept art profile of {description}. "
            "Rendered in a fantasy-steampunk illustration style inspired by graphic novel and fantasy "
            "RPG character art with bold, clean line work, muted yet rich colors, and dramatic cel-shading. "
            "Facial features are expressive and detailed, with textured hair and stylized lighting "
            "that adds depth and mood. The background fades into negative space, as if the character is "
            "emerging from the page. The character is looking directly at the viewer. The background is white. "
            "The character is centered in the frame, with their head and shoulders fitting within the image. "
        )
        return prompt
    
    def get_description(self, text: str, prompt: str = DEFAULT_CONTEXT_PROMPT, reference_images: Optional[List[pathlib.Path]] = None) -> str:
        """
        Extract a physical description from the provided text.

        Args:
            text (str): The text containing the character's description.
            prompt (str): The context prompt for the description.
            reference_images (List[pathlib.Path], optional): Optional list of reference image paths.

        Returns:
            str: A concise physical description of the character.
        """
        # Build messages with optional reference images
        messages: List[Dict[str, Union[str, List[Dict[str, str]]]]] = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that creates short but detailed character descriptions "
                    "based on the prompt provided and a general description of the character's appearance. "
                    "Always give preference to the prompt over the general description (e.g., the "
                    "prompt might ask them to wear a specific outfit or have a certain hairstyle while"
                    "the general description describes them as typically wearing a different outfit). "
                    "This will be used as a prompt for generating an image, so be as consistent and descriptive as possible. "
                    "Focus on the physical description and do not include any names (even the character's name), personality traits, lore, etc. "
                )
            }
        ]

        # Build user message content
        user_content = []

        # Add reference images first if provided
        if reference_images:
            for img_path in reference_images:
                with open(img_path, "rb") as img_file:
                    img_bytes = img_file.read()
                    base64_image = b64encode(img_bytes).decode('utf-8')
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    })

        # Add text prompt
        user_content.append({
            "type": "text",
            "text": (
                prompt + "\n\n"
                "Overall character description:\n" + text
            )
        })

        messages.append({
            "role": "user",
            "content": user_content
        })

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages # type: ignore
        )
        if not response.choices or not response.choices[0].message:
            raise ValueError("No response from OpenAI API.")
        if not response.choices[0].message.content:
            raise ValueError("No content in the response message.")
        description = response.choices[0].message.content.strip()
        return description
    
class SceneImageGenerator(ImageGenerator):
    DEFAULT_IMAGE_SIZE: IMAGE_SIZE = "1536x1024"
    def get_prompt(self, description: str) -> str:
        specific_prompt = f" featuring {description}" if description else ""
        prompt = (
            f"Highly stylized digital concept art{specific_prompt}. "
            "Rendered in a fantasy illustration style inspired by graphic novel and fantasy "
            "RPG scene art with bold, clean line work, muted yet rich colors, and dramatic cel-shading. "
            "The background fades into negative space, as if the scene is emerging from the page. "
            "The scene is from a ground, first-person perspective, with a wide view of the environment. "
            "Focus on the physical description and do not include any names, personality traits, lore, etc. "
            "The background is white."
        )
        return prompt
    
    def get_description(self, text: str, prompt: str = "", reference_images: Optional[List[pathlib.Path]] = None) -> str:
        """
        Extract a description for the scene from the provided text.

        Args:
            text (str): The text containing the scene's description.
            prompt (str): The context prompt for the description.
            reference_images (List[pathlib.Path], optional): Optional list of reference image paths.

        Returns:
            str: A concise description of the scene.
        """
        # Build messages with optional reference images
        messages: List[Dict[str, Union[str, List[Dict[str, str]]]]] = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that creates short but detailed scene descriptions "
                    "based on the prompt provided and a general description of the scene. "
                    "Always give preference to the prompt over the general description (e.g., the "
                    "prompt might ask for a specific setting or time of day while the general description "
                    "describes a different setting). This will be used as a prompt for generating an image, "
                    "so be as consistent and descriptive as possible. "
                    "Focus on the physical description and do not include any names, personality traits, lore, etc. "
                )
            }
        ]

        # Build user message content
        user_content = []

        # Add reference images first if provided
        if reference_images:
            for img_path in reference_images:
                with open(img_path, "rb") as img_file:
                    img_bytes = img_file.read()
                    base64_image = b64encode(img_bytes).decode('utf-8')
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    })

        # Add text prompt
        user_content.append({
            "type": "text",
            "text": (
                prompt + "\n\n"
                "Overall scene description:\n" + text
            )
        })

        messages.append({
            "role": "user",
            "content": user_content
        })

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages  # type: ignore
        )
        if not response.choices or not response.choices[0].message:
            raise ValueError("No response from OpenAI API.")
        if not response.choices[0].message.content:
            raise ValueError("No content in the response message.")
        description = response.choices[0].message.content.strip()
        return description

class CreatureImageGenerator(ImageGenerator):
    DEFAULT_CONTEXT_PROMPT = "Generate a physical description of a creature."
    def get_prompt(self, description: str) -> str:
        prompt = (
            f"Highly stylized digital concept art profile of {description}. "
            "Rendered in a fantasy illustration style inspired by graphic novel and fantasy "
            "RPG creature art with bold, clean line work, muted yet rich colors, and dramatic cel-shading. "
            "Facial features are expressive and detailed, with textured skin/fur/scales and stylized lighting "
            "that adds depth and mood. The background fades into negative space, as if the creature is "
            "emerging from the page. The creature is looking directly at the viewer. The background is white. "
            "The creature is centered in the frame, with their head and shoulders fitting within the image. "
        )
        return prompt
    
    def get_description(self, text: str, prompt: str = DEFAULT_CONTEXT_PROMPT, reference_images: Optional[List[pathlib.Path]] = None) -> str:
        """
        Extract a physical description from the provided text.

        Args:
            text (str): The text containing the creature's description.
            prompt (str): The context prompt for the description.
            reference_images (List[pathlib.Path], optional): Optional list of reference image paths.
        Returns:
            str: A concise physical description of the creature.
        """
        # Build messages with optional reference images
        messages: List[Dict[str, Union[str, List[Dict[str, str]]]]] = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that creates short but detailed creature descriptions "
                    "based on the prompt provided and a general description of the creature's appearance. "
                    "Always give preference to the prompt over the general description (e.g., the "
                    "prompt might ask them to have a specific feature or color while the general description "
                    "describes them as typically having different features). "
                    "This will be used as a prompt for generating an image, so be as consistent and descriptive as possible. "
                    "Focus on the physical description and do not include any names (even the creature's name), personality traits, lore, etc. "
                )
            }
        ]

        # Build user message content
        user_content = []

        # Add reference images first if provided
        if reference_images:
            for img_path in reference_images:
                with open(img_path, "rb") as img_file:
                    img_bytes = img_file.read()
                    base64_image = b64encode(img_bytes).decode('utf-8')
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    })

        # Add text prompt
        user_content.append({
            "type": "text",
            "text": (
                prompt + "\n\n"
                "Overall creature description:\n" + text
            )
        })

        messages.append({
            "role": "user",
            "content": user_content
        })

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages  # type: ignore
        )
        if not response.choices or not response.choices[0].message:
            raise ValueError("No response from OpenAI API.")
        if not response.choices[0].message.content:
            raise ValueError("No content in the response message.")
        description = response.choices[0].message.content.strip()
        return description
    
class ItemImageGenerator(ImageGenerator):
    DEFAULT_CONTEXT_PROMPT = "Generate a physical description of the item."
    def get_prompt(self, description: str) -> str:
        prompt = (
            f"Highly stylized digital concept art of {description}. "
            "Rendered in a fantasy illustration style inspired by graphic novel and fantasy "
            "RPG item art with bold, clean line work, muted yet rich colors, and dramatic cel-shading. "
            "The item is detailed and textured, with stylized lighting that adds depth and mood. "
            "The background fades into negative space, as if the item is emerging from the page. "
            "The item is centered in the frame, fitting within the image with space around it. The background is white."
        )
        return prompt
    
    def get_description(self, text: str, prompt: str = DEFAULT_CONTEXT_PROMPT, reference_images: Optional[List[pathlib.Path]] = None) -> str:
        """
        Extract a physical description from the provided text.

        Args:
            text (str): The text containing the item's description.
            prompt (str): The context prompt for the description.
            reference_images (List[pathlib.Path], optional): Optional list of reference image paths.
        Returns:
            str: A concise physical description of the item.
        """
        # Build messages with optional reference images
        messages: List[Dict[str, Union[str, List[Dict[str, str]]]]] = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that creates short but detailed item descriptions "
                    "based on the prompt provided and a general description of the item's appearance. "
                    "Always give preference to the prompt over the general description (e.g., the "
                    "prompt might ask for a specific material or design while the general description "
                    "describes it as typically having different features). "
                    "This will be used as a prompt for generating an image, so be as consistent and descriptive as possible. "
                    "Only relate the physical description of the item and do not include any names (even of the item itself), lore, personality, etc. "
                )
            }
        ]

        # Build user message content
        user_content = []

        # Add reference images first if provided
        if reference_images:
            for img_path in reference_images:
                with open(img_path, "rb") as img_file:
                    img_bytes = img_file.read()
                    base64_image = b64encode(img_bytes).decode('utf-8')
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    })

        # Add text prompt
        user_content.append({
            "type": "text",
            "text": (
                prompt + "\n\n"
                "General item description:\n" + text
            )
        })

        messages.append({
            "role": "user",
            "content": user_content
        })

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages  # type: ignore
        )
        if not response.choices or not response.choices[0].message:
            raise ValueError("No response from OpenAI API.")
        if not response.choices[0].message.content:
            raise ValueError("No content in the response message.")
        description = response.choices[0].message.content.strip()
        return description
