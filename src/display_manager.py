"""
Display manager for RGB LED Matrix
Uses hzeller/rpi-rgb-led-matrix library
"""

import logging
from typing import Optional, List, Tuple
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
    MATRIX_AVAILABLE = True
except ImportError:
    MATRIX_AVAILABLE = False
    logging.warning("rgbmatrix library not available - running in simulation mode")


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
        """Load fonts for text rendering using native graphics.Font() for BDF"""
        try:
            font_dir = Path(__file__).parent.parent / "fonts"

            # Default to PIL built-in fonts
            self.fonts = {
                1: ImageFont.load_default(),
                2: ImageFont.load_default(),
                3: ImageFont.load_default(),
                4: ImageFont.load_default(),
                5: ImageFont.load_default(),
                6: ImageFont.load_default(),
            }
            self.fonts_are_bdf = {1: False, 2: False, 3: False, 4: False, 5: False, 6: False}

            # Font ascent values for BDF fonts (converts top-left to baseline positioning)
            # graphics.DrawText() uses baseline, CircuitPython used top-left anchor
            self.font_ascents = {
                1: 5,   # 4x6.bdf ascent
                2: 7,   # 5x8.bdf ascent
                3: 10,  # ter-u12n.bdf ascent
                4: 12,  # 9x15.bdf ascent
                5: 16,  # 10x20.bdf ascent
                6: 19,  # texgyre-27.bdf ascent
            }

            # Try to load BDF fonts using native graphics.Font() if available
            if font_dir.exists() and MATRIX_AVAILABLE:
                # Map specific BDF fonts to size slots
                # Sizes 4-6 provide graduated large font options
                font_mapping = {
                    1: "4x6.bdf",          # Small (6px)
                    2: "5x8.bdf",          # Medium (8px)
                    3: "ter-u12n.bdf",     # Large (12px)
                    4: "9x15B.bdf",        # XLarge Bold (15px) - fits ON-CALL preset
                    5: "10x20.bdf",        # XXLarge (20px)
                    6: "texgyre-27.bdf",   # Huge (24px) - for FREE preset
                }

                for size, filename in font_mapping.items():
                    font_path = font_dir / filename
                    if font_path.exists():
                        try:
                            # Use native graphics.Font() for BDF fonts
                            font = graphics.Font()
                            font.LoadFont(str(font_path))
                            self.fonts[size] = font
                            self.fonts_are_bdf[size] = True
                            logging.info(f"Loaded BDF font size {size}: {filename}")
                        except Exception as e:
                            logging.warning(f"Could not load BDF font {filename}: {e}")

                # Also try TTF fonts as fallback for sizes not loaded
                ttf_files = list(font_dir.glob("*.ttf"))
                if ttf_files:
                    for size in [1, 2, 3, 4, 5, 6]:
                        if not self.fonts_are_bdf[size]:
                            try:
                                font_sizes = {1: 6, 2: 8, 3: 12, 4: 15, 5: 20, 6: 24}
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

        # Get current palette
        palette = self.config.get_palette()

        # Calculate positions
        from .text_renderer import calculate_layout
        positioned_lines = calculate_layout(parsed_lines, self.config.display_height)

        # Check if all fonts are BDF (can use direct canvas drawing)
        all_bdf = all(self.fonts_are_bdf.get(size, False) for _, size, _, _ in positioned_lines)

        if all_bdf and self.matrix:
            # All BDF fonts - draw directly on canvas for better performance
            self.canvas.Clear()

            # First pass: calculate text widths by drawing offscreen
            text_info = []
            for color_idx, size, y_pos, text in positioned_lines:
                if not text.strip():
                    continue

                font = self.fonts.get(size, self.fonts[2])
                color = palette.get(color_idx, (255, 255, 255))
                text_color = graphics.Color(color[0], color[1], color[2])

                # Draw at position -1000 to measure width without being visible
                text_width = graphics.DrawText(self.canvas, font, -1000, y_pos, text_color, text)
                x_pos = (self.config.display_width - text_width) // 2

                # Manual horizontal offset for specific text
                if text == "ON-CALL":
                    x_pos += 1  # Move right by 1px

                # Convert from top-left positioning to baseline positioning
                # CircuitPython used anchor_point=(0.5, 0) where y is top of text
                # graphics.DrawText() expects y to be the baseline
                baseline_y = y_pos + self.font_ascents.get(size, 7)

                text_info.append((font, x_pos, baseline_y, text_color, text))

            # Clear canvas and draw all text at correct positions
            self.canvas.Clear()
            for font, x_pos, baseline_y, text_color, text in text_info:
                graphics.DrawText(self.canvas, font, x_pos, baseline_y, text_color, text)

            # Swap canvas to display
            self.canvas = self.matrix.SwapOnVSync(self.canvas)

        else:
            # Mixed fonts or PIL only - use image-based rendering
            img = Image.new('RGB', (self.config.display_width, self.config.display_height), color=(0, 0, 0))
            draw = ImageDraw.Draw(img)

            for color_idx, size, y_pos, text in positioned_lines:
                if not text.strip():
                    continue

                font = self.fonts.get(size, self.fonts[2])
                color = palette.get(color_idx, (255, 255, 255))

                # Regular PIL font
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                x_pos = (self.config.display_width - text_width) // 2

                # Manual horizontal offset for specific text
                if text == "ON-CALL":
                    x_pos += 1  # Move right by 1px

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
            "FREE": [(3, 6, "FREE"), (1, 3, "But Knock")],
            "BUSY": [(2, 3, "BUSY"), (2, 3, "DO NOT"), (2, 3, "ENTER")],
            "QUIET": [(9, 6, "QUIET"), (22, 2, "MEETING IN"), (22, 2, "PROGRESS")],
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
            font_large.draw_text(img, (1, 0), temp_text, temp_color)
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
            font_small.draw_text(img, (1, 11), f"FL:{feels}F", info_color)
        else:
            draw.text((1, 11), f"FL:{feels}F", font=font_small, fill=info_color)

        # Line 3: Wind
        if self.fonts_are_bdf.get(1, False):
            font_small.draw_text(img, (1, 18), f"W:{wind_dir} {wind_speed}", info_color)
        else:
            draw.text((1, 18), f"W:{wind_dir} {wind_speed}", font=font_small, fill=info_color)

        # Line 4: Humidity
        if self.fonts_are_bdf.get(1, False):
            font_small.draw_text(img, (1, 25), f"H:{humidity}%", info_color)
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
