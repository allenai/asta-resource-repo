"""Tests for short ID generation utilities"""

import pytest
from asta.resources.utils.short_id import generate_short_id, generate_unique_short_id


def test_generate_short_id_default_length():
    """Test that default length is 10 characters"""
    short_id = generate_short_id()
    assert len(short_id) == 10


def test_generate_short_id_custom_length():
    """Test custom length generation"""
    short_id = generate_short_id(length=15)
    assert len(short_id) == 15


def test_generate_short_id_is_alphanumeric():
    """Test that generated IDs are alphanumeric (a-zA-Z0-9)"""
    short_id = generate_short_id()
    assert short_id.isalnum()


def test_generate_short_id_is_random():
    """Test that consecutive IDs are different (randomness)"""
    ids = {generate_short_id() for _ in range(100)}
    # All 100 IDs should be unique (collision probability is infinitesimal)
    assert len(ids) == 100


def test_generate_unique_short_id_no_collisions():
    """Test that unique ID generation avoids existing IDs"""
    existing = {"abc123xyz0", "def456uvw1", "ghi789rst2"}
    new_id = generate_unique_short_id(existing)

    assert new_id not in existing
    assert len(new_id) == 10
    assert new_id.isalnum()


def test_generate_unique_short_id_empty_set():
    """Test unique ID generation with empty existing set"""
    existing = set()
    new_id = generate_unique_short_id(existing)

    assert len(new_id) == 10
    assert new_id.isalnum()


def test_generate_unique_short_id_large_set():
    """Test unique ID generation with large existing set"""
    # Create 1000 existing IDs
    existing = {generate_short_id() for _ in range(1000)}
    new_id = generate_unique_short_id(existing)

    assert new_id not in existing
    assert len(new_id) == 10


def test_generate_unique_short_id_custom_length():
    """Test unique ID generation with custom length"""
    existing = {"abc", "def", "ghi"}
    new_id = generate_unique_short_id(existing, length=5)

    assert new_id not in existing
    assert len(new_id) == 5


def test_generate_unique_short_id_retry_limit():
    """Test that RuntimeError is raised after max retries"""
    # Create a scenario where collision is guaranteed
    # (all possible 1-char IDs are taken)
    existing = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

    with pytest.raises(RuntimeError) as exc_info:
        generate_unique_short_id(existing, length=1, max_retries=5)

    assert "Failed to generate unique short ID" in str(exc_info.value)
    assert "5 attempts" in str(exc_info.value)


def test_generate_unique_short_id_adds_to_set():
    """Test that generated IDs can be added to the set without collision"""
    existing = set()

    # Generate 100 IDs and add them to the set
    for _ in range(100):
        new_id = generate_unique_short_id(existing)
        assert new_id not in existing
        existing.add(new_id)

    # Verify all 100 IDs were generated
    assert len(existing) == 100
