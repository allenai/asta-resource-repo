"""Tests for cross-platform file locking"""

from asta.resources.utils.file_lock import locked


def test_exclusive_lock_write_then_shared_lock_read(tmp_path):
    path = tmp_path / "index.yaml"

    with open(path, "w", encoding="utf-8") as f:
        with locked(f):
            f.write("name: café ☕\n")

    with open(path, "r", encoding="utf-8") as f:
        with locked(f, shared=True):
            assert f.read() == "name: café ☕\n"


def test_lock_preserves_file_position(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("abcdef", encoding="utf-8")

    with open(path, "r", encoding="utf-8") as f:
        f.read(3)
        with locked(f, shared=True):
            assert f.read() == "def"


def test_lock_can_be_reacquired(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("x", encoding="utf-8")

    with open(path, "r", encoding="utf-8") as f:
        with locked(f):
            pass
        with locked(f):
            assert f.read() == "x"
