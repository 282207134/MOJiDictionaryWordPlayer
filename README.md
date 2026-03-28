# MOJi 辞书词汇播放器

从文件夹或单个 PDF/TXT 中读取 MOJi 格式词条，逐条显示并通过 Edge TTS 朗读日语读音的桌面小工具。

## 环境要求

- Windows / macOS / Linux（需图形界面）
- Python 3.10+（推荐 3.11+）
- 朗读功能需可访问网络（使用 Microsoft Edge TTS）

## 安装依赖

在项目根目录（与 `main.py`、`requirements.txt` 同级）打开终端，执行：

```bash
python -m pip install -r requirements.txt
```

若系统上 `python` 不可用，可尝试：

```bash
py -m pip install -r requirements.txt
```

## 运行项目

```bash
python main.py
```

或：

```bash
py main.py
```

启动后会自动尝试加载 **上次打开的文件夹或单个文件**（路径写在 `settings.json`）；亦可从顶部 **选择文件夹**、**单个文件…** 重新指定。底部在 **播放读音** 右侧可设置 **自动下一条** 与 **间隔(秒)**；点击 **「设置…」** 可调整外观、字号、朗读语音及收藏导出等选项。

## 数据文件

用户数据保存在 **`data/`** 目录（若不存在会在首次运行时创建）：源码运行时在与 `main.py` 同级；**打包成 exe 后在与 exe 同级**。

| 文件 | 说明 |
|------|------|
| `settings.json` | 窗口透明度、颜色、字号、语音、上次打开的文件夹/文件路径等 |
| `remembered.json` | 「已记住」词条 |
| `favorites.json` | 「收藏」词条 |

`data/*.json` 已列入 `.gitignore`，不会提交到 Git。若你本地仓库里曾经跟踪过这些 JSON，可在项目根目录执行一次：

```bash
git rm --cached data/*.json
git commit -m "chore: 停止跟踪 data 下用户数据"
git push
```

## 打包为 Windows exe（PyInstaller）

在已安装好本程序依赖的前提下，额外安装打包工具：

```bash
python -m pip install pyinstaller
```

在项目根目录执行（生成**单文件夹**分发包，启动快、排错容易；可执行文件在 `dist/MOJiDictionaryWordPlayer/`）：

```bash
pyinstaller --noconfirm --windowed --name MOJiDictionaryWordPlayer --collect-all customtkinter main.py
```

说明：

- **`--windowed`**：不显示黑色控制台窗口；若需要看报错，可改为 **`--console`** 再打包。
- **`--collect-all customtkinter`**：把主题资源打进包内，避免界面缺样式。
- 打包后的 **`data/`** 会出现在 **exe 同目录**（与源码行为一致，已适配 `PyInstaller` 的 `frozen` 模式）。

若需要**单文件** exe（只有一个 `.exe`，首次启动会解压到临时目录，略慢），并**使用项目根目录的图标**（优先 `logo.jpg` / `logo.jpeg`，否则 `logo.png`）：

在项目根目录执行（会自动安装 `pillow`、`pyinstaller`，用 Pillow 将上述图片转为 `logo.ico` 后打包）：

```bash
python build_onefile.py
```

完成后可执行文件在 **`dist/MOJiDictionaryWordPlayer.exe`**。

也可手动打包（需自行先把 `logo.jpg` / `logo.png` 转为 `.ico`，或省略 `--icon`）：

```bash
pyinstaller --noconfirm --clean --windowed --onefile --name MOJiDictionaryWordPlayer --icon logo.ico --collect-all customtkinter main.py
```

将 `dist` 里生成的文件夹或 `MOJiDictionaryWordPlayer.exe` 拷贝到其他电脑时，需保证该机已联网（朗读依赖 Edge TTS），部分杀毒软件可能误报 PyInstaller 生成的 exe，属常见情况。

## 导出收藏

在 **设置** 窗口中点击 **「导出收藏为 TXT…」**，可将当前收藏导出为文本，便于备份或在外部编辑。
