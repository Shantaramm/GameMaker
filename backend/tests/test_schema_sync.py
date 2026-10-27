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
