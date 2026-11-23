"""~/.config/powerdevilrc の読み書きを担当するモジュール。

KDE の設定ファイル形式（[AC][Display] のような入れ子グループ）を
そのまま保ったまま、必要なキーだけを書き換える。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "powerdevilrc"
BACKUP_PATH = CONFIG_PATH.with_name("powerdevilrc.motivnavi-screentweaks.bak")

DEFAULT_MODE = "pc"

MODES = {
    "pc": {
        "id": "pc",
        "name": "PCモード",
        "description": (
            "PCとして使うために最適なスクリーンです。電源接続中は永続的に画面が点灯し、"
            "バッテリー駆動時は30秒で画面が暗くなり、60秒でスリープします。"
        ),
        "dim_sec": 30,
        "suspend_sec": 60,
    },
    "navi": {
        "id": "navi",
        "name": "カーナビモード",
        "description": (
            "カーナビとして使うために最適なスクリーンです。車のアクセサリ電源で運転中は"
            "常時充電することを前提とします。電源接続中は永続的に画面が点灯し、"
            "バッテリー駆動時は1秒で画面が暗くなり、3秒でスリープします。"
        ),
        "dim_sec": 1,
        "suspend_sec": 3,
    },
}

# 綴りの古い（または誤記の）キー。存在する場合だけ同じ値で更新する。
LEGACY_ALIASES = {
    ("Battery", "Display"): {"TurnOffDisplayIdleTimeoutSec": "TurnOffDisplayIdleTimeout"},
    ("LowBattery", "Display"): {"TurnOffDisplayIdleTimeoutSec": "TurnOffDisplayIdleTimeout"},
}


def build_settings(mode_id: str) -> list[tuple[tuple[str, ...], list[tuple[str, str]]]]:
    """モードに対応する [グループ] -> [(キー, 値)] の一覧を返す。"""
    mode = MODES[mode_id]
    dim = str(mode["dim_sec"])
    sleep = str(mode["suspend_sec"])
    return [
        (("AC", "Display"), [
            ("DimDisplayIdleTimeoutSec", "-1"),
            ("DimDisplayWhenIdle", "false"),
            ("TurnOffDisplayIdleTimeoutSec", "-1"),
            ("TurnOffDisplayWhenIdle", "false"),
        ]),
        (("AC", "SuspendAndShutDown"), [
            ("AutoSuspendAction", "0"),
            ("LidAction", "0"),
            ("PowerButtonAction", "16"),
        ]),
        (("Battery", "Display"), [
            ("DimDisplayIdleTimeoutSec", dim),
            ("TurnOffDisplayIdleTimeoutSec", sleep),
        ]),
        (("Battery", "SuspendAndShutDown"), [
            ("AutoSuspendIdleTimeoutSec", sleep),
            ("PowerButtonAction", "16"),
        ]),
        (("LowBattery", "Display"), [
            ("DimDisplayIdleTimeoutSec", dim),
            ("TurnOffDisplayIdleTimeoutSec", sleep),
        ]),
        (("LowBattery", "SuspendAndShutDown"), [
            ("AutoSuspendIdleTimeoutSec", sleep),
            ("PowerButtonAction", "16"),
        ]),
    ]


# ---------------------------------------------------------------------------
# KDE 設定ファイルの簡易パーサ
# ---------------------------------------------------------------------------

def _parse_header(line: str) -> tuple[str, ...] | None:
    s = line.strip()
    if not (s.startswith("[") and s.endswith("]")):
        return None
    # "[AC][Display]" -> ("AC", "Display")
    inner = s[1:-1]
    return tuple(inner.split("]["))


def _header_line(group: tuple[str, ...]) -> str:
    return "".join(f"[{g}]" for g in group)


def _key_of(line: str) -> str | None:
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    key = s.split("=", 1)[0].strip()
    # "Key[$i]" のような KDE の修飾子は比較時に取り除く
    if "[" in key:
        key = key.split("[", 1)[0]
    return key


class KConfig:
    """行単位で保持し、触らない部分はそのまま書き戻す。"""

    def __init__(self, text: str = ""):
        # sections: [(group or None, [lines])]。先頭の None はグループ前の行。
        self.sections: list[tuple[tuple[str, ...] | None, list[str]]] = [(None, [])]
        for raw in text.splitlines():
            group = _parse_header(raw)
            if group is not None:
                self.sections.append((group, []))
            else:
                self.sections[-1][1].append(raw)

    def _find(self, group: tuple[str, ...]):
        for g, lines in self.sections:
            if g == group:
                return lines
        return None

    def get(self, group: tuple[str, ...], key: str) -> str | None:
        lines = self._find(group)
        if lines is None:
            return None
        value = None
        for line in lines:
            if _key_of(line) == key:
                value = line.split("=", 1)[1].strip()
        return value

    def set(self, group: tuple[str, ...], key: str, value: str, only_if_exists: bool = False) -> None:
        lines = self._find(group)
        if lines is None:
            if only_if_exists:
                return
            lines = []
            self.sections.append((group, lines))
        found = False
        for i, line in enumerate(lines):
            if _key_of(line) == key:
                lines[i] = f"{key}={value}"
                found = True
        if found or only_if_exists:
            return
        # グループ末尾の空行の手前に追加する
        insert_at = len(lines)
        while insert_at > 0 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, f"{key}={value}")

    def dump(self) -> str:
        out: list[str] = []
        for group, lines in self.sections:
            if group is not None:
                if out and out[-1].strip():
                    out.append("")
                out.append(_header_line(group))
            out.extend(lines)
        # 末尾の余分な空行を 1 行の改行にそろえる
        while out and not out[-1].strip():
            out.pop()
        return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def read_config() -> KConfig:
    try:
        return KConfig(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return KConfig()


def detect_mode(cfg: KConfig | None = None) -> str | None:
    """現在の設定がどのモードに一致するかを返す。一致しなければ None。"""
    cfg = cfg or read_config()
    for mode_id, mode in MODES.items():
        ok = (
            cfg.get(("Battery", "Display"), "DimDisplayIdleTimeoutSec") == str(mode["dim_sec"])
            and cfg.get(("Battery", "SuspendAndShutDown"), "AutoSuspendIdleTimeoutSec") == str(mode["suspend_sec"])
            and cfg.get(("AC", "Display"), "DimDisplayWhenIdle") == "false"
            and cfg.get(("AC", "Display"), "TurnOffDisplayWhenIdle") == "false"
        )
        if ok:
            return mode_id
    return None


def current_summary(cfg: KConfig | None = None) -> dict:
    cfg = cfg or read_config()
    return {
        "configPath": str(CONFIG_PATH),
        "exists": CONFIG_PATH.exists(),
        "batteryDimSec": cfg.get(("Battery", "Display"), "DimDisplayIdleTimeoutSec"),
        "batterySuspendSec": cfg.get(("Battery", "SuspendAndShutDown"), "AutoSuspendIdleTimeoutSec"),
    }


def apply_mode(mode_id: str) -> dict:
    if mode_id not in MODES:
        raise ValueError(f"unknown mode: {mode_id}")

    cfg = read_config()
    for group, pairs in build_settings(mode_id):
        aliases = LEGACY_ALIASES.get(group, {})
        for key, value in pairs:
            cfg.set(group, key, value)
            if key in aliases:
                cfg.set(group, aliases[key], value, only_if_exists=True)

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        shutil.copy2(CONFIG_PATH, BACKUP_PATH)

    # 途中で失敗しても元ファイルが壊れないよう一時ファイル経由で置き換える
    fd, tmp = tempfile.mkstemp(prefix=".powerdevilrc.", dir=str(CONFIG_PATH.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(cfg.dump())
        if CONFIG_PATH.exists():
            shutil.copymode(CONFIG_PATH, tmp)
        os.replace(tmp, CONFIG_PATH)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    reloaded = reload_powerdevil()
    return {
        "mode": mode_id,
        "name": MODES[mode_id]["name"],
        "configPath": str(CONFIG_PATH),
        "backupPath": str(BACKUP_PATH) if BACKUP_PATH.exists() else None,
        "reloaded": reloaded,
    }


def reload_powerdevil() -> bool:
    """PowerDevil に設定を読み直させる。成功したら True。"""
    service = "org.kde.Solid.PowerManagement"
    path = "/org/kde/Solid/PowerManagement"
    candidates = []
    for qdbus in ("qdbus6", "qdbus-qt6", "qdbus"):
        if shutil.which(qdbus):
            candidates.append([qdbus, service, path, f"{service}.reparseConfiguration"])
            break
    if shutil.which("dbus-send"):
        candidates.append([
            "dbus-send", "--session", "--print-reply", f"--dest={service}",
            path, f"{service}.reparseConfiguration",
        ])
    if shutil.which("gdbus"):
        candidates.append([
            "gdbus", "call", "--session", "--dest", service,
            "--object-path", path, "--method", f"{service}.reparseConfiguration",
        ])

    for cmd in candidates:
        try:
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0:
            # 状態の再評価も依頼しておく（失敗しても問題なし）
            refresh = list(cmd)
            refresh[-1] = refresh[-1].replace("reparseConfiguration", "refreshStatus")
            try:
                subprocess.run(refresh, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            return True
    return False
