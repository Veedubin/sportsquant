"""Hero card image generator for Discord Top Insights.

Generates a PNG matchup card image with team logos, date/time, and branding.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from sportsquant.notifications.models import Event


@dataclass(frozen=True)
class HeroCardConfig:
    """Configuration for hero card generation."""

    width: int = 1000
    height: int = 500
    padding: int = 40
    logo_size: int = 120
    font_size_large: int = 48
    font_size_medium: int = 32
    font_size_small: int = 24

    # Colors (hex to RGB)
    color_teal: tuple[int, int, int] = (20, 120, 130)
    color_plum: tuple[int, int, int] = (80, 40, 100)
    color_text: tuple[int, int, int] = (250, 250, 250)
    color_text_dark: tuple[int, int, int] = (20, 20, 30)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color string to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return (20, 20, 30)  # Fallback to dark
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b)


def interpolate_color(
    color1: tuple[int, int, int], color2: tuple[int, int, int], factor: float
) -> tuple[int, int, int]:
    """Interpolate between two colors."""
    return tuple(int(color1[i] + factor * (color2[i] - color1[i])) for i in range(3))


def download_team_logo(url: str | None, size: int) -> Image.Image | None:
    """Download team logo from URL. Returns None if unavailable."""
    if not url:
        return None

    try:
        import httpx  # pylint: disable=import-outside-toplevel

        response = httpx.get(url, timeout=10.0)
        if response.status_code == 200:
            image = Image.open(BytesIO(response.content))
            image = image.resize((size, size), Image.Resampling.LANCZOS)
            return image
    except Exception:
        pass

    return None


def create_placeholder_logo(abbr: str, size: int, bg_color: tuple[int, int, int]) -> Image.Image:
    """Create a placeholder circular badge with team abbreviation."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw circle with background color
    margin = size // 10
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=bg_color,
        outline=(*bg_color, 100),
        width=2,
    )

    # Draw abbreviation text
    try:
        font_size = size // 3
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    # Calculate text position for centering
    bbox = draw.textbbox((0, 0), abbr, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (size - text_width) // 2 - bbox[0]
    y = (size - text_height) // 2 - bbox[1]

    draw.text((x, y), abbr, fill=(255, 255, 255, 255), font=font)

    return image


def generate_hero_card(
    event: Event,
    config: HeroCardConfig | None = None,
) -> bytes:
    """Generate a hero card PNG for the given event.

    Args:
        event: Event with away_team, home_team, and display_time_local
        config: Optional configuration for card generation

    Returns:
        PNG image bytes
    """
    if config is None:
        config = HeroCardConfig()

    width = config.width
    height = config.height

    # Create image with transparent background
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw diagonal gradient background (teal to plum)
    for y in range(height):
        factor = y / height
        color = interpolate_color(config.color_teal, config.color_plum, factor)
        draw.line([(0, y), (width, y)], fill=color, width=1)

    # Get team colors (fallback to defaults if not provided)
    away_primary = hex_to_rgb(event.away_team.primary_color_hex)
    home_primary = hex_to_rgb(event.home_team.primary_color_hex)

    # Load fonts (fallback to default if not available)
    try:
        font_large = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            config.font_size_large,
        )
        font_medium = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            config.font_size_medium,
        )
        font_small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", config.font_size_small
        )
    except Exception:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Calculate positions
    logo_y = int(height * 0.30)
    team_y = int(height * 0.55)
    time_y = int(height * 0.70)
    subtitle_y = int(height * 0.88)

    # Left team logo
    left_logo_x = int(width * 0.25)
    away_logo = download_team_logo(event.away_team.logo_url, config.logo_size)
    if away_logo is None:
        away_logo = create_placeholder_logo(event.away_team.abbr, config.logo_size, away_primary)
    image.paste(
        away_logo,
        (left_logo_x - config.logo_size // 2, logo_y - config.logo_size // 2),
        away_logo,
    )

    # Right team logo
    right_logo_x = int(width * 0.75)
    home_logo = download_team_logo(event.home_team.logo_url, config.logo_size)
    if home_logo is None:
        home_logo = create_placeholder_logo(event.home_team.abbr, config.logo_size, home_primary)
    image.paste(
        home_logo,
        (right_logo_x - config.logo_size // 2, logo_y - config.logo_size // 2),
        home_logo,
    )

    # Center "@" symbol
    at_text = "@"
    at_font_size = int(config.font_size_large * 1.5)
    try:
        at_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", at_font_size
        )
    except Exception:
        at_font = font_large

    bbox = draw.textbbox((0, 0), at_text, font=at_font)
    at_width = bbox[2] - bbox[0]
    at_height = bbox[3] - bbox[1]
    draw.text(
        (width // 2 - at_width // 2, logo_y - at_height // 2 - 10),
        at_text,
        fill=config.color_text,
        font=at_font,
    )

    # Team names
    away_name = event.away_team.short_name or event.away_team.name
    home_name = event.home_team.short_name or event.home_team.name

    # Draw away team name (centered under left logo)
    bbox = draw.textbbox((0, 0), away_name, font=font_large)
    text_width = bbox[2] - bbox[0]
    draw.text(
        (left_logo_x - text_width // 2 - bbox[0], team_y),
        away_name,
        fill=config.color_text,
        font=font_large,
    )

    # Draw home team name (centered under right logo)
    bbox = draw.textbbox((0, 0), home_name, font=font_large)
    text_width = bbox[2] - bbox[0]
    draw.text(
        (right_logo_x - text_width // 2 - bbox[0], team_y),
        home_name,
        fill=config.color_text,
        font=font_large,
    )

    # Date/time
    time_text = event.display_time_local
    bbox = draw.textbbox((0, 0), time_text, font=font_medium)
    text_width = bbox[2] - bbox[0]
    draw.text(
        (width // 2 - text_width // 2 - bbox[0], time_y),
        time_text,
        fill=config.color_text,
        font=font_medium,
    )

    # Subtitle
    subtitle = event.hero_card.subtitle if event.hero_card else "Trending Insights"
    bbox = draw.textbbox((0, 0), subtitle, font=font_small)
    text_width = bbox[2] - bbox[0]
    draw.text(
        (width // 2 - text_width // 2 - bbox[0], subtitle_y),
        subtitle,
        fill=config.color_text,
        font=font_small,
    )

    # Convert to PNG bytes
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def save_hero_card(
    event: Event,
    output_path: Path | str,
    config: HeroCardConfig | None = None,
) -> None:
    """Save hero card to file."""
    png_bytes = generate_hero_card(event, config)
    with open(output_path, "wb") as f:
        f.write(png_bytes)


def get_hero_card_bytes(
    event: Event,
    config: HeroCardConfig | None = None,
) -> bytes:
    """Get hero card as bytes (for webhook attachment)."""
    return generate_hero_card(event, config)
