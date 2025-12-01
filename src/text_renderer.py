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
                        font_size = max(1, min(5, font_size))  # 1-5 font sizes

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

                    if font_size < 1 or font_size > 5:
                        issues.append(f"Line {i + 1}: Font size {font_size} out of range (1-5)")

                except (ValueError, IndexError):
                    issues.append(f"Line {i + 1}: Invalid format")

        return issues if issues else ["Valid format"]


# Font size mapping (height in pixels for each size)
# Matches CircuitPython display_core.py uniform layout font_heights (line 89)
FONT_SIZES = {
    1: 6,   # Small - 4x6.bdf (no scaling)
    2: 8,   # Medium - 5x8.bdf (no scaling)
    3: 8,   # Large - ter-u12n.bdf (no scaling) - visual height 8px in uniform layouts
    4: 14,  # XLarge - terminalio.FONT with scale=2 (12px base × 2 ≈ 14px visual)
    5: 16,  # XXLarge - MatrixChunky8.bdf with scale=2 or 3
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
        # Calculate based on actual font metrics (ascent + descent)
        size = parsed_lines[0][1]

        # Font ascent values (top of glyph to baseline)
        font_ascents = {1: 5, 2: 7, 3: 10, 4: 11, 5: 14}
        # Font descent values (baseline to bottom of glyph)
        font_descents = {1: 1, 2: 1, 3: 2, 4: 3, 5: 4}

        ascent = font_ascents.get(size, 7)
        descent = font_descents.get(size, 1)
        total_font_height = ascent + descent

        # Baseline-to-baseline spacing
        baseline_spacing = total_font_height + 1  # 1px gap between lines

        # Calculate total block height (first ascent + spacing + last descent)
        total_block_height = ascent + (baseline_spacing * (num_lines - 1)) + descent

        # Center the block and calculate first baseline position
        first_baseline = (display_height - total_block_height) // 2 + ascent

        # Calculate top positions (baseline - ascent) for each line
        for i in range(num_lines):
            baseline_y = first_baseline + (i * baseline_spacing)
            top_y = baseline_y - ascent  # Convert baseline to top position
            positions.append(top_y)

    else:
        # Mixed fonts - use custom layouts for common patterns
        if num_lines == 3 and font_sizes == [4, 3, 2]:
            # ON-CALL pattern: Large, Medium, Small
            positions = [1, 17, 26]
        elif num_lines == 2 and font_sizes == [4, 3]:
            # FREE pattern: XLarge, Large
            positions = [1, 22]
        elif num_lines == 3 and font_sizes == [3, 3, 3]:
            # BUSY pattern: Three large lines (adjusted for baseline positioning)
            # Moved up 2px from CircuitPython [0, 11, 22] to prevent bottom clipping
            positions = [-2, 9, 20]
        else:
            # Default distribution
            positions = [2, 12, 22][:num_lines]

    # Combine into output format
    result = []
    for (color, size, text), y_pos in zip(parsed_lines, positions):
        result.append((color, size, y_pos, text))

    return result
