"""
Unit tests for agent_tools module.

Tests file operations, directory traversal, and safety features.
"""

import unittest
import tempfile
import os
import json
import difflib
import subprocess
from unittest import mock
from pathlib import Path

from tools import (
    AgentTools,
    ToolError,
    PathError,
    FileSizeError,
    PackageError,
    GitError,
    get_tools,
)


class TestAgentToolsBasics(unittest.TestCase):
    """Test basic agent tools functionality."""

    def setUp(self):
        """Set up test fixtures with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_initialization(self):
        """Should initialize with valid working directory."""
        self.assertEqual(self.tools.working_dir, os.path.abspath(self.temp_dir))
        self.assertTrue(os.path.isdir(self.tools.working_dir))

    def test_initialization_invalid_directory(self):
        """Should raise ToolError for invalid working directory."""
        with self.assertRaises(ToolError):
            AgentTools(working_dir="/nonexistent/path")


class TestDirectoryOperations(unittest.TestCase):
    """Test directory exploration operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)
        
        # Create test structure
        os.makedirs(os.path.join(self.temp_dir, "subdir1"))
        os.makedirs(os.path.join(self.temp_dir, "subdir2"))
        Path(os.path.join(self.temp_dir, "file1.txt")).touch()
        Path(os.path.join(self.temp_dir, "file2.txt")).touch()

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_list_directory(self):
        """Should list directory contents."""
        result = self.tools.list_directory(".")
        
        self.assertEqual(result["total"], 4)
        self.assertEqual(len(result["directories"]), 2)
        self.assertEqual(len(result["files"]), 2)
        self.assertIn("subdir1", result["directories"])
        self.assertIn("file1.txt", result["files"])

    def test_list_subdirectory(self):
        """Should list subdirectory contents."""
        # Create file in subdir
        Path(os.path.join(self.temp_dir, "subdir1", "nested.txt")).touch()
        
        result = self.tools.list_directory("subdir1")
        
        self.assertEqual(result["total"], 1)
        self.assertIn("nested.txt", result["files"])

    def test_list_nonexistent_directory(self):
        """Should raise ToolError for nonexistent directory."""
        with self.assertRaises(ToolError):
            self.tools.list_directory("nonexistent")


class TestFileReadWrite(unittest.TestCase):
    """Test file reading and writing operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_write_file_creates_new(self):
        """Should create new file."""
        result = self.tools.write_file("test.txt", "Hello world")
        
        self.assertTrue(result["created"])
        self.assertEqual(result["size"], 11)
        
        # Verify file exists
        file_path = os.path.join(self.temp_dir, "test.txt")
        self.assertTrue(os.path.exists(file_path))

    def test_write_file_overwrites_existing(self):
        """Should overwrite existing file."""
        # Create initial file
        self.tools.write_file("test.txt", "Original")
        
        # Overwrite
        result = self.tools.write_file("test.txt", "Updated")
        
        self.assertFalse(result["created"])
        self.assertEqual(result["size"], 7)
        
        # Verify content
        content = self.tools.read_file("test.txt")
        self.assertEqual(content, "Updated")

    def test_read_file(self):
        """Should read file contents."""
        content = "Test file content"
        self.tools.write_file("test.txt", content)
        
        read_content = self.tools.read_file("test.txt")
        
        self.assertEqual(read_content, content)

    def test_read_nonexistent_file(self):
        """Should raise ToolError for nonexistent file."""
        with self.assertRaises(ToolError):
            self.tools.read_file("nonexistent.txt")

    def test_read_file_size_limit(self):
        """Should raise FileSizeError for large files."""
        # Create tools with small limit
        tools = AgentTools(working_dir=self.temp_dir, max_file_size=100)
        
        # Write large file
        large_content = "x" * 1000
        tools.write_file("large.txt", large_content)
        
        # Should fail to read
        with self.assertRaises(FileSizeError):
            tools.read_file("large.txt")

    def test_write_file_creates_parent_directories(self):
        """Should create parent directories if needed."""
        result = self.tools.write_file("nested/dir/file.txt", "Content")
        
        self.assertTrue(result["created"])
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "nested", "dir", "file.txt")))


class TestFileEditing(unittest.TestCase):
    """Test file editing operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_append_file_creates_new(self):
        """Should create file if it doesn't exist."""
        result = self.tools.append_file("test.txt", "First line\n")
        
        self.assertEqual(result["lines_added"], 1)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "test.txt")))

    def test_append_file_adds_content(self):
        """Should append content to existing file."""
        self.tools.write_file("test.txt", "Line 1\n")
        result = self.tools.append_file("test.txt", "Line 2\n")
        
        self.assertEqual(result["lines_added"], 1)
        
        content = self.tools.read_file("test.txt")
        self.assertEqual(content, "Line 1\nLine 2\n")

    def test_edit_file_replaces_text(self):
        """Should replace text in file."""
        self.tools.write_file("test.txt", "Hello world\n")
        before = "Hello world\n"
        after = "Hello Python\n"
        diff = "".join(difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="test.txt",
            tofile="test.txt",
        ))
        result = self.tools.edit_file("test.txt", diff)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["hunks"], 1)
        
        content = self.tools.read_file("test.txt")
        self.assertEqual(content, "Hello Python\n")

    def test_edit_file_multiple_replacements(self):
        """Should replace multiple occurrences."""
        self.tools.write_file("test.txt", "foo bar foo baz foo\n")
        before = "foo bar foo baz foo\n"
        after = "qux bar qux baz qux\n"
        diff = "".join(difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="test.txt",
            tofile="test.txt",
        ))
        result = self.tools.edit_file("test.txt", diff)
        
        self.assertEqual(result["hunks"], 1)
        
        content = self.tools.read_file("test.txt")
        self.assertEqual(content, "qux bar qux baz qux\n")

    def test_edit_file_no_matches(self):
        """Should return success=False if no matches found."""
        self.tools.write_file("test.txt", "Hello planet\n")
        before = "Hello world\n"
        after = "Hello universe\n"
        diff = "".join(difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="test.txt",
            tofile="test.txt",
        ))
        
        with self.assertRaises(ToolError):
            self.tools.edit_file("test.txt", diff)


class TestCodeExecution(unittest.TestCase):
    """Test code execution tools."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir)

    @mock.patch("tools.code_runner.subprocess.run")
    def test_run_python_writes_log(self, mock_run):
        """Should execute Python and write log output when log_path is provided."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["python", "temp.py"],
            returncode=0,
            stdout="ok\n",
            stderr="",
        )

        result = self.tools.run_python("print('ok')", log_path="logs/output.txt")

        self.assertTrue(result["success"])
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["stdout"], "ok\n")
        self.assertIn("log_path", result)

        log_path = os.path.join(self.temp_dir, "logs", "output.txt")
        self.assertTrue(os.path.exists(log_path))
        with open(log_path, "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("STDOUT:", content)
        self.assertIn("ok", content)

    def test_run_python_rejects_invalid_log_path(self):
        """Should reject log paths that escape working directory."""
        with self.assertRaises(PathError):
            self.tools.run_python("print('ok')", log_path="../outside.txt")


class TestFileSearch(unittest.TestCase):
    """Test file search operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)
        
        # Create test files
        self.tools.write_file("file1.py", "# Python")
        self.tools.write_file("file2.py", "# Python")
        self.tools.write_file("file3.txt", "# Text")
        self.tools.write_file("dir1/nested.py", "# Python")

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_search_files_simple(self):
        """Should find files matching pattern."""
        result = self.tools.search_files("*.py", ".")
        
        self.assertEqual(result["total_matches"], 2)
        self.assertIn("file1.py", result["matches"])
        self.assertIn("file2.py", result["matches"])

    def test_search_files_recursive(self):
        """Should find files recursively."""
        result = self.tools.search_files("**/*.py", ".")
        
        self.assertEqual(result["total_matches"], 3)
        self.assertTrue(any(Path(m).name == "nested.py" for m in result["matches"]))

    def test_search_files_single_file(self):
        """Should find single file."""
        result = self.tools.search_files("file3.txt", ".")
        
        self.assertEqual(result["total_matches"], 1)
        self.assertIn("file3.txt", result["matches"])


class TestFileInfo(unittest.TestCase):
    """Test file information operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_get_file_info_for_file(self):
        """Should get file information."""
        content = "Test content\nLine 2\n"
        self.tools.write_file("test.txt", content)
        
        info = self.tools.get_file_info("test.txt")
        
        self.assertTrue(info["is_file"])
        self.assertFalse(info["is_dir"])
        self.assertGreater(info["size"], 0)  # File should have content
        self.assertEqual(info["lines"], 2)  # 2 lines (newline behavior)

    def test_get_file_info_for_directory(self):
        """Should get directory information."""
        self.tools.write_file("file.txt", "Content")
        os.makedirs(os.path.join(self.temp_dir, "subdir"))
        
        info = self.tools.get_file_info(".")
        
        self.assertFalse(info["is_file"])
        self.assertTrue(info["is_dir"])
        self.assertEqual(info["entry_count"], 2)

    def test_get_file_info_nonexistent(self):
        """Should raise ToolError for nonexistent path."""
        with self.assertRaises(ToolError):
            self.tools.get_file_info("nonexistent.txt")


class TestFileDeletion(unittest.TestCase):
    """Test file deletion operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_delete_file(self):
        """Should delete file."""
        self.tools.write_file("test.txt", "Content")
        
        result = self.tools.delete_file("test.txt")
        
        self.assertTrue(result["deleted"])
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "test.txt")))

    def test_delete_nonexistent_file(self):
        """Should raise ToolError when deleting nonexistent file."""
        with self.assertRaises(ToolError):
            self.tools.delete_file("nonexistent.txt")


class TestListAllFiles(unittest.TestCase):
    """Test recursive file listing operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)
        
        # Create test structure
        self.tools.write_file("file1.py", "")
        self.tools.write_file("file2.txt", "")
        self.tools.write_file("dir1/file3.py", "")
        self.tools.write_file("dir1/file4.txt", "")
        self.tools.write_file("dir2/file5.py", "")

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_list_all_files(self):
        """Should list all files recursively."""
        result = self.tools.list_all_files(".")
        
        self.assertEqual(result["total"], 5)
        self.assertEqual(len(result["files"]), 5)

    def test_list_all_files_by_extension(self):
        """Should filter files by extension."""
        result = self.tools.list_all_files(".", extensions=[".py"])
        
        self.assertEqual(result["total"], 3)
        for file in result["files"]:
            self.assertTrue(file.endswith(".py"))


class TestSecurity(unittest.TestCase):
    """Test security features (directory traversal prevention)."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_path_traversal_prevention_parent(self):
        """Should prevent directory traversal with ../ """
        with self.assertRaises(PathError):
            self.tools.list_directory("../etc")

    def test_path_traversal_prevention_absolute(self):
        """Should prevent access to absolute paths outside working dir."""
        with self.assertRaises(PathError):
            self.tools.read_file("/etc/passwd")

    def test_relative_path_validation(self):
        """Should allow legitimate relative paths."""
        self.tools.write_file("test.txt", "Content")
        
        # Should not raise
        content = self.tools.read_file("./test.txt")
        self.assertEqual(content, "Content")


class TestHelperFunctions(unittest.TestCase):
    """Test helper functions."""

    def test_get_tools_factory(self):
        """Should create AgentTools instance."""
        temp_dir = tempfile.mkdtemp()
        try:
            tools = get_tools(working_dir=temp_dir)
            self.assertIsInstance(tools, AgentTools)
        finally:
            import shutil
            shutil.rmtree(temp_dir)


class TestPackageManagement(unittest.TestCase):
    """Test package search and installation tools."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_validate_package_name_valid(self):
        """Should validate correct package names."""
        valid_names = [
            "requests",
            "numpy",
            "pandas",
            "my-package",
            "my_package",
            "my.package",
            "pytest-cov",
            "my_pkg-2.0",
        ]
        for name in valid_names:
            self.assertTrue(
                self.tools._validate_package_name(name),
                f"Should accept valid package name: {name}"
            )

    def test_validate_package_name_invalid(self):
        """Should reject malicious package names."""
        invalid_names = [
            "",
            None,
            "package;rm -rf /",
            "package|cat /etc/passwd",
            "package && malicious",
            "package`whoami`",
            "package$(whoami)",
            "../package",
            "/etc/package",
            "\\windows\\system32",
            "package/subdir",
        ]
        for name in invalid_names:
            self.assertFalse(
                self.tools._validate_package_name(name),
                f"Should reject invalid package name: {name}"
            )

    def test_check_package_installed_python(self):
        """Should check if a Python package is installed."""
        # Check for a package that should be installed (pip itself)
        result = self.tools.check_package_installed("pip", language="python")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["language"], "python")
        self.assertTrue(result["installed"] or "error" in result)

    def test_check_package_not_installed(self):
        """Should detect when a package is not installed."""
        result = self.tools.check_package_installed("totally-fake-package-xyz", language="python")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["language"], "python")
        self.assertFalse(result["installed"])

    def test_list_installed_packages_python(self):
        """Should list installed Python packages."""
        result = self.tools.list_installed_packages(language="python")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["language"], "python")
        self.assertIsInstance(result["packages"], list)
        self.assertGreater(result["count"], 0)  # pip should have some packages

    def test_search_package_invalid_language(self):
        """Should handle invalid language gracefully."""
        from tools import PackageError
        with self.assertRaises(PackageError):
            self.tools.search_package("requests", language="ruby")

    def test_install_invalid_package_name(self):
        """Should reject installation of packages with invalid names."""
        from tools import PackageError
        with self.assertRaises(PackageError):
            self.tools.install_package("package;rm -rf /", language="python")


class TestGitOperations(unittest.TestCase):
    """Test git operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_clone_repo_derives_directory_name(self):
        """Should derive destination directory from repo URL."""
        repo_url = "https://github.com/example/repo.git"
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with mock.patch("tools.agent_tools.subprocess.run", return_value=completed) as mocked_run:
            result = self.tools.clone_repo(repo_url)

        self.assertEqual(result["path"], "repo")
        called_cmd = mocked_run.call_args[0][0]
        self.assertIn("git", called_cmd)
        self.assertIn("clone", called_cmd)
        self.assertTrue(called_cmd[-1].endswith(os.path.join(self.temp_dir, "repo")))

    def test_clone_repo_with_branch_and_depth(self):
        """Should pass branch and depth arguments to git clone."""
        repo_url = "https://github.com/example/repo.git"
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with mock.patch("tools.agent_tools.subprocess.run", return_value=completed) as mocked_run:
            result = self.tools.clone_repo(repo_url, branch="master", depth=1)

        self.assertTrue(result["success"])
        called_cmd = mocked_run.call_args[0][0]
        self.assertIn("--branch", called_cmd)
        self.assertIn("master", called_cmd)
        self.assertIn("--single-branch", called_cmd)
        self.assertIn("--depth", called_cmd)
        self.assertIn("1", called_cmd)

    def test_clone_repo_rejects_nonempty_destination(self):
        """Should reject cloning into a non-empty directory."""
        os.makedirs(os.path.join(self.temp_dir, "repo"), exist_ok=True)
        with open(os.path.join(self.temp_dir, "repo", "file.txt"), "w", encoding="utf-8") as f:
            f.write("data")

        with self.assertRaises(ToolError):
            self.tools.clone_repo("https://github.com/example/repo.git", dest_dir="repo")

    def test_clone_repo_invalid_depth(self):
        """Should reject invalid depth values."""
        with self.assertRaises(ToolError):
            self.tools.clone_repo("https://github.com/example/repo.git", depth=0)


class TestGitCheckoutBranch(unittest.TestCase):
    """Test git branch checkout operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_checkout_branch_creates_new_branch(self):
        """Should create and checkout a new branch."""
        # Create a mock git repo directory
        repo_dir = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(os.path.join(repo_dir, ".git"), exist_ok=True)

        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with mock.patch("tools.agent_tools.subprocess.run", return_value=completed) as mocked_run:
            result = self.tools.checkout_branch("test_repo", "task_123_implement_feature")

        self.assertTrue(result["success"])
        self.assertEqual(result["branch_name"], "task_123_implement_feature")
        self.assertTrue(result["created"])
        
        called_cmd = mocked_run.call_args[0][0]
        self.assertIn("git", called_cmd)
        self.assertIn("checkout", called_cmd)
        self.assertIn("-b", called_cmd)
        self.assertIn("task_123_implement_feature", called_cmd)

    def test_checkout_existing_branch(self):
        """Should checkout existing branch without creating."""
        repo_dir = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(os.path.join(repo_dir, ".git"), exist_ok=True)

        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with mock.patch("tools.agent_tools.subprocess.run", return_value=completed) as mocked_run:
            result = self.tools.checkout_branch("test_repo", "existing_branch", create=False)

        self.assertTrue(result["success"])
        self.assertFalse(result["created"])
        
        called_cmd = mocked_run.call_args[0][0]
        self.assertNotIn("-b", called_cmd)

    def test_checkout_branch_invalid_name(self):
        """Should reject invalid branch names."""
        repo_dir = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(os.path.join(repo_dir, ".git"), exist_ok=True)

        # Branch names with invalid characters
        with self.assertRaises(ToolError):
            self.tools.checkout_branch("test_repo", "invalid branch name")
        
        with self.assertRaises(ToolError):
            self.tools.checkout_branch("test_repo", "branch@name")

    def test_checkout_branch_not_a_repo(self):
        """Should reject checkout in non-git directory."""
        repo_dir = os.path.join(self.temp_dir, "not_a_repo")
        os.makedirs(repo_dir, exist_ok=True)

        with self.assertRaises(GitError):
            self.tools.checkout_branch("not_a_repo", "task_123_test")

    def test_checkout_branch_repo_not_found(self):
        """Should raise error if repository directory doesn't exist."""
        with self.assertRaises(ToolError):
            self.tools.checkout_branch("nonexistent_repo", "task_123_test")


class TestGitPushBranch(unittest.TestCase):
    """Test git branch push operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_push_branch_uses_current_branch(self):
        """Should push current branch when branch name not provided."""
        repo_dir = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(os.path.join(repo_dir, ".git"), exist_ok=True)

        completed_rev = subprocess.CompletedProcess(args=[], returncode=0, stdout="feature/test\n", stderr="")
        completed_remote = subprocess.CompletedProcess(args=[], returncode=0, stdout="origin\n", stderr="")
        completed_push = subprocess.CompletedProcess(args=[], returncode=0, stdout="pushed\n", stderr="")

        with mock.patch("tools.agent_tools.subprocess.run", side_effect=[
            completed_rev,
            completed_remote,
            completed_push,
        ]) as mocked_run:
            result = self.tools.push_branch("test_repo")

        self.assertTrue(result["success"])
        self.assertEqual(result["branch_name"], "feature/test")
        self.assertEqual(result["remote"], "origin")

        push_cmd = mocked_run.call_args_list[-1][0][0]
        self.assertIn("git", push_cmd)
        self.assertIn("push", push_cmd)
        self.assertIn("-u", push_cmd)
        self.assertIn("origin", push_cmd)
        self.assertIn("feature/test", push_cmd)

    def test_push_branch_no_remote(self):
        """Should raise GitError when no remote is configured."""
        repo_dir = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(os.path.join(repo_dir, ".git"), exist_ok=True)

        completed_rev = subprocess.CompletedProcess(args=[], returncode=0, stdout="feature/test\n", stderr="")
        completed_remote = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with mock.patch("tools.agent_tools.subprocess.run", side_effect=[
            completed_rev,
            completed_remote,
        ]):
            with self.assertRaises(GitError):
                self.tools.push_branch("test_repo")


class TestGitCreatePullRequest(unittest.TestCase):
    """Test git pull request creation operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tools = AgentTools(working_dir=self.temp_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_create_pull_request_success(self):
        """Should create a pull request when gh is available."""
        repo_dir = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(os.path.join(repo_dir, ".git"), exist_ok=True)

        completed_gh = subprocess.CompletedProcess(args=[], returncode=0, stdout="gh version 2.0\n", stderr="")
        completed_rev = subprocess.CompletedProcess(args=[], returncode=0, stdout="feature_add\n", stderr="")
        completed_pr = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="https://github.com/example/repo/pull/1\n",
            stderr="",
        )

        with mock.patch("tools.agent_tools.subprocess.run", side_effect=[
            completed_gh,
            completed_rev,
            completed_pr,
        ]) as mocked_run:
            result = self.tools.create_pull_request("test_repo", base_branch="main")

        self.assertTrue(result["success"])
        self.assertEqual(result["pr_url"], "https://github.com/example/repo/pull/1")

        pr_cmd = mocked_run.call_args_list[-1][0][0]
        self.assertIn("gh", pr_cmd)
        self.assertIn("pr", pr_cmd)
        self.assertIn("create", pr_cmd)
        self.assertIn("--head", pr_cmd)
        self.assertIn("feature_add", pr_cmd)
        self.assertIn("--base", pr_cmd)
        self.assertIn("main", pr_cmd)

    def test_create_pull_request_already_exists(self):
        """Should return success when PR already exists."""
        repo_dir = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(os.path.join(repo_dir, ".git"), exist_ok=True)

        completed_gh = subprocess.CompletedProcess(args=[], returncode=0, stdout="gh version 2.0\n", stderr="")
        completed_rev = subprocess.CompletedProcess(args=[], returncode=0, stdout="feature_add\n", stderr="")
        completed_pr = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="A pull request already exists for branch feature_add",
        )

        with mock.patch("tools.agent_tools.subprocess.run", side_effect=[
            completed_gh,
            completed_rev,
            completed_pr,
        ]):
            result = self.tools.create_pull_request("test_repo", base_branch="main")

        self.assertTrue(result["success"])
        self.assertTrue(result.get("already_exists"))

    def test_create_pull_request_missing_gh(self):
        """Should raise GitError when GitHub CLI is missing."""
        repo_dir = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(os.path.join(repo_dir, ".git"), exist_ok=True)

        with mock.patch("tools.agent_tools.subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(GitError):
                self.tools.create_pull_request("test_repo")


if __name__ == "__main__":
    unittest.main()
