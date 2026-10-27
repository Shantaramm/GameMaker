import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_schema.py"
_spec = importlib.util.spec_from_file_location("export_schema", _SCRIPT)
export_schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_schema)


def test_committed_json_schema_matches_models():
    assert export_schema.SCHEMA_PATH.read_text(encoding="utf-8") == export_schema.render(), (
        "schema/game.schema.json устарела: запусти python scripts/export_schema.py"
    )


def test_compiled_demo_for_frontend_is_up_to_date():
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_demo.py"
    spec = importlib.util.spec_from_file_location("build_demo", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.OUT.read_text(encoding="utf-8") == mod.render(), (
        "frontend/src/data/demo_game.json устарел: запусти python scripts/build_demo.py"
    )
