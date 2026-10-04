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


def t_job_running_recoverable():
    """★ P1-1：进程被杀时档案来不及标记、停在 running——扫描必须能发现，
    退出兜底标记（等价 closeEvent 动作）后可正常恢复"""
    from app.enhance import (write_job, find_interrupted_jobs,
                             mark_running_jobs_interrupted)
    d = tempfile.mkdtemp()
    tmp = os.path.join(d, ".sgtmp_77_1")
    os.makedirs(os.path.join(tmp, "out"))
    for i in range(1, 6):
        open(os.path.join(tmp, "out", f"{i:06d}.jpg"), "w").close()
    # 模拟进程被杀：档案停留在 running（工作线程没机会执行 mark_job）
    write_job(d, 77, "C:/v.mp4", "anime", 2, ".sgtmp_77_1", 30.0, 40,
              status="running")
    jobs = find_interrupted_jobs(d)
    assert len(jobs) == 1 and jobs[0][2] == 5, f"running 档案应可发现: {jobs}"
    # 主线程兜底标记 → 状态转 interrupted，仍可发现
    mark_running_jobs_interrupted(d)
    jobs = find_interrupted_jobs(d)
    assert len(jobs) == 1 and jobs[0][1]["status"] == "interrupted", jobs
    # 没有现场目录（成功清理与档案删除之间被杀）→ 不可恢复，不得出现
    write_job(d, 78, "C:/v.mp4", "anime", 2, ".sgtmp_78_1", 30.0, 0,
              status="running")
    assert all(j[1].get("tmp") != ".sgtmp_78_1" for j in find_interrupted_jobs(d)), \
        "无现场目录的档案不应进入恢复列表"
    shutil.rmtree(d)


def t_m3u8_save_names():
    """★ P1-2：多个 m3u8 任务同秒启动，兜底名不得冲突（否则分片互相覆盖写坏文件）"""
    import hashlib
    from app.m3u8_dl import default_save_name
    a = default_save_name("http://a.live/x/index.m3u8")
    b = default_save_name("http://b.live/x/index.m3u8")
    assert a != b, f"同秒兜底名冲突: {a} vs {b}"
    # 同一链接的哈希后缀稳定（同名重复下载覆盖，不产生垃圾副本）；
    # 只比后缀，避免两次调用恰好跨秒时时间戳变化造成偶发失败
    ha = hashlib.md5(b"http://a.live/x/index.m3u8").hexdigest()[:6]
    assert a.endswith("_" + ha), f"缺少 URL 哈希后缀: {a}"
    assert default_save_name("http://a.live/x/index.m3u8", audio_only=True) \
        .startswith("音频_"), "仅音频任务应以 音频_ 开头"


def t_frame_integrity():
    """P2-5：半写截断的 jpg 必须被判为损坏，按缺失帧重算"""
    from app.enhance import _frame_ok
    good = os.path.join(tempfile.mkdtemp(), "000001.jpg")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi",
                    "-i", "color=c=red:s=32x32", "-frames:v", "1", good],
                   check=True)
    assert _frame_ok(good), "完整 jpg 应通过校验"
    trunc = good.replace("000001", "000002")
    data = open(good, "rb").read()
    with open(trunc, "wb") as f:
        f.write(data[:len(data) // 2])
    assert not _frame_ok(trunc), "截断 jpg 应判为损坏"
    empty = good.replace("000001", "000003")
    open(empty, "wb").close()
    assert not _frame_ok(empty), "空文件应判为损坏"
    assert not _frame_ok(good.replace("000001", "000004")), "不存在的文件应判为损坏"
    shutil.rmtree(os.path.dirname(good))


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


def t_video_enhance_resume_zero_total():
    """★ P1-3：抽帧阶段被中断（档案 total=0）→ 恢复必须全量重抽，
    不得把半截帧当全部合成出时长短一截的半成品"""
    from app.enhance import write_job, ResumeTask, find_interrupted_jobs, \
        mark_running_jobs_interrupted
    d = tempfile.mkdtemp()
    src = os.path.join(d, "v.mp4")
    gen_test_video(src, seconds=2, size="320x240")  # 60 帧 @30fps
    tmp_name = ".sgtmp_zt_1"
    frames_in = os.path.join(d, tmp_name, "in")
    os.makedirs(frames_in)
    os.makedirs(os.path.join(d, tmp_name, "out"))
    # 模拟抽帧中途被杀：现场只有前 10 帧输入帧，档案停在 running 且 total=0
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", src, "-frames:v", "10",
                    os.path.join(frames_in, "%06d.jpg")], check=True)
    write_job(d, "zt1", src, "anime", 2, tmp_name, 30.0, 0, status="running")
    mark_running_jobs_interrupted(d)  # 等价 closeEvent 退出兜底
    jobs = find_interrupted_jobs(d)
    assert len(jobs) == 1, f"应发现 1 个可恢复任务: {jobs}"
    r = ResumeTask("ztr", d, jobs[0][0])
    events = run_task_until(r, 300)
    done = [e for e in events if e["event"] == "done"]
    assert done, f"恢复失败: {events[-1] if events else '无事件'}"
    dur, (w, h), has_audio = probe(done[0]["path"])
    # 修复前：10 帧/30fps ≈ 0.33s 且音画不同步；修复后：全片 2s
    assert abs(dur - 2.0) < 0.3, f"恢复出的视频时长 {dur:.2f}s，应为全片 2s"
    assert (w, h) == (640, 480), f"输出 {w}x{h} != 640x480"
    assert has_audio, "恢复输出丢失音频"
    assert find_interrupted_jobs(d) == [], "恢复后任务档案未清理"
    shutil.rmtree(d)


def t_video_enhance_real_filename_scale():
    """★ P2-4：真人视频固定输出 2 倍，文件名必须标实际倍数（不得虚标 3x/4x）"""
    from app.enhance import EnhanceTask
    d = tempfile.mkdtemp()
    src = os.path.join(d, "clip.mp4")
    gen_test_video(src, seconds=1, size="320x240")
    t = EnhanceTask(9, [src], "real", 3, d)  # 用户选 3 倍，实际固定输出 2 倍
    events = run_task_until(t, 300)
    done = [e for e in events if e["event"] == "done"]
    assert done and done[0].get("results"), f"失败: {events[-1] if events else '无事件'}"
    out = done[0]["results"][0][1]
    assert os.path.basename(out).endswith("_高清2x.mp4"), \
        f"文件名应标实际 2 倍: {os.path.basename(out)}"
    dur, (w, h), _ = probe(out)
    assert (w, h) == (640, 480), f"输出 {w}x{h} != 640x480"
    assert not [x for x in os.listdir(d) if x.startswith(".sgjob_")], "成功后档案未清理"
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
    # 抖音分享文本：emoji / 中文标点 / 短链
    share = ("8.88 Kfx.zda 10/26 q@W.eu 复制打开抖音，看看【张三的作品】恭喜发财 "
             "https://v.douyin.com/ybM4vQ3JbgA/ 复制此链接，打开抖音搜索，直接观看视频！")
    durls = [u for u in extract_urls(share) if "v.douyin.com" in u]
    assert len(durls) == 1, f"抖音短链提取失败: {durls}"
    # 无空格口令：链接后紧跟中文不得污染（此前会崩在 ascii 编码）
    nospace = ("7.99复制打开抖音，看看【张三的作品】"
               "https://v.douyin.com/iRNBho6u/复制此链接，打开Dou音搜索")
    nurls = [u for u in extract_urls(nospace) if "v.douyin.com" in u]
    assert nurls == ["https://v.douyin.com/iRNBho6u/"], nurls


def t_extract_urls_bare():
    """U1：无协议头 / 裸短链 / 纯 BV 号，以及既有行为零回归"""
    from app.url_detect import extract_urls
    # 必须保持通过的既有行为（中文口令剥离、紧跟中文截断、一行多个）
    assert extract_urls("7.43 复制打开抖音，看看 https://v.douyin.com/abc/ 的作品") \
        == ["https://v.douyin.com/abc/"]
    assert extract_urls("https://v.douyin.com/abc/这个视频很好看") \
        == ["https://v.douyin.com/abc/"]
    assert len(extract_urls("https://a.com/1.mp4 和 https://b23.tv/xyz")) == 2
    # 新增能力
    assert extract_urls("www.bilibili.com/video/BV1xx411c7mD") \
        == ["https://www.bilibili.com/video/BV1xx411c7mD"]
    assert extract_urls("b23.tv/abc123") == ["https://b23.tv/abc123"]
    assert extract_urls("BV1xx411c7mD") == ["https://www.bilibili.com/video/BV1xx411c7mD"]
    # 带协议头的完整链接 + 同一个裸 BV 号：只保留原文那份，不重复
    both = extract_urls("https://www.bilibili.com/video/BV1xx411c7mD BV1xx411c7mD")
    assert both == ["https://www.bilibili.com/video/BV1xx411c7mD"], both
    # 不应误抓
    assert extract_urls("这个网站 example.org 不错") == []
    assert extract_urls("请打开 C:\\www\\bilibili.com\\x") == []
    # 带协议头的链接不得被裸主机规则重复匹配
    assert extract_urls("https://www.bilibili.com/video/BV1xx411c7mD") \
        == ["https://www.bilibili.com/video/BV1xx411c7mD"]
    # detect_engine 对补全后的形态走既有路径
    from app.url_detect import detect_engine
    assert detect_engine("https://b23.tv/abc123") == "site"
    assert detect_engine("https://www.bilibili.com/video/BV1xx411c7mD") == "site"


def t_estimate_video_job():
    """B2 预检估算：用 E2E2 实测样本（8 秒 1080x1920 真人·通用）回代。
    实测：中间文件 1.9 GB / 耗时 843 s / 195 帧（24fps×8s=192）。"""
    from app.enhance import estimate_video_job
    d = tempfile.mkdtemp()
    src = os.path.join(d, "v.mp4")
    gen_test_video(src, seconds=8, size="1080x1920", fps=24)
    r = estimate_video_job(src, "real", 2)
    assert r, "估算不应返回 None"
    assert abs(r["frames"] - 192) <= 3, f"frames={r['frames']}"
    # 磁盘估算刻意保守：应落在实测 1.9GB 的 1.3~2.0 倍区间（宁可误拦不可漏拦）
    assert 1.3 <= r["gb"] / 1.9 <= 2.0, f"gb={r['gb']:.2f}"
    # 耗时估算按实测 843s 校验，系数拟合 ±3%、整体精度约 ±20%
    assert 0.8 <= (r["hours"] * 3600) / 843 <= 1.3, f"hours={r['hours']:.3f}"
    # 读不到源信息 → None，调用方跳过预检（预检不能变成新故障点）
    assert estimate_video_job(os.path.join(d, "不存在.mp4"), "real", 2) is None
    # 动漫模式（m_scale 随用户倍数、系数按 m_scale/2 线性放大）：4x 耗时应为 2x 的 2 倍
    r2a = estimate_video_job(src, "anime", 2)
    r2 = estimate_video_job(src, "anime", 4)
    assert r2a and r2, "动漫模式估算不应返回 None"
    assert abs(r2["hours"] / r2a["hours"] - 2.0) < 0.01, \
        f"anime 4x/2x = {r2['hours'] / r2a['hours']:.3f}，应为线性 2.0"
    # 动漫 4x（0.93 s/Mpx）仍应快于真人 2x（2.05 s/Mpx、同 m_scale=4）：系数表在起作用
    assert r2["hours"] < r["hours"], "动漫 4x 不应比真人模式更慢"
    shutil.rmtree(d)


_DY_SAMPLE_DATA = {
    "loaderData": {
        "video_layout": None,
        "video_(id)/page": {
            "itemId": "7609259711708378534",
            "videoInfoRes": {"item_list": [{
                "desc": "恭喜发财 #测试",
                "author": {"nickname": "测试作者"},
                "video": {
                    "duration": 67221,
                    "play_addr": {"url_list": [
                        "https://aweme.snssdk.com/aweme/v1/playwm/"
                        "?line=0&ratio=720p&video_id=v0300fg10000"]},
                    "cover": {"url_list": ["https://p11-sign.douyinpic.com/cover.jpg"]},
                },
            }]},
        },
    }
}
_DY_SAMPLE_HTML = ("<html><script>window._ROUTER_DATA = "
                   + json.dumps(_DY_SAMPLE_DATA, ensure_ascii=False)
                   + ";</script></html>")


def t_douyin_parse():
    from app.douyin import (parse_share_html, build_play_url, is_douyin,
                            extract_aweme_id, DouyinError)
    assert is_douyin("https://v.douyin.com/abc123/")
    assert is_douyin("https://www.iesdouyin.com/share/video/123/")
    assert not is_douyin("https://www.bilibili.com/video/BV1x")

    # 视频链接的各形态 ID 提取（含精选页 modal_id 形式）
    assert extract_aweme_id("https://www.douyin.com/video/7609259711708378534") \
        == "7609259711708378534"
    assert extract_aweme_id("https://www.douyin.com/note/7609259711708378534") \
        == "7609259711708378534"
    assert (extract_aweme_id(
        "https://www.douyin.com/jingxuan?modal_id=7690158493193588010")
        == "7690158493193588010")
    assert (extract_aweme_id(
        "https://www.douyin.com/discover?modal_id=7609259711708378534&foo=1")
        == "7609259711708378534")
    assert extract_aweme_id("https://live.douyin.com/123abc") == ""

    info = parse_share_html(_DY_SAMPLE_HTML)
    assert info["title"] == "恭喜发财 #测试", info["title"]
    assert info["author"] == "测试作者"
    assert abs(info["duration"] - 67.221) < 0.01, info["duration"]
    assert info["cover"].startswith("https://p11-sign.douyinpic.com/")
    play = info["play_url"]
    assert "/play/" in play and "playwm" not in play, play
    assert "ratio=1080p" in play, play

    assert (build_play_url("https://aweme.snssdk.com/aweme/v1/playwm/?ratio=720p&x=1")
            == "https://aweme.snssdk.com/aweme/v1/play/?ratio=1080p&x=1")

    # 空壳 SSR（视频失效）应有明确错误
    empty = "<script>window._ROUTER_DATA = " + json.dumps(
        {"loaderData": {"video_(id)/page": {"itemId": "1"}}}) + ";</script>"
    try:
        parse_share_html(empty)
        raise AssertionError("空壳应报错")
    except DouyinError:
        pass
    # 图集（note）应有明确错误
    gallery = ("<script>window._ROUTER_DATA = " + json.dumps(
        {"loaderData": {"note_(id)/page": {"videoInfoRes": {"item_list": [{
            "desc": "图集",
            "images": [{"url_list": ["https://x/a.jpg"]}],
            "video": {},
        }]}}}}) + ";</script>")
    try:
        parse_share_html(gallery)
        raise AssertionError("图集应报错")
    except DouyinError as e:
        assert "图集" in str(e)
    # 服务端 filter_list 的失败原因原样透传（仅自己可见等）
    filtered = ("<script>window._ROUTER_DATA = " + json.dumps({
        "loaderData": {"video_(id)/page": {"videoInfoRes": {
            "item_list": [],
            "filter_list": [{"filter_reason": "status_self_see",
                             "notice": "抱歉，作品不见了",
                             "detail_msg": "因作品权限或已被删除，无法观看"}]}}}})
        + ";</script>")
    try:
        parse_share_html(filtered)
        raise AssertionError("filtered 应报错")
    except DouyinError as e:
        assert "仅作者自己可见" in str(e) and "作品权限" in str(e), str(e)
    # 口令无空格粘贴：SHORT_RE.group(0) 是不含中文的干净短链
    from app.douyin import SHORT_RE
    m = SHORT_RE.match("https://v.douyin.com/iRNBho6u/复制此链接，打开Dou音搜索")
    assert m and m.group(0) == "https://v.douyin.com/iRNBho6u/", m and m.group(0)


def t_friendly_errors():
    """全界面中文报错：底层英文异常 → 中文；项目内中文消息透传"""
    from app.errors import friendly_error
    import urllib.error

    # 项目内抛出的中文错误原样透传
    assert friendly_error(Exception("抖音解析失败：测试")) == "抖音解析失败：测试"
    # 文件系统类
    assert friendly_error(FileNotFoundError(2, "No such file", "C:/x.mp4")) \
        == "找不到文件：C:/x.mp4"
    assert "没有权限" in friendly_error(PermissionError(13, "Permission denied"))
    assert "磁盘空间不足" in friendly_error(OSError(28, "No space left on device"))
    # 网络类
    assert "404" in friendly_error(urllib.error.HTTPError(
        "http://a", 404, "Not Found", {}, None))
    assert "超时" in friendly_error(TimeoutError("timed out"))
    assert "网络连接失败" in friendly_error(ConnectionResetError())
    ue = urllib.error.URLError(ConnectionRefusedError(111))
    assert "无法连接" in friendly_error(ue)
    # 关键词映射（yt-dlp 英文消息）
    assert "暂不支持" in friendly_error(Exception("ERROR: Unsupported URL: https://x"))
    assert "登录" in friendly_error(Exception("ERROR: Sign in to confirm you're not a bot"))
    assert "429" in friendly_error(Exception("HTTP Error 429: Too Many Requests"))
    # Cookie 三连：需要 cookie / cookie 文件坏 / 自动读取被禁
    assert "Cookie" in friendly_error(
        Exception("[Douyin] Fresh cookies (not necessarily logged in) are needed"))
    assert "Cookie 文件格式不正确" in friendly_error(
        Exception("Cookie file cookies.txt is not valid"))
    assert "cookies.txt" in friendly_error(
        Exception("Failed to decrypt with DPAPI"))
    # 无 format / 上游 extractor 崩溃 / GitHub issue 链接截断
    assert "视频流" in friendly_error(Exception("[XiaoHongShu] No video formats found!"))
    assert "上游" in friendly_error(TypeError("'NoneType' object is not subscriptable"))
    out2 = friendly_error(Exception(
        "ERROR: something (see https://github.com/yt-dlp/yt-dlp/issues/12345)"))
    assert "github.com" not in out2, out2
    # netenv：代理决策
    from app.netenv import effective_proxy
    assert effective_proxy("off", "http://x:1") == ""
    assert effective_proxy("manual", " http://127.0.0.1:7890 ") == "http://127.0.0.1:7890"
    # 兜底不暴露英文细节
    out = friendly_error(RuntimeError("some weird english detail"), "下载失败")
    assert "weird" not in out and "下载失败" in out, out
    assert friendly_error(RuntimeError(""), "下载失败") == "下载失败"


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
        # 清除记录回归：任务结束后线程已移除，行必须仍可清除（曾经清不掉）
        assert len(tab.rows) == 5, f"完成后应剩 5 行: {len(tab.rows)}"
        tab._clear_finished()
        assert tab.list.count() == 0 and not tab.rows, "清除记录后仍有残留行"
        assert tab.empty_state.isVisibleTo(tab), "清除后应回到空状态"
        shutil.rmtree(s.save_dir)
    finally:
        srv.shutdown()


def t_direct_guard():
    """直链防线：HTML 验证页拒绝落盘 + 标题文件名按类型补扩展名"""
    from app.direct_dl import DirectDownloadTask, _ext_for_content

    assert _ext_for_content("video/mp4") == ".mp4"
    assert _ext_for_content("image/png; charset=binary") == ".png"
    assert _ext_for_content("application/octet-stream") == ""

    # 1) 服务器返回 text/html（模拟抖音风控验证页）：必须报错且不落盘
    d = tempfile.mkdtemp()
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<html><head><meta charset=\"UTF-8\"></head><body>verify</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=UTF-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        t = DirectDownloadTask(90, f"http://127.0.0.1:{srv.server_address[1]}/v",
                               d, name="标题 #测试")
        events = run_task_until(t, 30)
        errs = [e for e in events if e["event"] == "error"]
        assert errs and "网页" in errs[0]["error"], events[-1] if events else "无事件"
        assert os.listdir(d) == [], f"不应落盘: {os.listdir(d)}"
    finally:
        srv.shutdown()

    # 2) video/mp4 响应 + 无扩展名的标题 → 文件名自动补 .mp4
    class H2(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"\x00\x00\x00 ftypisom" + b"\x00" * 4096
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv2 = ThreadingHTTPServer(("127.0.0.1", 0), H2)
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    try:
        t = DirectDownloadTask(91, f"http://127.0.0.1:{srv2.server_address[1]}/v",
                               d, name="恶搞之家 #动画 #解说")
        events = run_task_until(t, 30)
        done = [e for e in events if e["event"] == "done"]
        assert done, f"未完成: {events[-1] if events else '无事件'}"
        assert os.path.basename(done[0]["path"]) == "恶搞之家 #动画 #解说.mp4"
    finally:
        srv2.shutdown()
    # 3) 403（如抖音 CDN 签名过期）：报错含 403 且不落盘
    class H3(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv3 = ThreadingHTTPServer(("127.0.0.1", 0), H3)
    threading.Thread(target=srv3.serve_forever, daemon=True).start()
    d3 = tempfile.mkdtemp()
    try:
        t = DirectDownloadTask(92, f"http://127.0.0.1:{srv3.server_address[1]}/v", d3)
        events = run_task_until(t, 30)
        errs = [e for e in events if e["event"] == "error"]
        assert errs and "403" in errs[0]["error"], events[-1] if events else "无事件"
        assert os.listdir(d3) == [], f"不应落盘: {os.listdir(d3)}"
    finally:
        srv3.shutdown()
        shutil.rmtree(d)


def t_douyin_download_referer():
    """★ 抖音 403 修复：CDN 把播放链接自身域名当 Referer 会判盗链 403
    （实测 2026-10），DouyinDownloadTask 必须固定 Referer=https://www.douyin.com/"""
    from app.direct_dl import DouyinDownloadTask
    payload = bytes(range(256)) * 1024  # 256 KB
    seen = {"referer": []}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            ref = self.headers.get("Referer")
            if ref is None:
                # 预检（_play_is_stale）无 Referer：CDN 放行，返回媒体头
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", "16")
                self.end_headers()
                self.wfile.write(b"\x00\x00\x00 ftypisom")
                return
            seen["referer"].append(ref)
            if ref != "https://www.douyin.com/":
                # 模拟 CDN 防盗链：Referer 不对直接 403
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        d = tempfile.mkdtemp()
        t = DouyinDownloadTask(
            93, "https://v.douyin.com/mocktest/", d,
            play_url=f"http://127.0.0.1:{srv.server_address[1]}/play.mp4",
            name="防盗链测试")
        events = run_task_until(t, 60)
        done = [e for e in events if e["event"] == "done"]
        assert done, f"未完成: {events[-1] if events else '无事件'}"
        assert seen["referer"], "下载请求未经过 Referer 校验点"
        assert all(r == "https://www.douyin.com/" for r in seen["referer"]), \
            f"Referer 未固定为站点页: {seen['referer']}"
        assert open(done[0]["path"], "rb").read() == payload, "下载内容不一致"
        shutil.rmtree(d)
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


def t_all_pages_construct():
    """★ 四页全部实例化（新增设置项后最容易漏 import/拼错控件名）"""
    from app.main_window import MainWindow

    class _S:
        pass
    s = _S()
    s.save_dir = tempfile.mkdtemp()
    s.enhance_dir = tempfile.mkdtemp()
    s.dl_quality = "best"
    s.dl_format = "auto"
    s.theme = "light"
    s.cookie_file = ""
    s.proxy_mode = "off"
    s.proxy_url = ""
    w = MainWindow(s)
    assert w.stack.count() == 4
    st = w.page_set
    assert st.theme_combo.count() == 3
    assert st.proxy_mode.count() == 3
    for attr in ("theme_combo", "proxy_mode", "proxy_edit"):
        assert hasattr(st, attr), attr
    shutil.rmtree(s.save_dir)
    shutil.rmtree(s.enhance_dir)


def main():
    make_app()
    print("== 单元测试 ==")
    check("工具函数", t_utils)
    check("URL 识别", t_url_detect)
    check("模型方案表", t_plans)
    check("尺寸取偶滤镜", t_even_vf)
    check("防睡眠引用计数", t_sleep_guard)
    check("任务档案读写/扫描", t_job_descriptors)
    check("任务档案 running 可发现+退出兜底", t_job_running_recoverable)
    check("m3u8 兜底名防同秒冲突", t_m3u8_save_names)
    check("输出帧完整性校验", t_frame_integrity)
    check("时间解析", t_parse_time)
    check("yt-dlp 画质/格式参数", t_build_ytdlp_opts)
    check("解析画质列表去重", t_dedupe_formats)
    check("直链媒体类别识别", t_url_media_kind)
    check("多 URL 提取", t_extract_urls)
    check("无协议头/裸短链/BV号 提取", t_extract_urls_bare)
    check("增强预检估算（E2E2 回代）", t_estimate_video_job)
    check("抖音解析（离线样本）", t_douyin_parse)
    check("四页全构造冒烟", t_all_pages_construct)
    check("中文报错翻译层", t_friendly_errors)
    print("== 下载引擎集成 ==")
    check("直链下载 Range 断点续传", t_direct_download_resume)
    check("直链下载全新下载", t_direct_download_fresh_and_cancel)
    check("直链防线（HTML 拒绝/扩展名补全）", t_direct_guard)
    check("抖音下载 Referer 防盗链", t_douyin_download_referer)
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
    check("视频增强·抽帧中断恢复（total=0 全量重抽）", t_video_enhance_resume_zero_total)
    check("视频增强·真人文件名标实际倍数", t_video_enhance_real_filename_scale)

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print()
    print(f"总计 {len(RESULTS)} 项，通过 {len(RESULTS)-len(fails)}，失败 {len(fails)}")
    if fails:
        for name, _, _, err in fails:
            print(f"  FAIL {name}: {err[:200]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
