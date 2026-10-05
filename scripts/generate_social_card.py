"""Generate the Open Graph preview card for the public case study."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "chargeforward-social.png"
W, H = 1200, 630


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default(size=size)


image = Image.new("RGB", (W, H), "#0b0c0b")
draw = ImageDraw.Draw(image)

for x in range(0, W, 64):
    draw.line((x, 0, x, H), fill="#1a1c19", width=1)
for y in range(0, H, 64):
    draw.line((0, y, W, y), fill="#1a1c19", width=1)

draw.ellipse((810, -260, 1350, 280), fill="#172017")
draw.ellipse((930, -130, 1280, 220), outline="#d5ff46", width=2)
draw.rectangle((0, 576, W, H), fill="#d5ff46")

draw.ellipse((72, 60, 112, 100), outline="#fffef8", width=2)
draw.rectangle((84, 77, 88, 91), fill="#d5ff46")
draw.rectangle((91, 69, 95, 91), fill="#d5ff46")
draw.rectangle((98, 81, 102, 91), fill="#d5ff46")
draw.text((128, 64), "ChargeForward", fill="#fffef8", font=font(30, bold=True))

draw.text((72, 162), "WASHINGTON EV INTELLIGENCE", fill="#8f948a", font=font(18, bold=True), spacing=3)
draw.text((72, 210), "Evidence for the next", fill="#fffef8", font=font(69, bold=True))
draw.text((72, 286), "electric mile.", fill="#d5ff46", font=font(78, bold=True))
draw.text((75, 395), "County forecasting · uncertainty · cloud data engineering", fill="#afb3aa", font=font(26))

stats = [("298,916", "WA EVs"), ("576,457", "transactions"), ("39", "counties"), ("10.3%", "lower RMSE")]
for index, (value, label) in enumerate(stats):
    x = 75 + index * 270
    draw.text((x, 470), value, fill="#fffef8", font=font(29, bold=True))
    draw.text((x, 513), label.upper(), fill="#777d74", font=font(13, bold=True))

draw.text((74, 591), "cr-shah.github.io/chargeforward-ev-analytics", fill="#0b0c0b", font=font(17, bold=True))
draw.text((1040, 591), "BUILD →", fill="#0b0c0b", font=font(17, bold=True))

OUT.parent.mkdir(parents=True, exist_ok=True)
image.save(OUT, optimize=True)
print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")
