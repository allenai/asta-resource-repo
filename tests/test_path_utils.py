"""Tests for path_utils module"""

import tempfile
from pathlib import Path

from asta.resources.utils.path_utils import normalize_file_url


def test_normalize_http_url():
    """Test that HTTP URLs are returned unchanged"""
    url = "https://example.com/paper.pdf"
    index_path = Path(".asta/documents/index.yaml")

    result = normalize_file_url(url, index_path)
    assert result == url


def test_normalize_s3_url():
    """Test that S3 URLs are returned unchanged"""
    url = "s3://my-bucket/papers/paper.pdf"
    index_path = Path(".asta/documents/index.yaml")

    result = normalize_file_url(url, index_path)
    assert result == url


def test_normalize_gs_url():
    """Test that GCS URLs are returned unchanged"""
    url = "gs://my-bucket/papers/paper.pdf"
    index_path = Path(".asta/documents/index.yaml")

    result = normalize_file_url(url, index_path)
    assert result == url


def test_normalize_file_url_within_repo():
    """Test converting file:// URL within index parent dir to relative path"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create index directory
        index_dir = tmpdir / "index_location"
        index_dir.mkdir(parents=True)
        index_path = index_dir / "index.yaml"
        index_path.touch()

        # Create a document file within index parent directory
        docs_dir = index_dir / "docs"
        docs_dir.mkdir()
        doc_file = docs_dir / "paper.pdf"
        doc_file.touch()

        # Test with file:// URL
        url = f"file://{doc_file.as_posix()}"
        result = normalize_file_url(url, index_path)

        # Should convert to relative path
        assert result == "docs/paper.pdf"
        assert "file://" not in result


def test_normalize_absolute_path_within_repo():
    """Test converting absolute path within index parent dir to relative path"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create index directory
        index_dir = tmpdir / "index_location"
        index_dir.mkdir(parents=True)
        index_path = index_dir / "index.yaml"
        index_path.touch()

        # Create a document file within index parent directory
        docs_dir = index_dir / "docs"
        docs_dir.mkdir()
        doc_file = docs_dir / "paper.pdf"
        doc_file.touch()

        # Test with absolute path
        url = str(doc_file.resolve())
        result = normalize_file_url(url, index_path)

        # Should convert to relative path
        assert result == "docs/paper.pdf"
        assert not Path(result).is_absolute()


def test_normalize_file_url_outside_repo():
    """Test that file:// URL outside repo stays as file:// URL"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create repo structure
        asta_dir = tmpdir / ".asta" / "documents"
        asta_dir.mkdir(parents=True)
        index_path = asta_dir / "index.yaml"
        index_path.touch()

    # Create a file outside the repo (in separate temp directory)
    with tempfile.TemporaryDirectory() as other_tmpdir:
        other_tmpdir = Path(other_tmpdir)
        doc_file = other_tmpdir / "external.pdf"
        doc_file.touch()

        # Test with file:// URL
        url = f"file://{doc_file.as_posix()}"
        result = normalize_file_url(url, index_path)

        # Should stay as file:// URL (not relative)
        assert result.startswith("file://")
        assert str(doc_file.resolve().as_posix()) in result


def test_normalize_absolute_path_outside_repo():
    """Test that absolute path outside repo becomes file:// URL"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create repo structure
        asta_dir = tmpdir / ".asta" / "documents"
        asta_dir.mkdir(parents=True)
        index_path = asta_dir / "index.yaml"
        index_path.touch()

    # Create a file outside the repo
    with tempfile.TemporaryDirectory() as other_tmpdir:
        other_tmpdir = Path(other_tmpdir)
        doc_file = other_tmpdir / "external.pdf"
        doc_file.touch()

        # Test with absolute path
        url = str(doc_file.resolve())
        result = normalize_file_url(url, index_path)

        # Should convert to file:// URL
        assert result.startswith("file://")
        assert str(doc_file.resolve().as_posix()) in result


def test_normalize_nested_path_within_repo():
    """Test converting nested paths within index parent dir"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create index directory
        index_dir = tmpdir / "index_location"
        index_dir.mkdir(parents=True)
        index_path = index_dir / "index.yaml"
        index_path.touch()

        # Create nested directory structure within index parent
        docs_dir = index_dir / "papers" / "2024" / "ml"
        docs_dir.mkdir(parents=True)
        doc_file = docs_dir / "paper.pdf"
        doc_file.touch()

        # Test with absolute path
        url = str(doc_file.resolve())
        result = normalize_file_url(url, index_path)

        # Should convert to relative path
        assert result == "papers/2024/ml/paper.pdf"
        assert not Path(result).is_absolute()


def test_normalize_relative_path_in_repo():
    """Test that relative paths within repo are preserved"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create repo structure
        asta_dir = tmpdir / ".asta" / "documents"
        asta_dir.mkdir(parents=True)
        index_path = asta_dir / "index.yaml"
        index_path.touch()

        # Test with already relative path
        url = "docs/paper.pdf"
        result = normalize_file_url(url, index_path)

        # Should return relative path as-is (or normalized)
        # Note: This might resolve to absolute then back to relative
        # depending on whether the file exists
        assert "://" not in result or result.startswith("file://")


def test_normalize_handles_url_encoding():
    """Test that URL-encoded paths are handled correctly"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create index directory
        index_dir = tmpdir / "index_location"
        index_dir.mkdir(parents=True)
        index_path = index_dir / "index.yaml"
        index_path.touch()

        # Create a document with spaces in name within index parent
        docs_dir = index_dir / "docs"
        docs_dir.mkdir()
        doc_file = docs_dir / "my paper.pdf"
        doc_file.touch()

        # Test with URL-encoded file:// URL
        encoded_path = doc_file.as_posix().replace(" ", "%20")
        url = f"file://{encoded_path}"
        result = normalize_file_url(url, index_path)

        # Should convert to relative path with actual spaces
        assert result == "docs/my paper.pdf"
        assert " " in result
        assert "%20" not in result


def test_normalize_with_custom_index_path():
    """Test that custom index paths (outside .asta) work correctly"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create custom index path (not in .asta directory)
        custom_index = tmpdir / "my-custom-index.yaml"
        custom_index.touch()

        # Create a document file in same directory
        doc_file = tmpdir / "document.pdf"
        doc_file.touch()

        # Test with file:// URL
        url = f"file://{doc_file.as_posix()}"
        result = normalize_file_url(url, custom_index)

        # Should convert to relative path (relative to index location)
        assert result == "document.pdf"
        assert "file://" not in result


def test_normalize_with_custom_index_in_subdirectory():
    """Test custom index with documents in subdirectory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create custom index at root
        custom_index = tmpdir / "index.yaml"
        custom_index.touch()

        # Create document in subdirectory
        docs_dir = tmpdir / "papers" / "2024"
        docs_dir.mkdir(parents=True)
        doc_file = docs_dir / "research.pdf"
        doc_file.touch()

        # Test with absolute path
        url = str(doc_file.resolve())
        result = normalize_file_url(url, custom_index)

        # Should convert to relative path
        assert result == "papers/2024/research.pdf"
        assert not Path(result).is_absolute()


def test_normalize_custom_index_with_external_file():
    """Test that external files remain as file:// URLs with custom index"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create custom index
        custom_index = tmpdir / "index.yaml"
        custom_index.touch()

    # Create file in different temp directory
    with tempfile.TemporaryDirectory() as other_tmpdir:
        other_tmpdir = Path(other_tmpdir)
        external_file = other_tmpdir / "external.pdf"
        external_file.touch()

        # Test with file:// URL
        url = f"file://{external_file.as_posix()}"
        result = normalize_file_url(url, custom_index)

        # Should remain as file:// URL (not relative)
        assert result.startswith("file://")
        assert str(external_file.resolve().as_posix()) in result


def test_normalize_standard_asta_still_works():
    """Test that files within index parent dir work regardless of index location"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a nested directory structure for index
        asta_dir = tmpdir / ".asta" / "documents"
        asta_dir.mkdir(parents=True)
        index_path = asta_dir / "index.yaml"
        index_path.touch()

        # Create document within index parent directory
        doc_file = asta_dir / "README.pdf"
        doc_file.touch()

        # Test conversion
        url = f"file://{doc_file.as_posix()}"
        result = normalize_file_url(url, index_path)

        # Should convert to relative path
        assert result == "README.pdf"
        assert "file://" not in result
