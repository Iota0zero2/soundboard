"""PySide6 GUI for the soundboard."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .audio_engine import AudioEngine, EngineConfig, list_devices
from .config import Config, SoundEntry
from .hotkeys import HotkeyManager


class SoundDialog(QDialog):
    """Edit a single sound entry."""

    def __init__(self, entry: SoundEntry, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit sound")
        self.entry = entry

        form = QFormLayout(self)
        self.name = QLineEdit(entry.name)
        self.path = QLineEdit(entry.path)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path)
        path_row.addWidget(browse)

        self.hotkey = QLineEdit(entry.hotkey)
        self.hotkey.setPlaceholderText("e.g. <ctrl>+<alt>+1")
        self.gain = QDoubleSpinBox()
        self.gain.setRange(0.0, 4.0)
        self.gain.setSingleStep(0.1)
        self.gain.setValue(entry.gain)
        self.loop = QCheckBox()
        self.loop.setChecked(entry.loop)

        form.addRow("Name", self.name)
        form.addRow("File", path_row)
        form.addRow("Hotkey", self.hotkey)
        form.addRow("Gain", self.gain)
        form.addRow("Loop", self.loop)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose sound", "", "Audio (*.wav *.flac *.ogg *.mp3 *.aiff)"
        )
        if path:
            self.path.setText(path)
            if not self.name.text():
                self.name.setText(Path(path).stem)

    def result_entry(self) -> SoundEntry:
        return SoundEntry(
            name=self.name.text() or "Sound",
            path=self.path.text(),
            hotkey=self.hotkey.text().strip(),
            gain=self.gain.value(),
            loop=self.loop.isChecked(),
            color=self.entry.color,
        )


class MainWindow(QMainWindow):
    # Emitted from the global-hotkey thread; a queued connection marshals the
    # actual playback (and any error dialog) back onto the GUI thread.
    play_requested = Signal(object)

    def __init__(self, config: Config, config_path: str | Path):
        super().__init__()
        self.setWindowTitle("Soundboard")
        self.play_requested.connect(self._play_entry)
        self.config = config
        self.config_path = config_path
        self.engine = AudioEngine(self._engine_config())
        self.hotkeys = HotkeyManager()
        self._clip_cache: dict[str, object] = {}

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.addLayout(self._build_toolbar())
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        root.addWidget(self.grid_host, 1)

        self._rebuild_grid()
        self._apply_hotkeys()

    # ---- config glue ---------------------------------------------------
    def _engine_config(self) -> EngineConfig:
        c = self.config
        return EngineConfig(
            samplerate=c.samplerate,
            blocksize=c.blocksize,
            channels=c.channels,
            input_device=c.input_device,
            output_device=c.output_device,
            mic_passthrough=c.mic_passthrough,
            mic_gain=c.mic_gain,
            master_gain=c.master_gain,
        )

    def _save(self):
        self.config.save(self.config_path)

    # ---- toolbar -------------------------------------------------------
    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        devices = list_devices()
        inputs = [d for d in devices if d["max_input_channels"] > 0]
        outputs = [d for d in devices if d["max_output_channels"] > 0]

        self.input_box = QComboBox()
        self.input_box.addItem("Default input", None)
        for d in inputs:
            self.input_box.addItem(d["name"], d["index"])
        self._select_device(self.input_box, self.config.input_device)
        self.input_box.currentIndexChanged.connect(self._on_input_changed)

        self.output_box = QComboBox()
        self.output_box.addItem("Default output", None)
        for d in outputs:
            self.output_box.addItem(d["name"], d["index"])
        self._select_device(self.output_box, self.config.output_device)
        self.output_box.currentIndexChanged.connect(self._on_output_changed)

        self.passthrough = QCheckBox("Mic passthrough")
        self.passthrough.setChecked(self.config.mic_passthrough)
        self.passthrough.toggled.connect(self._on_passthrough)

        self.master = self._slider(self.config.master_gain, self._on_master)
        self.mic = self._slider(self.config.mic_gain, self._on_mic)

        self.toggle_btn = QPushButton("Start")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.clicked.connect(self._toggle_engine)

        stop_btn = QPushButton("Stop all")
        stop_btn.clicked.connect(self.engine.stop_all)

        add_btn = QPushButton("+ Add sound")
        add_btn.clicked.connect(self._add_sound)

        bar.addWidget(QLabel("In"))
        bar.addWidget(self.input_box)
        bar.addWidget(QLabel("Out"))
        bar.addWidget(self.output_box)
        bar.addWidget(self.passthrough)
        bar.addWidget(QLabel("Mic"))
        bar.addWidget(self.mic)
        bar.addWidget(QLabel("Master"))
        bar.addWidget(self.master)
        bar.addStretch(1)
        bar.addWidget(add_btn)
        bar.addWidget(stop_btn)
        bar.addWidget(self.toggle_btn)
        return bar

    def _slider(self, value: float, handler) -> QSlider:
        s = QSlider(Qt.Horizontal)
        s.setMinimum(0)
        s.setMaximum(200)  # 0.0 .. 2.0
        s.setValue(int(value * 100))
        s.setFixedWidth(90)
        s.valueChanged.connect(handler)
        return s

    @staticmethod
    def _select_device(box: QComboBox, value):
        for i in range(box.count()):
            if box.itemData(i) == value:
                box.setCurrentIndex(i)
                return

    # ---- toolbar handlers ---------------------------------------------
    def _on_input_changed(self, _):
        self.config.input_device = self.input_box.currentData()
        self.engine.config.input_device = self.config.input_device
        self._restart_if_running()
        self._save()

    def _on_output_changed(self, _):
        self.config.output_device = self.output_box.currentData()
        self.engine.config.output_device = self.config.output_device
        self._restart_if_running()
        self._save()

    def _on_passthrough(self, checked: bool):
        self.config.mic_passthrough = checked
        self.engine.config.mic_passthrough = checked
        self._save()

    def _on_master(self, v: int):
        self.config.master_gain = v / 100.0
        self.engine.config.master_gain = self.config.master_gain
        self._save()

    def _on_mic(self, v: int):
        self.config.mic_gain = v / 100.0
        self.engine.config.mic_gain = self.config.mic_gain
        self._save()

    def _restart_if_running(self):
        if self.engine.running:
            try:
                self.engine.restart()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Audio error", str(exc))

    def _toggle_engine(self):
        try:
            if self.engine.running:
                self.engine.stop()
                self.toggle_btn.setText("Start")
                self.toggle_btn.setChecked(False)
            else:
                self.engine.start()
                self.toggle_btn.setText("Stop")
                self.toggle_btn.setChecked(True)
        except Exception as exc:  # noqa: BLE001
            self.toggle_btn.setChecked(False)
            QMessageBox.critical(self, "Audio error", str(exc))

    # ---- sound grid ----------------------------------------------------
    def _rebuild_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cols = max(1, self.config.columns)
        for i, entry in enumerate(self.config.sounds):
            btn = QPushButton(entry.name)
            btn.setMinimumHeight(72)
            if entry.color:
                btn.setStyleSheet(f"background-color: {entry.color};")
            tip = entry.hotkey or "no hotkey"
            btn.setToolTip(f"{entry.path}\n{tip}")
            btn.clicked.connect(partial(self._play_entry, entry))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(partial(self._sound_menu, entry))
            self.grid.addWidget(btn, i // cols, i % cols)

    def _play_entry(self, entry: SoundEntry):
        try:
            self.engine.play_file(entry.path, gain=entry.gain, loop=entry.loop)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Playback error", str(exc))

    def _sound_menu(self, entry: SoundEntry, pos):
        menu = QMenu(self)
        edit = QAction("Edit…", self)
        remove = QAction("Remove", self)
        edit.triggered.connect(partial(self._edit_sound, entry))
        remove.triggered.connect(partial(self._remove_sound, entry))
        menu.addAction(edit)
        menu.addAction(remove)
        menu.exec(self.sender().mapToGlobal(pos))

    def _add_sound(self):
        entry = SoundEntry(name="", path="")
        dlg = SoundDialog(entry, self)
        if dlg.exec() == QDialog.Accepted:
            new = dlg.result_entry()
            if not new.path:
                return
            self.config.sounds.append(new)
            self._save()
            self._rebuild_grid()
            self._apply_hotkeys()

    def _edit_sound(self, entry: SoundEntry):
        dlg = SoundDialog(entry, self)
        if dlg.exec() == QDialog.Accepted:
            idx = self.config.sounds.index(entry)
            self.config.sounds[idx] = dlg.result_entry()
            self._save()
            self._rebuild_grid()
            self._apply_hotkeys()

    def _remove_sound(self, entry: SoundEntry):
        self.config.sounds.remove(entry)
        self._save()
        self._rebuild_grid()
        self._apply_hotkeys()

    # ---- hotkeys -------------------------------------------------------
    def _apply_hotkeys(self):
        if not self.hotkeys.available:
            return
        bindings: dict[str, object] = {}
        for entry in self.config.sounds:
            if entry.hotkey:
                # Emit the signal (thread-safe) rather than touching Qt widgets
                # directly from the pynput listener thread.
                bindings[entry.hotkey] = partial(self.play_requested.emit, entry)
        if self.config.stop_hotkey:
            bindings[self.config.stop_hotkey] = self.engine.stop_all
        self.hotkeys.set_bindings(bindings)
        if self.hotkeys.last_error:
            self.statusBar().showMessage(self.hotkeys.last_error)
        elif self.hotkeys.active:
            self.statusBar().showMessage("Global hotkeys active", 3000)

    # ---- shutdown ------------------------------------------------------
    def closeEvent(self, event):
        self.hotkeys.stop()
        self.engine.stop()
        self._save()
        super().closeEvent(event)


def run(config_path: str | Path):
    config = Config.load(config_path)
    app = QApplication.instance() or QApplication([])
    win = MainWindow(config, config_path)
    win.resize(720, 480)
    win.show()
    app.exec()
