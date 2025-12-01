"""
Display manager for RGB LED Matrix
Uses hzeller/rpi-rgb-led-matrix library
"""

import logging
from typing import Optional, List, Tuple
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import bdfparser

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
    MATRIX_AVAILABLE = True
except ImportError:
    MATRIX_AVAILABLE = False
    logging.warning("rgbmatrix library not available - running in simulation mode")


class BDFFont:
    """Wrapper for BDF fonts to work with PIL ImageDraw"""

    def __init__(self, bdf_path):
        """Load a BDF font file"""
        self.font = bdfparser.Font(bdf_path)
        self.font_height = self.font.headers.get('FONT_ASCENT', 0) + abs(self.font.headers.get('FONT_DESCENT', 0))

    def getsize(self, text):
        """Get the size of text rendered with this font (deprecated but still used)"""
        width = 0
        for char in text:
            try:
                glyph = self.font.glyph(char)
                # Get advance width from glyph metadata (DWIDTH x value)
                width += glyph.meta.get('dwx0', self.font.headers.get('SPACING', 8))
            except KeyError:
                # Character not in font, use average width
                width += self.font.headers.get('SPACING', 8)
        return (width, self.font_height)

    def getbbox(self, text):
        """Get bounding box for text"""
        width = 0
        for char in text:
            try:
                glyph = self.font.glyph(char)
                # Get advance width from glyph metadata (DWIDTH x value)
                width += glyph.meta.get('dwx0', self.font.headers.get('SPACING', 8))
            except KeyError:
                # Character not in font, use average width
                width += self.font.headers.get('SPACING', 8)
        return (0, 0, width, self.font_height)

    def draw_text(self, draw, position, text, fill):
        """Draw text using BDF font on a PIL ImageDraw object"""
        x, y = position
        for char in text:
            try:
                glyph = self.font.glyph(char)
                # Draw the glyph bitmap
                bitmap = glyph.draw()
                for gy, row in enumerate(bitmap.todata(2)):
                    for gx, pixel in enumerate(row):
                        if pixel == '#':
                            # Adjust for glyph offset
                            px = x + gx + glyph.meta['bbx'][0]
                            py = y + gy + glyph.meta['bby'][1]
                            draw.point((px, py), fill=fill)
                # Get advance width from glyph metadata (DWIDTH x value)
                x += glyph.meta.get('dwx0', self.font.headers.get('SPACING', 8))
            except KeyError:
                # Character not in font, add space
                x += self.font.headers.get('SPACING', 8)


class DisplayManager:
    """Manages the RGB LED matrix display"""

    def __init__(self, config):
        """
        Initialize display manager

        Args:
            config: Config object with display settings
        """
        self.config = config
        self.matrix = None
        self.canvas = None
        self.current_image = None

        # Font cache
        self.fonts = {}
        self._load_fonts()

        # Initialize matrix
        if MATRIX_AVAILABLE:
            self._init_matrix()
        else:
            logging.warning("Matrix hardware not available - using simulation mode")

    def _init_matrix(self):
        """Initialize RGB matrix hardware"""
        options = RGBMatrixOptions()

        # Basic dimensions
        options.rows = self.config.data['display'].get('rows', 32)
        options.cols = self.config.display_width
        options.chain_length = self.config.data['display'].get('chain_length', 1)
        options.parallel = self.config.data['display'].get('parallel', 1)

        # Hardware mapping
        options.hardware_mapping = self.config.hardware_mapping

        # Quality settings
        options.pwm_bits = self.config.pwm_bits
        options.brightness = self.config.brightness
        options.gpio_slowdown = self.config.gpio_slowdown

        # Advanced options
        options.multiplexing = self.config.data['display'].get('multiplexing', 0)
        options.disable_hardware_pulsing = True  # Required for sound support

        try:
            self.matrix = RGBMatrix(options=options)
            self.canvas = self.matrix.CreateFrameCanvas()
            logging.info(f"Initialized {options.cols}x{options.rows} RGB matrix")
        except Exception as e:
            logging.error(f"Failed to initialize matrix: {e}")
            raise

    def _load_fonts(self):
        """Load BDF fonts for text rendering"""
        # Default fonts (PIL built-in)
        try:
            font_dir = Path(__file__).parent.parent / "fonts"

            # Default to PIL built-in fonts
            self.fonts = {
                1: ImageFont.load_default(),
                2: ImageFont.load_default(),
                3: ImageFont.load_default(),
                4: ImageFont.load_default(),
            }
            self.fonts_are_bdf = {1: False, 2: False, 3: False, 4: False}

            # Try to load BDF fonts if they exist
            if font_dir.exists():
                # Map specific BDF fonts to size slots
                font_mapping = {
                    1: "4x6.bdf",          # Small
                    2: "5x8.bdf",          # Medium
                    3: "ter-u12n.bdf",     # Large
                    4: "MatrixChunky8.bdf" # XLarge (will be scaled)
                }

                for size, filename in font_mapping.items():
                    font_path = font_dir / filename
                    if font_path.exists():
                        try:
                            self.fonts[size] = BDFFont(str(font_path))
                            self.fonts_are_bdf[size] = True
                            logging.info(f"Loaded BDF font size {size}: {filename}")
                        except Exception as e:
                            logging.warning(f"Could not load BDF font {filename}: {e}")

                # Also try TTF fonts as fallback
                ttf_files = list(font_dir.glob("*.ttf"))
                if ttf_files:
                    for size in [1, 2, 3, 4]:
                        if not self.fonts_are_bdf[size]:
                            try:
                                font_sizes = {1: 6, 2: 8, 3: 12, 4: 16}
                                self.fonts[size] = ImageFont.truetype(str(ttf_files[0]), font_sizes[size])
                                logging.info(f"Loaded TTF font for size {size}")
                            except Exception as e:
                                logging.warning(f"Could not load TTF font for size {size}: {e}")

        except Exception as e:
            logging.warning(f"Font loading error: {e}")

    def clear(self):
        """Clear the display"""
        if self.matrix:
            self.canvas.Clear()
            self.matrix.SwapOnVSync(self.canvas)

        self.current_image = None

    def show_text(self, parsed_lines: List[Tuple[int, int, str]]):
        """
        Display formatted text lines

        Args:
            parsed_lines: List of (color_index, font_size, text) tuples
        """
        if not parsed_lines:
            self.clear()
            return

        # Create image
        img = Image.new('RGB', (self.config.display_width, self.config.display_height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Get current palette
        palette = self.config.get_palette()

        # Calculate positions
        from .text_renderer import calculate_layout
        positioned_lines = calculate_layout(parsed_lines, self.config.display_height)

        # Draw each line
        for color_idx, size, y_pos, text in positioned_lines:
            if not text.strip():
                continue

            font = self.fonts.get(size, self.fonts[2])
            color = palette.get(color_idx, (255, 255, 255))

            # Check if this is a BDF font or regular PIL font
            is_bdf = self.fonts_are_bdf.get(size, False)

            if is_bdf:
                # BDF font - use custom draw method
                bbox = font.getbbox(text)
                text_width = bbox[2] - bbox[0]
                x_pos = (self.config.display_width - text_width) // 2
                font.draw_text(draw, (x_pos, y_pos), text, color)
            else:
                # Regular PIL font
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                x_pos = (self.config.display_width - text_width) // 2
                draw.text((x_pos, y_pos), text, font=font, fill=color)

        # Display image
        self._show_image(img)

    def show_preset(self, preset_name: str):
        """
        Show predefined layout

        Args:
            preset_name: Name of preset (ON-CALL, FREE, BUSY, QUIET, KNOCK)
        """
        preset_name = preset_name.upper().strip()

        preset_map = {
            "ON-CALL": [(2, 4, "ON-CALL"), (1, 3, "Urgent"), (1, 2, "Needs Only")],
            "FREE": [(3, 4, "FREE"), (1, 3, "But Knock")],
            "BUSY": [(2, 3, "BUSY"), (2, 3, "DO NOT"), (2, 3, "ENTER")],
            "QUIET": [(9, 3, "QUIET"), (22, 2, "MEETING IN"), (22, 2, "PROGRESS")],
            "KNOCK": [(9, 4, "KNOCK"), (22, 2, "MEETING IN"), (22, 2, "PROGRESS")],
        }

        if preset_name in preset_map:
            self.show_text(preset_map[preset_name])
        else:
            logging.warning(f"Unknown preset: {preset_name}")
            self.show_simple_message("Unknown", "Preset")

    def show_simple_message(self, line1: str, line2: Optional[str] = None):
        """
        Show simple 1-2 line message

        Args:
            line1: First line of text
            line2: Optional second line
        """
        lines = [(1, 2, line1)]  # White, medium
        if line2:
            lines.append((1, 2, line2))

        self.show_text(lines)

    def show_weather(self, weather_data: dict, condition: str):
        """
        Display weather information

        Args:
            weather_data: Dictionary with weather values
            condition: Weather condition code
        """
        # Create image
        img = Image.new('RGB', (self.config.display_width, self.config.display_height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)

        palette = self.config.get_palette()

        # Try to load weather icon
        icon_path = self._get_weather_icon_path(condition, weather_data.get('is_night', False))
        if icon_path and icon_path.exists():
            try:
                icon = Image.open(icon_path)
                # Resize if needed (assuming icons are 24x24)
                if icon.size != (24, 24):
                    icon = icon.resize((24, 24))
                # Place icon in top-right
                img.paste(icon, (40, 0))
            except Exception as e:
                logging.warning(f"Could not load weather icon: {e}")

        # Temperature (large, left side)
        temp = weather_data.get('temp', 0)
        temp_color = palette.get(weather_data.get('temp_color', 1), (255, 255, 255))
        temp_text = f"{temp}F"

        font_large = self.fonts[3]
        if self.fonts_are_bdf.get(3, False):
            font_large.draw_text(draw, (1, 0), temp_text, temp_color)
        else:
            draw.text((1, 0), temp_text, font=font_large, fill=temp_color)

        # Additional weather info (smaller, bottom)
        feels = weather_data.get('feels_like', temp)
        wind_speed = weather_data.get('wind_speed', 0)
        wind_dir = weather_data.get('wind_dir', 'N')
        humidity = weather_data.get('humidity', 0)

        font_small = self.fonts[1]
        info_color = palette[1]  # White

        # Line 2: Feels like
        if self.fonts_are_bdf.get(1, False):
            font_small.draw_text(draw, (1, 11), f"FL:{feels}F", info_color)
        else:
            draw.text((1, 11), f"FL:{feels}F", font=font_small, fill=info_color)

        # Line 3: Wind
        if self.fonts_are_bdf.get(1, False):
            font_small.draw_text(draw, (1, 18), f"W:{wind_dir} {wind_speed}", info_color)
        else:
            draw.text((1, 18), f"W:{wind_dir} {wind_speed}", font=font_small, fill=info_color)

        # Line 4: Humidity
        if self.fonts_are_bdf.get(1, False):
            font_small.draw_text(draw, (1, 25), f"H:{humidity}%", info_color)
        else:
            draw.text((1, 25), f"H:{humidity}%", font=font_small, fill=info_color)

        self._show_image(img)

    def _get_weather_icon_path(self, condition: str, is_night: bool) -> Optional[Path]:
        """Get path to weather icon file"""
        icon_dir = Path(__file__).parent.parent / "icons"

        if not icon_dir.exists():
            return None

        # Map condition to icon filename (simplified)
        icon_map = {
            "Clear": "clear",
            "MostlyClear": "mostly_clear",
            "PartlyCloudy": "partly_cloudy",
            "Cloudy": "cloudy",
            "Rain": "rain",
            "Snow": "snow",
            "Thunderstorms": "tstorm",
        }

        icon_base = icon_map.get(condition, "clear")
        suffix = "_night" if is_night else ""

        # Try PNG first, then BMP
        for ext in ['.png', '.bmp']:
            icon_path = icon_dir / f"{icon_base}{suffix}{ext}"
            if icon_path.exists():
                return icon_path

        return None

    def _show_image(self, img: Image.Image):
        """
        Display PIL Image on matrix

        Args:
            img: PIL Image to display
        """
        if not self.matrix:
            logging.debug("Matrix not available - image would be displayed")
            return

        try:
            # Ensure image is RGB mode
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Resize if needed
            if img.size != (self.config.display_width, self.config.display_height):
                img = img.resize((self.config.display_width, self.config.display_height))

            # Clear canvas
            self.canvas.Clear()

            # Set pixels
            for y in range(self.config.display_height):
                for x in range(self.config.display_width):
                    r, g, b = img.getpixel((x, y))
                    self.canvas.SetPixel(x, y, r, g, b)

            # Swap buffers
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            self.current_image = img

        except Exception as e:
            logging.error(f"Error displaying image: {e}")

    def set_brightness(self, brightness: int):
        """
        Set display brightness

        Args:
            brightness: Brightness level 0-100
        """
        if self.matrix:
            self.matrix.brightness = max(0, min(100, brightness))
            logging.debug(f"Set brightness to {brightness}")

    def __del__(self):
        """Cleanup on destruction"""
        if self.matrix:
            try:
                self.clear()
            except:
                pass
