"""
Generate icon-192.png and icon-512.png from icon.svg.
Run: python generate_icons.py
Requires: pip install cairosvg
"""
try:
    import cairosvg
    import os

    svg_path = os.path.join(os.path.dirname(__file__), "icon.svg")
    out_dir = os.path.dirname(__file__)

    for size in [192, 512]:
        out_path = os.path.join(out_dir, f"icon-{size}.png")
        cairosvg.svg2png(url=svg_path, write_to=out_path, output_width=size, output_height=size)
        print(f"Generated {out_path}")

    print("Icons generated successfully!")

except ImportError:
    print("cairosvg not installed. Trying Pillow fallback...")
    try:
        from PIL import Image, ImageDraw
        import os

        out_dir = os.path.dirname(__file__)

        for size in [192, 512]:
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Dark rounded background
            pad = int(size * 0.0)
            draw.rounded_rectangle([pad, pad, size - pad, size - pad],
                                    radius=int(size * 0.19), fill="#1A1A1A")

            # Draw waveform bars
            scale = size / 512
            bars = [
                (80, 196, 28, 120, "#C17F59"),
                (122, 156, 28, 200, "#C17F59"),
                (164, 176, 28, 160, "#C17F59"),
                (206, 216, 28, 80,  "#C17F59"),
                (282, 216, 28, 80,  "#D4A574"),
                (324, 166, 28, 180, "#D4A574"),
                (366, 186, 28, 140, "#D4A574"),
                (408, 206, 28, 100, "#D4A574"),
            ]
            for x, y, w, h, color in bars:
                sx, sy, sw, sh = int(x*scale), int(y*scale), int(w*scale), int(h*scale)
                r = sw // 2
                draw.rounded_rectangle([sx, sy, sx+sw, sy+sh], radius=r, fill=color)

            # Center pip
            cx, cy, cw, ch = 244, 236, 24, 40
            sx, sy, sw, sh = int(cx*scale), int(cy*scale), int(cw*scale), int(ch*scale)
            draw.rounded_rectangle([sx, sy, sx+sw, sy+sh], radius=sw//2, fill="#5A8F6E")

            out_path = os.path.join(out_dir, f"icon-{size}.png")
            img.save(out_path, "PNG")
            print(f"Generated {out_path}")

        print("Icons generated (Pillow fallback)!")
    except ImportError:
        print("Neither cairosvg nor Pillow found.")
        print("Install one: pip install cairosvg  OR  pip install Pillow")
        print("Then re-run this script.")
