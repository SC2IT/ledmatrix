"""
Text parsing and formatting for Stream Deck format
Format: {color}<size>text
"""

import re
from typing import List, Tuple


class TextParser:
    """Parse Stream Deck formatted text"""

    MAX_LINES = 3  # Maximum lines for 32px display

    @staticmethod
    def parse(text: str) -> List[Tuple[int, int, str]]:
        """
        Parse Stream Deck format text into structured data

        Format: {color}<size>text
        Returns: List of (color_index, font_size, text) tuples
        """
        if not text or not text.strip():
            return []

        lines = text.strip().split("\n")[:TextParser.MAX_LINES]
        parsed = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for format: {color}<size>text
            if line.startswith('{') and '}<' in line and '>' in line:
                try:
                    # Find positions
                    color_end = line.find('}')
                    size_start = line.find('<', color_end) + 1
                    size_end = line.find('>', size_start)

                    if color_end > 1 and size_start > color_end and size_end > size_start:
                        # Extract parts
                        color_str = line[1:color_end]
                        size_str = line[size_start:size_end]
                        text_part = line[size_end + 1:]

                        # Convert to integers
                        color_index = int(color_str)
                        font_size = int(size_str)

                        # Validate ranges
                        color_index = max(0, min(27, color_index))  # 0-27 palette
                        font_size = max(1, min(7, font_size))  # 1-7 font sizes

                        parsed.append((color_index, font_size, text_part))
                    else:
                        # Malformed, use defaults
                        parsed.append((1, 2, line))  # White, medium

                except (ValueError, IndexError):
                    # Parse error, use defaults
                    parsed.append((1, 2, line))  # White, medium
            else:
                # Plain text, use defaults
                parsed.append((1, 2, line))  # White, medium

        return parsed

    @staticmethod
    def validate(text: str) -> List[str]:
        """
        Validate Stream Deck format and return issues

        Returns: List of issue strings, or ["Valid format"] if no issues
        """
        issues = []

        if not text:
            return ["Empty text"]

        lines = text.strip().split("\n")

        if len(lines) > TextParser.MAX_LINES:
            issues.append(f"Too many lines ({len(lines)}), max is {TextParser.MAX_LINES}")

        for i, line in enumerate(lines[:TextParser.MAX_LINES]):
            if line.startswith('{') and '}<' in line and '>' in line:
                try:
                    color_end = line.find('}')
                    size_start = line.find('<', color_end) + 1
                    size_end = line.find('>', size_start)

                    color_str = line[1:color_end]
                    size_str = line[size_start:size_end]

                    color_index = int(color_str)
                    font_size = int(size_str)

                    if color_index < 0 or color_index > 27:
                        issues.append(f"Line {i + 1}: Color {color_index} out of range (0-27)")

                    if font_size < 1 or font_size > 7:
                        issues.append(f"Line {i + 1}: Font size {font_size} out of range (1-7)")

                except (ValueError, IndexError):
                    issues.append(f"Line {i + 1}: Invalid format")

        return issues if issues else ["Valid format"]


# Font size mapping (height in pixels for each size)
# Updated to use larger BDF fonts from rpi-rgb-led-matrix repository
FONT_SIZES = {
    1: 6,   # Small - 4x6.bdf
    2: 8,   # Medium - 5x8.bdf
    3: 8,   # Large - ter-u12n.bdf (visual height 8px in uniform layouts)
    4: 15,  # XLarge - 9x15B.bdf (for ON-CALL preset)
    5: 20,  # XXLarge - 10x20.bdf
    6: 22,  # Huge Bold - ter-u22b.bdf (for QUIET preset)
    7: 24,  # Massive - texgyre-27.bdf (for FREE preset)
}


def calculate_layout(parsed_lines: List[Tuple[int, int, str]], display_height: int = 32) -> List[Tuple[int, int, int, str]]:
    """
    Calculate vertical positioning for parsed text lines

    Args:
        parsed_lines: List of (color, size, text) tuples
        display_height: Height of display in pixels (default 32)

    Returns:
        List of (color, size, y_position, text) tuples
    """
    if not parsed_lines:
        return []

    num_lines = len(parsed_lines)

    # Check if all fonts are uniform size
    font_sizes = [size for _, size, _ in parsed_lines]
    is_uniform = len(set(font_sizes)) == 1

    positions = []

    if num_lines == 1:
        # Single line - center vertically
        _, size, _ = parsed_lines[0]
        height = FONT_SIZES.get(size, 8)
        y_pos = (display_height - height) // 2
        positions.append(y_pos)

    elif is_uniform:
        # Uniform fonts - distribute evenly with proper centering
        # Matches CircuitPython display_core.py spacing logic
        size = parsed_lines[0][1]

        # Visual heights for spacing calculations
        # Sizes 4-7 provide graduated large font options
        visual_heights = {1: 6, 2: 8, 3: 8, 4: 15, 5: 20, 6: 22, 7: 24}

        # Row spacing between lines (matches CircuitPython)
        # Size 3 uses 3px spacing (line 103), sizes 1&2 use 2px (line 111)
        row_spacing = 3 if size == 3 else 2

        visual_height = visual_heights.get(size, 8)

        # Calculate total content height
        total_text_height = visual_height * num_lines
        total_spacing = row_spacing * (num_lines - 1)
        total_content_height = total_text_height + total_spacing

        # Center the block
        start_y = (display_height - total_content_height) // 2

        # Adjust for size 3 to match CircuitPython (line 105: move up 2px)
        if size == 3:
            start_y = max(-2, start_y - 2)

        # Calculate positions with consistent spacing
        spacing_per_gap = visual_height + row_spacing
        for i in range(num_lines):
            y_pos = start_y + (i * spacing_per_gap)
            positions.append(y_pos)

    else:
        # Mixed fonts - use custom layouts for common patterns
        if num_lines == 3 and font_sizes == [4, 3, 2]:
            # ON-CALL pattern: XLarge Bold (15px) + Large (8px) + Medium (8px)
            # Urgent moved up 3px from 15 to 12
            positions = [0, 12, 24]
        elif num_lines == 2 and font_sizes == [7, 3]:
            # FREE pattern: Massive (24px) + Large (actual 12px, visual 8px)
            # FREE down 1px, But Knock up 1px for better balance
            positions = [2, 21]
        elif num_lines == 3 and font_sizes == [3, 3, 3]:
            # BUSY pattern: Three large lines (adjusted for baseline positioning)
            # Moved up 2px from CircuitPython [0, 11, 22] to prevent bottom clipping
            positions = [-2, 9, 20]
        elif num_lines == 3 and font_sizes == [6, 2, 2]:
            # QUIET pattern: Huge Bold top line (22px), medium lines at bottom
            # QUIET moved up 2px to -2 (top clip for tighter layout)
            positions = [-2, 17, 25]
        elif num_lines == 3 and font_sizes == [4, 2, 2]:
            # KNOCK pattern: Large top line, two small lines at bottom
            # Bottom two lines close together, 1px from bottom
            positions = [0, 14, 23]
        else:
            # Default distribution
            positions = [2, 12, 22][:num_lines]

    # Combine into output format
    result = []
    for (color, size, text), y_pos in zip(parsed_lines, positions):
        result.append((color, size, y_pos, text))

    return result
