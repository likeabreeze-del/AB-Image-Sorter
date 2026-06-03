# 截图对比工具

这个工具用于把两组截图整理成 `A1、B1、A2、B2` 的最终对比文件夹。它只复制文件，不会移动、删除或重命名原始 A/B 截图。

## 推荐使用方式

如果已经有 `dist\screenshot_compare_gui.exe`，直接双击它，选择：

- A 截图总文件夹
- B 截图总文件夹
- 输出文件夹

`screenshot_compare_gui.exe` 专门给双击使用；批处理和命令行请用 `screenshot_compare.exe`。

如果同事电脑运行报错，先让对方运行 `run_with_log.bat`。它会保留窗口，并生成 `run_log.txt`；程序内部错误会额外生成 `screenshot_compare_error.log`。

如果公司电脑拦截单文件 exe，可以改用 `screenshot_compare_folder` 文件夹里的版本。分享时要把整个 `screenshot_compare_folder` 文件夹一起发给同事，不要只发里面的 exe。

处理完成后，输出文件夹中会生成：

- `normalized_A`：A 侧按编号规范命名后的图片
- `normalized_B`：B 侧按编号规范命名后的图片
- `ABAB_compare`：最终 `A1、B1、A2、B2` 排列的对比图片
- `report.txt`：中文处理报告
- `report.json`：结构化处理报告

## 文件夹要求

工具支持两种输入方式，可以混用，但建议同一次处理尽量保持 A/B 结构一致。

方式一：A 和 B 的总文件夹下面放多个子文件夹，每个子文件夹里有 1 张图片。

示例：

```text
A截图总文件夹
  页面 601
    screenshot.png
  页面 602
    screenshot.png

B截图总文件夹
  页面 601
    screenshot.jpg
  页面 602
    screenshot.jpg
```

工具会优先从子文件夹名提取最后一个数字作为编号；如果子文件夹名没有数字，再从图片文件名提取数字。它严格按编号匹配，例如 `601` 对 `601`，不会因为排序位置相同就强行配对。

方式二：A 和 B 文件夹里直接放图片，不再套子文件夹。

```text
A截图文件夹
  screenshot_601.png
  screenshot_602.png

B截图文件夹
  compare_601.jpg
  compare_602.jpg
```

直接放图片时，工具会从图片文件名提取最后一个数字作为编号，再按编号生成 `normalized_A`、`normalized_B` 和 `ABAB_compare`。

## 命令行使用

```powershell
dist\screenshot_compare.exe --a "A截图总文件夹" --b "B截图总文件夹" --out "输出文件夹"
```

如果要覆盖输出文件夹中已有的工具结果：

```powershell
dist\screenshot_compare.exe --a "A截图总文件夹" --b "B截图总文件夹" --out "输出文件夹" --overwrite
```

## 从源码运行

如果电脑安装了 Python 3.10 或更高版本，也可以运行：

```powershell
python screenshot_compare.py --gui
```

或：

```powershell
python screenshot_compare.py --a "A截图总文件夹" --b "B截图总文件夹" --out "输出文件夹"
```

## 打包 exe

在装有 Python 的电脑上，先安装 PyInstaller：

```powershell
python -m pip install pyinstaller
```

然后双击 `build_exe.bat`，或运行：

```powershell
python -m PyInstaller.__main__ --onefile --name screenshot_compare screenshot_compare.py
python -m PyInstaller.__main__ --onefile --windowed --name screenshot_compare_gui screenshot_compare.py
```

打包完成后，exe 会出现在：

```text
dist\screenshot_compare.exe
dist\screenshot_compare_gui.exe
```

文件夹版可以这样打包：

```powershell
python -m PyInstaller.__main__ --onedir --name screenshot_compare_folder screenshot_compare.py
```

## 报告会提示什么

报告会列出：

- 成功配对数量
- 最终输出图片数量
- A 缺失编号
- B 缺失编号
- 空子文件夹
- 多图子文件夹
- 无法提取编号的子文件夹
- 无法提取编号的根目录图片
- 重复编号

遇到多图子文件夹时，工具不会悄悄选其中一张，会把该子文件夹写入报告。
