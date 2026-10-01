"""拾光工具箱 v1.1 自动化测试套件。

运行： QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe tests/test_suite.py
覆盖：单元测试（工具/识别/方案表/防睡眠/任务档案）+ 集成测试
（Range 续传下载、视频剪切两种模式、GPU 图片增强、GPU 视频增强中断→恢复全流程）。
"""
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

RESULTS = []


def check(name, fn):
    t0 = time.time()
    try:
        fn()
        RESULTS.append((name, "PASS", time.time() - t0, ""))
        print(f"  ✓ {name} ({time.time()-t0:.1f}s)")
    except Exception as e:
        RESULTS.append((name, "FAIL", time.time() - t0, str(e)))
        print(f"  ✗ {name} ({time.time()-t0:.1f}s) -> {e}")
        import traceback
        traceback.print_exc()


# ---------------- 基础设施 ----------------
def make_app():
    # 下载页含 QWidget，必须用 QApplication（offscreen 平台）
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def run_task_until(task, timeout, stop_when=None, poll=0.15):
    """启动任务线程并轮询直至结束/满足条件/超时。
    必须周期性 processEvents，否则跨线程队列信号永远送不到主线程。"""
    events = []
    task.sig.connect(events.append)
    task.start()
    t0 = time.time()
    while time.time() - t0 < timeout:
        QCoreApplication.processEvents()
        if stop_when is not None and stop_when(events):
            break
        if task.isFinished():
            break
        time.sleep(0.1)
    deadline = time.time() + 15
    while task.isRunning() and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.05)
    # 线程结束后最后一条事件可能还在队列里，再多泵几轮
    for _ in range(10):
        QApplication.processEvents()
        time.sleep(0.03)
    return events


FFMPEG = os.path.join(ROOT, "tools", "ffmpeg.exe")
FFPROBE = os.path.join(ROOT, "tools", "ffprobe.exe")


def gen_test_video(path, seconds=2, size="320x240", fps=30, gop=None):
    cmd = [FFMPEG, "-y", "-v", "error",
           "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={fps}:duration={seconds}",
           "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
           "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-shortest"]
    if gop:
        cmd += ["-g", str(gop), "-keyint_min", str(gop)]
    cmd.append(path)
    subprocess.run(cmd, check=True)


def probe(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries",
         "stream=codec_type,width,height:format=duration", "-of", "json", path],
        capture_output=True, text=True)
    info = json.loads(r.stdout)
    dur = float(info["format"]["duration"])
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
    a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), {})
    return dur, (v.get("width", 0), v.get("height", 0)), bool(a)


# ---------------- 单元测试 ----------------
def t_utils():
    from app.utils import sanitize_name, unique_path, human_size, filename_from_url
    expect = "a_b_c" + "_" * 7
    assert sanitize_name('a/b\\c:*?"<>|') == expect, \
        f"sanitize: {sanitize_name('a/b\\c:*?\"<>|')!r} != {expect!r}"
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.txt")
    open(p, "w").close()
    up = unique_path(p)
    assert up != p and up.endswith(" (1).txt"), f"unique_path: {up}"
    assert human_size(1536) == "1.5 KB", f"human_size: {human_size(1536)}"
    assert filename_from_url("http://a.com/b/c/%E5%9B%BE.jpg") == "图.jpg"
    shutil.rmtree(d)


def t_url_detect():
    from app.url_detect import detect_engine
    assert detect_engine("http://a/x/index.m3u8?token=1") == "m3u8"
    assert detect_engine("http://a/x.mpd") == "m3u8"
    assert detect_engine("https://a.com/v/a.mp4") == "direct"
    assert detect_engine("https://a.com/img/pic.JPG") == "direct"
    assert detect_engine("https://www.bilibili.com/video/BV1xx") == "site"
    assert detect_engine("https://youtu.be/abc") == "site"


def t_plans():
    from app.enhance import plan_for
    from app.paths import realesrgan_model
    has_general = os.path.isfile(realesrgan_model("realesr-general-x4v3"))
    assert plan_for("photo", 2, False) == ("realesrgan-x4plus", 4, 0.5)
    assert plan_for("photo", 3, False) == ("realesrgan-x4plus", 4, 0.75)
    assert plan_for("anime", 2, False) == ("realesr-animevideov3", 2, 1.0)
    assert plan_for("anime", 4, False) == ("realesrgan-x4plus-anime", 4, 1.0)
    for s in (2, 3, 4):
        assert plan_for("anime", s, True)[0] == "realesr-animevideov3"
        assert plan_for("anime", s, True)[1] == s
    if has_general:
        assert plan_for("real", 4, False) == ("realesr-general-x4v3", 4, 1.0)
        assert plan_for("real", 2, True) == ("realesr-general-x4v3", 4, 0.5)
    else:
        raise AssertionError("general-x4v3 模型缺失")


def t_even_vf():
    from app.enhance import even_vf
    # 641(奇数) x2: 输出应为偶数
    import subprocess
    vf = even_vf(1.0)
    assert "trunc(iw*1.0/2)*2" in vf
    vf5 = even_vf(0.5)
    assert "trunc(iw*0.5/2)*2" in vf5


def t_sleep_guard():
    from app.sleep_guard import acquire, release, active
    acquire(); acquire()
    assert active()
    release(); release()
    assert not active()


def t_job_descriptors():
    from app.enhance import (write_job, mark_job, find_interrupted_jobs, clear_job,
                         job_file)
    d = tempfile.mkdtemp()
    tmp = os.path.join(d, ".sgtmp_9_1")
    os.makedirs(os.path.join(tmp, "out"))
    for i in range(1, 8):
        open(os.path.join(tmp, "out", f"{i:06d}.jpg"), "w").close()
    write_job(d, 9, "C:/v.mp4", "anime", 2, ".sgtmp_9_1", 30.0, 100,
              status="running")
    assert os.path.isfile(job_file(d, 9)), "任务档案未写入"
    mark_job(d, 9, "interrupted")
    jobs = find_interrupted_jobs(d)
    assert len(jobs) == 1 and jobs[0][2] == 7, f"jobs={jobs}"
    # json 往返会把路径规范化为 Windows 分隔符，比较时归一化
    assert os.path.normcase(jobs[0][1]["source"]) == os.path.normcase("C:/v.mp4"), \
        f"source={jobs[0][1]['source']}"
    clear_job(d, 9)
    assert find_interrupted_jobs(d) == [], "清除后仍能扫描到任务"
    shutil.rmtree(d)


# ---------------- Range 续传集成测试 ----------------
def t_direct_download_resume():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from app.direct_dl import DirectDownloadTask

    payload = bytes(range(256)) * 8192  # 2 MB
    served = {"range_hits": 0}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            rng = self.headers.get("Range")
            if rng:
                served["range_hits"] += 1
                start = int(re.match(r"bytes=(\d+)-", rng).group(1))
                self.send_response(206)
                self.send_header("Content-Range",
                                 f"bytes {start}-{len(payload)-1}/{len(payload)}")
                self.send_header("Content-Length", str(len(payload) - start))
                self.end_headers()
                self.wfile.write(payload[start:])
            else:
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        d = tempfile.mkdtemp()
        # 模拟上次中断：预置 700KB 的 .part
        part = os.path.join(d, "data.bin.part")
        with open(part, "wb") as f:
            f.write(payload[:700 * 1024])
        t = DirectDownloadTask(1, f"http://127.0.0.1:{port}/data.bin", d)
        events = run_task_until(t, 60)
        done = [e for e in events if e["event"] == "done"]
        assert done, f"未完成: {events[-1] if events else '无事件'}"
        assert served["range_hits"] >= 1, "服务器未收到 Range 请求（未走续传）"
        out = done[0]["path"]
        assert os.path.basename(out) == "data.bin"
        assert open(out, "rb").read() == payload, "续传后的文件内容不一致"
        assert not os.path.exists(part)
        shutil.rmtree(d)
    finally:
        srv.shutdown()


def t_direct_download_fresh_and_cancel():
    from app.direct_dl import DirectDownloadTask
    payload = bytes(range(256)) * 4096  # 1 MB

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        d = tempfile.mkdtemp()
        t = DirectDownloadTask(2, f"http://127.0.0.1:{port}/video.mp4", d)
        events = run_task_until(t, 60)
        done = [e for e in events if e["event"] == "done"]
        assert done and open(done[0]["path"], "rb").read() == payload
        shutil.rmtree(d)
    finally:
        srv.shutdown()


# ---------------- 剪切集成测试 ----------------
def t_cut_accurate():
    from app.cut_engine import CutTask
    d = tempfile.mkdtemp()
    src = os.path.join(d, "src.mp4")
    gen_test_video(src, seconds=6)
    t = CutTask(3, src, 1.0, 4.0, "accurate")
    events = run_task_until(t, 120)
    done = [e for e in events if e["event"] == "done"]
    assert done, f"剪切失败: {events[-1] if events else '无事件'}"
    dur, wh, has_audio = probe(done[0]["path"])
    assert abs(dur - 3.0) < 0.2, f"精确剪切时长 {dur} != 3"
    assert has_audio, "精确剪切丢失音频"
    shutil.rmtree(d)


def t_cut_lossless():
    from app.cut_engine import CutTask
    d = tempfile.mkdtemp()
    src = os.path.join(d, "src.mp4")
    # 关键帧间隔 1 秒：无损剪切按关键帧对齐，正常片源下偏差应 < 1s
    gen_test_video(src, seconds=6, gop=30)
    t = CutTask(4, src, 1.0, 4.0, "lossless")
    events = run_task_until(t, 60)
    done = [e for e in events if e["event"] == "done"]
    assert done, f"剪切失败: {events[-1] if events else '无事件'}"
    dur, wh, has_audio = probe(done[0]["path"])
    assert abs(dur - 3.0) < 1.0, f"无损剪切时长 {dur}（关键帧对齐允许 ±1s）"
    assert has_audio, "无损剪切丢失音频"
    shutil.rmtree(d)


def t_parse_time():
    from app.cut_engine import parse_time, fmt_time
    assert parse_time("83.5") == 83.5
    assert parse_time("1:23.5") == 83.5
    assert parse_time("1:00:04") == 3604.0
    assert parse_time("abc") is None
    assert fmt_time(83.5) == "01:23.50"


# ---------------- GPU 集成测试 ----------------
def t_image_enhance_real_mode():
    """真人·通用模式图片（使用新转换的 general-x4v3 模型）"""
    from app.enhance import EnhanceTask
    from PIL import Image
    d = tempfile.mkdtemp()
    src = os.path.join(d, "in.png")
    Image.new("RGB", (320, 240), (120, 80, 200)).save(src)
    t = EnhanceTask(5, [src], "real", 2, d)
    events = run_task_until(t, 180)
    done = [e for e in events if e["event"] == "done"]
    assert done and done[0].get("results"), f"失败: {events[-1] if events else '无事件'}"
    out = done[0]["results"][0][1]
    w, h = Image.open(out).size
    assert (w, h) == (640, 480), f"输出尺寸 {w}x{h} != 640x480"
    shutil.rmtree(d)


def t_video_enhance_anime_3x():
    """动漫视频 3 倍（v1.1 新路径，官方 -x3 权重）"""
    from app.enhance import EnhanceTask
    d = tempfile.mkdtemp()
    src = os.path.join(d, "v.mp4")
    gen_test_video(src, seconds=1, size="320x240")
    t = EnhanceTask(6, [src], "anime", 3, d)
    events = run_task_until(t, 300)
    done = [e for e in events if e["event"] == "done"]
    assert done and done[0].get("results"), f"失败: {events[-1] if events else '无事件'}"
    dur, (w, h), has_audio = probe(done[0]["results"][0][1])
    assert (w, h) == (960, 720), f"输出 {w}x{h} != 960x720"
    assert has_audio, "3x 视频丢失音频"
    shutil.rmtree(d)


def t_video_enhance_resume():
    """★ 核心测试：视频增强中断 → 保留现场 → 恢复 → 成品"""
    from app.enhance import EnhanceTask, ResumeTask, find_interrupted_jobs
    d = tempfile.mkdtemp()
    src = os.path.join(d, "v.mp4")
    gen_test_video(src, seconds=2, size="320x240")  # 60 帧
    t = EnhanceTask(7, [src], "anime", 2, d)
    events = []
    t.sig.connect(events.append)
    t.start()
    t0 = time.time()
    tmp_out = None
    # 等到完成 >= 15 帧后取消
    while time.time() - t0 < 60:
        QCoreApplication.processEvents()
        tmps = [x for x in os.listdir(d) if x.startswith(".sgtmp_") and
                os.path.isdir(os.path.join(d, x))]
        if tmps:
            tmp_out = os.path.join(d, tmps[0], "out")
            if os.path.isdir(tmp_out) and len(os.listdir(tmp_out)) >= 15:
                break
        time.sleep(0.12)
    t.cancel()
    deadline = time.time() + 15
    while t.isRunning() and time.time() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.05)
    # 线程结束后最后一条取消事件可能还在队列里，再泵几轮
    for _ in range(10):
        QCoreApplication.processEvents()
        time.sleep(0.05)
    cancelled = [e for e in events if e["event"] in ("cancelled", "error")]
    assert cancelled, f"任务未按预期取消, events={events}"
    jobs = find_interrupted_jobs(d)
    assert len(jobs) == 1, f"未找到可恢复任务: {jobs}"
    name, jd, done_frames = jobs[0]
    assert done_frames >= 15, f"已完成帧数异常: {done_frames}"
    assert jd["status"] == "interrupted"
    assert os.path.isfile(jd["source"])

    # ---- 恢复 ----
    r = ResumeTask(8, d, name)
    events2 = run_task_until(r, 300)
    done2 = [e for e in events2 if e["event"] == "done"]
    assert done2, f"恢复失败: {events2[-1] if events2 else '无事件'}"
    dur, (w, h), has_audio = probe(done2[0]["path"])
    assert (w, h) == (640, 480), f"恢复输出 {w}x{h} != 640x480"
    assert has_audio
    assert find_interrupted_jobs(d) == [], "恢复后任务档案未清理"
    assert not [x for x in os.listdir(d) if x.startswith(".sgtmp_")], "恢复后临时帧未清理"
    shutil.rmtree(d)


def t_model_conversion_validation():
    """重跑官方权重逐字节验证（转换器正确性的金标准）"""
    sys.path.insert(0, os.path.join(ROOT, "model_conv"))
    import importlib
    import convert
    importlib.reload(convert)
    models = os.path.join(ROOT, "tools", "realesrgan", "models")
    layers = convert.parse_param_layers(
        os.path.join(models, "realesr-animevideov3-x4.param"))
    sd = convert.load_state(os.path.join(ROOT, "model_conv", "realesr-animevideov3.pth"))
    tmp = os.path.join(tempfile.mkdtemp(), "r.bin")
    convert.write_bin(layers, sd, tmp)
    with open(os.path.join(models, "realesr-animevideov3-x4.bin"), "rb") as f:
        official = f.read()
    with open(tmp, "rb") as f:
        assert f.read() == official, "转换器输出与官方 bin 不一致！"
    # general-x4v3 模型文件存在且 param 魔数正确
    p = os.path.join(models, "realesr-general-x4v3.param")
    assert os.path.isfile(p)
    with open(p, "rb") as f:
        assert int(f.readline()) == 7767517
    assert os.path.getsize(os.path.join(models, "realesr-general-x4v3.bin")) > 2_000_000


def make_server(payload):
    """带 Range 支持的本地测试 HTTP 服务器，返回已启动的 server 对象。"""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            rng = self.headers.get("Range")
            if rng:
                start = int(re.match(r"bytes=(\d+)-", rng).group(1))
                self.send_response(206)
                self.send_header("Content-Range",
                                 f"bytes {start}-{len(payload)-1}/{len(payload)}")
                self.send_header("Content-Length", str(len(payload) - start))
                self.end_headers()
                self.wfile.write(payload[start:])
            else:
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def t_build_ytdlp_opts():
    from app.ytdlp_dl import build_ytdlp_opts as B
    assert B("best", "auto") == {"format": "bv*+ba/b"}
    assert B("720p", "auto") == {"format": "bv*[height<=720]+ba/b[height<=720]"}
    o = B("1080p", "mkv")
    assert o["format"].startswith("bv*[height<=1080]") and o["merge_output_format"] == "mkv"
    o = B("audio", "auto")
    assert o["format"] == "ba/b" and o["postprocessors"][0]["preferredcodec"] == "mp3"
    o = B("best", "m4a")
    assert o["format"] == "ba/b" and o["postprocessors"][0]["preferredcodec"] == "m4a"
    # 解析卡片选中的具体画质优先于预设
    assert B("best", "auto", format_id="137") == {"format": "137+bestaudio/best"}
    assert B("1080p", "mp4", format_id="137")["format"] == "137+bestaudio/best"
    assert B("1080p", "mp4", format_id="137")["merge_output_format"] == "mp4"


def t_dedupe_formats():
    from app.ytdlp_dl import dedupe_formats
    raw = [
        {"format_id": "a1", "height": 720, "vcodec": "avc1", "tbr": 2000},
        {"format_id": "a2", "height": 720, "vcodec": "avc1", "tbr": 3500},
        {"format_id": "a3", "height": 1080, "vcodec": "vp9", "tbr": 5000, "fps": 60},
        {"format_id": "a4", "height": 480, "vcodec": "avc1", "tbr": 800},
        {"format_id": "audio1", "vcodec": "none", "tbr": 128},
        {"format_id": "a5", "vcodec": "avc1", "tbr": 900},  # 无高度，应忽略
    ]
    out = dedupe_formats(raw)
    assert [f["height"] for f in out] == [1080, 720, 480], out
    by_h = {f["height"]: f for f in out}
    assert by_h[720]["format_id"] == "a2", "同高度应取最高码率"
    assert "60帧" in by_h[1080]["label"]
    assert all(f["format_id"] != "audio1" for f in out)
    assert out[-1]["label"] == "480p"


def t_url_media_kind():
    from app.url_detect import url_media_kind
    assert url_media_kind("http://a/x.mp4") == "video"
    assert url_media_kind("http://a/x.FLAC") == "audio"
    assert url_media_kind("http://a/x.webp") == "image"
    assert url_media_kind("https://b.com/page?id=1") is None


def t_extract_urls():
    from app.url_detect import extract_urls
    text = ("看这个 https://www.bilibili.com/video/BV1xx411c7mD 好看\n"
            "http://a.com/v/1.mp4，http://a.com/v/2.mp4。\n"
            "重复 https://WWW.Bilibili.com/video/BV1xx411c7mD 以及 "
            "https://a.com/x.m3u8）。")
    urls = extract_urls(text)
    assert urls[0] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert "http://a.com/v/1.mp4" in urls and "http://a.com/v/2.mp4" in urls
    assert "https://a.com/x.m3u8" in urls, f"中文标点截断失败: {urls}"
    assert len([u for u in urls if "bilibili" in u.lower()]) == 1, "大小写去重失败"
    assert extract_urls("没有链接的一句话") == []
    assert extract_urls("") == []


def t_download_tab_batch():
    """★ 下载页批量粘贴：6 个 URL（含 1 个重复）→ 去重 5 个 → 3 并发自动排队"""
    from app.download_tab import DownloadTab
    payload = bytes(range(256)) * 512  # 128 KB
    srv = make_server(payload)
    try:
        class _S:
            pass
        s = _S()
        s.save_dir = tempfile.mkdtemp()
        s.dl_quality = "best"
        s.dl_format = "auto"
        tab = DownloadTab(s)
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        text = "\n".join(f"{base}/f{i}.mp4" for i in range(1, 6))
        tab.url_edit.setPlainText(text + f"\n重复 {base}/f1.mp4")
        assert len(tab._urls()) == 5, "应去重为 5 个链接"
        tab._start()
        t0 = time.time()
        while time.time() - t0 < 60:
            QApplication.processEvents()
            if (not tab.threads and tab.active == 0
                    and tab.pending.qsize() == 0 and tab.next_id > 1):
                break
            time.sleep(0.05)
        for _ in range(10):
            QApplication.processEvents()
            time.sleep(0.03)
        files = [f for f in os.listdir(s.save_dir) if f.endswith(".mp4")]
        assert len(files) == 5, f"完成 5 个任务, 实际 {len(files)}: {files}"
        for f in files:
            assert open(os.path.join(s.save_dir, f), "rb").read() == payload, f"{f} 内容不一致"
        shutil.rmtree(s.save_dir)
    finally:
        srv.shutdown()


def t_direct_convert_image():
    """直链 PNG 下载后转 JPG"""
    from app.direct_dl import DirectDownloadTask
    d = tempfile.mkdtemp()
    src = os.path.join(d, "pic.png")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi",
                    "-i", "color=c=red:s=64x64", "-frames:v", "1", src], check=True)
    srv = make_server(open(src, "rb").read())
    try:
        out_d = tempfile.mkdtemp()
        t = DirectDownloadTask(10, f"http://127.0.0.1:{srv.server_address[1]}/pic.png",
                               out_d, fmt="jpg")
        events = run_task_until(t, 60)
        done = [e for e in events if e["event"] == "done"]
        assert done, f"未完成: {events[-1] if events else '无事件'}"
        out = done[0]["path"]
        assert out.lower().endswith(".jpg"), f"输出 {out}"
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                            "stream=codec_name", "-of", "csv=p=0", out],
                           capture_output=True, text=True)
        assert "mjpeg" in r.stdout, f"codec={r.stdout!r}"
        assert done[0].get("note"), "缺少转换说明"
        shutil.rmtree(out_d); shutil.rmtree(d)
    finally:
        srv.shutdown()


def t_direct_convert_audio():
    """直链 MP4 下载后提取 MP3"""
    from app.direct_dl import DirectDownloadTask
    d = tempfile.mkdtemp()
    src = os.path.join(d, "clip.mp4")
    gen_test_video(src, seconds=1)
    srv = make_server(open(src, "rb").read())
    try:
        out_d = tempfile.mkdtemp()
        t = DirectDownloadTask(11, f"http://127.0.0.1:{srv.server_address[1]}/clip.mp4",
                               out_d, fmt="mp3")
        events = run_task_until(t, 60)
        done = [e for e in events if e["event"] == "done"]
        assert done, f"未完成: {events[-1] if events else '无事件'}"
        out = done[0]["path"]
        assert out.lower().endswith(".mp3"), f"输出 {out}"
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                            "stream=codec_type,codec_name", "-of", "csv=p=0", out],
                           capture_output=True, text=True)
        assert "mp3" in r.stdout and "video" not in r.stdout, f"streams={r.stdout!r}"
        shutil.rmtree(out_d); shutil.rmtree(d)
    finally:
        srv.shutdown()


def t_extract_audio_mp3():
    """本地 MP4 全程提取 MP3"""
    from app.cut_engine import CutTask
    d = tempfile.mkdtemp()
    src = os.path.join(d, "mv.mp4")
    gen_test_video(src, seconds=6)
    t = CutTask(12, src, 0.0, 6.0, "accurate", audio_fmt="mp3")
    events = run_task_until(t, 120)
    done = [e for e in events if e["event"] == "done"]
    assert done, f"提取失败: {events[-1] if events else '无事件'}"
    out = done[0]["path"]
    assert out.lower().endswith(".mp3"), f"输出 {out}"
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                        "stream=codec_type,codec_name:format=duration",
                        "-of", "csv=p=0", out], capture_output=True, text=True)
    assert "mp3" in r.stdout and "video" not in r.stdout, f"streams={r.stdout!r}"
    dur = float([l for l in r.stdout.strip().splitlines() if "," not in l][0])
    assert abs(dur - 6.0) < 0.3, f"时长 {dur}"
    shutil.rmtree(d)


def t_extract_audio_m4a_range():
    """本地 MP4 指定片段（1s→4s）提取 M4A"""
    from app.cut_engine import CutTask
    d = tempfile.mkdtemp()
    src = os.path.join(d, "mv.mp4")
    gen_test_video(src, seconds=6)
    t = CutTask(13, src, 1.0, 4.0, "accurate", audio_fmt="m4a")
    events = run_task_until(t, 120)
    done = [e for e in events if e["event"] == "done"]
    assert done, f"提取失败: {events[-1] if events else '无事件'}"
    out = done[0]["path"]
    assert out.lower().endswith(".m4a"), f"输出 {out}"
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                        "stream=codec_type,codec_name:format=duration",
                        "-of", "csv=p=0", out], capture_output=True, text=True)
    assert "aac" in r.stdout and "video" not in r.stdout, f"streams={r.stdout!r}"
    dur = float([l for l in r.stdout.strip().splitlines() if "," not in l][0])
    assert abs(dur - 3.0) < 0.3, f"时长 {dur}"
    shutil.rmtree(d)


def main():
    make_app()
    print("== 单元测试 ==")
    check("工具函数", t_utils)
    check("URL 识别", t_url_detect)
    check("模型方案表", t_plans)
    check("尺寸取偶滤镜", t_even_vf)
    check("防睡眠引用计数", t_sleep_guard)
    check("任务档案读写/扫描", t_job_descriptors)
    check("时间解析", t_parse_time)
    check("yt-dlp 画质/格式参数", t_build_ytdlp_opts)
    check("解析画质列表去重", t_dedupe_formats)
    check("直链媒体类别识别", t_url_media_kind)
    check("多 URL 提取", t_extract_urls)
    print("== 下载引擎集成 ==")
    check("直链下载 Range 断点续传", t_direct_download_resume)
    check("直链下载全新下载", t_direct_download_fresh_and_cancel)
    check("直链 PNG→JPG 转换", t_direct_convert_image)
    check("直链 MP4→MP3 提取", t_direct_convert_audio)
    check("下载页批量粘贴自动排队", t_download_tab_batch)
    print("== 剪切集成 ==")
    check("精确剪切（重编码）", t_cut_accurate)
    check("无损剪切（流复制）", t_cut_lossless)
    check("本地 MP4 提取 MP3（全程）", t_extract_audio_mp3)
    check("本地 MP4 提取 M4A（片段）", t_extract_audio_m4a_range)
    print("== 模型转换 ==")
    check("转换器官方权重逐字节验证", t_model_conversion_validation)
    print("== GPU 集成 ==")
    check("图片增强·真人通用模式 2x", t_image_enhance_real_mode)
    check("视频增强·动漫 3x", t_video_enhance_anime_3x)
    check("视频增强·中断→恢复全流程", t_video_enhance_resume)

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print()
    print(f"总计 {len(RESULTS)} 项，通过 {len(RESULTS)-len(fails)}，失败 {len(fails)}")
    if fails:
        for name, _, _, err in fails:
            print(f"  FAIL {name}: {err[:200]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
