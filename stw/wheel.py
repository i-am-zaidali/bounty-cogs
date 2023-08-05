import io
import math
import random
from collections import deque
from typing import List, Tuple

import imageio
from PIL import Image, ImageDraw, ImageFont
from redbot.core.data_manager import bundled_data_path

__all__ = ["get_animated_wheel", "draw_still_wheel"]


def get_animated_wheel(
    cog,
    section_labels: List[str],
    section_colors: List[Tuple[int, int, int]],
    width: int,
    height: int,
    num_frames: int,
):
    num_sections = len(section_labels)
    random.shuffle(section_colors)
    random.shuffle(section_labels)
    colors = deque(section_colors)

    color_label_map = dict(zip(colors, section_labels[1:] + section_labels[:2]))

    center: Tuple[int, int] = (width // 2, height // 2)
    radius: float = min(center) * 0.9

    section_angle: float = 360 / num_sections

    offset: float = section_angle / 2

    images: List[Image.Image] = []

    spins = random.randrange(round(num_frames / 2), num_frames) + 1

    # Create the frames
    for i in range(1, spins):
        # Create a new image
        img: Image.Image = Image.new("RGB", (width, height), (255, 255, 255))

        colors.appendleft(colors.pop())

        draw_sections(img, num_sections, section_angle, colors, center, radius, offset)
        draw_labels(cog, img, num_sections, section_angle, section_labels, center, radius, i - 1)
        draw_arrow(img, center, radius)

        images.append(img)

    # # Randomly spin the wheel
    # random_spin: int = random.randint(0, spins - 1)
    # part1 = images[random_spin:]
    # part2 = images[:random_spin]
    # images = part1 + part2

    # Save the frames as animated GIF to BytesIO
    animated_gif = io.BytesIO()
    imageio.mimsave(animated_gif, images, format="GIF", duration=1000 * 1 / 60)
    animated_gif.seek(0)
    # Return the color and text label of the section
    return animated_gif, color_label_map[colors[-1]]


def draw_still_wheel(
    cog,
    section_labels: List[str],
    section_colors: List[Tuple[int, int, int]],
    width: int,
    height: int,
):
    num_sections = len(section_labels)
    random.shuffle(section_colors)
    random.shuffle(section_labels)
    colors = deque(section_colors)

    center: Tuple[int, int] = (width // 2, height // 2)
    radius: float = min(center) * 0.9

    section_angle: float = 360 / num_sections

    offset: float = section_angle / 2

    # Create a new image
    img: Image.Image = Image.new("RGB", (width, height), (255, 255, 255))

    draw_sections(img, num_sections, section_angle, colors, center, radius, offset)
    draw_labels(cog, img, num_sections, section_angle, section_labels, center, radius)
    draw_arrow(img, center, radius)

    # Save the frames as animated GIF to BytesIO
    image = io.BytesIO()
    img.save(image, format="PNG")
    image.seek(0)
    # Return the color and text label of the section
    return image


def draw_sections(
    img: Image.Image,
    num_sections: int,
    section_angle: float,
    section_colors: List[Tuple[int, int, int]],
    center: Tuple[int, int],
    radius: float,
    offset: float,
) -> None:
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
    start_angle: float = 0
    for j in range(num_sections):
        end_angle: float = start_angle + section_angle
        bbox: Tuple[Tuple[int, int], Tuple[int, int]] = [
            (center[0] - radius, center[1] - radius),
            (center[0] + radius, center[1] + radius),
        ]
        draw.pieslice(
            bbox,
            start_angle + offset,
            end_angle + offset,
            fill=section_colors[j],
            outline=(0, 0, 0),
        )
        start_angle = end_angle


def draw_labels(
    cog,
    img: Image.Image,
    num_sections: int,
    section_angle: float,
    section_labels: List[str],
    center: Tuple[int, int],
    radius: float,
    iteration: int = 1,
) -> None:
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(bundled_data_path(cog) / "arial.ttf"), 30)
    for j in range(1, num_sections + 1):
        sa: float = j * section_angle
        mid_angle: float = math.radians(sa)
        label: str = section_labels[j - 1]
        label_bbox: Tuple[int, int, int, int] = font.getbbox(label)
        label_width: float = label_bbox[2] - label_bbox[0]
        label_height: float = label_bbox[3] - label_bbox[1]
        label_angle: float = mid_angle + iteration * math.radians(section_angle)
        label_x: float = center[0] + (radius * 0.7) * math.cos(label_angle) - label_width / 2
        label_y: float = center[1] + (radius * 0.7) * math.sin(label_angle) - label_height / 2
        draw.text((label_x, label_y), label, font=font, fill=(0, 0, 0))


def draw_arrow(img: Image.Image, center: Tuple[int, int], radius: float) -> None:
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
    arrow_points: List[Tuple[int, int]] = [
        (center[0] + radius + 20, center[1] - 40 / 2),
        (center[0] + radius, center[1]),
        (center[0] + radius + 20, center[1] + 40 / 2),
    ]
    draw.polygon(arrow_points, fill=(0, 0, 0))


# def get_random_colors(n):
#     for i in range(n):
#         r = random.randint(0, 255)
#         g = random.randint(0, 255)
#         b = random.randint(0, 255)
#         yield (r, g, b)


# img, selected = get_animated_wheel(
#     ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
#     list(get_random_colors(10)),
#     500,
#     500,
#     60,
# )
# with open("wheel.gif", "wb") as f:
#     f.write(img.getvalue())
