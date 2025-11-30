#!/usr/bin/env python3
"""
Simple test script to paint the LED matrix blue
Run with: sudo python3 test_display.py
"""

import time
import sys

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
except ImportError:
    print("ERROR: rgbmatrix library not found")
    print("Make sure you installed it with the install.sh script")
    sys.exit(1)

# Configuration
options = RGBMatrixOptions()
options.rows = 32
options.cols = 64
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'adafruit-hat-pwm'
options.gpio_slowdown = 4
options.disable_hardware_pulsing = True
options.brightness = 100
options.pwm_bits = 11

print("Initializing RGB matrix...")
print(f"Size: {options.cols}x{options.rows}")
print(f"Hardware: {options.hardware_mapping}")
print(f"Brightness: {options.brightness}")
print("")

try:
    matrix = RGBMatrix(options=options)
    print("✅ Matrix initialized successfully!")
    print("")

    # Paint entire display BLUE
    print("Painting display BLUE...")
    for y in range(32):
        for x in range(64):
            matrix.SetPixel(x, y, 0, 0, 255)  # RGB: Blue

    print("✅ Display should now be BLUE")
    print("")
    print("If you see a blue display, hardware is working!")
    print("Press Ctrl+C to exit and clear display")
    print("")

    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nClearing display...")
        matrix.Clear()
        print("Done!")

except Exception as e:
    print(f"❌ ERROR: {e}")
    print("")
    print("Troubleshooting:")
    print("1. Make sure LED matrix is connected to the HAT")
    print("2. Make sure 5V power supply is connected and ON")
    print("3. Check ribbon cable is properly seated")
    print("4. Try running with: sudo python3 test_display.py")
    sys.exit(1)
