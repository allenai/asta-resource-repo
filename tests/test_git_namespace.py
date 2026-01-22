"""Tests for git namespace derivation utilities"""

from unittest.mock import patch, MagicMock
from pathlib import Path

from asta.resources.utils.git_namespace import (
    parse_git_remote,
    derive_namespace,
    is_in_git_repo,
    get_remote_url,
    get_current_branch,
)


class TestParseGitRemote:
    """Tests for parsing git remote URLs"""

    def test_ssh_github(self):
        """Test parsing SSH format GitHub URL"""
        url = "git@github.com:allenai/asta-resource-repo.git"
        result = parse_git_remote(url)
        assert result == {"owner": "allenai", "repo": "asta-resource-repo"}

    def test_https_github(self):
        """Test parsing HTTPS format GitHub URL"""
        url = "https://github.com/allenai/asta-resource-repo.git"
        result = parse_git_remote(url)
        assert result["owner"] == "allenai"
        assert result["repo"] == "asta-resource-repo"

    def test_gitlab_ssh(self):
        """Test parsing GitLab SSH URL"""
        url = "git@gitlab.com:company/project.git"
        result = parse_git_remote(url)
        assert result["owner"] == "company"
        assert result["repo"] == "project"

    def test_gitlab_https(self):
        """Test parsing GitLab HTTPS URL"""
        url = "https://gitlab.com/company/project.git"
        result = parse_git_remote(url)
        assert result["owner"] == "company"
        assert result["repo"] == "project"

    def test_without_git_suffix(self):
        """Test parsing URL without .git suffix"""
        url = "git@github.com:user/repo"
        result = parse_git_remote(url)
        assert result["owner"] == "user"
        assert result["repo"] == "repo"

    def test_https_without_git_suffix(self):
        """Test parsing HTTPS URL without .git suffix"""
        url = "https://github.com/user/repo"
        result = parse_git_remote(url)
        assert result["owner"] == "user"
        assert result["repo"] == "repo"

    def test_invalid_url(self):
        """Test parsing invalid URL returns None"""
        url = "not-a-git-url"
        result = parse_git_remote(url)
        assert result is None


class TestDeriveNamespace:
    """Tests for namespace derivation"""

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_git_based_namespace(self, mock_run):
        """Test deriving namespace from git repository"""
        # Mock git commands
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_in_git_repo
            MagicMock(
                returncode=0, stdout="git@github.com:owner/repo.git\n"
            ),  # get_remote_url
        ]

        namespace = derive_namespace(Path("/Users/test/repo/.asta/index.yaml"))
        assert namespace == "owner/repo"

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_git_based_namespace_different_repo(self, mock_run):
        """Test namespace from different repository"""
        # Mock git commands
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_in_git_repo
            MagicMock(
                returncode=0, stdout="git@github.com:company/project.git\n"
            ),  # get_remote_url
        ]

        namespace = derive_namespace(Path("/Users/test/repo/.asta/index.yaml"))
        assert namespace == "company/project"

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_local_fallback_not_in_git(self, mock_run):
        """Test fallback to local path when not in git repo"""
        # Mock git command failure (not in git repo)
        mock_run.return_value = MagicMock(returncode=128)

        namespace = derive_namespace(Path("/Users/test/project/.asta/index.yaml"))
        assert namespace.startswith("local:")
        assert "index.yaml" in namespace

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_local_fallback_no_remote(self, mock_run):
        """Test fallback when git repo has no remote"""
        # Git repo exists but no remote configured
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_in_git_repo
            MagicMock(returncode=1, stdout=""),  # get_remote_url fails
        ]

        namespace = derive_namespace(Path("/tmp/.asta/index.yaml"))
        assert namespace.startswith("local:")

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_git_namespace_works_in_detached_head(self, mock_run):
        """Test namespace still works in detached HEAD state"""
        # Git repo exists with remote, branch doesn't matter anymore
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_in_git_repo
            MagicMock(
                returncode=0, stdout="git@github.com:owner/repo.git\n"
            ),  # get_remote_url
        ]

        namespace = derive_namespace(Path("/tmp/.asta/index.yaml"))
        assert namespace == "owner/repo"

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_local_fallback_unparseable_remote(self, mock_run):
        """Test fallback when remote URL can't be parsed"""
        # Git repo with unparseable remote URL
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_in_git_repo
            MagicMock(returncode=0, stdout="invalid-url\n"),  # unparseable remote
            MagicMock(returncode=0, stdout="main\n"),  # get_current_branch
        ]

        namespace = derive_namespace(Path("/tmp/.asta/index.yaml"))
        assert namespace.startswith("local:")


class TestIsInGitRepo:
    """Tests for checking if in git repo"""

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_in_git_repo(self, mock_run):
        """Test detection when in git repository"""
        mock_run.return_value = MagicMock(returncode=0)
        assert is_in_git_repo() is True

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_not_in_git_repo(self, mock_run):
        """Test detection when not in git repository"""
        mock_run.return_value = MagicMock(returncode=128)
        assert is_in_git_repo() is False

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_git_not_installed(self, mock_run):
        """Test when git is not installed"""
        mock_run.side_effect = FileNotFoundError()
        assert is_in_git_repo() is False


class TestGetRemoteUrl:
    """Tests for getting git remote URL"""

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_get_origin_remote(self, mock_run):
        """Test getting origin remote URL"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="git@github.com:owner/repo.git\n"
        )
        url = get_remote_url()
        assert url == "git@github.com:owner/repo.git"

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_get_custom_remote(self, mock_run):
        """Test getting custom remote URL"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="git@gitlab.com:owner/repo.git\n"
        )
        url = get_remote_url("upstream")
        assert url == "git@gitlab.com:owner/repo.git"

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_no_remote(self, mock_run):
        """Test when remote doesn't exist"""
        mock_run.return_value = MagicMock(returncode=1)
        url = get_remote_url()
        assert url is None


class TestGetCurrentBranch:
    """Tests for getting current branch"""

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_on_branch(self, mock_run):
        """Test getting branch when on a branch"""
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
        branch = get_current_branch()
        assert branch == "main"

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_detached_head(self, mock_run):
        """Test when in detached HEAD state"""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        branch = get_current_branch()
        assert branch is None

    @patch("asta.resources.utils.git_namespace.subprocess.run")
    def test_git_error(self, mock_run):
        """Test when git command fails"""
        mock_run.return_value = MagicMock(returncode=128)
        branch = get_current_branch()
        assert branch is None
