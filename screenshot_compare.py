from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}

OUTPUT_DIRS = ("normalized_A", "normalized_B", "ABAB_compare")
REPORT_TXT = "report.txt"
REPORT_JSON = "report.json"


def natural_key(value: str) -> list[object]:
    parts = re.split(r"(\d+)", value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def natural_path_key(path: Path) -> list[object]:
    return natural_key(str(path))


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and not path.name.startswith(".")


def last_number(value: str) -> str | None:
    matches = re.findall(r"\d+", value)
    return matches[-1] if matches else None


def display_id(image_id: int, width: int) -> str:
    return str(image_id).zfill(width)


@dataclass(frozen=True)
class ImageRecord:
    image_id: int
    raw_id: str
    subfolder: str
    source: str
    extension: str


@dataclass
class SideScan:
    label: str
    root: str
    selected: dict[int, ImageRecord] = field(default_factory=dict)
    direct_images: list[str] = field(default_factory=list)
    empty_folders: list[str] = field(default_factory=list)
    multi_image_folders: dict[str, list[str]] = field(default_factory=dict)
    no_id_folders: list[str] = field(default_factory=list)
    no_id_images: list[str] = field(default_factory=list)
    duplicates: dict[int, list[ImageRecord]] = field(default_factory=dict)


@dataclass
class CompareResult:
    a_root: str
    b_root: str
    output_root: str
    normalized_a_dir: str
    normalized_b_dir: str
    compare_dir: str
    report_txt: str
    report_json: str
    matched_ids: list[int]
    missing_in_a: list[int]
    missing_in_b: list[int]
    matched_pair_count: int
    output_image_count: int
    id_width: int
    side_a: SideScan
    side_b: SideScan


def resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def write_error_log(message: str) -> Path:
    log_path = app_dir() / "screenshot_compare_error.log"
    log_path.write_text(message, encoding="utf-8")
    return log_path


def ensure_source_dir(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} 文件夹不存在：{path}")
    if not path.is_dir():
        raise NotADirectoryError(f"{label} 不是文件夹：{path}")


def ensure_output_not_inside_sources(output_root: Path, sources: Iterable[Path]) -> None:
    for source in sources:
        try:
            output_root.relative_to(source)
        except ValueError:
            continue
        raise ValueError(f"输出文件夹不能放在源文件夹里面：{output_root}")


def extract_record_id(subfolder: Path, image_path: Path) -> str | None:
    return last_number(subfolder.name) or last_number(image_path.stem)


def add_record(records_by_id: dict[int, list[ImageRecord]], raw_id: str, container: Path, image_path: Path) -> None:
    image_id = int(raw_id)
    record = ImageRecord(
        image_id=image_id,
        raw_id=raw_id,
        subfolder=str(container),
        source=str(image_path),
        extension=image_path.suffix.lower(),
    )
    records_by_id.setdefault(image_id, []).append(record)


def scan_side(root: Path, label: str) -> SideScan:
    scan = SideScan(label=label, root=str(root))
    records_by_id: dict[int, list[ImageRecord]] = {}

    direct_images = sorted([child for child in root.iterdir() if is_image(child)], key=natural_path_key)
    for image_path in direct_images:
        raw_id = last_number(image_path.stem)
        if raw_id is None:
            scan.no_id_images.append(str(image_path))
            continue
        scan.direct_images.append(str(image_path))
        add_record(records_by_id, raw_id, root, image_path)

    subfolders = sorted(
        [child for child in root.iterdir() if child.is_dir() and not child.name.startswith(".")],
        key=natural_path_key,
    )

    for subfolder in subfolders:
        images = sorted([child for child in subfolder.iterdir() if is_image(child)], key=natural_path_key)
        if not images:
            scan.empty_folders.append(str(subfolder))
            continue
        if len(images) > 1:
            scan.multi_image_folders[str(subfolder)] = [str(image) for image in images]
            continue

        image_path = images[0]
        raw_id = extract_record_id(subfolder, image_path)
        if raw_id is None:
            scan.no_id_folders.append(str(subfolder))
            continue

        add_record(records_by_id, raw_id, subfolder, image_path)

    for image_id, records in sorted(records_by_id.items()):
        ordered = sorted(records, key=lambda record: natural_key(record.source))
        scan.selected[image_id] = ordered[0]
        if len(ordered) > 1:
            scan.duplicates[image_id] = ordered

    return scan


def prepare_output(output_root: Path, overwrite: bool) -> tuple[Path, Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    target_dirs = tuple(output_root / name for name in OUTPUT_DIRS)
    target_files = (output_root / REPORT_TXT, output_root / REPORT_JSON)

    if overwrite:
        for target_dir in target_dirs:
            if target_dir.exists():
                shutil.rmtree(target_dir)
        for target_file in target_files:
            if target_file.exists():
                target_file.unlink()
    else:
        existing = [path for path in (*target_dirs, *target_files) if path.exists()]
        if existing:
            names = "、".join(path.name for path in existing)
            raise FileExistsError(f"输出文件夹里已存在工具结果：{names}。请选择空输出文件夹，或使用 --overwrite。")

    for target_dir in target_dirs:
        target_dir.mkdir(parents=True, exist_ok=True)

    return target_dirs


def copy_normalized(scan: SideScan, target_dir: Path, prefix: str, id_width: int) -> dict[int, Path]:
    copied: dict[int, Path] = {}
    for image_id, record in sorted(scan.selected.items()):
        target_name = f"{prefix}_{display_id(image_id, id_width)}{record.extension}"
        target_path = target_dir / target_name
        shutil.copy2(record.source, target_path)
        copied[image_id] = target_path
    return copied


def copy_abab(
    matched_ids: list[int],
    normalized_a: dict[int, Path],
    normalized_b: dict[int, Path],
    compare_dir: Path,
    id_width: int,
) -> int:
    sequence_width = max(4, len(str(len(matched_ids) * 2)))
    sequence = 1
    for image_id in matched_ids:
        for prefix, copied in (("A", normalized_a), ("B", normalized_b)):
            source = copied[image_id]
            target_name = f"{str(sequence).zfill(sequence_width)}_{prefix}_{display_id(image_id, id_width)}{source.suffix.lower()}"
            shutil.copy2(source, compare_dir / target_name)
            sequence += 1
    return sequence - 1


def calculate_id_width(side_a: SideScan, side_b: SideScan) -> int:
    raw_lengths = [len(record.raw_id) for record in [*side_a.selected.values(), *side_b.selected.values()]]
    max_id = max([0, *side_a.selected.keys(), *side_b.selected.keys()])
    return max(4, len(str(max_id)), *raw_lengths)


def format_id_list(values: list[int], width: int) -> str:
    if not values:
        return "无"
    return "、".join(display_id(value, width) for value in values)


def format_side_report(scan: SideScan, id_width: int) -> list[str]:
    lines = [
        f"{scan.label} 源文件夹：{scan.root}",
        f"{scan.label} 有效编号数：{len(scan.selected)}",
        f"{scan.label} 根目录直接图片数：{len(scan.direct_images)}",
    ]

    if scan.empty_folders:
        lines.append(f"{scan.label} 空子文件夹：")
        lines.extend(f"  - {path}" for path in scan.empty_folders)
    else:
        lines.append(f"{scan.label} 空子文件夹：无")

    if scan.multi_image_folders:
        lines.append(f"{scan.label} 多图子文件夹：")
        for folder, images in scan.multi_image_folders.items():
            lines.append(f"  - {folder}（{len(images)} 张）")
            lines.extend(f"    * {image}" for image in images)
    else:
        lines.append(f"{scan.label} 多图子文件夹：无")

    if scan.no_id_folders:
        lines.append(f"{scan.label} 无法提取编号的子文件夹：")
        lines.extend(f"  - {path}" for path in scan.no_id_folders)
    else:
        lines.append(f"{scan.label} 无法提取编号的子文件夹：无")

    if scan.no_id_images:
        lines.append(f"{scan.label} 无法提取编号的根目录图片：")
        lines.extend(f"  - {path}" for path in scan.no_id_images)
    else:
        lines.append(f"{scan.label} 无法提取编号的根目录图片：无")

    if scan.duplicates:
        lines.append(f"{scan.label} 重复编号：")
        for image_id, records in sorted(scan.duplicates.items()):
            lines.append(f"  - {display_id(image_id, id_width)}：保留 {records[0].source}")
            lines.extend(f"    * 重复项 {record.source}" for record in records[1:])
    else:
        lines.append(f"{scan.label} 重复编号：无")

    return lines


def write_reports(result: CompareResult) -> None:
    report_path = Path(result.report_txt)
    json_path = Path(result.report_json)

    lines = [
        "截图对比工具处理报告",
        "=" * 24,
        f"输出文件夹：{result.output_root}",
        f"规范化 A：{result.normalized_a_dir}",
        f"规范化 B：{result.normalized_b_dir}",
        f"最终对比：{result.compare_dir}",
        "",
        f"成功配对数量：{result.matched_pair_count}",
        f"最终输出图片数量：{result.output_image_count}",
        f"A 缺失编号（B 有、A 没有）：{format_id_list(result.missing_in_a, result.id_width)}",
        f"B 缺失编号（A 有、B 没有）：{format_id_list(result.missing_in_b, result.id_width)}",
        "",
        "[A 扫描结果]",
        *format_side_report(result.side_a, result.id_width),
        "",
        "[B 扫描结果]",
        *format_side_report(result.side_b, result.id_width),
    ]

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")


def process(a_root: str | Path, b_root: str | Path, output_root: str | Path, overwrite: bool = False) -> CompareResult:
    a_path = resolve_path(a_root)
    b_path = resolve_path(b_root)
    out_path = resolve_path(output_root)

    ensure_source_dir(a_path, "A")
    ensure_source_dir(b_path, "B")
    ensure_output_not_inside_sources(out_path, (a_path, b_path))

    side_a = scan_side(a_path, "A")
    side_b = scan_side(b_path, "B")
    id_width = calculate_id_width(side_a, side_b)

    matched_ids = sorted(set(side_a.selected) & set(side_b.selected))
    missing_in_a = sorted(set(side_b.selected) - set(side_a.selected))
    missing_in_b = sorted(set(side_a.selected) - set(side_b.selected))

    normalized_a_dir, normalized_b_dir, compare_dir = prepare_output(out_path, overwrite=overwrite)
    normalized_a = copy_normalized(side_a, normalized_a_dir, "A", id_width)
    normalized_b = copy_normalized(side_b, normalized_b_dir, "B", id_width)
    output_image_count = copy_abab(matched_ids, normalized_a, normalized_b, compare_dir, id_width)

    result = CompareResult(
        a_root=str(a_path),
        b_root=str(b_path),
        output_root=str(out_path),
        normalized_a_dir=str(normalized_a_dir),
        normalized_b_dir=str(normalized_b_dir),
        compare_dir=str(compare_dir),
        report_txt=str(out_path / REPORT_TXT),
        report_json=str(out_path / REPORT_JSON),
        matched_ids=matched_ids,
        missing_in_a=missing_in_a,
        missing_in_b=missing_in_b,
        matched_pair_count=len(matched_ids),
        output_image_count=output_image_count,
        id_width=id_width,
        side_a=side_a,
        side_b=side_b,
    )
    write_reports(result)
    return result


def print_summary(result: CompareResult) -> None:
    print("处理完成")
    print(f"成功配对数量：{result.matched_pair_count}")
    print(f"最终输出图片数量：{result.output_image_count}")
    print(f"A 缺失编号（B 有、A 没有）：{format_id_list(result.missing_in_a, result.id_width)}")
    print(f"B 缺失编号（A 有、B 没有）：{format_id_list(result.missing_in_b, result.id_width)}")
    print(f"报告：{result.report_txt}")
    print(f"最终对比文件夹：{result.compare_dir}")


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_powershell(script: str) -> subprocess.CompletedProcess[str]:
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    try:
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 powershell.exe。请改用 screenshot_compare.exe 命令行版。") from exc


def choose_folder_with_windows_dialog(title: str) -> str | None:
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = {powershell_quote(title)}
$dialog.ShowNewFolderButton = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
  Write-Output $dialog.SelectedPath
  exit 0
}}
exit 1
"""
    try:
        completed = run_powershell(script)
    except Exception as exc:
        write_error_log(f"{title}\n{exc}\n\n{traceback.format_exc()}")
        raise
    if completed.returncode != 0:
        return None
    selected = completed.stdout.strip()
    return selected or None


def show_windows_message(title: str, message: str, error: bool = False) -> None:
    icon = "Error" if error else "Information"
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show({powershell_quote(message)}, {powershell_quote(title)}, 'OK', '{icon}') | Out-Null
"""
    run_powershell(script)


def run_windows_dialogs(prefill_a: str = "", prefill_b: str = "", prefill_out: str = "") -> int:
    if not sys.platform.startswith("win"):
        return run_console_prompt(prefill_a, prefill_b, prefill_out)

    try:
        a_path = prefill_a or choose_folder_with_windows_dialog("请选择 A 截图总文件夹")
        if not a_path:
            return 0
        b_path = prefill_b or choose_folder_with_windows_dialog("请选择 B 截图总文件夹")
        if not b_path:
            return 0
        out_path = prefill_out or choose_folder_with_windows_dialog("请选择输出文件夹")
        if not out_path:
            return 0
    except Exception:
        if sys.stdin and sys.stdin.isatty():
            return run_console_prompt(prefill_a, prefill_b, prefill_out)
        return 1

    try:
        result = process(a_path, b_path, out_path)
    except FileExistsError:
        confirm = run_powershell(
            f"""
Add-Type -AssemblyName System.Windows.Forms
$choice = [System.Windows.Forms.MessageBox]::Show(
  {powershell_quote("输出文件夹里已有工具结果。是否覆盖 normalized_A、normalized_B、ABAB_compare 和旧报告？")},
  {powershell_quote("确认覆盖")},
  'YesNo',
  'Question'
)
if ($choice -eq [System.Windows.Forms.DialogResult]::Yes) {{ exit 0 }}
exit 1
"""
        )
        if confirm.returncode != 0:
            return 0
        try:
            result = process(a_path, b_path, out_path, overwrite=True)
        except Exception as exc:
            show_windows_message("处理失败", str(exc), error=True)
            return 1
    except Exception as exc:
        write_error_log(f"{exc}\n\n{traceback.format_exc()}")
        show_windows_message("处理失败", str(exc), error=True)
        return 1

    show_windows_message(
        "处理完成",
        "\n".join(
            [
                f"成功配对数量：{result.matched_pair_count}",
                f"最终输出图片数量：{result.output_image_count}",
                f"报告：{result.report_txt}",
                f"最终对比文件夹：{result.compare_dir}",
            ]
        ),
    )
    return 0


def run_console_prompt(prefill_a: str = "", prefill_b: str = "", prefill_out: str = "") -> int:
    print("截图对比工具")
    print("请输入 A、B 和输出文件夹路径。原始截图只会被复制，不会被改动。")
    a_path = prefill_a or input("A 截图总文件夹：").strip().strip('"')
    b_path = prefill_b or input("B 截图总文件夹：").strip().strip('"')
    out_path = prefill_out or input("输出文件夹：").strip().strip('"')
    overwrite_answer = input("如果已有工具输出，是否覆盖？输入 y 覆盖，直接回车不覆盖：").strip().lower()
    overwrite = overwrite_answer in {"y", "yes"}

    try:
        result = process(a_path, b_path, out_path, overwrite=overwrite)
    except Exception as exc:
        print(f"处理失败：{exc}", file=sys.stderr)
        input("按回车退出。")
        return 1

    print_summary(result)
    input("按回车退出。")
    return 0


def run_gui(prefill_a: str = "", prefill_b: str = "", prefill_out: str = "") -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception as exc:
        if sys.platform.startswith("win"):
            return run_windows_dialogs(prefill_a, prefill_b, prefill_out)
        print(f"无法启动图形窗口：{exc}", file=sys.stderr)
        return run_console_prompt(prefill_a, prefill_b, prefill_out)

    root = tk.Tk()
    root.title("截图对比工具")
    root.geometry("720x300")
    root.resizable(False, False)

    paths = {
        "a": tk.StringVar(value=prefill_a),
        "b": tk.StringVar(value=prefill_b),
        "out": tk.StringVar(value=prefill_out),
    }
    overwrite = tk.BooleanVar(value=False)
    status = tk.StringVar(value="请选择 A、B 和输出文件夹。")

    def choose_folder(key: str) -> None:
        selected = filedialog.askdirectory()
        if selected:
            paths[key].set(selected)

    def start() -> None:
        try:
            result = process(paths["a"].get(), paths["b"].get(), paths["out"].get(), overwrite=overwrite.get())
        except Exception as exc:
            status.set(f"处理失败：{exc}")
            messagebox.showerror("处理失败", str(exc))
            return

        status.set(f"处理完成：成功配对 {result.matched_pair_count} 组。")
        messagebox.showinfo(
            "处理完成",
            "\n".join(
                [
                    f"成功配对数量：{result.matched_pair_count}",
                    f"最终输出图片数量：{result.output_image_count}",
                    f"报告：{result.report_txt}",
                    f"最终对比文件夹：{result.compare_dir}",
                ]
            ),
        )

    container = tk.Frame(root, padx=18, pady=18)
    container.pack(fill="both", expand=True)

    rows = [
        ("A 截图总文件夹", "a"),
        ("B 截图总文件夹", "b"),
        ("输出文件夹", "out"),
    ]
    for index, (label, key) in enumerate(rows):
        tk.Label(container, text=label, anchor="w", width=16).grid(row=index, column=0, sticky="w", pady=8)
        tk.Entry(container, textvariable=paths[key], width=66).grid(row=index, column=1, sticky="ew", pady=8)
        tk.Button(container, text="选择", command=lambda current=key: choose_folder(current), width=10).grid(
            row=index,
            column=2,
            padx=(8, 0),
            pady=8,
        )

    tk.Checkbutton(container, text="覆盖输出文件夹中已有的工具结果", variable=overwrite).grid(
        row=3,
        column=1,
        sticky="w",
        pady=(8, 0),
    )
    tk.Button(container, text="开始处理", command=start, width=18, height=2).grid(
        row=4,
        column=1,
        pady=18,
    )
    tk.Label(container, textvariable=status, anchor="w", fg="#444").grid(row=5, column=0, columnspan=3, sticky="w")

    container.columnconfigure(1, weight=1)
    root.mainloop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="把 A/B 两组子截图文件夹整理成 A1、B1、A2、B2 的对比文件夹。")
    parser.add_argument("--a", help="A 截图总文件夹")
    parser.add_argument("--b", help="B 截图总文件夹")
    parser.add_argument("--out", help="输出文件夹")
    parser.add_argument("--overwrite", action="store_true", help="覆盖输出文件夹中已有的工具结果")
    parser.add_argument("--gui", action="store_true", help="启动图形窗口")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.gui or not (args.a and args.b and args.out):
            return run_gui(args.a or "", args.b or "", args.out or "")

        result = process(args.a, args.b, args.out, overwrite=args.overwrite)
    except Exception as exc:
        write_error_log(f"{exc}\n\n{traceback.format_exc()}")
        print(f"处理失败：{exc}", file=sys.stderr)
        return 1

    print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
