#!/usr/bin/env python3
"""motivnavi-screentweaks: 画面の持続時間（PCモード / カーナビモード）を切り替える。

画面は HTML/CSS/JavaScript で作り、Python 側はローカル HTTP サーバーとして
設定の読み書きを担当する。ウィンドウは次の順で使えるものを選ぶ:
  1. PyQt6 WebEngine（KDE Plasma と相性がよい）
  2. pywebview
  3. PyQt5 WebEngine
  4. Chromium などの --app ウィンドウ
  5. 既定のブラウザ（xdg-open）
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import powerdevil  # noqa: E402

APP_ID = "motivnavi-screentweaks"
APP_TITLE = "スクリーン設定"
VERSION = "1.0.0"
WEB_DIR = Path(__file__).resolve().parent / "web"
WINDOW_SIZE = (960, 680)


# ---------------------------------------------------------------------------
# HTTP サーバー
# ---------------------------------------------------------------------------

class AppState:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(24)
        self.quit_event = threading.Event()
        self.last_ping = time.monotonic()
        self.lock = threading.Lock()


def make_handler(state: AppState):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"{APP_ID}/{VERSION}"

        def log_message(self, fmt, *args):  # 端末を汚さない
            if os.environ.get("MOTIVNAVI_DEBUG"):
                super().log_message(fmt, *args)

        # --- 共通 ---
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data) -> None:
            self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _authorized(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-Token", ""), state.token)

        def _touch(self) -> None:
            state.last_ping = time.monotonic()

        # --- GET ---
        def do_GET(self):
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                if not self._authorized():
                    return self._json(403, {"error": "forbidden"})
                self._touch()
                if path == "/api/state":
                    cfg = powerdevil.read_config()
                    return self._json(200, {
                        "modes": list(powerdevil.MODES.values()),
                        "defaultMode": powerdevil.DEFAULT_MODE,
                        "currentMode": powerdevil.detect_mode(cfg),
                        "current": powerdevil.current_summary(cfg),
                        "version": VERSION,
                    })
                if path == "/api/ping":
                    return self._json(200, {"ok": True})
                return self._json(404, {"error": "not found"})

            if path == "/":
                path = "/index.html"
            target = (WEB_DIR / path.lstrip("/")).resolve()
            if WEB_DIR not in target.parents or not target.is_file():
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            return self._send(200, target.read_bytes(), ctype)

        # --- POST ---
        def do_POST(self):
            path = urlparse(self.path).path
            if not self._authorized():
                return self._json(403, {"error": "forbidden"})
            self._touch()
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"error": "bad json"})

            if path == "/api/apply":
                mode = payload.get("mode")
                if mode not in powerdevil.MODES:
                    return self._json(400, {"error": "不明なモードです"})
                try:
                    with state.lock:
                        result = powerdevil.apply_mode(mode)
                except OSError as e:
                    return self._json(500, {"error": f"設定ファイルを書き込めませんでした: {e}"})
                return self._json(200, result)

            if path == "/api/close":
                self._json(200, {"ok": True})
                state.quit_event.set()
                return None

            return self._json(404, {"error": "not found"})

    return Handler


def start_server(state: AppState) -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    return httpd, f"http://127.0.0.1:{port}/index.html?token={state.token}"


# ---------------------------------------------------------------------------
# ウィンドウ表示
# ---------------------------------------------------------------------------

def run_qt(url: str, state: AppState, qt: str) -> bool:
    try:
        if qt == "qt6":
            from PyQt6.QtCore import QTimer, QUrl
            from PyQt6.QtGui import QIcon
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWidgets import QApplication
        else:
            from PyQt5.QtCore import QTimer, QUrl
            from PyQt5.QtGui import QIcon
            from PyQt5.QtWebEngineWidgets import QWebEngineView
            from PyQt5.QtWidgets import QApplication
    except ImportError:
        return False

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_TITLE)
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName(APP_ID)
    view = QWebEngineView()
    view.setWindowTitle(APP_TITLE)
    view.setWindowIcon(QIcon.fromTheme(APP_ID))
    view.resize(*WINDOW_SIZE)
    view.setUrl(QUrl(url))
    view.show()

    timer = QTimer()
    timer.setInterval(200)
    timer.timeout.connect(lambda: state.quit_event.is_set() and app.quit())
    timer.start()

    (app.exec() if qt == "qt6" else app.exec_())
    return True


def run_pywebview(url: str, state: AppState) -> bool:
    try:
        import webview  # type: ignore
    except ImportError:
        return False
    window = webview.create_window(APP_TITLE, url, width=WINDOW_SIZE[0], height=WINDOW_SIZE[1])

    def watcher():
        state.quit_event.wait()
        try:
            window.destroy()
        except Exception:
            pass

    threading.Thread(target=watcher, daemon=True).start()
    webview.start()
    return True


def _wait_with_heartbeat(state: AppState, proc: subprocess.Popen | None) -> None:
    """ブラウザ表示時: 閉じるボタン or ページの通信が途絶えたら終了する。"""
    state.last_ping = time.monotonic()
    while not state.quit_event.wait(1.0):
        if time.monotonic() - state.last_ping > 20:
            break
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except OSError:
            pass


def run_app_browser(url: str, state: AppState) -> bool:
    for name in ("/snap/bin/chromium", "chromium", "chromium-browser",
                 "google-chrome", "google-chrome-stable", "microsoft-edge"):
        exe = name if os.path.isabs(name) and os.path.exists(name) else shutil.which(name)
        if exe:
            proc = subprocess.Popen(
                [exe, f"--app={url}", f"--window-size={WINDOW_SIZE[0]},{WINDOW_SIZE[1]}",
                 f"--class={APP_ID}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            _wait_with_heartbeat(state, None if proc.poll() is not None else proc)
            return True
    return False


def run_default_browser(url: str, state: AppState) -> bool:
    opener = shutil.which("xdg-open")
    if opener:
        subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        import webbrowser
        webbrowser.open(url)
    print(f"ブラウザで開いています: {url}")
    _wait_with_heartbeat(state, None)
    return True


def run_gui(backend: str) -> int:
    state = AppState()
    httpd, url = start_server(state)
    order = {
        "auto": ["qt6", "webview", "qt5", "app", "browser"],
        "qt": ["qt6", "qt5"],
        "webview": ["webview"],
        "app": ["app"],
        "browser": ["browser"],
    }[backend]

    try:
        for b in order:
            if b in ("qt6", "qt5") and run_qt(url, state, b):
                break
            if b == "webview" and run_pywebview(url, state):
                break
            if b == "app" and run_app_browser(url, state):
                break
            if b == "browser" and run_default_browser(url, state):
                break
        else:
            print("ウィンドウを表示できませんでした。python3-pyqt6.qtwebengine を入れてください。",
                  file=sys.stderr)
            return 1
    finally:
        httpd.shutdown()
    return 0


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=APP_ID,
        description="画面の持続時間を PCモード / カーナビモード に切り替えます。",
    )
    parser.add_argument("--mode", choices=list(powerdevil.MODES),
                        help="画面を出さずに指定モードを適用する（pc / navi）")
    parser.add_argument("--status", action="store_true", help="現在のモードを表示する")
    parser.add_argument("--backend", choices=["auto", "qt", "webview", "app", "browser"],
                        default=os.environ.get("MOTIVNAVI_SCREENTWEAKS_BACKEND", "auto"),
                        help="画面の表示方法（既定: auto）")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = parser.parse_args(argv)

    if args.status:
        mode = powerdevil.detect_mode()
        name = powerdevil.MODES[mode]["name"] if mode else "カスタム（どちらのモードにも一致しません）"
        print(f"現在のモード: {name}")
        print(f"設定ファイル: {powerdevil.CONFIG_PATH}")
        return 0

    if args.mode:
        result = powerdevil.apply_mode(args.mode)
        print(f"{result['name']} を適用しました: {result['configPath']}")
        if not result["reloaded"]:
            print("※ PowerDevil への反映を確認できませんでした。再ログイン後に有効になります。")
        return 0

    return run_gui(args.backend)


if __name__ == "__main__":
    sys.exit(main())
