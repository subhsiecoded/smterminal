"""Regression test: don't override Textual Widget.refresh()."""
import ast
from pathlib import Path
import unittest


class ScreenerRefreshMethodNameTest(unittest.TestCase):
    def test_screen_uses_refresh_data_not_widget_refresh(self):
        source_path = Path(__file__).parents[1] / "app" / "screens" / "india_screener.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        screen = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "IndiaScreenerScreen"
        )
        methods = {
            node.name: node
            for node in screen.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        self.assertNotIn("refresh", methods)
        self.assertIn("refresh_data", methods)

        # All internal refresh work must route through refresh_data.
        calls = [
            node.func.attr
            for node in ast.walk(screen)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        self.assertIn("refresh_data", calls)
        self.assertNotIn("refresh", calls)


if __name__ == "__main__":
    unittest.main()
