"""把 SRVGG 架构的 .pth 权重写成 2022-04 版 realesrgan-ncnn-vulkan 兼容的 bin。

布局（通过对官方 realesr-animevideov3-x4.bin 的逐字节解剖确认）：
  Convolution 层: [4字节标志 0x01306B47][fp16 截断式权重] + [fp32 bias，无标志]
  PReLU 层:       [fp32，无标志]
  fp16 转换规则:   指数域直接移位、尾数向零截断、fp16 亚正规范围直接冲成 ±0
  各张量按 param 层顺序依次紧密排列，state dict 用 pth 的插入序（weight 在 bias 前）。

正确性验证：对官方 realesr-animevideov3.pth 执行同样流程，
生成的 bin 必须与官方发布的 realesr-animevideov3-x4.bin 逐字节一致。
"""
import os
import struct

import numpy as np
import torch

MAGIC_FP16 = 0x01306B47
WEIGHTED = {"Convolution", "PReLU"}


def f32_to_f16_trunc(a):
    """float32 -> float16 bit pattern，向零截断（复刻官方转换器的舍入方式）。"""
    b = np.ascontiguousarray(a, dtype="<f4").view("<u4").astype(np.uint32)
    sign = (b >> 16) & 0x8000
    exp = ((b >> 23) & 0xFF).astype(np.int64)
    man = b & 0x7FFFFF
    normal = sign | (((exp - 112).clip(0, 31) << 10) | (man >> 13)).astype(np.uint32)
    # 官方转换器把 fp16 亚正规范围(极小值)直接冲成 ±0
    out = np.where((exp >= 113) & (exp <= 142), normal, sign)
    out = np.where(exp > 142, sign | np.uint32(0x7C00), out)          # 溢出->inf
    out = np.where((exp == 255) & (man != 0), sign | np.uint32(0x7E00), out)  # NaN
    return out.astype("<u2")


def load_state(pth_path):
    sd = torch.load(pth_path, map_location="cpu")
    if isinstance(sd, dict):
        for key in ("params_ema", "params"):
            if key in sd and isinstance(sd[key], dict):
                return sd[key]
    return sd


def parse_param_layers(param_path):
    with open(param_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    assert int(lines[0]) == 7767517, "param 魔数不对"
    n_layers, _ = map(int, lines[1].split())
    return [line.split()[0] for line in lines[2:2 + n_layers]]


def write_bin(layers, state, out_path):
    """按 param 层顺序消费 state（插入序：weight 在 bias 前），写出 bin。"""
    buf = bytearray()
    it = iter(state.items())
    for typ in layers:
        if typ not in WEIGHTED:
            continue
        w_key, w = next(it)
        assert w_key.endswith(".weight"), f"期望 weight 实际 {w_key}"
        if typ == "Convolution":
            b_key, b = next(it)
            assert b_key.endswith(".bias"), f"期望 bias 实际 {b_key}"
            buf += struct.pack("<i", MAGIC_FP16)
            buf += f32_to_f16_trunc(w.float().numpy()).tobytes()
            buf += np.ascontiguousarray(b.float().numpy(), dtype="<f4").tobytes()
        else:  # PReLU
            buf += np.ascontiguousarray(w.float().numpy(), dtype="<f4").tobytes()
    leftover = [k for k, _ in it]
    if leftover:
        raise RuntimeError(f"state 中还有未消费的张量: {leftover}")
    with open(out_path, "wb") as f:
        f.write(buf)
    return len(buf)


def build_srvgg_param(num_intermediate, feat=64, scale=4):
    """生成与官方 animevideov3-x4 同构的 param 文本。
    num_intermediate = 初始卷积之后的 64->64 卷积层数。"""
    lines = []

    def add(layer):
        lines.append(f"{layer[0]:<24} {layer[1]:<24} " + " ".join(layer[2:]))

    blob = 2  # 0=data(输入), 1=split的残差分支; 之后顺序分配
    add(("Input", "input.1", "0", "1", "data"))
    add(("Split", "splitncnn_input0", "1", "2", "data",
         "input.1_splitncnn_0", "input.1_splitncnn_1"))
    cur = "input.1_splitncnn_1"
    conv_idx = 0
    for i in range(num_intermediate + 2):  # 初始卷积 + 中间卷积 + 最终卷积
        wsize = 1728 if i == 0 else (27648 if i == num_intermediate + 1 else 36864)
        out_ch = 64 if i != num_intermediate + 1 else 48
        dst = f"b{blob}"; blob += 1
        add(("Convolution", f"Conv_{conv_idx}", "1", "1", cur, dst,
             f"0={out_ch}", "1=3", "4=1", "5=1", f"6={wsize}"))
        cur = dst; conv_idx += 1
        if i != num_intermediate + 1:  # 最终卷积后无激活
            dst = f"b{blob}"; blob += 1
            add(("PReLU", f"PRelu_{conv_idx}", "1", "1", cur, dst, "0=64"))
            cur = dst; conv_idx += 1
    add(("PixelShuffle", "DepthToSpace", "1", "1", cur, "b_ps", "0=4"))
    add(("Interp", "Resize_base", "1", "1", "input.1_splitncnn_0", "b_base",
         "0=1", "1=4.000000e+00", "2=4.000000e+00"))
    add(("BinaryOp", "Add_out", "2", "1", "b_ps", "b_base", "output"))
    return f"7767517\n{len(lines)} {len(lines) + 1}\n" + "\n".join(lines) + "\n"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    models = os.path.join(os.path.dirname(here), "tools", "realesrgan", "models")

    # ---- 第 1 步：用官方 animevideov3.pth 验证转换器 ----
    layers = parse_param_layers(os.path.join(models, "realesr-animevideov3-x4.param"))
    sd_official = load_state(os.path.join(here, "realesr-animevideov3.pth"))
    regen = os.path.join(here, "regen_animevideov3_x4.bin")
    size = write_bin(layers, sd_official, regen)
    with open(os.path.join(models, "realesr-animevideov3-x4.bin"), "rb") as f:
        official = f.read()
    with open(regen, "rb") as f:
        mine = f.read()
    if mine == official:
        print(f"验证通过：重新生成的 bin 与官方发布逐字节一致（{size} 字节）")
    else:
        diff = sum(1 for x, y in zip(mine, official) if x != y)
        raise SystemExit(f"验证失败：长度 {len(mine)} vs {len(official)}，差异字节 {diff}")
    os.remove(regen)

    # ---- 第 2 步：为 general-x4v3 生成 param + bin ----
    # 结构：初始卷积(3->64) + 32 个 64->64 卷积(每个后接 PReLU) + 最终卷积(64->48)
    #       + PixelShuffle(4) + 残差最近邻×4 相加，与官方 x4 同构图
    sd_general = load_state(os.path.join(here, "realesr-general-x4v3.pth"))
    param_text = build_srvgg_param(num_intermediate=32)
    param_out = os.path.join(models, "realesr-general-x4v3.param")
    with open(param_out, "w", encoding="utf-8") as f:
        f.write(param_text)
    layers_g = parse_param_layers(param_out)
    bin_out = os.path.join(models, "realesr-general-x4v3.bin")
    n = write_bin(layers_g, sd_general, bin_out)
    print(f"realesr-general-x4v3 生成完毕：{len(layers_g)} 层，bin {n} 字节")


if __name__ == "__main__":
    main()
