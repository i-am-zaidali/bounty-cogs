import io
import math
import random
from collections import deque
from pathlib import Path
from typing import List, Tuple

import imageio
from PIL import Image, ImageDraw, ImageFont

__all__ = ["get_animated_wheel", "draw_still_wheel"]


def get_animated_wheel(
    cog_path: Path,
    section_labels: List[Tuple[str, int]],
    section_colors: List[Tuple[int, int, int]],
    width: int,
    height: int,
    num_frames: int = 60,
):
    num_sections = len(section_labels)
    labels: List[str]
    weights: List[int]
    labels, weights = map(list, zip(*section_labels))
    random.shuffle(section_colors)
    random.shuffle(labels)
    colors = deque(section_colors)

    color_label_map = dict(zip(colors, labels[1:] + labels[:2]))

    center: Tuple[int, int] = (width // 2, height // 2)
    radius: float = min(center) * 0.9

    section_angle: float = 360 / num_sections

    offset: float = section_angle / 2

    images: List[Image.Image] = []

    final = random.choices(labels, weights=weights)[0]
    index_final = labels.index(final)

    closest_multiple = (num_frames // num_sections) * num_sections

    spins = closest_multiple + (abs(index_final - num_sections) - 1)

    # Create the frames
    for i in range(spins):
        # Create a new image
        img: Image.Image = Image.new("RGB", (width, height), (255, 255, 255))

        colors.appendleft(colors.pop())

        draw_sections(img, num_sections, section_angle, colors, center, radius, offset)
        draw_labels(
            cog_path, img, num_sections, section_angle, labels, center, radius, i
        )
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
    cog_path: Path,
    section_labels: List[str],
    section_colors: List[Tuple[int, int, int]],
    width: int,
    height: int,
):
    num_sections = len(section_labels)
    labels, weights = map(list, zip(*section_labels))
    random.shuffle(section_colors)
    random.shuffle(labels)
    colors = deque(section_colors)

    center: Tuple[int, int] = (width // 2, height // 2)
    radius: float = min(center) * 0.9

    section_angle: float = 360 / num_sections

    offset: float = section_angle / 2

    # Create a new image
    img: Image.Image = Image.new("RGB", (width, height), (255, 255, 255))

    draw_sections(img, num_sections, section_angle, colors, center, radius, offset)
    draw_labels(cog_path, img, num_sections, section_angle, labels, center, radius)
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
    cog_path: Path,
    img: Image.Image,
    num_sections: int,
    section_angle: float,
    section_labels: List[str],
    center: Tuple[int, int],
    radius: float,
    iteration: int = 1,
) -> None:
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(cog_path / "arial.ttf"), 30)
    for j in range(1, num_sections + 1):
        sa: float = j * section_angle
        mid_angle: float = math.radians(sa)
        label: str = section_labels[j - 1]
        label_bbox: Tuple[int, int, int, int] = font.getbbox(label)
        label_width: float = label_bbox[2] - label_bbox[0]
        label_height: float = label_bbox[3] - label_bbox[1]
        label_angle: float = mid_angle + math.radians(iteration * section_angle)
        label_x: float = (
            center[0] + (radius * 0.7) * math.cos(label_angle) - label_width / 2
        )
        label_y: float = (
            center[1] + (radius * 0.7) * math.sin(label_angle) - label_height / 2
        )
        draw.text(
            (label_x, label_y),
            label,
            font=font,
            fill=(0, 0, 0),
        )


def draw_arrow(img: Image.Image, center: Tuple[int, int], radius: float) -> None:
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
    arrow_size = radius / 10  # Increase arrow size based on radius
    arrow_points: List[Tuple[int, int]] = [
        (center[0] + radius + arrow_size, center[1] - arrow_size / 2),
        (center[0] + radius, center[1]),
        (center[0] + radius + arrow_size, center[1] + arrow_size / 2),
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
