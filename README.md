# motivnavi-screentweaks

Motivnavi OS 用の「スクリーン設定」アプリです。KDE Plasma の電源管理（PowerDevil）の
画面持続時間を、2 つのモードから選んで切り替えます。

| モード                 | 電源接続中               | バッテリー駆動時           |
| ---------------------- | ------------------------ | -------------------------- |
| PCモード（デフォルト） | 常時点灯・スリープしない | 30秒で暗く、60秒でスリープ |
| カーナビモード         | 常時点灯・スリープしない | 1秒で暗く、3秒でスリープ   |

OK を押すと `~/.config/powerdevilrc` を書き換え、PowerDevil に設定を読み直させます。
書き換え前のファイルは `~/.config/powerdevilrc.motivnavi-screentweaks.bak` に保存されます。

## ビルド

```sh
./build-deb.sh
# → ./dist/motivnavi-screentweaks.deb
```

## インストール

```sh
sudo apt install ./dist/motivnavi-screentweaks.deb
```

画面表示には `python3-pyqt6.qtwebengine`（推奨パッケージとして自動で入ります）を使います。
入っていない場合は pywebview → PyQt5 → Chromium の `--app` ウィンドウ → 既定のブラウザの順に切り替わります。

## 使い方

```sh
motivnavi-screentweaks              # 画面を開く
motivnavi-screentweaks --status     # 現在のモードを表示
motivnavi-screentweaks --mode navi  # 画面を出さずにカーナビモードを適用（pc / navi）
motivnavi-screentweaks --backend app  # 表示方法を指定（auto / qt / webview / app / browser）
```

## 書き換える項目

```ini
[AC][Display]
DimDisplayIdleTimeoutSec=-1
DimDisplayWhenIdle=false
TurnOffDisplayIdleTimeoutSec=-1
TurnOffDisplayWhenIdle=false

[AC][SuspendAndShutDown]
AutoSuspendAction=0
LidAction=0
PowerButtonAction=16

[Battery][Display]
DimDisplayIdleTimeoutSec=<暗くなる秒数>
TurnOffDisplayIdleTimeoutSec=<スリープ秒数>

[Battery][SuspendAndShutDown]
AutoSuspendIdleTimeoutSec=<スリープ秒数>
PowerButtonAction=16

[LowBattery][Display]
DimDisplayIdleTimeoutSec=<暗くなる秒数>
TurnOffDisplayIdleTimeoutSec=<スリープ秒数>

[LowBattery][SuspendAndShutDown]
AutoSuspendIdleTimeoutSec=<スリープ秒数>
PowerButtonAction=16
```

上記以外のグループやキーはそのまま残します。
