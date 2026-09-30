"""画质增强页 v1.1：三种模式、视频倍率选择、断点续跑恢复横幅。"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QVBoxLayout, QWidget, QProgressBar,
)

import theme
from theme import elide
from utils import IMAGE_EXTS, VIDEO_EXTS, open_in_explorer, human_size
from app_settings import AppSettings

FILTER = "媒体文件 (*" + " *".join(sorted(IMAGE_EXTS | VIDEO_EXTS)) + ")"

MODES = [
    ("photo", "照片模式（风景/人像/截图）"),
    ("anime", "动漫·动画模式"),
    ("real", "真人·通用模式"),
]


class FileList(QListWidget):
    """支持拖拽的文件列表。"""

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        files = []
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.isfile(p):
                files.append(p)
        self.tab.add_files(files)


class EnhanceTab(QWidget):
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.thread = None
        self.resume_thread = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)

        c1 = QFrame(objectName="card")
        v1 = QVBoxLayout(c1)
        v1.setContentsMargins(20, 18, 20, 18)
        v1.setSpacing(10)
        t = QLabel("画质增强")
        t.setObjectName("h1")
        s = QLabel("用 AI 把图片和视频变得更清晰（超分辨率）。把文件拖到下面，或点「添加文件」。"
                   "风景/人像选照片模式，动漫/动画选动漫模式，真人视频选真人·通用模式。")
        s.setObjectName("sub")
        s.setWordWrap(True)
        v1.addWidget(t)
        v1.addWidget(s)

        # 恢复横幅（检测到被中断的任务时显示）
        self.resume_box = QFrame()
        self.resume_box.setStyleSheet(
            f"QFrame {{ background:#fff8e6; border:1px solid #f0d9a8;"
            f" border-radius:10px; }}")
        self.resume_lay = QHBoxLayout(self.resume_box)
        self.resume_lay.setContentsMargins(12, 8, 12, 8)
        self.resume_lay.setSpacing(8)
        self.resume_lay.addWidget(QLabel("🔄"))
        self.resume_label = QLabel("检测到上次未完成的增强任务")
        self.resume_lay.addWidget(self.resume_label, 1)
        self.resume_btn = QPushButton("恢复任务")
        self.resume_btn.clicked.connect(self._resume_last)
        self.resume_lay.addWidget(self.resume_btn)
        self.resume_box.setVisible(False)
        v1.addWidget(self.resume_box)

        self.file_list = FileList(self)
        self.file_list.setMinimumHeight(120)
        self.file_list.setStyleSheet(
            f"QListWidget {{ background:#fbfcfe; border:1.5px dashed {theme.BORDER};"
            f" border-radius:10px; padding:6px; }}"
            f"QListWidget:hover {{ border-color:{theme.ACCENT}; }}")
        v1.addWidget(self.file_list)

        brow = QHBoxLayout()
        b1 = QPushButton("添加文件")
        b1.setProperty("ghost", True)
        b1.clicked.connect(self._add_dialog)
        b2 = QPushButton("清空")
        b2.setProperty("ghost", True)
        b2.clicked.connect(lambda: self.file_list.clear())
        brow.addWidget(b1)
        brow.addWidget(b2)
        brow.addStretch(1)
        lbl1 = QLabel("模式")
        lbl1.setObjectName("h2")
        self.mode = QComboBox()
        for data, text in MODES:
            self.mode.addItem(text, data)
        lbl2 = QLabel("倍数")
        lbl2.setObjectName("h2")
        self.scale = QComboBox()
        for s_, label in ((2, "2 倍"), (3, "3 倍"), (4, "4 倍")):
            self.scale.addItem(label, s_)
        self.scale.setCurrentIndex(0)
        brow.addWidget(lbl1)
        brow.addWidget(self.mode)
        brow.addSpacing(6)
        brow.addWidget(lbl2)
        brow.addWidget(self.scale)
        v1.addLayout(brow)

        self.hint = QLabel("")
        self.hint.setObjectName("sub")
        self.hint.setWordWrap(True)
        v1.addWidget(self.hint)
        self.mode.currentIndexChanged.connect(self._update_hint)
        self.scale.currentIndexChanged.connect(self._update_hint)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{theme.BORDER}; border:none;")
        v1.addWidget(line)

        orow = QHBoxLayout()
        lbl = QLabel("输出位置")
        lbl.setObjectName("h2")
        self.out_label = QLabel()
        self.out_label.setObjectName("sub")
        self.out_label.setText(elide(self.settings.enhance_dir, 52))
        self.out_label.setToolTip(self.settings.enhance_dir)
        ob = QPushButton("更改…")
        ob.setProperty("ghost", True)
        ob.clicked.connect(self._pick_out)
        ob2 = QPushButton("打开文件夹")
        ob2.setProperty("ghost", True)
        ob2.clicked.connect(lambda: open_in_explorer(self.settings.enhance_dir))
        orow.addWidget(lbl)
        orow.addWidget(self.out_label, 1)
        orow.addWidget(ob)
        orow.addWidget(ob2)
        v1.addLayout(orow)

        srow = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("sub")
        self.btn_start = QPushButton("开始增强")
        self.btn_start.setObjectName("big")
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setProperty("danger", True)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.setVisible(False)
        srow.addWidget(self.status, 1)
        srow.addWidget(self.btn_cancel)
        srow.addWidget(self.btn_start)
        v1.addLayout(srow)
        root.addWidget(c1)

        c2 = QFrame(objectName="card")
        v2 = QVBoxLayout(c2)
        v2.setContentsMargins(20, 16, 20, 16)
        v2.setSpacing(8)
        t2 = QLabel("处理进度")
        t2.setObjectName("h2")
        v2.addWidget(t2)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        v2.addWidget(self.bar)
        self.now_label = QLabel("等待任务…")
        self.now_label.setObjectName("sub")
        v2.addWidget(self.now_label)
        self.log = QListWidget()
        self.log.setMinimumHeight(140)
        v2.addWidget(self.log)
        root.addWidget(c2, 1)

        self._update_hint()
        self._refresh_resume()

    # ---------- 断点续跑 ----------
    def _refresh_resume(self):
        from enhance import find_interrupted_jobs
        jobs = find_interrupted_jobs(self.settings.enhance_dir)
        while self.resume_lay.count() > 2:  # 保留图标和文字标签
            item = self.resume_lay.takeAt(2)
            w = item.widget()
            if w:
                w.deleteLater()
        self._resume_jobs = jobs
        if not jobs or (self.thread and self.thread.isRunning()):
            self.resume_box.setVisible(False)
            return
        name, d, done = jobs[0]
        src = os.path.basename(d.get("source", "未知视频"))
        total = d.get("total", 0) or "?"
        self.resume_label.setText(
            f"检测到未完成任务：《{elide(src, 24)}》 已完成 {done}/{total} 帧 —"
            " 重启/关闭软件不会丢失该进度")
        for extra in jobs[1:3]:
            n2, d2, done2 = extra
            btn2 = QPushButton(f"恢复《{elide(os.path.basename(d2.get('source','')), 14)}》"
                               f"({done2}帧)")
            btn2.setProperty("ghost", True)
            btn2.clicked.connect(lambda _=False, j=(n2, d2, done2): self._resume(j))
            self.resume_lay.addWidget(btn2)
        self.resume_btn.setText("恢复任务")
        self.resume_box.setVisible(True)

    def _resume_last(self):
        if getattr(self, "_resume_jobs", None):
            self._resume(self._resume_jobs[0])

    def _resume(self, job):
        if self.thread and self.thread.isRunning():
            return
        from enhance import ResumeTask
        name, d, done = job
        self.resume_thread = ResumeTask(2, self.settings.enhance_dir, name)
        self.resume_thread.sig.connect(self._on_event)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.status.setStyleSheet("")
        self.status.setText("恢复中…")
        self.log.addItem(f"↻ 恢复任务：{os.path.basename(d.get('source',''))}（已有 {done} 帧）")
        self.resume_thread.start()

    # ---------- 文件 ----------
    def add_files(self, files):
        cur = set(self.file_list.item(i).text() for i in range(self.file_list.count()))
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in (IMAGE_EXTS | VIDEO_EXTS):
                continue
            if f not in cur:
                self.file_list.addItem(f)
        self._update_hint()

    def _add_dialog(self):
        start = self.settings.enhance_dir if os.path.isdir(self.settings.enhance_dir) else ""
        files, _ = QFileDialog.getOpenFileNames(self, "选择要增强的文件", start, FILTER)
        self.add_files(files)

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出位置", self.settings.enhance_dir)
        if d:
            self.settings.enhance_dir = d
            self.out_label.setText(elide(d, 52))
            self.out_label.setToolTip(d)
            self._refresh_resume()

    def _files(self):
        return [self.file_list.item(i).text() for i in range(self.file_list.count())]

    def _update_hint(self):
        files = self._files()
        has_video = any(os.path.splitext(f)[1].lower() in VIDEO_EXTS for f in files)
        mode = self.mode.currentData()
        scale = self.scale.currentData()
        if has_video:
            if mode == "anime":
                tip = (f"动漫视频将输出 {scale} 倍（快速视频模型，约 2~4 帧/秒）。"
                       f"4 倍画面像素是原视频的 16 倍，耗时约为 2 倍的 4 倍以上。")
            else:
                tip = ("⚠ 真人/照片模式下视频固定输出 2 倍：使用通用模型逐帧处理，"
                       "速度中等；如内容其实是动漫，请改用动漫·动画模式（快好几倍）。")
        else:
            if mode == "photo":
                tip = "照片模式：4 倍超分后精细缩放到目标倍数，人像/风景质量最好。"
            elif mode == "anime":
                tip = "动漫模式：动漫图片质量最佳；2 倍时自动使用快速模型。"
            else:
                tip = "真人·通用模式：通用模型，真实照片速度快、细节自然。"
        self.hint.setText(tip)

    # ---------- 运行 ----------
    def _start(self):
        files = self._files()
        if not files:
            self.status.setText("请先添加文件")
            self.status.setStyleSheet(
                f"color:{theme.RED}; background:transparent; border:none;")
            return
        os.makedirs(self.settings.enhance_dir, exist_ok=True)
        from enhance import EnhanceTask
        self.thread = EnhanceTask(1, files, self.mode.currentData(),
                                  self.scale.currentData(), self.settings.enhance_dir)
        self.thread.sig.connect(self._on_event)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.log.clear()
        self.bar.setValue(0)
        self.status.setStyleSheet("")
        self.status.setText("处理中…")
        self.thread.start()

    def _cancel(self):
        if self.thread and self.thread.isRunning():
            self.thread.cancel()
            self.status.setText("正在取消…")
        if self.resume_thread and self.resume_thread.isRunning():
            self.resume_thread.cancel()
            self.status.setText("正在取消…")

    def _on_event(self, ev):
        event = ev.get("event")
        if event == "progress":
            name = ev.get("name", "")
            idx, n = ev.get("idx", 1), ev.get("n", 1)
            stage = ev.get("stage", "")
            parts = [f"（{idx}/{n}）", elide(name, 36), stage]
            if ev.get("done") is not None and ev.get("total"):
                parts.append(f"{ev['done']}/{ev['total']} 帧")
            if ev.get("fps") is not None:
                parts.append(f"{ev['fps']:.1f} 帧/秒")
            self.now_label.setText("  ·  ".join(parts))
            if ev.get("pct") is not None:
                self.bar.setRange(0, 100)
                self.bar.setValue(int(ev["pct"]))
            else:
                self.bar.setRange(0, 0)
        elif event == "file_done":
            self.log.addItem(f"✓ {ev['name']}  →  {os.path.basename(ev.get('path',''))}")
            self.log.scrollToBottom()
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
        elif event == "done":
            errs = ev.get("errors") or []
            n_ok = len(ev.get("results") or [])
            self.bar.setRange(0, 100)
            self.bar.setValue(100)
            for name, msg in errs:
                self.log.addItem(f"✗ {name}：{msg}")
            self.status.setStyleSheet(
                f"color:{theme.GREEN}; font-weight:600; background:transparent; border:none;")
            self.status.setText(f"完成：成功 {n_ok} 个" + (f"，失败 {len(errs)} 个" if errs else ""))
            self._finish_ui()
        elif event in ("error", "cancelled"):
            msg = ev.get("error", "")
            self.status.setStyleSheet(
                f"color:{theme.RED}; background:transparent; border:none;")
            if event == "cancelled":
                self.status.setText(msg or "已取消")
            else:
                self.status.setText(f"失败：{msg}")
            self.bar.setRange(0, 100)
            self._finish_ui()
            self._refresh_resume()

    def _finish_ui(self):
        if self.thread:
            self.thread.wait(3000)
            self.thread.deleteLater()
            self.thread = None
        if self.resume_thread:
            self.resume_thread.wait(3000)
            self.resume_thread.deleteLater()
            self.resume_thread = None
        self.btn_start.setEnabled(True)
        self.btn_cancel.setVisible(False)
