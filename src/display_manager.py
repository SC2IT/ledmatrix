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

        # Forecast carousel state
        self.carousel_view = 0  # 0 = hourly, 1 = daily

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

        # Hardware pulse (improves display quality but disables sound)
        # When True: enables hardware pulse, disables sound
        # When False: disables hardware pulse, enables sound support
        options.disable_hardware_pulsing = not self.config.hardware_pulse

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
                7: ImageFont.load_default(),
            }
            self.fonts_are_bdf = {1: False, 2: False, 3: False, 4: False, 5: False, 6: False, 7: False}

            # Font ascent values for BDF fonts (converts top-left to baseline positioning)
            # graphics.DrawText() uses baseline, CircuitPython used top-left anchor
            self.font_ascents = {
                1: 5,   # 4x6.bdf ascent
                2: 7,   # 5x8.bdf ascent
                3: 10,  # ter-u12n.bdf ascent
                4: 12,  # 9x15B.bdf ascent
                5: 16,  # 10x20.bdf ascent
                6: 17,  # ter-u22n.bdf ascent
                7: 19,  # texgyre-27.bdf ascent
            }

            # Try to load BDF fonts using native graphics.Font() if available
            if font_dir.exists() and MATRIX_AVAILABLE:
                # Map specific BDF fonts to size slots
                # Sizes 4-7 provide graduated large font options
                font_mapping = {
                    1: "4x6.bdf",          # Small (6px)
                    2: "5x8.bdf",          # Medium (8px)
                    3: "ter-u12n.bdf",     # Large (12px)
                    4: "9x15B.bdf",        # XLarge Bold (15px) - for ON-CALL preset
                    5: "10x20.bdf",        # XXLarge (20px)
                    6: "ter-u22b.bdf",     # Huge Bold (22px) - for QUIET preset
                    7: "texgyre-27.bdf",   # Massive (24px) - for FREE preset
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
                    for size in [1, 2, 3, 4, 5, 6, 7]:
                        if not self.fonts_are_bdf[size]:
                            try:
                                font_sizes = {1: 6, 2: 8, 3: 12, 4: 15, 5: 20, 6: 22, 7: 24}
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

        # Sync hardware brightness with day/night mode
        self.sync_brightness_with_night_mode()

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
            "FREE": [(3, 7, "FREE"), (1, 3, "But Knock")],
            "BUSY": [(2, 3, "BUSY"), (2, 3, "DO NOT"), (2, 3, "ENTER")],
            "QUIET": [(9, 6, "QUIET"), (22, 2, "MEETING IN"), (22, 2, "PROGRESS")],
            "KNOCK": [(4, 6, "KNOCK"), (22, 2, "MEETING IN"), (22, 2, "PROGRESS")],
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
        Display weather information using BDF fonts and direct canvas rendering

        Args:
            weather_data: Dictionary with weather values
            condition: Weather condition code
        """
        if not self.matrix:
            logging.debug("Matrix not available - weather would be displayed")
            return

        try:
            # Sync hardware brightness with day/night mode
            self.sync_brightness_with_night_mode()

            palette = self.config.get_palette()

            # Clear canvas
            self.canvas.Clear()
            logging.debug(f"Rendering weather: condition={condition}, is_night={weather_data.get('is_night', False)}")

            # Try to load and draw weather icon
            icon_path = self._get_weather_icon_path(condition, weather_data.get('is_night', False))
            logging.debug(f"Weather icon path: {icon_path}")

            if icon_path and icon_path.exists():
                try:
                    logging.info(f"Loading weather icon: {icon_path}")
                    icon = Image.open(icon_path)
                    # Resize if needed (assuming icons are 24x24)
                    if icon.size != (24, 24):
                        icon = icon.resize((24, 24))

                    # Convert to RGB if needed
                    if icon.mode != 'RGB':
                        icon = icon.convert('RGB')

                    # Draw icon pixel by pixel at top-right (x=40, y=0)
                    # Adjust brightness to match text (night palette is 25% = /4)
                    # Day: 2x boost, Night: 2x * 0.25 = 0.5x to match night palette
                    is_night = weather_data.get('is_night', False)
                    brightness_multiplier = 0.5 if is_night else 2.0

                    for y in range(min(24, self.config.display_height)):
                        for x in range(24):
                            if x + 40 < self.config.display_width:
                                r, g, b = icon.getpixel((x, y))
                                # Only draw non-black pixels (transparent background)
                                if r > 0 or g > 0 or b > 0:
                                    # Adjust brightness to match text
                                    r = min(255, int(r * brightness_multiplier))
                                    g = min(255, int(g * brightness_multiplier))
                                    b = min(255, int(b * brightness_multiplier))
                                    self.canvas.SetPixel(x + 40, y, r, g, b)
                    logging.info("Weather icon drawn successfully")
                except Exception as e:
                    logging.error(f"Error loading weather icon: {e}", exc_info=True)
            else:
                logging.warning(f"Weather icon not found: {icon_path}")

            # Get BDF fonts
            font_large = self.fonts.get(3, self.fonts[2])  # Size 3 for temperature
            font_small = self.fonts.get(1, self.fonts[2])  # Size 1 for details

            # Check if fonts are BDF
            if not self.fonts_are_bdf.get(3, False) or not self.fonts_are_bdf.get(1, False):
                logging.warning("BDF fonts not loaded, weather display may not render correctly")

            # Temperature (large, left side) - matches CircuitPython layout
            temp = weather_data.get('temp', 0)
            temp_color = palette.get(weather_data.get('temp_color', 1), (255, 255, 255))
            temp_str = str(temp)

            temp_graphics_color = graphics.Color(temp_color[0], temp_color[1], temp_color[2])
            baseline_y = 0 + self.font_ascents.get(3, 10)  # Convert top-left to baseline

            # Draw temperature number
            temp_width = graphics.DrawText(self.canvas, font_large, 1, baseline_y, temp_graphics_color, temp_str)

            # Draw "F" after temperature (positioned dynamically based on temp digits)
            f_x = 1 + len(temp_str) * 7 + 2
            graphics.DrawText(self.canvas, font_large, f_x, baseline_y, temp_graphics_color, "F")

            # Additional weather info (smaller, bottom) - matches CircuitPython positions
            feels = weather_data.get('feels_like', temp)
            feels_color = palette.get(weather_data.get('feels_like_color', 1), (255, 255, 255))
            wind_speed = weather_data.get('wind_speed', 0)
            wind_dir = weather_data.get('wind_dir', 'N')
            humidity = weather_data.get('humidity', 0)

            # Line 2: Feels like (y=10) - feels_like colored
            feels_graphics_color = graphics.Color(feels_color[0], feels_color[1], feels_color[2])
            baseline_y2 = 10 + self.font_ascents.get(2, 7)
            graphics.DrawText(self.canvas, self.fonts.get(2, font_small), 1, baseline_y2, feels_graphics_color, f"FL{feels}F")

            # Line 3: Wind (y=17) - color 8 (orange) with 2px spacing between components
            wind_color = palette.get(8, (255, 165, 0))  # Orange
            wind_graphics_color = graphics.Color(wind_color[0], wind_color[1], wind_color[2])
            baseline_y3 = 17 + self.font_ascents.get(2, 7)

            # Draw wind components separately with 2px spacing
            current_x = 1
            # Draw direction
            dir_width = graphics.DrawText(self.canvas, self.fonts.get(2, font_small), current_x, baseline_y3, wind_graphics_color, wind_dir)
            current_x += dir_width + 2  # 2px spacing

            # Draw speed
            speed_str = f"{wind_speed:02d}"
            speed_width = graphics.DrawText(self.canvas, self.fonts.get(2, font_small), current_x, baseline_y3, wind_graphics_color, speed_str)
            current_x += speed_width + 2  # 2px spacing

            # Draw MPH
            graphics.DrawText(self.canvas, self.fonts.get(2, font_small), current_x, baseline_y3, wind_graphics_color, "MPH")

            # Line 4: Humidity (y=24) - color 9 (pink/magenta)
            humidity_color = palette.get(9, (255, 0, 255))  # Pink/Magenta
            humidity_graphics_color = graphics.Color(humidity_color[0], humidity_color[1], humidity_color[2])
            baseline_y4 = 24 + self.font_ascents.get(2, 7)
            graphics.DrawText(self.canvas, self.fonts.get(2, font_small), 1, baseline_y4, humidity_graphics_color, f"RH{humidity}%")

            # Pressure with trend arrow - right-aligned on same line as humidity
            pressure = weather_data.get('pressure', 0)
            pressure_trend = weather_data.get('pressure_trend', 'steady')

            # Map trend to arrow
            trend_arrows = {'rising': '↑', 'falling': '↓', 'steady': '→'}
            arrow = trend_arrows.get(pressure_trend.lower(), '→')

            # Split pressure into parts for smaller decimal point
            pressure_int = int(pressure)
            pressure_dec = int((pressure - pressure_int) * 100)  # Get 2 decimal places

            font_medium = self.fonts.get(2, font_small)
            font_tiny = self.fonts.get(1, font_small)

            # Measure widths offscreen
            arrow_int_width = graphics.DrawText(self.canvas, font_medium, -1000, baseline_y4, humidity_graphics_color, f"{arrow}{pressure_int}")
            period_width = graphics.DrawText(self.canvas, font_tiny, -1000, baseline_y4, humidity_graphics_color, ".")
            dec_width = graphics.DrawText(self.canvas, font_medium, -1000, baseline_y4, humidity_graphics_color, f"{pressure_dec:02d}")
            in_width = graphics.DrawText(self.canvas, font_tiny, -1000, baseline_y4 - 1, humidity_graphics_color, "in")

            # Calculate total width with tighter decimal spacing (reduce gaps by 1px each)
            leading_space = 2  # Space before arrow (away from %)
            tighter_spacing = -1  # Negative to overlap/tighten
            total_width = leading_space + arrow_int_width + period_width + tighter_spacing + dec_width + tighter_spacing + in_width
            pressure_x = self.config.display_width - total_width - 1  # 1px margin from right

            # Add leading space
            current_x = pressure_x + leading_space

            # Draw arrow + integer part (size 2)
            graphics.DrawText(self.canvas, font_medium, current_x, baseline_y4, humidity_graphics_color, f"{arrow}{pressure_int}")
            current_x += arrow_int_width

            # Draw period (size 1 - smaller) with tighter spacing
            graphics.DrawText(self.canvas, font_tiny, current_x + tighter_spacing, baseline_y4, humidity_graphics_color, ".")
            current_x += period_width + tighter_spacing

            # Draw decimal digits (size 2) with tighter spacing
            graphics.DrawText(self.canvas, font_medium, current_x + tighter_spacing, baseline_y4, humidity_graphics_color, f"{pressure_dec:02d}")
            current_x += dec_width + tighter_spacing

            # Draw "in" (size 1) moved up 3px from baseline
            graphics.DrawText(self.canvas, font_tiny, current_x, baseline_y4 - 1, humidity_graphics_color, "in")

            logging.debug("Weather text rendered, swapping canvas")
            # Swap canvas to display
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            logging.info("Weather display updated successfully")

        except Exception as e:
            logging.error(f"Error in show_weather: {e}", exc_info=True)
            # Try to clear and show error message
            try:
                self.show_simple_message("Weather", "Error")
            except:
                pass

    def show_weather_with_progress(self, weather_data: dict, condition: str, elapsed_seconds: float, duration: float):
        """
        Display weather information with progress bar (for 'Weather on the 8s')

        Args:
            weather_data: Dictionary with weather values
            condition: Weather condition code
            elapsed_seconds: Seconds elapsed in current display
            duration: Total duration to display (30 seconds)
        """
        if not self.matrix:
            logging.debug("Matrix not available - weather with progress would be displayed")
            return

        try:
            # Sync hardware brightness with day/night mode
            self.sync_brightness_with_night_mode()

            palette = self.config.get_palette()

            # Clear canvas
            self.canvas.Clear()
            logging.debug(f"Rendering weather with progress: condition={condition}, elapsed={elapsed_seconds:.1f}s")

            # Try to load and draw weather icon
            icon_path = self._get_weather_icon_path(condition, weather_data.get('is_night', False))

            if icon_path and icon_path.exists():
                try:
                    icon = Image.open(icon_path)
                    # Resize if needed (assuming icons are 24x24)
                    if icon.size != (24, 24):
                        icon = icon.resize((24, 24))

                    # Convert to RGB if needed
                    if icon.mode != 'RGB':
                        icon = icon.convert('RGB')

                    # Draw icon pixel by pixel at top-right (x=40, y=0)
                    is_night = weather_data.get('is_night', False)
                    brightness_multiplier = 0.5 if is_night else 2.0

                    for y in range(min(24, self.config.display_height)):
                        for x in range(24):
                            if x + 40 < self.config.display_width:
                                r, g, b = icon.getpixel((x, y))
                                # Only draw non-black pixels (transparent background)
                                if r > 0 or g > 0 or b > 0:
                                    # Adjust brightness to match text
                                    r = min(255, int(r * brightness_multiplier))
                                    g = min(255, int(g * brightness_multiplier))
                                    b = min(255, int(b * brightness_multiplier))
                                    self.canvas.SetPixel(x + 40, y, r, g, b)
                except Exception as e:
                    logging.error(f"Error loading weather icon: {e}", exc_info=True)

            # Get BDF fonts
            font_large = self.fonts.get(3, self.fonts[2])  # Size 3 for temperature
            font_small = self.fonts.get(1, self.fonts[2])  # Size 1 for details

            # Temperature (large, left side)
            temp = weather_data.get('temp', 0)
            temp_color = palette.get(weather_data.get('temp_color', 1), (255, 255, 255))
            temp_str = str(temp)

            temp_graphics_color = graphics.Color(temp_color[0], temp_color[1], temp_color[2])
            baseline_y = 0 + self.font_ascents.get(3, 10)

            # Draw temperature number
            temp_width = graphics.DrawText(self.canvas, font_large, 1, baseline_y, temp_graphics_color, temp_str)

            # Draw "F" after temperature
            f_x = 1 + len(temp_str) * 7 + 2
            graphics.DrawText(self.canvas, font_large, f_x, baseline_y, temp_graphics_color, "F")

            # Additional weather info (smaller, bottom)
            feels = weather_data.get('feels_like', temp)
            feels_color = palette.get(weather_data.get('feels_like_color', 1), (255, 255, 255))
            wind_speed = weather_data.get('wind_speed', 0)
            wind_dir = weather_data.get('wind_dir', 'N')
            humidity = weather_data.get('humidity', 0)

            # Line 2: Feels like (y=10)
            feels_graphics_color = graphics.Color(feels_color[0], feels_color[1], feels_color[2])
            baseline_y2 = 10 + self.font_ascents.get(2, 7)
            graphics.DrawText(self.canvas, self.fonts.get(2, font_small), 1, baseline_y2, feels_graphics_color, f"FL{feels}F")

            # Line 3: Wind (y=17) - with 2px spacing between components
            wind_color = palette.get(8, (255, 165, 0))  # Orange
            wind_graphics_color = graphics.Color(wind_color[0], wind_color[1], wind_color[2])
            baseline_y3 = 17 + self.font_ascents.get(2, 7)

            # Draw wind components separately with 2px spacing
            current_x = 1
            # Draw direction
            dir_width = graphics.DrawText(self.canvas, self.fonts.get(2, font_small), current_x, baseline_y3, wind_graphics_color, wind_dir)
            current_x += dir_width + 2  # 2px spacing

            # Draw speed
            speed_str = f"{wind_speed:02d}"
            speed_width = graphics.DrawText(self.canvas, self.fonts.get(2, font_small), current_x, baseline_y3, wind_graphics_color, speed_str)
            current_x += speed_width + 2  # 2px spacing

            # Draw MPH
            graphics.DrawText(self.canvas, self.fonts.get(2, font_small), current_x, baseline_y3, wind_graphics_color, "MPH")

            # Line 4: Humidity (y=24)
            humidity_color = palette.get(9, (255, 0, 255))  # Pink/Magenta
            humidity_graphics_color = graphics.Color(humidity_color[0], humidity_color[1], humidity_color[2])
            baseline_y4 = 24 + self.font_ascents.get(2, 7)
            graphics.DrawText(self.canvas, self.fonts.get(2, font_small), 1, baseline_y4, humidity_graphics_color, f"RH{humidity}%")

            # Pressure with trend arrow - right-aligned on same line as humidity
            pressure = weather_data.get('pressure', 0)
            pressure_trend = weather_data.get('pressure_trend', 'steady')

            # Map trend to arrow
            trend_arrows = {'rising': '↑', 'falling': '↓', 'steady': '→'}
            arrow = trend_arrows.get(pressure_trend.lower(), '→')

            # Split pressure into parts for smaller decimal point
            pressure_int = int(pressure)
            pressure_dec = int((pressure - pressure_int) * 100)

            font_medium = self.fonts.get(2, font_small)
            font_tiny = self.fonts.get(1, font_small)

            # Measure widths offscreen
            arrow_int_width = graphics.DrawText(self.canvas, font_medium, -1000, baseline_y4, humidity_graphics_color, f"{arrow}{pressure_int}")
            period_width = graphics.DrawText(self.canvas, font_tiny, -1000, baseline_y4, humidity_graphics_color, ".")
            dec_width = graphics.DrawText(self.canvas, font_medium, -1000, baseline_y4, humidity_graphics_color, f"{pressure_dec:02d}")
            in_width = graphics.DrawText(self.canvas, font_tiny, -1000, baseline_y4 - 1, humidity_graphics_color, "in")

            # Calculate total width with tighter decimal spacing
            leading_space = 2
            tighter_spacing = -1
            total_width = leading_space + arrow_int_width + period_width + tighter_spacing + dec_width + tighter_spacing + in_width
            pressure_x = self.config.display_width - total_width - 1

            # Add leading space
            current_x = pressure_x + leading_space

            # Draw arrow + integer part
            graphics.DrawText(self.canvas, font_medium, current_x, baseline_y4, humidity_graphics_color, f"{arrow}{pressure_int}")
            current_x += arrow_int_width

            # Draw period with tighter spacing
            graphics.DrawText(self.canvas, font_tiny, current_x + tighter_spacing, baseline_y4, humidity_graphics_color, ".")
            current_x += period_width + tighter_spacing

            # Draw decimal digits with tighter spacing
            graphics.DrawText(self.canvas, font_medium, current_x + tighter_spacing, baseline_y4, humidity_graphics_color, f"{pressure_dec:02d}")
            current_x += dec_width + tighter_spacing

            # Draw "in" moved up 1px from baseline
            graphics.DrawText(self.canvas, font_tiny, current_x, baseline_y4 - 1, humidity_graphics_color, "in")

            # Progress bar on row 31 (30-second countdown)
            progress = min(1.0, elapsed_seconds / duration)
            bar_width = int(progress * self.config.display_width)

            # Color gradient from palette: cyan -> yellow -> orange -> red
            if progress < 0.5:
                color_rgb = palette.get(7, (0, 255, 255))  # Cyan
            elif progress < 0.8:
                color_rgb = palette.get(5, (255, 255, 0))  # Yellow
            elif progress < 0.95:
                color_rgb = palette.get(8, (255, 128, 0))  # Orange
            else:
                color_rgb = palette.get(2, (255, 0, 0))  # Red (warning: about to resume)

            # Draw filled portion of progress bar
            for x in range(bar_width):
                self.canvas.SetPixel(x, 31, color_rgb[0], color_rgb[1], color_rgb[2])

            # Swap canvas to display
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            logging.debug("Weather with progress display updated")

        except Exception as e:
            logging.error(f"Error in show_weather_with_progress: {e}", exc_info=True)
            try:
                self.show_simple_message("Weather", "Error")
            except:
                pass

    def flip_carousel_view(self):
        """Flip to next carousel view"""
        self.carousel_view = 1 - self.carousel_view
        logging.info(f"Carousel flipped to: {'DAILY' if self.carousel_view else 'HOURLY'}")

    def show_forecast_carousel(self, current_weather: dict, hourly_forecasts: dict,
                               daily_forecasts: dict, elapsed_seconds: float):
        """Display forecast carousel with auto-flip and progress bar"""
        if not self.matrix:
            return

        try:
            self.sync_brightness_with_night_mode()
            self.canvas.Clear()

            # Render active view
            if self.carousel_view == 0:
                self._render_hourly_view(current_weather, hourly_forecasts)
            else:
                self._render_daily_view(daily_forecasts, current_weather)

            # Draw progress bar on row 31
            self._render_progress_bar(elapsed_seconds)

            self.canvas = self.matrix.SwapOnVSync(self.canvas)

        except Exception as e:
            logging.error(f"Error in show_forecast_carousel: {e}", exc_info=True)

    def _get_temp_color_index(self, temp_f: int) -> int:
        """Get palette color index for temperature"""
        if temp_f <= 32:
            return 4  # Blue
        if temp_f >= 100:
            return 2  # Red
        progress = (temp_f - 32) / 68.0
        if progress < 0.4:
            return 7  # Cyan
        if progress <= 0.603:
            return 3  # Green
        if progress < 0.8:
            return 5  # Yellow
        return 8  # Orange

    def _abbreviate_condition(self, condition: str) -> str:
        """Abbreviate weather condition to 2-4 chars"""
        abbrev_map = {
            'Clear': 'CLR',
            'MostlyClear': 'CLR',
            'PartlyCloudy': 'PC',
            'MostlyCloudy': 'CLY',
            'Cloudy': 'CLY',
            'Rain': 'RN',
            'Drizzle': 'DRZ',
            'Snow': 'SNW',
            'Sleet': 'SLT',
            'Hail': 'HAIL',
            'Thunderstorm': 'THND',
            'Fog': 'FOG',
            'Windy': 'WND'
        }
        return abbrev_map.get(condition, condition[:3].upper())

    def _render_hourly_view(self, current_weather: dict, hourly_forecasts: dict):
        """Render 3-panel hourly forecast: NOW | +6H | +12H"""
        palette = self.config.get_palette()
        font_tiny = self.fonts.get(1)
        font_small = self.fonts.get(2)

        panels = [
            {'x': 0, 'width': 21, 'label': 'NOW', 'data': current_weather},
            {'x': 21, 'width': 21, 'label': '+6H', 'data': hourly_forecasts.get(6)},
            {'x': 43, 'width': 21, 'label': '+12H', 'data': hourly_forecasts.get(12)}
        ]

        for panel in panels:
            if not panel['data']:
                continue

            x_offset = panel['x']
            w = panel['width']

            # Line 1: Time label (centered, from palette)
            label_rgb = palette.get(1, (255, 255, 255))  # White (dimmed at night)
            label_color = graphics.Color(label_rgb[0], label_rgb[1], label_rgb[2])
            label_w = graphics.DrawText(self.canvas, font_tiny, -1000, 0, label_color, panel['label'])
            label_x = x_offset + (w - label_w) // 2
            graphics.DrawText(self.canvas, font_tiny, label_x,
                             self.font_ascents.get(1, 5), label_color, panel['label'])

            # Line 2: Temperature (centered, color-coded) - matches daily view
            temp = panel['data'].get('temp', 0)
            temp_str = str(temp)
            temp_idx = self._get_temp_color_index(temp)
            temp_rgb = palette.get(temp_idx, (255, 255, 255))
            temp_color = graphics.Color(temp_rgb[0], temp_rgb[1], temp_rgb[2])

            temp_w = graphics.DrawText(self.canvas, font_small, -1000, 0, temp_color, temp_str)
            temp_x = x_offset + (w - temp_w) // 2
            graphics.DrawText(self.canvas, font_small, temp_x,
                             8 + self.font_ascents.get(2, 7), temp_color, temp_str)

            # Line 3: Condition abbreviation (centered) - matches daily view position
            condition = panel['data'].get('condition', 'Clear')
            abbrev = self._abbreviate_condition(condition)
            cond_rgb = palette.get(1, (255, 255, 255))
            cond_color = graphics.Color(cond_rgb[0], cond_rgb[1], cond_rgb[2])

            cond_w = graphics.DrawText(self.canvas, font_tiny, -1000, 0, cond_color, abbrev)
            cond_x = x_offset + (w - cond_w) // 2
            graphics.DrawText(self.canvas, font_tiny, cond_x,
                             17 + self.font_ascents.get(1, 5), cond_color, abbrev)

            # Line 4: Precipitation percentage (centered) - matches daily view
            precip = panel['data'].get('precip_chance', 0)
            precip_str = f"{precip}"
            precip_w = graphics.DrawText(self.canvas, font_tiny, -1000, 0, cond_color, precip_str)
            precip_x = x_offset + (w - precip_w) // 2
            graphics.DrawText(self.canvas, font_tiny, precip_x,
                             24 + self.font_ascents.get(1, 5), cond_color, precip_str)

    def _render_daily_view(self, daily_forecasts: dict, current_weather: dict = None):
        """Render 2-panel daily forecast with icons: TODAY | TOMORROW"""
        palette = self.config.get_palette()
        font_tiny = self.fonts.get(1)
        font_small = self.fonts.get(2)

        day_labels = ['TODAY', 'TMR']
        panels = [
            {'x': 0, 'width': 32, 'label': day_labels[0], 'data': daily_forecasts.get(0)},
            {'x': 32, 'width': 32, 'label': day_labels[1], 'data': daily_forecasts.get(1)}
        ]

        for panel in panels:
            if not panel['data']:
                continue

            x_offset = panel['x']
            w = panel['width']

            # Get weather data
            temp_max = panel['data'].get('temp_max', 0)
            temp_min = panel['data'].get('temp_min', 0)
            condition = panel['data'].get('condition', 'Clear')
            precip = panel['data'].get('precip_chance', 0)
            is_night = panel['data'].get('is_night', self.config._is_night)

            # Row 0-5: Day label (centered)
            label_rgb = palette.get(1, (255, 255, 255))
            label_color = graphics.Color(label_rgb[0], label_rgb[1], label_rgb[2])
            label_w = graphics.DrawText(self.canvas, font_tiny, -1000, 0, label_color, panel['label'])
            label_x = x_offset + (w - label_w) // 2
            graphics.DrawText(self.canvas, font_tiny, label_x, 0 + self.font_ascents.get(1, 5), label_color, panel['label'])

            # Row 6-29: Weather icon (24x24, centered)
            icon_path = self._get_weather_icon_path(condition, is_night)
            if icon_path and icon_path.exists():
                try:
                    icon = Image.open(icon_path)
                    if icon.size != (24, 24):
                        icon = icon.resize((24, 24))
                    if icon.mode != 'RGB':
                        icon = icon.convert('RGB')

                    # Center icon horizontally in panel (32px wide, icon 24px = 4px margin on each side)
                    icon_x = x_offset + 4
                    icon_y = 6

                    # Adjust brightness to match palette
                    brightness_multiplier = 0.5 if is_night else 2.0

                    for y in range(24):
                        for x in range(24):
                            r, g, b = icon.getpixel((x, y))
                            if r > 0 or g > 0 or b > 0:  # Skip black pixels (transparent)
                                r = min(255, int(r * brightness_multiplier))
                                g = min(255, int(g * brightness_multiplier))
                                b = min(255, int(b * brightness_multiplier))
                                self.canvas.SetPixel(icon_x + x, icon_y + y, r, g, b)
                except Exception as e:
                    logging.error(f"Error loading icon for {condition}: {e}")

            # Temps to the right of icon (x_offset + 28 to x_offset + 31)
            # High temp
            high_idx = self._get_temp_color_index(temp_max)
            high_rgb = palette.get(high_idx, (255, 255, 255))
            high_color = graphics.Color(high_rgb[0], high_rgb[1], high_rgb[2])
            graphics.DrawText(self.canvas, font_tiny, x_offset + 28, 12, high_color, str(temp_max))

            # Low temp
            low_idx = self._get_temp_color_index(temp_min)
            low_rgb = palette.get(low_idx, (255, 255, 255))
            low_color = graphics.Color(low_rgb[0], low_rgb[1], low_rgb[2])
            graphics.DrawText(self.canvas, font_tiny, x_offset + 28, 20, low_color, str(temp_min))

            # Row 30-31: Condition + precipitation (centered)
            abbrev = self._abbreviate_condition(condition)
            precip_str = f"{precip}"
            info_text = f"{abbrev} {precip_str}"

            white_rgb = palette.get(1, (255, 255, 255))
            white_color = graphics.Color(white_rgb[0], white_rgb[1], white_rgb[2])

            info_w = graphics.DrawText(self.canvas, font_tiny, -1000, 0, white_color, info_text)
            info_x = x_offset + (w - info_w) // 2
            graphics.DrawText(self.canvas, font_tiny, info_x, 30, white_color, info_text)

    def _render_progress_bar(self, elapsed_seconds: float):
        """Render animated progress bar on row 31"""
        palette = self.config.get_palette()
        flip_interval = self.config.forecast_flip_interval
        progress = min(1.0, elapsed_seconds / flip_interval)

        # Calculate bar width (will reach full 64 pixels at 100%)
        bar_width = int(progress * self.config.display_width)

        # Color gradient from palette: cyan -> yellow -> orange -> red
        if progress < 0.5:
            color_rgb = palette.get(7, (0, 255, 255))  # Cyan
        elif progress < 0.8:
            color_rgb = palette.get(5, (255, 255, 0))  # Yellow
        elif progress < 0.95:
            color_rgb = palette.get(8, (255, 128, 0))  # Orange
        else:
            color_rgb = palette.get(2, (255, 0, 0))  # Red (warning: about to flip)

        color = graphics.Color(color_rgb[0], color_rgb[1], color_rgb[2])

        # Draw filled portion of progress bar
        for x in range(bar_width):
            self.canvas.SetPixel(x, 31, color.red, color.green, color.blue)

    def _get_weather_icon_path(self, condition: str, is_night: bool) -> Optional[Path]:
        """Get path to weather icon file using Tomorrow.io naming convention"""
        icon_dir = Path(__file__).parent.parent / "icons"

        if not icon_dir.exists():
            return None

        # Map Apple WeatherKit condition codes to Tomorrow.io icon codes
        # Format: {code}{night_flag}_{description}_small.bmp
        # Night flag: 1 suffix for night (e.g., 10001 for clear night)
        icon_map = {
            "Clear": "1000_clear_sunny",
            "MostlyClear": "1100_mostly_clear",
            "PartlyCloudy": "1101_partly_cloudy",
            "MostlyCloudy": "1102_mostly_cloudy",
            "Cloudy": "1001_cloudy",
            "Fog": "2000_fog",
            "LightFog": "2100_fog_light",
            "Drizzle": "4000_drizzle",
            "Rain": "4001_rain",
            "LightRain": "4200_rain_light",
            "HeavyRain": "4201_rain_heavy",
            "Snow": "5000_snow",
            "Flurries": "5001_flurries",
            "LightSnow": "5100_snow_light",
            "HeavySnow": "5101_snow_heavy",
            "FreezingDrizzle": "6000_freezing_rain_drizzle",
            "FreezingRain": "6001_freezing_rain",
            "LightFreezingRain": "6200_freezing_rain_light",
            "HeavyFreezingRain": "6201_freezing_rain_heavy",
            "IcePellets": "7000_ice_pellets",
            "HeavyIcePellets": "7101_ice_pellets_heavy",
            "LightIcePellets": "7102_ice_pellets_light",
            "Thunderstorms": "8000_tstorm",
        }

        icon_base = icon_map.get(condition, "1000_clear_sunny")

        # Add night suffix if nighttime (1 gets appended to code)
        if is_night:
            # Insert '1' before the underscore (e.g., "1000" -> "10001")
            parts = icon_base.split('_', 1)
            icon_base = f"{parts[0]}1_{parts[1]}"

        # Icons are BMP files with _small suffix
        icon_path = icon_dir / f"{icon_base}_small.bmp"

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

    def sync_brightness_with_night_mode(self):
        """Ensure hardware brightness stays constant regardless of day/night mode"""
        if self.matrix:
            palette_type = "NIGHT" if self.config._is_night else "DAY"
            logging.info(f"sync_brightness: HW brightness={self.config.brightness}, Palette={palette_type}")
            self.matrix.brightness = self.config.brightness

    def __del__(self):
        """Cleanup on destruction"""
        if self.matrix:
            try:
                self.clear()
            except:
                pass
