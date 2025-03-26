import io
import pathlib

from PIL import Image, ImageDraw, ImageFont


class RiskMapGenerator:
    @staticmethod
    def get_text_color(background_color: tuple[int, int, int, int]):
        """Returns black or white text color based on the brightness of the background."""
        r, g, b = background_color[:3]
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        return (0, 0, 0) if brightness > 128 else (255, 255, 255)

    @staticmethod
    def color_territories(
        clear_image_path: pathlib.Path,
        territory_colors: dict[tuple[int, int], tuple[int, int, int, int]],
        territory_armies: dict[tuple[int, int], str],
    ):
        """Colors the given territories on the RISK map and overlays army counts with contrast-aware text."""
        image = Image.open(clear_image_path).convert("RGBA")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=50)

        for coords, color in territory_colors.items():
            ImageDraw.floodfill(image, coords, (*color[:3], 255), thresh=30)

        # Overlay army counts
        for (x, y), armies in territory_armies.items():
            text = armies
            text_size = draw.textbbox((0, 0), text, font=font)
            text_x, text_y = text_size[2] - text_size[0], text_size[3] - text_size[1]

            adjusted_x = x - text_x // 2
            adjusted_y = y - text_y // 2

            background_color = image.getpixel((x, y))
            text_color = RiskMapGenerator.get_text_color(background_color)

            draw.text((adjusted_x, adjusted_y), text, fill=text_color, font=font)

        file = io.BytesIO()
        image.save(file, format="PNG")
        file.seek(0)
        return file
