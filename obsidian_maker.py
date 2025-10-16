import logging
import pathlib
from typing import Type
import uuid
import argparse
import dotenv
import os
import obsidiantools.api as otools

from maker import (
    ImageGenerator,
    CharacterImageGenerator,
    SceneImageGenerator,
    CreatureImageGenerator,
    ItemImageGenerator,
    IMAGE_SIZE,
    QUALITY,
    BACKGROUND,
)

dotenv.load_dotenv()

thisdir = pathlib.Path(__file__).parent
vault_path = pathlib.Path(os.environ["VAULT_PATH"]).resolve(strict=True)
vault = otools.Vault(vault_path).connect().gather()

file_metadata = vault.get_all_file_metadata()
# media_metadata = vault.get_media_file_metadata()
media_paths = {}
for path in vault_path.glob("**/*"):
    if ".obsidian" in path.parts:
        continue
    if path.suffix.lower() != ".md" and path.is_file():
        if path.name in media_paths:
            raise ValueError(f"Duplicate media file name found: {path.name}")
        media_paths[path.name] = path.resolve(strict=True)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="Generate images from Obsidian notes.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    commands = {
        "character": CharacterImageGenerator,
        "scene": SceneImageGenerator,
        "creature": CreatureImageGenerator,
        "item": ItemImageGenerator,
    }

    for cmd, cls in commands.items():
        cmd_parser = subparsers.add_parser(cmd, help=f"Generate a {cmd} image.")
        cmd_parser.add_argument("filename", type=str, help="The filename of the Obsidian note (with .md extension).")
        cmd_parser.add_argument("--model", type=str, default="gpt-image-1-mini", help="The OpenAI model to use for image generation.")
        cmd_parser.add_argument("--context", type=str, default="", help="Additional context prompt for description generation.")
        cmd_parser.add_argument("--image-size", type=str, choices=IMAGE_SIZE.__args__, default=getattr(cls, 'DEFAULT_IMAGE_SIZE', '1024x1024'), help="Size of the generated image.")
        cmd_parser.add_argument("--quality", type=str, choices=QUALITY.__args__, default=getattr(cls, 'DEFAULT_QUALITY', 'medium'), help="Quality of the generated image.")
        cmd_parser.add_argument("--background", type=str, choices=BACKGROUND.__args__, default=getattr(cls, 'DEFAULT_BACKGROUND', 'transparent'), help="Background of the generated image.")
        cmd_parser.add_argument(
            "--format",
            type=str,
            choices=["png", "webp"],
            default="webp",
            help="Output image format (default: webp)"
        )

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    text = vault.get_readable_text(args.filename)
    embedded_files = []
    for path in vault.get_embedded_files(args.filename):
        path_name = pathlib.Path(path).name
        if path_name in media_paths:
            embedded_files.append(media_paths[path_name])

    if args.command in commands:
        subclass: Type[ImageGenerator] = commands[args.command]
        logging.info(f"Extracting description for {args.command} from the note...")
        generator = subclass()
        description = generator.get_description(text, args.context or getattr(subclass, "DEFAULT_CONTEXT_PROMPT", ""))
        logging.info(f"Generated description: {description}")
        savepath = thisdir / f"{args.command}s" / f"{args.filename}_{uuid.uuid4().hex[:8]}.{args.format}"
        generator.generate_image(
            description=description,
            savepath=savepath,
            reference_images=embedded_files,
            model=args.model,
            image_size=args.image_size,
            quality=args.quality,
            background=args.background
        )
        logging.info(f"{args.command.capitalize()} generated and saved at: {savepath.resolve()}")


if __name__ == "__main__":
    main()
    

