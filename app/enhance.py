"""画质增强引擎 v1.1：
- 三种模式：照片(x4plus) / 动漫·动画(6B+视频快速模型) / 真人·通用(general-x4v3)
- 视频断点续跑：任务档案 JSON + 失败保留现场 + 硬链接跳过已完成帧
"""
import json
import os
import shutil
import subprocess
import time

from base_task import BaseTask
from paths import ffmpeg, ffprobe, realesrgan_exe, realesrgan_model
from utils import IMAGE_EXTS, VIDEO_EXTS, unique_path

CREATE_NO_WINDOW = 0x08000000
JOB_PREFIX = ".sgjob_"

# 图片模式 -> 4倍质量模型（低于4倍的倍数用「放大后精细缩回」实现）
IMAGE_MODELS = {
    "photo": "realesrgan-x4plus",
    "anime": "realesrgan-x4plus-anime",
}


def plan_for(mode, scale, is_video):
    scale = int(scale)
    if is_video:
        if mode == "anime":
            # 官方视频快速模型自带 2/3/4 倍权重，exe 按 -s 自动加载对应 -xN 文件
            return ("realesr-animevideov3", scale, 1.0)
        # 真人/照片视频：固定输出 2x；通用模型快，缺失时回退 x4plus（极慢）
        if os.path.isfile(realesrgan_model("realesr-general-x4v3")):
            return ("realesr-general-x4v3", 4, 0.5)
        return ("realesrgan-x4plus", 4, 0.5)
    # ---- 图片 ----
    if mode == "anime" and scale == 2:
        # 快速模型原生 2 倍，比 6B 放大再缩回更快
        return ("realesr-animevideov3", 2, 1.0)
    if mode == "real":
        model = ("realesr-general-x4v3"
                 if os.path.isfile(realesrgan_model("realesr-general-x4v3"))
                 else "realesrgan-x4plus")
        return (model, 4, scale / 4.0)
    model = IMAGE_MODELS.get(mode, "realesrgan-x4plus")
    return (model, 4, scale / 4.0)


def even_vf(eff):
    """输出缩放：eff 相对模型输出帧的系数；并保证宽高为偶数（yuv420p 要求）。"""
    return (f"scale=trunc(iw*{eff}/2)*2:trunc(ih*{eff}/2)*2"
            f":flags=lanczos")


class CancelledError(Exception):
    pass


# ---------------- 任务档案（断点续跑） ----------------

def job_file(out_dir, task_id):
    return os.path.join(out_dir, f"{JOB_PREFIX}{task_id}.json")


def write_job(out_dir, task_id, source, mode, scale, tmp_name, fps, total,
              status="running"):
    data = {
        "kind": "video",
        "source": os.path.abspath(source),
        "mode": mode,
        "scale": int(scale),
        "tmp": tmp_name,
        "fps": fps,
        "total": int(total),
        "status": status,
        "created": time.time(),
        "updated": time.time(),
    }
    with open(job_file(out_dir, task_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def mark_job(out_dir, task_id, status):
    p = job_file(out_dir, task_id)
    if not os.path.isfile(p):
        return
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        d["status"] = status
        d["updated"] = time.time()
        d["done"] = _count_frames(os.path.join(out_dir, d.get("tmp", ""), "out"))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except (OSError, ValueError, KeyError):
        pass


def clear_job(out_dir, task_id):
    p = job_file(out_dir, task_id)
    if os.path.isfile(p):
        try:
            os.remove(p)
        except OSError:
            pass


def _count_frames(d):
    try:
        with os.scandir(d) as it:
            return sum(1 for _ in it)
    except OSError:
        return 0


def find_interrupted_jobs(out_dir):
    """扫描输出目录中可续跑的任务，返回 [(job文件名, 描述dict, 已完成帧数), ...]"""
    jobs = []
    try:
        names = os.listdir(out_dir)
    except OSError:
        return jobs
    for fn in names:
        if not (fn.startswith(JOB_PREFIX) and fn.endswith(".json")):
            continue
        p = os.path.join(out_dir, fn)
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        tmp_root = os.path.join(out_dir, d.get("tmp", ""))
        if d.get("status") != "interrupted" or not os.path.isdir(tmp_root):
            continue
        done = _count_frames(os.path.join(tmp_root, "out"))
        jobs.append((fn, d, done))
    jobs.sort(key=lambda x: -x[1].get("updated", 0))
    return jobs


def run_realesrgan(task, inp, outp, model, m_scale, fmt="png",
                   progress_cb=None):
    """启动超分引擎；目录模式输出必须为 jpg。返回退出码。
    进程句柄挂到 task._proc 上（cancel 时由 BaseTask 统一杀死）。
    注意：stdout/stderr 必须 DEVNULL——挂 PIPE 不读会塞满管道卡死进程。"""
    cmd = [realesrgan_exe(), "-i", inp, "-o", outp,
           "-n", model, "-s", str(m_scale), "-f", fmt]
    proc = subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    task._proc = proc
    try:
        if progress_cb is None:
            rc = proc.wait()
        else:
            while proc.poll() is None:
                if task._cancelled:
                    proc.kill()
                    raise CancelledError()
                progress_cb(_count_frames(outp) if os.path.isdir(outp) else 0)
                time.sleep(0.6)
            rc = proc.wait()
    finally:
        task._proc = None
    if task._cancelled:
        raise CancelledError()
    if rc != 0:
        raise RuntimeError(
            f"超分引擎退出码 {rc}（可能显卡驱动不支持 Vulkan，或模型加载失败）")
    return rc


def probe_fps(src):
    try:
        r = subprocess.run(
            [ffprobe(), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate,avg_frame_rate",
             "-of", "json", src],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=30)
        info = json.loads(r.stdout or b"{}")
        rate = (info.get("streams") or [{}])[0].get("r_frame_rate") or "25/1"
        num, _, den = rate.partition("/")
        num, den = float(num or 25), float(den or 1) or 1.0
        fps = num / den
    except Exception:
        fps = 25.0
    if not (1 <= fps <= 240):
        fps = 25.0
    return fps


def extract_frames(src, frames_in, fps):
    os.makedirs(frames_in, exist_ok=True)
    subprocess.run(
        [ffmpeg(), "-y", "-i", src, "-r", f"{fps:g}", "-qscale:v", "1",
         os.path.join(frames_in, "%06d.jpg")],
        creationflags=CREATE_NO_WINDOW, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return _count_frames(frames_in)


def assemble(frames_out, src, fps, m_scale, eff, out_path):
    """把超分后的帧序列与原视频的音频合成成品。音频编解码不兼容时自动转 AAC。"""
    base = [ffmpeg(), "-y", "-framerate", f"{fps:g}",
            "-i", os.path.join(frames_out, "%06d.jpg"), "-i", src,
            "-map", "0:v:0", "-map", "1:a?",
            "-vf", even_vf(eff),
            "-c:v", "libx264", "-crf", "16", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-c:a", "copy",
            "-movflags", "+faststart", out_path]
    try:
        subprocess.run(base, creationflags=CREATE_NO_WINDOW, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        cmd = base[:]
        i = cmd.index("-c:a")
        cmd[i + 1] = "aac"
        cmd[i:i] = ["-b:a", "192k"]
        subprocess.run(cmd, creationflags=CREATE_NO_WINDOW, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_path


class EnhanceTask(BaseTask):
    def __init__(self, task_id, files, mode, scale, out_dir, parent=None):
        super().__init__(task_id, parent)
        self.files = list(files)
        self.mode = mode
        self.scale = int(scale)
        self.out_dir = out_dir

    def _file_progress(self, name, idx, pct=None, **kw):
        self.progress(pct, name=name, idx=idx, n=len(self.files), **kw)

    def run(self):
        results, errors = [], []
        for i, src in enumerate(self.files, 1):
            if self._cancelled:
                self.error("已取消", cancelled=True)
                return
            name = os.path.basename(src)
            ext = os.path.splitext(src)[1].lower()
            try:
                if ext in VIDEO_EXTS:
                    out = self._video(src, i)
                elif ext in IMAGE_EXTS:
                    out = self._image(src, i)
                else:
                    errors.append((name, "不支持的文件格式"))
                    continue
                results.append((src, out))
                self._emit(event="file_done", name=name, idx=i,
                           n=len(self.files), path=out)
            except CancelledError:
                self.error("已取消（进度已保留，可稍后恢复）", cancelled=True)
                return
            except Exception as e:
                errors.append((name, str(e) or e.__class__.__name__))
        self._emit(event="done", results=results, errors=errors,
                   out_dir=self.out_dir)

    # ---------- 图片 ----------
    def _image(self, src, idx):
        name = os.path.basename(src)
        model, m_scale, eff = plan_for(self.mode, self.scale, is_video=False)
        stem = os.path.splitext(name)[0]
        out = unique_path(os.path.join(self.out_dir, f"{stem}_高清{self.scale}x.png"))
        tmp = os.path.join(self.out_dir, f".sgtmp_{self.task_id}_{idx}.png")
        try:
            self._file_progress(name, idx, None, stage="AI处理中")
            run_realesrgan(self, src, tmp, model, m_scale, fmt="png")
            if eff != 1.0:
                self._file_progress(name, idx, None, stage="缩放输出")
                subprocess.run(
                    [ffmpeg(), "-y", "-i", tmp, "-vf", even_vf(eff),
                     "-frames:v", "1", out],
                    creationflags=CREATE_NO_WINDOW, check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                os.remove(tmp)
            else:
                os.replace(tmp, out)
            return out
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    # ---------- 视频（带任务档案，失败/取消保留现场供续跑） ----------
    def _video(self, src, idx):
        name = os.path.basename(src)
        model, m_scale, eff = plan_for(self.mode, self.scale, is_video=True)
        stem = os.path.splitext(name)[0]
        out = unique_path(os.path.join(self.out_dir, f"{stem}_高清{self.scale}x.mp4"))
        fps = probe_fps(src)

        tmp_name = f".sgtmp_{self.task_id}_{idx}"
        tmp_root = os.path.join(self.out_dir, tmp_name)
        frames_in = os.path.join(tmp_root, "in")
        frames_out = os.path.join(tmp_root, "out")
        os.makedirs(frames_in, exist_ok=True)
        os.makedirs(frames_out, exist_ok=True)
        write_job(self.out_dir, self.task_id, src, self.mode, self.scale,
                  tmp_name, fps, 0, status="running")
        try:
            self._file_progress(name, idx, None, stage="抽取视频帧")
            total = extract_frames(src, frames_in, fps)
            if self._cancelled:
                raise CancelledError()
            write_job(self.out_dir, self.task_id, src, self.mode, self.scale,
                      tmp_name, fps, total, status="running")

            t0 = time.time()

            def on_frame(done):
                self._file_progress(name, idx, done * 100.0 / total,
                                    stage="AI逐帧超分", done=done, total=total,
                                    fps=round(done / max(0.001, time.time() - t0), 2))

            self._file_progress(name, idx, 0, stage="AI逐帧超分", done=0, total=total)
            run_realesrgan(self, frames_in, frames_out, model, m_scale,
                           fmt="jpg", progress_cb=on_frame)

            self._file_progress(name, idx, None, stage="合成视频")
            assemble(frames_out, src, fps, m_scale, eff, out)
            # 成功：清理现场
            shutil.rmtree(tmp_root, ignore_errors=True)
            clear_job(self.out_dir, self.task_id)
            return out
        except (CancelledError, Exception):
            # 失败/取消：保留现场，标记可续跑
            mark_job(self.out_dir, self.task_id, "interrupted")
            raise


class ResumeTask(BaseTask):
    """从任务档案恢复被中断的视频增强任务。"""

    def __init__(self, task_id, out_dir, job_filename, parent=None):
        super().__init__(task_id, parent)
        self.out_dir = out_dir
        self.job_filename = job_filename

    def run(self):
        p = os.path.join(self.out_dir, self.job_filename)
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError) as e:
            self.error(f"任务档案损坏：{e}")
            return
        src = d.get("source", "")
        if not os.path.isfile(src):
            self.error("源视频已不存在，无法续跑。若已删除此记录将无法恢复。")
            return
        mode, scale = d.get("mode", "anime"), int(d.get("scale", 2))
        model, m_scale, eff = plan_for(mode, scale, is_video=True)
        fps = float(d.get("fps", 25))
        total_expected = int(d.get("total", 0))

        tmp_root = os.path.join(self.out_dir, d.get("tmp", ""))
        frames_in = os.path.join(tmp_root, "in")
        frames_out = os.path.join(tmp_root, "out")
        name = os.path.basename(src)
        stem = os.path.splitext(name)[0]
        out = unique_path(os.path.join(self.out_dir, f"{stem}_高清{scale}x.mp4"))
        try:
            write_job(self.out_dir, self.task_id, src, mode, scale,
                      d.get("tmp"), fps, total_expected, status="running")
            # 1) 抽帧未完成则重抽
            have_in = _count_frames(frames_in)
            if total_expected and have_in < total_expected:
                self.progress(None, name=name, stage="补齐抽帧")
                extract_frames(src, frames_in, fps)
            total = _count_frames(frames_in)
            if total == 0:
                raise RuntimeError("没有可用的视频帧")
            # 2) 计算缺失帧，硬链接到临时目录（已完成的帧不重算）
            missing = [fn for fn in os.listdir(frames_in)
                       if not os.path.exists(os.path.join(frames_out, fn))]
            self.progress(0, name=name, done=total - len(missing), total=total,
                          stage="AI逐帧超分")
            if missing:
                in_r = os.path.join(tmp_root, "in_r")
                out_r = os.path.join(tmp_root, "out_r")
                shutil.rmtree(in_r, ignore_errors=True)
                shutil.rmtree(out_r, ignore_errors=True)
                os.makedirs(in_r, exist_ok=True)
                os.makedirs(out_r, exist_ok=True)
                for fn in missing:
                    dst = os.path.join(in_r, fn)
                    try:
                        os.link(os.path.join(frames_in, fn), dst)
                    except OSError:
                        shutil.copy2(os.path.join(frames_in, fn), dst)
                t0 = time.time()
                base_done = total - len(missing)

                def on_frame(done):
                    self.progress((base_done + done) * 100.0 / total,
                                  name=name, done=base_done + done, total=total,
                                  stage="AI逐帧超分",
                                  fps=round(done / max(0.001, time.time() - t0), 2))

                run_realesrgan(self, in_r, out_r, model, m_scale,
                               fmt="jpg", progress_cb=on_frame)
                for fn in os.listdir(out_r):
                    shutil.move(os.path.join(out_r, fn),
                                os.path.join(frames_out, fn))
                shutil.rmtree(in_r, ignore_errors=True)
                shutil.rmtree(out_r, ignore_errors=True)
            # 3) 合成
            self.progress(None, name=name, stage="合成视频")
            assemble(frames_out, src, fps, m_scale, eff, out)
            shutil.rmtree(tmp_root, ignore_errors=True)
            clear_job(self.out_dir, self.task_id)
            self.progress(100, name=name)
            self.done(path=out)
        except CancelledError:
            mark_job(self.out_dir, self.task_id, "interrupted")
            self.error("已取消（进度已保留，可稍后恢复）", cancelled=True)
        except Exception as e:
            mark_job(self.out_dir, self.task_id, "interrupted")
            self.error(str(e) or e.__class__.__name__)
