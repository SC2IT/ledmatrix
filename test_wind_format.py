#!/usr/bin/env python3
"""Test script to show current wind formatting"""

# Wind direction conversion (same as code)
def get_wind_dir(degrees):
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[round(degrees / 45) % 8]

# Test with various wind conditions
test_cases = [
    {"dir_deg": 0, "speed_ms": 0, "desc": "Calm, North"},
    {"dir_deg": 45, "speed_ms": 2.2, "desc": "Light, Northeast"},
    {"dir_deg": 135, "speed_ms": 3.1, "desc": "Gentle, Southeast"},
    {"dir_deg": 180, "speed_ms": 4.5, "desc": "Moderate, South"},
    {"dir_deg": 225, "speed_ms": 8.9, "desc": "Fresh, Southwest"},
    {"dir_deg": 270, "speed_ms": 13.4, "desc": "Strong, West"},
    {"dir_deg": 315, "speed_ms": 17.9, "desc": "Gale, Northwest"},
]

print("\n" + "="*70)
print("CURRENT WIND FORMATTING (as displayed on LED matrix)")
print("="*70)
print(f"{'Condition':<25} {'Degrees':<10} {'m/s':<8} {'Display':<15} {'Chars'}")
print("-"*70)

for case in test_cases:
    degrees = case['dir_deg']
    speed_ms = case['speed_ms']
    desc = case['desc']

    # Convert exactly as code does
    wind_mph = round(speed_ms * 2.237)
    wind_dir = get_wind_dir(degrees)

    # Format exactly as code does
    formatted = f"{wind_dir}{wind_mph:02d}MPH"

    print(f"{desc:<25} {degrees:<10} {speed_ms:<8.1f} '{formatted}'  {len(formatted)}")

print("\n" + "="*70)
print("FORMAT DETAILS:")
print("="*70)
print("  Template: {direction}{speed:02d}MPH")
print("  - Direction: 1-2 characters (N, NE, SW, etc.)")
print("  - Speed: 2 digits with leading zero (00-99)")
print("  - Units: 'MPH' (3 characters)")
print("  - Total length: 7-9 characters")
print("\nEXAMPLES:")
print("  N05MPH  = North at 5 mph (7 chars)")
print("  SW12MPH = Southwest at 12 mph (8 chars)")
print("  NNE00MPH would be impossible (code uses 8 directions)")
print("="*70 + "\n")
