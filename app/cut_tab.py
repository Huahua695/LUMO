"""简单视频剪切页：播放预览 + 打点选段 + 精确/无损两种剪切。"""
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSlider, QVBoxLayout, QWidget, QProgressBar,
)

import theme
from theme import elide
from utils import VIDEO_EXTS, open_in_explorer
from cut_engine import CutTask, probe_duration, parse_time, fmt_time

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

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)

        c1 = QFrame(objectName="card")
        v1 = QVBoxLayout(c1)
        v1.setContentsMargins(20, 18, 20, 18)
        v1.setSpacing(10)
        t = QLabel("视频剪切")
        t.setObjectName("h1")
        s = QLabel("截取视频的一段。拖入或选择视频，播放预览时点「设为起点/设为终点」，"
                   "也可以直接输入时间。输出保存在原视频同一文件夹。")
        s.setObjectName("sub")
        s.setWordWrap(True)
        v1.addWidget(t)
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
                    lambda e, s: self._note("预览不可用（不影响剪切）：" + (s or "")))

                prow = QHBoxLayout()
                self.btn_play = QPushButton("播放")
                self.btn_play.setProperty("ghost", True)
                self.btn_play.clicked.connect(self._toggle_play)
                self.slider = QSlider(Qt.Orientation.Horizontal)
                self.slider.setRange(0, 0)
                self.slider.sliderPressed.connect(lambda: setattr(self, "_slider_pressed", True))
                self.slider.sliderReleased.connect(self._slider_released)
                self.slider.sliderMoved.connect(
                    lambda v: self.player.setPosition(v))
                self.time_label = QLabel("00:00.00 / 00:00.00")
                self.time_label.setObjectName("sub")
                prow.addWidget(self.btn_play)
                prow.addWidget(self.slider, 1)
                prow.addWidget(self.time_label)
                v1.addLayout(prow)
            except Exception:
                self.player = None
                self._note("播放组件初始化失败，仍可手动输入时间剪切。")

        # ---- 起止时间 ----
        trow = QHBoxLayout()
        lbl = QLabel("起点")
        lbl.setObjectName("h2")
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("如 00:12.50 或 12.5")
        self.start_edit.setFixedWidth(120)
        b1 = QPushButton("设为当前")
        b1.setProperty("ghost", True)
        b1.clicked.connect(lambda: self._set_point(self.start_edit))
        lbl2 = QLabel("终点")
        lbl2.setObjectName("h2")
        self.end_edit = QLineEdit()
        self.end_edit.setPlaceholderText("如 01:03.00 或 63")
        self.end_edit.setFixedWidth(120)
        b2 = QPushButton("设为当前")
        b2.setProperty("ghost", True)
        b2.clicked.connect(lambda: self._set_point(self.end_edit))
        trow.addWidget(lbl)
        trow.addWidget(self.start_edit)
        trow.addWidget(b1)
        trow.addSpacing(10)
        trow.addWidget(lbl2)
        trow.addWidget(self.end_edit)
        trow.addWidget(b2)
        trow.addStretch(1)
        self.seg_label = QLabel("未选择片段")
        self.seg_label.setObjectName("accent")
        trow.addWidget(self.seg_label)
        v1.addLayout(trow)

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
        lbl3 = QLabel("剪切方式")
        lbl3.setObjectName("h2")
        self.mode = QComboBox()
        self.mode.addItem("精确剪切（重新编码，帧级准确，速度较快）", "accurate")
        self.mode.addItem("无损剪切（不转码，秒出，按关键帧对齐可能略有偏差）", "lossless")
        mrow.addWidget(lbl3)
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
            self.end_edit.setText(fmt_time(dur))
            self.start_edit.setText(fmt_time(0.0))
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
            if not self.end_edit.text():
                self.end_edit.setText(fmt_time(self.duration))

    def _slider_released(self):
        self._slider_pressed = False
        if self.player:
            self.player.setPosition(self.slider.value())

    def _set_point(self, edit):
        if self.player:
            edit.setText(fmt_time(self.player.position() / 1000))
        elif self.slider.value():
            edit.setText(fmt_time(self.slider.value() / 1000))
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
        self.mode.setEnabled(not audio)
        if audio:
            self.mode.setToolTip("提取音频与剪切方式无关")
            self.btn_start.setText("提取音频")
            if getattr(self, "has_audio", True) is False:
                self._note("⚠ 该文件没有音频轨，请换用其他文件")
        else:
            self.mode.setToolTip("")
            self.btn_start.setText("开始剪切")

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
        self.status.setStyleSheet("")
        self.status.setText("提取音频中…" if audio_fmt else "剪切中…")
        self.bar.setValue(0)
        self.thread = CutTask(3, self.src, s, e, self.mode.currentData(),
                              audio_fmt=audio_fmt)
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
            self.status.setStyleSheet(
                f"color:{theme.GREEN}; font-weight:600; background:transparent; border:none;")
            self.status.setText(f"完成 → {os.path.basename(ev.get('path',''))}")
            self.out_hint.setText(ev.get("path", ""))
            self._finish()
        elif event in ("error", "cancelled"):
            self.status.setStyleSheet(
                f"color:{theme.RED}; background:transparent; border:none;")
            self.status.setText(ev.get("error", "已取消"))
            self._finish()

    def _finish(self):
        if self.thread:
            self.thread.wait(3000)
            self.thread.deleteLater()
            self.thread = None
        self.btn_start.setEnabled(True)
        self.btn_cancel.setVisible(False)
