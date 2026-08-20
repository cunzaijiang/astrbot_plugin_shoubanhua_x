import ast
import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def call_name(node):
    if isinstance(node, ast.Await):
        node = node.value
    if not isinstance(node, ast.Call):
        return ""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def load_web_api():
    fake_quart = types.ModuleType("quart")
    fake_quart.jsonify = lambda payload: payload
    fake_quart.request = types.SimpleNamespace()
    fake_quart.send_file = lambda *args, **kwargs: None

    fake_astrbot = types.ModuleType("astrbot")
    fake_astrbot.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )

    old_quart = sys.modules.get("quart")
    old_astrbot = sys.modules.get("astrbot")
    sys.modules["quart"] = fake_quart
    sys.modules["astrbot"] = fake_astrbot
    try:
        spec = importlib.util.spec_from_file_location(
            "shoubanhua_web_api_regression", ROOT / "web_api.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if old_quart is None:
            sys.modules.pop("quart", None)
        else:
            sys.modules["quart"] = old_quart
        if old_astrbot is None:
            sys.modules.pop("astrbot", None)
        else:
            sys.modules["astrbot"] = old_astrbot


class GalleryWriteRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "main.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_register_helper_has_no_gallery_persistence_side_effect(self):
        helper = next(
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_register_generated_image"
        )
        calls = [call_name(node) for node in ast.walk(helper) if isinstance(node, ast.Call)]
        self.assertNotIn("record_generated_image", calls)

    def test_every_session_registration_has_one_adjacent_explicit_gallery_write(self):
        register_sites = []
        record_sites = []

        for node in ast.walk(self.tree):
            for field in ("body", "orelse", "finalbody"):
                statements = getattr(node, field, None)
                if not isinstance(statements, list):
                    continue
                for index, statement in enumerate(statements):
                    if not isinstance(statement, ast.Expr):
                        continue
                    name = call_name(statement.value)
                    if name == "record_generated_image":
                        record_sites.append(statement.lineno)
                    if name != "_register_generated_image":
                        continue

                    register_sites.append(statement.lineno)
                    self.assertGreaterEqual(index, 2, statement.lineno)
                    record_statement = statements[index - 2]
                    success_statement = statements[index - 1]
                    self.assertIsInstance(record_statement, ast.Expr)
                    self.assertIsInstance(success_statement, ast.Expr)
                    self.assertEqual(
                        call_name(record_statement.value),
                        "record_generated_image",
                        f"line {statement.lineno} must explicitly persist once before registration",
                    )
                    self.assertEqual(
                        call_name(success_statement.value),
                        "_register_generation_success",
                        f"line {statement.lineno} must keep success accounting between persistence and registration",
                    )

                    record_text = ast.unparse(record_statement.value)
                    self.assertNotIn("unified_msg_origin", record_text)
                    self.assertIn("uid=", record_text)
                    self.assertIn("gid=", record_text)
                    self.assertIn("prompt=", record_text)
                    self.assertIn("preset_name=", record_text)
                    self.assertIn("model=", record_text)

        self.assertEqual(len(register_sites), 9)
        self.assertEqual(len(record_sites), 9)


class StatusCapacityRegressionTest(unittest.IsolatedAsyncioTestCase):
    async def test_status_uses_runtime_capacity_config(self):
        module = load_web_api()
        data_mgr = types.SimpleNamespace(
            daily_stats={"users": {}, "groups": {}},
            prompt_map={},
            user_counts={},
            group_counts={},
            get_generated_storage_stats=lambda: {
                "file_count": 1,
                "size_mb": 2.0,
                "size_gb": 0.002,
            },
        )
        plugin = types.SimpleNamespace(
            context=None,
            data_mgr=data_mgr,
            api_mgr=None,
            img_mgr=None,
            conf={"image_storage_max_gb": "1"},
        )

        response = await module.WebApiHandler(plugin).handle_status()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["data"]["max_gb"], 1.0)
        self.assertEqual(response["data"]["storage"]["file_count"], 1)


if __name__ == "__main__":
    unittest.main()
