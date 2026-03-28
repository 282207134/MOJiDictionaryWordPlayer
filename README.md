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

启动后主窗口顶部可 **选择文件夹**、**单个文件…**；底部在 **播放读音** 右侧可设置 **自动下一条** 与 **间隔(秒)**；点击 **「设置…」** 可调整外观、字号、朗读语音及收藏导出等选项。

## 数据文件

用户数据保存在项目下的 `data/` 目录（若不存在会在首次运行时创建）：

| 文件 | 说明 |
|------|------|
| `settings.json` | 窗口透明度、颜色、字号、语音等设置 |
| `remembered.json` | 「已记住」词条 |
| `favorites.json` | 「收藏」词条 |

`data/*.json` 已列入 `.gitignore`，不会提交到 Git。若你本地仓库里曾经跟踪过这些 JSON，可在项目根目录执行一次：

```bash
git rm --cached data/*.json
git commit -m "chore: 停止跟踪 data 下用户数据"
git push
```

## 导出收藏

在 **设置** 窗口中点击 **「导出收藏为 TXT…」**，可将当前收藏导出为文本，便于备份或在外部编辑。
