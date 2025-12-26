import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
import tempfile
import asyncio

# Import modules to test
from plexir.core.rag import CodebaseRetriever
from plexir.tools.definitions import ScratchpadTool, CodebaseSearchTool, GitCheckoutTool, GitBranchTool, GitPushTool, GitHubCreateIssueTool

class TestRAG(unittest.TestCase):
    def test_extract_keywords(self):
        query = "How do I implement the authentication logic for the User class?"
        keywords = CodebaseRetriever.extract_keywords(query)
        # Expected keywords (stop words removed)
        expected = {"implement", "authentication", "logic", "user", "class"}
        # Note: 'implement' might be in stop words depending on implementation, let's check broadly
        self.assertTrue("authentication" in keywords)
        self.assertTrue("user" in keywords)
        self.assertFalse("the" in keywords)
        self.assertFalse("how" in keywords)

    @patch("subprocess.run")
    def test_search_codebase_grep_fallback(self, mock_run):
        # Simulate grep output
        mock_output = MagicMock()
        mock_output.returncode = 0
        mock_output.stdout = "file.py:10:class User:\nfile.py:20:def auth(self):"
        mock_run.return_value = mock_output

        result = CodebaseRetriever.search_codebase("user auth", root_dir=".")
        
        self.assertIn("file.py", result)
        self.assertIn("class User", result)
        # Check command call
        args = mock_run.call_args[0][0]
        self.assertTrue("grep" in args or "rg" in args)

class TestScratchpad(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.tool = ScratchpadTool()
        self.tool.file_path = os.path.join(self.test_dir, "scratchpad.md")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_scratchpad_lifecycle(self):
        # 1. Read empty
        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(self.tool.run("read"))
        self.assertIn("empty", res)

        # 2. Append
        res = loop.run_until_complete(self.tool.run("append", content="Buy milk"))
        self.assertIn("appended", res)
        
        # 3. Read content
        res = loop.run_until_complete(self.tool.run("read"))
        self.assertIn("Buy milk", res)
        
        # 4. Clear
        res = loop.run_until_complete(self.tool.run("clear"))
        self.assertIn("cleared", res)
        
        # 5. Read again
        res = loop.run_until_complete(self.tool.run("read"))
        self.assertIn("empty", res)
        loop.close()

class TestGitTools(unittest.TestCase):
    @patch("subprocess.run")
    def test_git_checkout(self, mock_run):
        tool = GitCheckoutTool()
        loop = asyncio.new_event_loop()
        
        # Test basic checkout
        loop.run_until_complete(tool.run("main"))
        mock_run.assert_called_with(["git", "checkout", "main"], check=True, capture_output=True, text=True)
        
        # Test new branch
        loop.run_until_complete(tool.run("feature", create_new=True))
        mock_run.assert_called_with(["git", "checkout", "-b", "feature"], check=True, capture_output=True, text=True)
        loop.close()

    @patch("subprocess.run")
    def test_git_branch(self, mock_run):
        tool = GitBranchTool()
        loop = asyncio.new_event_loop()
        
        # Test list
        mock_run.return_value.stdout = "* main\n  dev"
        res = loop.run_until_complete(tool.run("list"))
        self.assertIn("* main", res)
        
        # Test create
        loop.run_until_complete(tool.run("create", branch_name="dev"))
        mock_run.assert_called_with(["git", "branch", "dev"], check=True)
        loop.close()

    @patch("subprocess.run")
    @patch("plexir.core.config_manager.config_manager.get_tool_config")
    def test_git_push_with_token(self, mock_get_config, mock_run):
        mock_get_config.return_value = "secret_token"
        
        tool = GitPushTool()
        loop = asyncio.new_event_loop()
        loop.run_until_complete(tool.run("origin", "main"))
        
        # Verify call arguments
        # subprocess.run args are positional args[0]
        call_args = mock_run.call_args[0][0]
        # Should contain config header
        self.assertTrue(any("http.extraHeader" in str(a) for a in call_args))
        mock_run.assert_called()
        loop.close()

class TestGitHubTools(unittest.TestCase):
    @patch("plexir.core.github.requests.post")
    @patch("plexir.core.config_manager.config_manager.get_tool_config")
    def test_create_issue(self, mock_get_config, mock_post):
        # Mock config
        def config_side_effect(domain, key):
            if domain == "github" and key == "token": return "secret"
            if domain == "github" and key == "allowed_repos": return "owner/repo"
            return None
        mock_get_config.side_effect = config_side_effect
        
        # Mock API
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"html_url": "https://github.com/owner/repo/issues/1"}
        mock_post.return_value = mock_response
        
        tool = GitHubCreateIssueTool()
        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(tool.run("owner/repo", "Title", "Body"))
        
        self.assertIn("Issue created successfully", res)
        mock_post.assert_called()
        
        # Test disallowed repo
        res = loop.run_until_complete(tool.run("evil/repo", "Title", "Body"))
        self.assertIn("not in the allowed list", res)
        loop.close()

if __name__ == "__main__":
    unittest.main()
