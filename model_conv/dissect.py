"""解剖官方 bin 布局：定位每个张量、读取 flag 与间隔，推导精确写盘格式。"""
import numpy as np
import torch
import struct
import collections


def f32_to_f16_trunc(a):
    """float32 -> float16 bit pattern，向零截断（复刻官方转换器的舍入方式）。"""
    b = np.ascontiguousarray(a, dtype="<f4").view("<u4").astype(np.uint32)
    sign = (b >> 16) & 0x8000
    exp = ((b >> 23) & 0xFF).astype(np.int64)
    man = b & 0x7FFFFF
    shift = np.clip(114 - exp, 0, 24)
    normal = sign | (((exp - 112).clip(0, 31) << 10) | (man >> 13)).astype(np.uint32)
    # 官方转换器把 fp16 亚正规范围(极小值)直接冲成 ±0
    out = np.where((exp >= 113) & (exp <= 142), normal, sign)
    out = np.where(exp > 142, sign | np.uint32(0x7C00), out)          # 溢出->inf
    out = np.where((exp == 255) & (man != 0), sign | np.uint32(0x7E00), out)  # NaN
    return out.astype("<u2")


def main():
    models = "tools/realesrgan/models"
    raw = open(models + "/realesr-animevideov3-x4.bin", "rb").read()
    sd = torch.load("model_conv/realesr-animevideov3.pth", map_location="cpu")["params"]

    prev_end = 0
    rows = []
    for k, t in sd.items():
        a = t.float().numpy().flatten()
        found = None
        for esz, dt in ((2, "fp16"), (4, "fp32")):
            if dt == "fp16":
                enc = f32_to_f16_trunc(a).tobytes()
            else:
                enc = a.astype("<f4").tobytes()
            v0 = enc[:2 if dt == "fp16" else 4]
            start = prev_end
            while True:
                i = raw.find(v0, start)
                if i < 0:
                    break
                need = a.size * esz
                if i + need <= len(raw):
                    if raw[i:i + need] == enc:
                        found = (i, esz, dt)
                        break
                start = i + 1
        if not found:
            print(f"{k}: 未定位! prev_end={prev_end}")
            return
        c, esz, dt = found
        flagv = struct.unpack("<i", raw[c - 4:c])[0]
        rows.append((k, c, esz, a.size, flagv, dt))
        prev_end = c + a.size * esz
        print(f"  {k:16s} payload@{c:8d} esz={esz} n={a.size:6d} "
              f"end={prev_end:8d} flag={hex(flagv)}")

    print("定位成功:", len(rows), "/", len(sd))
    print("flag 分布:", dict(collections.Counter(hex(r[4]) for r in rows)))
    print("格式分布:", dict(collections.Counter(r[5] for r in rows)))
    gaps = [rows[0][1] - 4] + [
        rows[i][1] - (rows[i - 1][1] + rows[i - 1][3] * rows[i - 1][2])
        for i in range(1, len(rows))
    ]
    print("相邻间隔分布:", dict(collections.Counter(gaps)))
    total = sum(4 + r[3] * r[2] for r in rows)
    print("理论总大小(每张量 flag+payload):", total, "实际:", len(raw))
    for r in rows[:4] + rows[-3:]:
        print(f"  {r[0]:16s} off={r[1]:8d} esz={r[2]} n={r[3]:6d} flag={hex(r[4])} 格式={r[5]}")


if __name__ == "__main__":
    main()
