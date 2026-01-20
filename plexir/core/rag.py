"""
RAG and Codebase Context Retrieval Utilities.
Provides "Smart Search" functionality for the agent.
"""

import os
import re
import ast
import subprocess
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class CodebaseRetriever:
    """
    Helper class to perform semantic-like searches using basic tools (grep/ast).
    """

    @staticmethod
    def extract_keywords(query: str) -> List[str]:
        """
        Extracts search keywords from a natural language query.
        Removes common stop words.
        """
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
            "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
            "did", "can", "could", "should", "would", "will", "shall", "may", "might", "must",
            "how", "what", "where", "when", "who", "why", "which", "show", "me", "find", "search",
            "code", "file", "files", "function", "class", "method", "variable", "implement", "fix"
        }
        # specialized code stop words
        
        words = re.findall(r'\b\w+\b', query.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        return list(set(keywords))

    @staticmethod
    def search_codebase(query: str, root_dir: str = ".") -> str:
        """
        Performs a keyword-based search across the codebase.
        Returns a formatted string of results.
        """
        keywords = CodebaseRetriever.extract_keywords(query)
        if not keywords:
            return "No valid keywords found in query."

        # Construct a grep/rg command
        # We search for lines matching ANY of the keywords
        # using a regex pattern like (key1|key2|key3)
        pattern = "|".join(re.escape(k) for k in keywords)
        
        # Try using ripgrep (rg) if available, else grep
        # We prefer rg for speed and .gitignore respect
        use_rg = False
        try:
            subprocess.run(["rg", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            use_rg = True
        except FileNotFoundError:
            pass

        results = []
        try:
            if use_rg:
                cmd = ["rg", "-n", "-e", pattern, root_dir]
            else:
                cmd = ["grep", "-rnE", pattern, root_dir]
            
            # Run search
            process = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            
            if process.returncode != 0 and not process.stdout:
                return f"No matches found for keywords: {keywords}"

            # Process output
            lines = process.stdout.splitlines()
            # Group by file
            file_matches = {}
            for line in lines:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    fname, lno, content = parts[0], parts[1], parts[2]
                    if fname not in file_matches:
                        file_matches[fname] = []
                    # Truncate content
                    file_matches[fname].append(f"  L{lno}: {content.strip()[:100]}")

            # Format results
            output_lines = [f"Search results for {keywords}:"]
            
            # Limit number of files to avoid context overflow
            sorted_files = sorted(file_matches.keys())[:10] 
            
            for fname in sorted_files:
                output_lines.append(f"\nFile: {fname}")
                # Limit matches per file
                matches = file_matches[fname][:5]
                output_lines.extend(matches)
                if len(file_matches[fname]) > 5:
                    output_lines.append(f"  ... (+{len(file_matches[fname]) - 5} more matches)")
            
            if len(file_matches) > 10:
                output_lines.append(f"\n... (+{len(file_matches) - 10} more files)")

            return "\n".join(output_lines)

        except Exception as e:
            return f"Error executing search: {e}"

    @staticmethod
    def get_file_definitions(file_path: str) -> str:
        """
        Parses a Python file and returns a summary of classes and functions.
        Useful for high-level understanding without reading the whole file.
        """
        if not file_path.endswith(".py"):
            return f"(Cannot summarize non-Python file: {file_path})"
            
        if not os.path.exists(file_path):
             return f"(File not found: {file_path})"

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
            
            definitions = []
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    definitions.append(f"Class: {node.name} (Methods: {', '.join(methods)})")
                elif isinstance(node, ast.FunctionDef):
                    definitions.append(f"Function: {node.name}")
                elif isinstance(node, ast.AsyncFunctionDef):
                    definitions.append(f"Async Function: {node.name}")
            
            if not definitions:
                return "No classes or functions found."
            
            return "\n".join(definitions)
            
        except Exception as e:
            return f"Error parsing file: {e}"

    @staticmethod
    def generate_repo_map(root_dir: str = ".", max_depth: int = 3) -> str:
        """
        Generates a high-level map of the repository structure.
        Recursively lists files and summarizes key symbols for Python files.
        """
        ignore_dirs = {'.git', '__pycache__', 'node_modules', 'venv', '.env', '.venv', 'dist', 'build', '.pytest_cache', '.mypy_cache', 'site-packages'}
        output = []

        for root, dirs, files in os.walk(root_dir):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            level = root.replace(root_dir, '').count(os.sep)
            if level > max_depth:
                continue

            indent = "  " * level
            output.append(f"{indent}{os.path.basename(root)}/")
            
            for file in files:
                if file.startswith('.'): continue
                file_path = os.path.join(root, file)
                output.append(f"{indent}  {file}")
                
                # Add symbol summary for python files
                if file.endswith(".py"):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            tree = ast.parse(f.read())
                        
                        symbols = []
                        for node in tree.body:
                            if isinstance(node, ast.ClassDef):
                                symbols.append(f"C:{node.name}")
                            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                symbols.append(f"F:{node.name}")
                        
                        if symbols:
                            # Limit symbols to keep map concise
                            symbol_str = ", ".join(symbols[:10])
                            if len(symbols) > 10: symbol_str += "..."
                            output.append(f"{indent}    └─ [{symbol_str}]")
                    except Exception:
                        pass # Ignore parsing errors in map generation

        return "\n".join(output)
