"""生成应用图标 icon.ico / icon.png。

优先使用项目根目录的 图标.jpeg（品牌设计稿）：居中裁方后缩放为多尺寸 ico。
没有设计稿时回退到程序化绘制的"拾"字图标。
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
ICO_SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]


def build_from_design():
    src = os.path.join(ROOT, "图标.jpeg")
    if not os.path.isfile(src):
        return False
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    side = min(w, h)
    # 居中裁方
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    icon = img.resize((256, 256), Image.LANCZOS)
    icon.save(os.path.join(ASSETS, "icon.png"))
    icon.save(os.path.join(ASSETS, "icon.ico"), sizes=ICO_SIZES)
    return True


def build_drawn():
    SIZE = 256
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    grad = Image.new("RGBA", (SIZE, SIZE))
    d = ImageDraw.Draw(grad)
    top, bottom = (79, 140, 255), (150, 94, 255)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        d.line([(0, y), (SIZE, y)], fill=c)
    mask = Image.new("L", (SIZE, SIZE), 0)
    dm = ImageDraw.Draw(mask)
    dm.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=56, fill=255)
    img.paste(grad, (0, 0), mask)
    draw = ImageDraw.Draw(img)
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
    img.save(os.path.join(ASSETS, "icon.png"))
    img.save(os.path.join(ASSETS, "icon.ico"), sizes=ICO_SIZES)


if __name__ == "__main__":
    os.makedirs(ASSETS, exist_ok=True)
    if build_from_design():
        print("icon 来自 图标.jpeg（居中裁方，多尺寸）")
    else:
        build_drawn()
        print("未找到设计稿，icon 为程序化绘制版本")
