"""生成应用图标 icon.ico / icon.png。"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 256


def build():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # 垂直渐变底：蓝 -> 紫
    grad = Image.new("RGBA", (SIZE, SIZE))
    top = (79, 140, 255)
    bottom = (150, 94, 255)
    d = ImageDraw.Draw(grad)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        d.line([(0, y), (SIZE, y)], fill=c)
    mask = Image.new("L", (SIZE, SIZE), 0)
    dm = ImageDraw.Draw(mask)
    dm.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=56, fill=255)
    img.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(img)
    # 白色"拾"字
    font = None
    for fp in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
               r"C:\Windows\Fonts\simhei.ttf"):
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 150)
                break
            except OSError:
                continue
    if font:
        draw.text((SIZE / 2, SIZE / 2 - 6), "拾", font=font, fill="white", anchor="mm")
    # 右上角小星星点缀
    r = 14
    cx, cy = SIZE - 44, 42
    draw.regular_polygon((cx, cy, r), n_sides=4, rotation=45, fill=(255, 255, 255, 230))

    img.save(os.path.join(HERE, "icon.png"))
    img.save(os.path.join(HERE, "icon.ico"),
             sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("icon written")


if __name__ == "__main__":
    build()
