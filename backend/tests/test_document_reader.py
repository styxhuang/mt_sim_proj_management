import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
PYPROJECT = (PROJECT_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")

sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

from sim_backend import document_reader  # noqa: E402


class DocumentReaderTests(unittest.TestCase):
    def test_python_docx_dependency_is_declared(self) -> None:
        self.assertIn("python-docx", PYPROJECT)

    def test_docx_reader_uses_python_docx_when_available(self) -> None:
        self.assertIn("Document(io.BytesIO(content))", pathlib.Path(document_reader.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
