"""视频剪切页：播放预览 + 拖拽选区条 + 精确/无损两种剪切。"""
import os
import uuid

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSlider, QVBoxLayout, QWidget, QProgressBar,
)

from . import theme
from .theme import elide
from .utils import VIDEO_EXTS, open_in_explorer
from .cut_engine import CutTask, probe_duration, parse_time, fmt_time
from .range_slider import RangeSlider
from .widgets import SectionCard, retire_thread

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    HAS_PLAYER = True
except Exception:
    HAS_PLAYER = False


class CutTab(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.src = ""
        self.duration = 0.0
        self.thread = None
        self._slider_pressed = False
        self._syncing = False  # 编辑框 <-> 选区条 双向同步防抖

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)

        c1 = SectionCard("视频剪切", title_style="h1")
        v1 = c1.body
        s = QLabel("截取视频的一段。拖入或选择视频，拖动下面的选区条定起止，"
                   "也可以直接输入时间。输出保存在原视频同一文件夹。")
        s.setObjectName("sub")
        s.setWordWrap(True)
        v1.addWidget(s)

        frow = QHBoxLayout()
        self.btn_pick = QPushButton("选择视频")
        self.btn_pick.setProperty("ghost", True)
        self.btn_pick.clicked.connect(self._pick)
        self.file_label = QLabel("未选择文件（也可以直接把视频拖进来）")
        self.file_label.setObjectName("sub")
        self.setAcceptDrops(True)
        frow.addWidget(self.btn_pick)
        frow.addWidget(self.file_label, 1)
        v1.addLayout(frow)

        # ---- 预览区 ----
        self.player = None
        if HAS_PLAYER:
            try:
                self.video = QVideoWidget()
                self.video.setFixedHeight(300)
                self.video.setStyleSheet("background:#000; border-radius:10px;")
                v1.addWidget(self.video)
                self.audio = QAudioOutput()
                self.player = QMediaPlayer()
                self.player.setAudioOutput(self.audio)
                self.player.setVideoOutput(self.video)
                self.audio.setVolume(0.8)
                self.player.positionChanged.connect(self._on_pos)
                self.player.durationChanged.connect(self._on_dur)
                self.player.errorOccurred.connect(
                    lambda e, s_: self._note("预览不可用（不影响剪切）：" + (s_ or "")))

                prow = QHBoxLayout()
                self.btn_play = QPushButton("播放")
                self.btn_play.setProperty("ghost", True)
                self.btn_play.clicked.connect(self._toggle_play)
                self.slider = QSlider(Qt.Orientation.Horizontal)
                self.slider.setRange(0, 0)
                self.slider.sliderPressed.connect(
                    lambda: setattr(self, "_slider_pressed", True))
                self.slider.sliderReleased.connect(self._slider_released)
                self.slider.sliderMoved.connect(
                    lambda v: self.player.setPosition(v))
                self.time_label = QLabel("00:00.00 / 00:00.00")
                self.time_label.setObjectName("sub")
                theme.tabular(self.time_label)
                prow.addWidget(self.btn_play)
                prow.addWidget(self.slider, 1)
                prow.addWidget(self.time_label)
                v1.addLayout(prow)
            except Exception:
                self.player = None
                self._note("播放组件初始化失败，仍可手动输入时间剪切。")

        # ---- 选区条：拖拽定起止（代替原来的两组「设为当前」）；输入框保留精确编辑 ----
        rrow = QHBoxLayout()
        rrow.setSpacing(10)
        self.range = RangeSlider()
        self.range.low_changed.connect(self._on_range_low)
        self.range.high_changed.connect(self._on_range_high)
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("起点 00:12.5")
        self.start_edit.setFixedWidth(104)
        self.end_edit = QLineEdit()
        self.end_edit.setPlaceholderText("终点 01:03.0")
        self.end_edit.setFixedWidth(104)
        self.start_edit.textChanged.connect(self._on_edits_changed)
        self.end_edit.textChanged.connect(self._on_edits_changed)
        rrow.addWidget(self.range, 1)
        rrow.addWidget(self.start_edit)
        rrow.addWidget(self.end_edit)
        v1.addLayout(rrow)

        self.seg_label = QLabel("未选择片段")
        self.seg_label.setObjectName("accent")
        v1.addWidget(self.seg_label)

        mrow = QHBoxLayout()
        lbl4 = QLabel("输出")
        lbl4.setObjectName("h2")
        self.out_type = QComboBox()
        self.out_type.addItem("视频（MP4）", "video")
        self.out_type.addItem("音频（MP3）", "mp3")
        self.out_type.addItem("音频（M4A）", "m4a")
        self.out_type.currentIndexChanged.connect(self._on_out_changed)
        mrow.addWidget(lbl4)
        mrow.addWidget(self.out_type)
        mrow.addSpacing(6)
        self.mode_label = QLabel("剪切方式")
        self.mode_label.setObjectName("h2")
        self.mode = QComboBox()
        self.mode.addItem("精确剪切（重新编码，帧级准确，速度较快）", "accurate")
        self.mode.addItem("无损剪切（不转码，秒出，按关键帧对齐可能略有偏差）", "lossless")
        mrow.addWidget(self.mode_label)
        mrow.addWidget(self.mode)
        mrow.addStretch(1)
        self.btn_start = QPushButton("开始剪切")
        self.btn_start.setObjectName("big")
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setProperty("danger", True)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.setVisible(False)
        mrow.addWidget(self.btn_cancel)
        mrow.addWidget(self.btn_start)
        v1.addLayout(mrow)

        self.status = QLabel("")
        self.status.setObjectName("sub")
        v1.addWidget(self.status)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        v1.addWidget(self.bar)

        drow = QHBoxLayout()
        self.out_hint = QLabel("")
        self.out_hint.setObjectName("sub")
        btn_open = QPushButton("打开所在文件夹")
        btn_open.setProperty("ghost", True)
        btn_open.clicked.connect(
            lambda: open_in_explorer(os.path.dirname(self.src) if self.src else ""))
        drow.addWidget(self.out_hint, 1)
        drow.addWidget(btn_open)
        v1.addLayout(drow)
        root.addWidget(c1)
        root.addStretch(1)

    # ---------- 文件 ----------
    def _pick(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "选择视频", "", "视频 (*" + " *".join(sorted(VIDEO_EXTS)) + ")")
        if f:
            self.load_file(f)

    def _apply_duration(self, dur: float):
        """视频时长确定后：选区条重置为全片，并同步起止输入框。"""
        ms = int(dur * 1000)
        self._syncing = True
        self.range.setRange(0, max(1, ms))
        self.range.set_low(0, emit=False)
        self.range.set_high(ms, emit=False)
        self.start_edit.setText(fmt_time(0.0))
        self.end_edit.setText(fmt_time(dur))
        self._syncing = False

    def load_file(self, path):
        if os.path.splitext(path)[1].lower() not in VIDEO_EXTS:
            self._note("请选择视频文件")
            return
        self.src = path
        self.file_label.setText(elide(path, 60))
        self.file_label.setToolTip(path)
        dur, wh, has_audio = probe_duration(path)
        self.duration = dur
        self.has_audio = has_audio
        if dur > 0:
            self._apply_duration(dur)
            if self.player:
                self.player.setSource(QUrl.fromLocalFile(path))
            else:
                self.slider.setRange(0, int(dur * 1000))
            self._update_seg()
            audio_tip = "" if has_audio else "（⚠ 该文件没有音频轨，无法提取音频）"
            self._note(f"已加载：{fmt_time(dur)}，{wh[0]}×{wh[1]}{audio_tip}")
        else:
            self._note("无法读取该视频信息")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.isfile(p):
                self.load_file(p)
                break

    # ---------- 预览 ----------
    def _toggle_play(self):
        if not self.player:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.btn_play.setText("播放")
        else:
            self.player.play()
            self.btn_play.setText("暂停")

    def _on_pos(self, ms):
        if not self._slider_pressed:
            self.slider.setValue(ms)
        if self.duration > 0:
            self.time_label.setText(f"{fmt_time(ms/1000)} / {fmt_time(self.duration)}")

    def _on_dur(self, ms):
        if ms > 0:
            self.duration = ms / 1000
            self.slider.setRange(0, ms)
            self._apply_duration(self.duration)

    def _slider_released(self):
        self._slider_pressed = False
        if self.player:
            self.player.setPosition(self.slider.value())

    # ---------- 选区条 <-> 输入框 ----------
    def _on_range_low(self, v):
        if self._syncing:
            return
        self._syncing = True
        self.start_edit.setText(fmt_time(v / 1000))
        self._syncing = False
        self._update_seg()

    def _on_range_high(self, v):
        if self._syncing:
            return
        self._syncing = True
        self.end_edit.setText(fmt_time(v / 1000))
        self._syncing = False
        self._update_seg()

    def _on_edits_changed(self, *_):
        if self._syncing:
            return
        s = parse_time(self.start_edit.text())
        e = parse_time(self.end_edit.text())
        self._syncing = True
        if s is not None:
            self.range.set_low(int(s * 1000), emit=False)
        if e is not None:
            self.range.set_high(int(e * 1000), emit=False)
        self._syncing = False
        self._update_seg()

    def _update_seg(self, *_):
        s = parse_time(self.start_edit.text())
        e = parse_time(self.end_edit.text())
        if s is None or e is None or e <= s:
            self.seg_label.setText("片段无效（终点需大于起点）")
            return
        self.seg_label.setText(f"将截取 {fmt_time(s)} → {fmt_time(e)}"
                               f"（{fmt_time(e - s)}）")

    def _note(self, text):
        self.status.setText(text)

    # ---------- 剪切 ----------
    def _on_out_changed(self):
        audio = self.out_type.currentData() != "video"
        # 输出音频时剪切方式无意义：直接隐藏，不留置灰控件
        self.mode.setVisible(not audio)
        self.mode_label.setVisible(not audio)
        self.btn_start.setText("提取音频" if audio else "开始剪切")
        if audio and getattr(self, "has_audio", True) is False:
            self._note("⚠ 该文件没有音频轨，请换用其他文件")

    def _start(self):
        if not self.src:
            self._note("请先选择视频")
            return
        s = parse_time(self.start_edit.text())
        e = parse_time(self.end_edit.text())
        if s is None or e is None or e <= s:
            self._note("时间格式不对，示例：01:23.50 或 83.5")
            return
        out_type = self.out_type.currentData()
        audio_fmt = None if out_type == "video" else out_type
        self.btn_start.setEnabled(False)
        self.btn_cancel.setVisible(True)
        theme.retag(self.status, "sub")
        self.status.setText("提取音频中…" if audio_fmt else "剪切中…")
        self.bar.setValue(0)
        self.thread = CutTask(uuid.uuid4().hex[:8], self.src, s, e,
                              self.mode.currentData(), audio_fmt=audio_fmt)
        self.thread.sig.connect(self._on_event)
        self.thread.start()

    def _cancel(self):
        if self.thread and self.thread.isRunning():
            self.thread.cancel()
            self.status.setText("正在取消…")

    def _on_event(self, ev):
        event = ev.get("event")
        if event == "progress":
            self.now = ev
            if ev.get("pct") is not None:
                self.bar.setRange(0, 100)
                self.bar.setValue(int(ev["pct"]))
            if ev.get("stage"):
                self.status.setText(f"{ev['stage']} {ev.get('done','')} / {ev.get('total','')}")
        elif event == "done":
            self.bar.setValue(100)
            theme.retag(self.status, "ok")
            self.status.setText(f"完成 → {os.path.basename(ev.get('path',''))}")
            self.out_hint.setText(ev.get("path", ""))
            self._finish()
        elif event in ("error", "cancelled"):
            theme.retag(self.status, "err")
            self.status.setText(ev.get("error", "已取消"))
            self._finish()

    def _finish(self):
        retire_thread(self, self.thread, 3000)
        self.thread = None
        self.btn_start.setEnabled(True)
        self.btn_cancel.setVisible(False)
