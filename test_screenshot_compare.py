from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import screenshot_compare


def make_image(root: Path, folder_name: str, image_name: str = "shot.png", content: bytes = b"image") -> Path:
    folder = root / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / image_name
    image.write_bytes(content)
    return image


class ScreenshotCompareTests(unittest.TestCase):
    def test_direct_images_in_root_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a = base / "A"
            b = base / "B"
            out = base / "out"
            a.mkdir()
            b.mkdir()

            (a / "shot_2.png").write_bytes(b"A2")
            (a / "shot_1.png").write_bytes(b"A1")
            (b / "compare_1.jpg").write_bytes(b"B1")
            (b / "compare_2.webp").write_bytes(b"B2")

            result = screenshot_compare.process(a, b, out)

            self.assertEqual(result.matched_ids, [1, 2])
            self.assertEqual(result.side_a.direct_images, [str(a / "shot_1.png"), str(a / "shot_2.png")])
            self.assertEqual(
                [path.name for path in sorted((out / "ABAB_compare").iterdir())],
                ["0001_A_0001.png", "0002_B_0001.jpg", "0003_A_0002.png", "0004_B_0002.webp"],
            )

    def test_direct_images_without_numbers_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a = base / "A"
            b = base / "B"
            out = base / "out"
            a.mkdir()
            b.mkdir()

            (a / "shot.png").write_bytes(b"no-id")
            (a / "shot_1.png").write_bytes(b"A1")
            (b / "compare_1.jpg").write_bytes(b"B1")

            result = screenshot_compare.process(a, b, out)
            report = (out / "report.txt").read_text(encoding="utf-8")

            self.assertEqual(result.matched_ids, [1])
            self.assertEqual(result.side_a.no_id_images, [str(a / "shot.png")])
            self.assertIn("A 无法提取编号的根目录图片", report)

    def test_matched_ids_are_output_in_numeric_abab_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a = base / "A 截图"
            b = base / "B 截图"
            out = base / "输出"
            a.mkdir()
            b.mkdir()

            make_image(a, "页面 602")
            make_image(a, "页面 601")
            make_image(b, "item", "b601.jpg")
            make_image(b, "item 602", "anything.webp")

            result = screenshot_compare.process(a, b, out)

            self.assertEqual(result.matched_ids, [601, 602])
            self.assertEqual(result.matched_pair_count, 2)
            self.assertEqual(result.output_image_count, 4)
            self.assertEqual(
                [path.name for path in sorted((out / "ABAB_compare").iterdir())],
                ["0001_A_0601.png", "0002_B_0601.jpg", "0003_A_0602.png", "0004_B_0602.webp"],
            )

    def test_reports_missing_empty_multi_image_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a = base / "A"
            b = base / "B"
            out = base / "out"
            a.mkdir()
            b.mkdir()

            make_image(a, "cap 1")
            make_image(a, "cap 2 first")
            make_image(a, "cap 2 second")
            (a / "empty 4").mkdir()
            make_image(a, "multi 5", "one.png")
            make_image(a, "multi 5", "two.jpg")

            make_image(b, "cap 1")
            make_image(b, "cap 3")

            result = screenshot_compare.process(a, b, out)
            report = (out / "report.txt").read_text(encoding="utf-8")

            self.assertEqual(result.matched_ids, [1])
            self.assertEqual(result.missing_in_a, [3])
            self.assertEqual(result.missing_in_b, [2])
            self.assertIn("A 空子文件夹", report)
            self.assertIn("A 多图子文件夹", report)
            self.assertIn("A 重复编号", report)

    def test_chinese_and_spaces_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a = base / "A 文件夹"
            b = base / "B 文件夹"
            out = base / "结果 文件夹"
            a.mkdir()
            b.mkdir()

            make_image(a, "第 10 张", "截图.png")
            make_image(b, "第 10 张", "截图.jpg")

            result = screenshot_compare.process(a, b, out)

            self.assertEqual(result.matched_ids, [10])
            self.assertTrue((out / "normalized_A" / "A_0010.png").exists())
            self.assertTrue((out / "normalized_B" / "B_0010.jpg").exists())

    def test_output_cannot_be_inside_source_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a = base / "A"
            b = base / "B"
            out = a / "out"
            a.mkdir()
            b.mkdir()
            make_image(a, "cap 1")
            make_image(b, "cap 1")

            with self.assertRaises(ValueError):
                screenshot_compare.process(a, b, out)


if __name__ == "__main__":
    unittest.main()
