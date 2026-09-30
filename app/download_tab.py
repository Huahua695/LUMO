"""下载页：粘贴链接 → 自动识别引擎 → 任务列表带进度。"""
import os
import queue

from PySide6.QtCore import QSize, Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QPlainTextEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
    QWidget, QProgressBar,
)

import theme
from theme import elide
from utils import human_size, human_speed, open_in_explorer
from url_detect import detect_engine, extract_urls, url_media_kind, ENGINE_LABEL
from paths import tools_ready

MAX_CONCURRENT = 3
MAX_BATCH = 50

QUALITY_ITEMS = [
    ("best", "最佳画质（推荐）"),
    ("1080p", "1080p"),
    ("720p", "720p"),
    ("480p", "480p"),
    ("audio", "仅音频（最高音质）"),
]
FMT_ITEMS = [
    ("auto", "自动（推荐）"),
    ("mp4", "MP4 视频"),
    ("mkv", "MKV 视频"),
    ("mp3", "MP3 音频"),
    ("m4a", "M4A 音频"),
    ("jpg", "JPG 图片"),
    ("png", "PNG 图片"),
]


class TaskRow(QWidget):
    """任务列表中的一行。"""

    cancel_clicked = Signal(int)

    def __init__(self, task_id, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFixedWidth(200)
        self.bar.setTextVisible(False)

        self.name_label = QLabel("准备中…")
        self.name_label.setStyleSheet("font-weight:600; font-size:13px;")
        self.name_label.setMinimumWidth(150)
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("sub")

        self.status_label = QLabel("排队中")
        self.status_label.setObjectName("sub")
        self.status_label.setMinimumWidth(130)

        self.btn = QPushButton("取消")
        self.btn.setProperty("danger", True)
        self.btn.setFixedWidth(72)
        self.btn.clicked.connect(lambda: self.cancel_clicked.emit(self.task_id))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(self.name_label)
        col.addWidget(self.meta_label)
        lay.addLayout(col, 1)
        lay.addWidget(self.bar)
        lay.addWidget(self.status_label)
        lay.addWidget(self.btn)

    def set_state(self, **kw):
        if "name" in kw and kw["name"]:
            self.name_label.setText(elide(kw["name"], 30))
            self.name_label.setToolTip(kw["name"])
        if "engine" in kw:
            self.meta_label.setText(kw["engine"])
        if "pct" in kw:
            pct = kw["pct"]
            if pct is None:
                self.bar.setRange(0, 0)
            else:
                self.bar.setRange(0, 100)
                self.bar.setValue(int(pct))
        parts = []
        if kw.get("stage"):
            parts.append(kw["stage"])
        if kw.get("total"):
            parts.append(f"{human_size(kw.get('done'))} / {human_size(kw['total'])}")
        elif kw.get("done"):
            parts.append(human_size(kw["done"]))
        if kw.get("fps") is not None:
            parts.append(f"{kw['fps']:.1f} 帧/秒")
        if kw.get("speed"):
            parts.append(human_speed(kw["speed"]))
        if parts:
            self.status_label.setText("  ·  ".join(parts))
        if kw.get("text"):
            self.status_label.setText(kw["text"])

    def finish(self, ok=True, text=None):
        self.bar.setRange(0, 100)
        self.bar.setValue(100 if ok else self.bar.value())
        self.status_label.setObjectName("ok" if ok else "err")
        self.status_label.setStyleSheet(
            f"color:{theme.GREEN if ok else theme.RED}; font-weight:600;"
            "background:transparent; border:none;")
        self.status_label.setText(text or ("已完成 ✓" if ok else "失败"))
        self.btn.setText("打开")
        self.btn.setProperty("danger", False)
        self.btn.setProperty("ghost", True)
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)
        try:
            self.cancel_clicked.disconnect()
        except (TypeError, RuntimeError):
            pass


class DownloadTab(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.threads = {}
        self.rows = {}
        self.next_id = 1
        self.pending = queue.Queue()
        self.active = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(14)

        # ---- 卡片1：链接与保存位置 ----
        c1 = QFrame(objectName="card")
        v1 = QVBoxLayout(c1)
        v1.setContentsMargins(24, 18, 24, 18)
        v1.setSpacing(10)
        t = QLabel("下载资源")
        t.setObjectName("h1")
        s = QLabel("支持网站链接（B站 / YouTube / 抖音等）、m3u8/HLS、文件直链，原始数据无损保存。")
        s.setObjectName("sub")
        s.setWordWrap(True)
        v1.addWidget(t)
        v1.addWidget(s)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.url_edit = QPlainTextEdit()
        self.url_edit.setPlaceholderText(
            "把链接粘贴到这里…（支持一次粘贴多个，自动排队下载；\n"
            "也可以粘贴整段文字，会自动提取其中的链接）")
        self.url_edit.setFixedHeight(62)
        self.url_edit.textChanged.connect(self._on_url_changed)
        self.btn_paste = QPushButton("粘贴")
        self.btn_paste.setProperty("ghost", True)
        self.btn_paste.clicked.connect(self._paste)
        row.addWidget(self.url_edit, 1)
        row.addWidget(self.btn_paste)
        v1.addLayout(row)

        self.detect_label = QLabel("自动识别：等待输入…")
        self.detect_label.setObjectName("accent")
        v1.addWidget(self.detect_label)

        # ---- 解析预览卡片（单条网站链接时自动后台解析） ----
        self.probe_card = QFrame()
        self.probe_card.setStyleSheet(
            f"QFrame {{ background:#f7faff; border:1px solid {theme.BORDER};"
            f" border-radius:10px; }}")
        pl = QHBoxLayout(self.probe_card)
        pl.setContentsMargins(10, 8, 10, 8)
        pl.setSpacing(12)
        self.thumb_label = QLabel("🖼")
        self.thumb_label.setFixedSize(112, 60)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet(
            "background:#e8edf5; border:none; border-radius:6px; font-size:22px;")
        pl.addWidget(self.thumb_label)
        pcol = QVBoxLayout()
        pcol.setSpacing(3)
        self.probe_title = QLabel("")
        self.probe_title.setStyleSheet(
            "font-weight:600; font-size:13px; background:transparent; border:none;")
        self.probe_title.setWordWrap(True)
        self.probe_meta = QLabel("")
        self.probe_meta.setObjectName("sub")
        pcol.addWidget(self.probe_title)
        pcol.addWidget(self.probe_meta)
        prow = QHBoxLayout()
        prow.setSpacing(6)
        self.probe_qlabel = QLabel("画质")
        self.probe_qlabel.setObjectName("h2")
        self.probe_quality = QComboBox()
        self.probe_quality.setMinimumWidth(170)
        self.probe_quality.currentIndexChanged.connect(self._on_probe_quality)
        prow.addWidget(self.probe_qlabel)
        prow.addWidget(self.probe_quality)
        prow.addStretch(1)
        self.probe_btn = QPushButton("全部加入下载队列")
        self.probe_btn.clicked.connect(self._enqueue_playlist)
        self.probe_btn.setVisible(False)
        prow.addWidget(self.probe_btn)
        pcol.addLayout(prow)
        pl.addLayout(pcol, 1)
        self.probe_status = QLabel("")
        self.probe_status.setObjectName("sub")
        self.probe_status.setFixedWidth(150)
        self.probe_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(self.probe_status)
        self.probe_card.setVisible(False)
        v1.addWidget(self.probe_card)

        self._probe_seq = 0
        self._probe_task_id = 0
        self._probe_task = None
        self._probe_url = ""
        self._probe_format_id = None
        self._probe_entries = None
        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.setInterval(900)
        self._probe_timer.timeout.connect(self._start_probe)

        # ---- 保存设置：画质/分辨率 + 保存格式 ----
        srow2 = QHBoxLayout()
        lblq = QLabel("画质 / 分辨率")
        lblq.setObjectName("h2")
        self.quality = QComboBox()
        for data, text in QUALITY_ITEMS:
            self.quality.addItem(text, data)
        lblf = QLabel("保存格式")
        lblf.setObjectName("h2")
        self.fmt = QComboBox()
        self.fmt.addItem(FMT_ITEMS[0][1], "auto")
        self.save_hint = QLabel("粘贴链接后，这里会给出可选的画质与格式。")
        self.save_hint.setObjectName("sub")
        srow2.addWidget(lblq)
        srow2.addWidget(self.quality)
        srow2.addSpacing(28)
        srow2.addWidget(lblf)
        srow2.addWidget(self.fmt)
        srow2.addStretch(1)
        v1.addLayout(srow2)
        v1.addWidget(self.save_hint)
        self.quality.currentIndexChanged.connect(self._on_quality_changed)
        self.fmt.currentIndexChanged.connect(self._on_fmt_changed)
        self._current_engine = "site"
        self._current_kind = None
        self._saved_fmt = self.settings.dl_format
        for i, (d_, _t_) in enumerate(QUALITY_ITEMS):
            if d_ == self.settings.dl_quality:
                self.quality.setCurrentIndex(i)
                break

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{theme.BORDER}; border:none;")
        v1.addWidget(line)

        srow = QHBoxLayout()
        srow.setSpacing(8)
        lbl = QLabel("保存位置")
        lbl.setObjectName("h2")
        self.dir_label = QLabel()
        self.dir_label.setObjectName("sub")
        self.dir_label.setText(elide(self.settings.save_dir, 52))
        self.dir_label.setToolTip(self.settings.save_dir)
        b1 = QPushButton("更改…")
        b1.setProperty("ghost", True)
        b1.clicked.connect(self._pick_dir)
        b2 = QPushButton("打开文件夹")
        b2.setProperty("ghost", True)
        b2.clicked.connect(lambda: open_in_explorer(self.settings.save_dir))
        srow.addWidget(lbl)
        srow.addWidget(self.dir_label, 1)
        srow.addWidget(b1)
        srow.addWidget(b2)
        v1.addLayout(srow)

        drow = QHBoxLayout()
        drow.setSpacing(8)
        self.missing = tools_ready()
        if self.missing:
            warn = QLabel("⚠ 外部组件缺失：" + "、".join(self.missing))
            warn.setObjectName("err")
            drow.addWidget(warn)
        drow.addStretch(1)
        self.btn_start = QPushButton("开始下载")
        self.btn_start.setObjectName("big")
        self.btn_start.clicked.connect(self._start)
        drow.addWidget(self.btn_start)
        v1.addLayout(drow)
        root.addWidget(c1)

        # ---- 卡片2：任务列表 ----
        c2 = QFrame(objectName="card")
        v2 = QVBoxLayout(c2)
        v2.setContentsMargins(24, 18, 24, 18)
        v2.setSpacing(8)
        h = QHBoxLayout()
        t2 = QLabel("任务列表")
        t2.setObjectName("h2")
        self.summary = QLabel("")
        self.summary.setObjectName("sub")
        clear = QPushButton("清除记录")
        clear.setProperty("ghost", True)
        clear.clicked.connect(self._clear_finished)
        h.addWidget(t2)
        h.addStretch(1)
        h.addWidget(self.summary)
        h.addWidget(clear)
        v2.addLayout(h)
        self.list = QListWidget()
        self.list.setSpacing(4)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setMinimumHeight(100)
        v2.addWidget(self.list)
        self.empty_hint = QLabel("还没有任务 —— 粘贴链接后点「开始下载」，进度会显示在这里"
                                 "（最多同时 3 个，完成后点任务右侧「打开」定位文件）")
        self.empty_hint.setObjectName("sub")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setContentsMargins(0, 12, 0, 12)
        self.empty_hint.setWordWrap(True)
        v2.addWidget(self.empty_hint)
        root.addWidget(c2, 1)

    # ---------- 交互 ----------
    def _paste(self):
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        if not cb.text():
            return
        cur = self.url_edit.toPlainText()
        if cur.strip():
            self.url_edit.setPlainText(cur.rstrip() + "\n" + cb.text().strip())
        else:
            self.url_edit.setPlainText(cb.text().strip())
        self.url_edit.verticalScrollBar().setValue(
            self.url_edit.verticalScrollBar().maximum())

    def _urls(self):
        return extract_urls(self.url_edit.toPlainText())[:MAX_BATCH]

    def _on_url_changed(self):
        urls = self._urls()
        # 解析卡片：仅单条网站链接时自动后台解析
        self._probe_timer.stop()
        self._probe_format_id = None
        if len(urls) == 1 and detect_engine(urls[0]) == "site":
            self._probe_timer.start()
        else:
            self._cancel_probe()
            self.probe_card.setVisible(False)
        if not urls:
            self._current_engine, self._current_kind = "site", None
            self.detect_label.setText("自动识别：等待输入…")
        elif len(urls) == 1:
            self._current_engine = detect_engine(urls[0])
            self._current_kind = (url_media_kind(urls[0])
                                  if self._current_engine == "direct" else None)
            self.detect_label.setText(f"自动识别 → {ENGINE_LABEL[self._current_engine]}")
        else:
            engines = {detect_engine(u) for u in urls}
            self._current_engine = engines.pop() if len(engines) == 1 else "mixed"
            self._current_kind = None
            self.detect_label.setText(
                f"已识别 {len(urls)} 个链接，最多同时下载 3 个，其余自动排队")
        self._refresh_save_options()

    # ---------- 解析预览 ----------
    def _cancel_probe(self):
        if self._probe_task and self._probe_task.isRunning():
            self._probe_task.cancel()
            self._probe_task.wait(2000)
        self._probe_task = None

    def _start_probe(self):
        urls = self._urls()
        if len(urls) != 1 or detect_engine(urls[0]) != "site":
            return
        if self.fmt.currentData() in ("mp3", "m4a"):
            # 仅音频模式无需解析画质
            self.probe_card.setVisible(False)
            return
        self._cancel_probe()
        self._probe_seq += 1
        self._probe_task_id = -1000 - self._probe_seq
        self._probe_url = urls[0]
        self._probe_format_id = None
        self._probe_entries = None
        from ytdlp_dl import ProbeTask
        self._probe_task = ProbeTask(self._probe_task_id, urls[0])
        self._probe_task.sig.connect(self._on_probe_event)
        self.probe_title.setText("")
        self.probe_meta.setText("")
        self.probe_status.setStyleSheet("")
        self.probe_status.setText("正在解析…")
        self.probe_quality.clear()
        self.probe_qlabel.setVisible(False)
        self.probe_quality.setVisible(False)
        self.probe_btn.setVisible(False)
        self.thumb_label.setText("🖼")
        self.probe_card.setVisible(True)
        self._probe_task.start()

    def _on_probe_event(self, ev):
        if ev.get("id") != self._probe_task_id:
            return
        event = ev.get("event")
        if event == "done":
            if ev.get("kind") == "playlist":
                self._probe_entries = ev.get("entries") or []
                self.probe_title.setText(elide(ev.get("title", "播放列表"), 52))
                extra = "（仅取前 100 条）" if ev.get("truncated") else ""
                self.probe_meta.setText(f"检测到播放列表 · {len(self._probe_entries)} 个视频{extra}")
                self.probe_status.setText("")
                self.probe_btn.setVisible(True)
            else:
                self._show_video_probe(ev)
        elif event == "error":
            self.probe_status.setText("解析失败\n可直接下载")
            self.probe_status.setStyleSheet(
                f"color:{theme.RED}; background:transparent; border:none;")
            self.probe_title.setText(elide(ev.get("error", "解析失败"), 52))

    def _show_video_probe(self, ev):
        from cut_engine import fmt_time
        from PySide6.QtGui import QPixmap
        self.probe_card.setVisible(True)
        thumb = ev.get("thumbnail") or ""
        if thumb and os.path.isfile(thumb):
            pm = QPixmap(thumb)
            if not pm.isNull():
                self.thumb_label.setPixmap(pm.scaled(
                    128, 72, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
        self.probe_title.setText(elide(ev.get("title") or "未知标题", 52))
        meta = []
        if ev.get("uploader"):
            meta.append(ev["uploader"])
        if ev.get("duration"):
            meta.append(fmt_time(ev["duration"]))
        fmts = ev.get("formats") or []
        meta.append(f"{len(fmts)} 种画质" if fmts else "画质信息不可用")
        self.probe_meta.setText(" · ".join(meta))
        self.probe_status.setText("✓ 解析成功")
        self.probe_status.setStyleSheet(
            f"color:{theme.GREEN}; background:transparent; border:none;")
        self.probe_quality.blockSignals(True)
        self.probe_quality.clear()
        self.probe_quality.addItem("最佳（推荐）", None)
        for f in fmts:
            size = f.get("size")
            label = f["label"] + (f"  ≈{human_size(size)}" if size else "")
            self.probe_quality.addItem(label, f.get("format_id"))
        self.probe_quality.blockSignals(False)
        self.probe_qlabel.setVisible(bool(fmts))
        self.probe_quality.setVisible(bool(fmts))

    def _on_probe_quality(self):
        self._probe_format_id = self.probe_quality.currentData()

    def _enqueue_playlist(self):
        entries = self._probe_entries or []
        if not entries:
            return
        os.makedirs(self.settings.save_dir, exist_ok=True)
        for e in entries:
            u = e.get("url")
            if u:
                self._spawn(detect_engine(u), u)
        self.probe_status.setText(f"已加入 {len(entries)} 个任务")
        self.probe_btn.setVisible(False)

    # ---------- 保存设置（画质/格式） ----------
    def _allowed_fmts(self, engine, kind):
        if engine == "site":
            return ["auto", "mp4", "mkv", "mp3", "m4a"]
        if engine == "m3u8":
            return ["auto", "mp4", "mp3", "m4a"]
        if kind == "video":
            return ["auto", "mp4", "mkv", "mp3", "m4a"]
        if kind == "audio":
            return ["auto", "mp3", "m4a"]
        if kind == "image":
            return ["auto", "jpg", "png"]
        return ["auto"]

    def _refresh_save_options(self):
        urls = self._urls()
        # 画质可用性：仅当全部链接都是网站视频且未选音频格式时可调
        all_site = bool(urls) and all(detect_engine(u) == "site" for u in urls)
        audio_fmt = self.fmt.currentData() in ("mp3", "m4a")
        self.quality.setEnabled(all_site and not audio_fmt)

        # 保存格式可选项：批量时取所有链接可选项的交集
        if urls:
            allowed = self._allowed_fmts(detect_engine(urls[0]),
                                         url_media_kind(urls[0])
                                         if detect_engine(urls[0]) == "direct" else None)
            for u in urls[1:]:
                e2 = detect_engine(u)
                k2 = url_media_kind(u) if e2 == "direct" else None
                allowed = [x for x in allowed if x in self._allowed_fmts(e2, k2)]
        else:
            allowed = ["auto"]
        cur = self.fmt.currentData() or getattr(self, "_saved_fmt", "auto")
        self.fmt.blockSignals(True)
        self.fmt.clear()
        for data, text in FMT_ITEMS:
            if data in allowed:
                self.fmt.addItem(text, data)
        if cur in allowed:
            self.fmt.setCurrentIndex(allowed.index(cur))
        else:
            self.fmt.setCurrentIndex(0)
        self._saved_fmt = self.fmt.currentData()
        self.fmt.blockSignals(False)
        self._update_save_hint()

    def _on_quality_changed(self):
        self.settings.dl_quality = self.quality.currentData()
        self._refresh_save_options()

    def _on_fmt_changed(self):
        self.settings.dl_format = self.fmt.currentData()
        self._refresh_save_options()
        # 仅音频模式：解析卡片（画质列表）无意义，隐藏；切回后重新解析
        if self.fmt.currentData() in ("mp3", "m4a"):
            self._probe_timer.stop()
            self._cancel_probe()
            self.probe_card.setVisible(False)
        else:
            urls = self._urls()
            if len(urls) == 1 and detect_engine(urls[0]) == "site":
                self._probe_timer.start()

    def _update_save_hint(self):
        urls = self._urls()
        if not urls:
            self.save_hint.setText("粘贴链接后，这里会给出可选的画质与格式。")
            return
        if len(urls) > 1:
            self.save_hint.setText(
                f"批量模式：共 {len(urls)} 个链接。画质/格式将应用于支持的链接，"
                "其余按原始格式无损保存。")
            return
        u = urls[0]
        eng = detect_engine(u)
        kind = url_media_kind(u) if eng == "direct" else None
        q = self.quality.currentData()
        f = self.fmt.currentData()
        audio = f in ("mp3", "m4a") or q == "audio"
        codec = f if f in ("mp3", "m4a") else "MP3"
        if eng == "site":
            if audio:
                self.save_hint.setText(f"仅提取音轨并转码为 {codec.upper()}（最高音质）")
            else:
                tail = {"mp4": "，封装为 MP4（兼容性最好）",
                        "mkv": "，封装为 MKV",
                        "auto": "（按源格式封装）"}.get(f, "")
                if q == "best":
                    self.save_hint.setText("下载最高画质视频" + tail)
                else:
                    self.save_hint.setText(
                        f"下载不超过 {q} 的最佳画质视频（源没有该分辨率时自动选最接近的）" + tail)
        elif eng == "m3u8":
            if audio:
                self.save_hint.setText(f"仅下载 m3u8 音轨并转为 {codec.upper()}")
            else:
                self.save_hint.setText("m3u8 源自动选取最高画质，合并封装为 MP4")
        else:
            if f == "auto":
                self.save_hint.setText("原样保存原始文件（无损）")
            elif f in ("mp4", "mkv"):
                self.save_hint.setText(f"下载原始文件并无损转封装为 {f.upper()}")
            elif f in ("mp3", "m4a"):
                self.save_hint.setText(f"下载后提取音频并转为 {f.upper()}")
            else:
                tip = "（JPG 为有损压缩）" if f == "jpg" else "（PNG 无损）"
                self.save_hint.setText(f"下载后转换为 {f.upper()} 图片{tip}")

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存位置", self.settings.save_dir)
        if d:
            self.settings.save_dir = d
            self.dir_label.setText(elide(d, 52))
            self.dir_label.setToolTip(d)

    def _clear_finished(self):
        for tid in [tid for tid, t in self.threads.items() if t.isFinished()]:
            row = self.rows.pop(tid, None)
            for it in list(self.list.items()):
                if it and self.list.itemWidget(it) is row:
                    self.list.takeItem(self.list.row(it))
            self.threads.pop(tid, None)

    # ---------- 启动任务 ----------
    def _start(self):
        if self.missing:
            return
        urls = self._urls()
        if not urls:
            self.url_edit.setFocus()
            return
        os.makedirs(self.settings.save_dir, exist_ok=True)
        for u in urls:
            self._spawn(detect_engine(u), u)
        # 提交后清空输入，避免再次点击造成重复下载
        n = len(urls)
        self.url_edit.clear()
        self.detect_label.setText(f"已提交 {n} 个下载任务")

    def _spawn(self, eng, url):
        tid = self.next_id
        self.next_id += 1

        if eng == "direct":
            from direct_dl import DirectDownloadTask
            th = DirectDownloadTask(tid, url, self.settings.save_dir,
                                    fmt=self.fmt.currentData())
        elif eng == "m3u8":
            from m3u8_dl import M3u8DownloadTask
            th = M3u8DownloadTask(tid, url, self.settings.save_dir,
                                  fmt=self.fmt.currentData())
        else:
            from ytdlp_dl import YtdlpTask
            format_id = None
            if (eng == "site" and self._probe_url == url
                    and self.fmt.currentData() not in ("mp3", "m4a")):
                format_id = self._probe_format_id
            th = YtdlpTask(tid, url, self.settings.save_dir,
                           quality=self.quality.currentData(),
                           fmt=self.fmt.currentData(), format_id=format_id)

        item = QListWidgetItem()
        row = TaskRow(tid)
        row.set_state(engine=ENGINE_LABEL[eng], pct=None, text="排队中")
        row.cancel_clicked.connect(self._cancel)
        item.setSizeHint(QSize(self.list.viewport().width() - 10,
                               max(56, row.sizeHint().height())))
        self.list.addItem(item)
        self.list.setItemWidget(item, row)

        th.sig.connect(self._on_event)
        self.threads[tid] = th
        self.rows[tid] = row

        if self.active < MAX_CONCURRENT:
            self.active += 1
            row.set_state(pct=None, text="准备中")
            th.start()
        else:
            self.pending.put((tid, eng, url))
        self._refresh_summary()

    def _cancel(self, tid):
        th = self.threads.get(tid)
        if th:
            th.cancel()

    # ---------- 事件 ----------
    def _on_event(self, ev):
        tid = ev["id"]
        row = self.rows.get(tid)
        if row is None:
            return
        event = ev.get("event")
        if event == "started":
            row.set_state(name=ev.get("name"), engine=row.meta_label.text(), pct=None,
                          text="准备中")
        elif event == "progress":
            row.set_state(pct=ev.get("pct"), done=ev.get("done"), total=ev.get("total"),
                          speed=ev.get("speed"), fps=ev.get("fps"),
                          stage=ev.get("stage"))
        elif event == "done":
            note = ev.get("note") or ""
            row.finish(True, "已完成 ✓" + (f" · {note}" if note else ""))
            row.set_state(pct=100)
            self._on_thread_end(tid)
        elif event == "cancelled":
            row.finish(False, "已取消")
            self._on_thread_end(tid)
        elif event == "error":
            msg = ev.get("error") or "失败"
            row.finish(False, elide(msg, 40))
            row.status_label.setToolTip(msg)
            self._on_thread_end(tid)

    def _on_thread_end(self, tid):
        th = self.threads.get(tid)
        if th:
            th.wait(2000)
            th.deleteLater()
            self.threads.pop(tid, None)
        self.active = max(0, self.active - 1)
        # 取一个排队任务
        while self.active < MAX_CONCURRENT:
            try:
                _tid, eng, url = self.pending.get_nowait()
            except queue.Empty:
                break
            row = self.rows.get(_tid)
            if row:
                row.set_state(pct=None, text="准备中")
                self.threads[_tid].start()
            self.active += 1
        self._refresh_summary()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._sync_row_widths()

    def _sync_row_widths(self):
        """任务行宽度跟随列表视口，避免长文件名把列表撑出横向滚动条。"""
        w = self.list.viewport().width() - 10
        if w <= 20:
            return
        for i in range(self.list.count()):
            it = self.list.item(i)
            r = self.list.itemWidget(it)
            if r is not None:
                it.setSizeHint(QSize(w, max(56, r.sizeHint().height())))

    def _refresh_summary(self):
        n_run = sum(1 for t in self.threads.values() if t.isRunning())
        self.summary.setText(f"进行中 {n_run} · 排队 {self.pending.qsize()}")
        self.empty_hint.setVisible(self.list.count() == 0)
