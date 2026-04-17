from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Defaults if not specified
DEFAULT_MAX_DISTILLED_CHARS = 1000 
MAX_MESSAGE_LENGTH = 200 
RECENT_MESSAGES_COUNT = 5 
KEEP_LAST_MESSAGES = 10 

def estimate_token_count(content: Any) -> int:
    """
    Estimates the number of tokens in a message or list of messages.
    Uses a standard heuristic of approx 1.3 tokens per word (more accurate than chars/4).
    """
    if content is None:
        return 0

    if isinstance(content, str):
        if not content.strip():
            return 0
        # 1.3 tokens per word is a common industry standard for English
        # We also add a small buffer for special tokens and structure
        return int(len(content.split()) * 1.3) + 2
    
    if isinstance(content, list):
        return sum(estimate_token_count(item) for item in content)

    if isinstance(content, dict):
        total = 0
        # Check standard message fields
        if "content" in content and content["content"]:
            total += estimate_token_count(content["content"])
        
        if "parts" in content and isinstance(content["parts"], list):
            for part in content["parts"]:
                if isinstance(part, dict):
                    # Text and Thought
                    if "text" in part: total += estimate_token_count(part["text"])
                    if "thought" in part: total += estimate_token_count(part["thought"])
                    
                    # Tool Calls (JSON-like structure)
                    if "function_call" in part:
                        fc = part["function_call"]
                        total += estimate_token_count(fc.get("name", ""))
                        total += estimate_token_count(str(fc.get("args", "")))
                        total += 10 # Structural overhead for call
                    
                    # Tool Responses
                    if "function_response" in part:
                        fr = part["function_response"]
                        total += estimate_token_count(fr.get("name", ""))
                        # Results can be large; stringify and count
                        total += estimate_token_count(str(fr.get("response", "")))
                        total += 10 # Structural overhead for response
                else:
                    total += estimate_token_count(str(part))
        
        # If it's just a generic dict, count its string representation
        if not total and content:
            return estimate_token_count(str(content))
            
        return total + 4 # Per-message overhead

    # Fallback for other types
    try:
        words = str(content).split()
        return int(len(words) * 1.3) + 2
    except Exception:
        return 0

def distill(history: List[Dict[str, Any]], max_chars: int = DEFAULT_MAX_DISTILLED_CHARS) -> str:
    """
    Distills conversation history with a focus on technical artifacts and core intent.
    Preserves file paths, tool calls, and high-signal technical content.
    """
    if not history:
        return "[No previous history to summarize]"

    distilled_parts = []
    current_length = 0
    # Reserve a small space for the header/footer
    available_chars = max(0, max_chars - 50)

    # Patterns to preserve at all costs
    TECH_PATTERNS = [
        re.compile(r"/[a-zA-Z0-9/_.-]+\.[a-zA-Z0-9]+"), # File paths with extensions
        re.compile(r"class [a-zA-Z0-9]+"),              # Class names
        re.compile(r"def [a-zA-Z0-9_]+"),                # Func signatures
        re.compile(r"0x[a-fA-F0-9]+"),                  # Addresses/Hashes
        re.compile(r"OBJECTIVE:.*"),                    # Sub-agent objectives
    ]

    for msg in reversed(history):
        role = msg.get("role", "unknown")
        content = ""

        if "content" in msg:
            content = msg["content"]
        elif "parts" in msg:
            parts = []
            for p in msg["parts"]:
                if "text" in p: parts.append(p["text"])
                if "function_call" in p: parts.append(f"CALL: {p['function_call']['name']}({p['function_call']['args']})")
                if "function_response" in p: 
                    res = p["function_response"].get("response", {}).get("result", "")
                    parts.append(f"RESULT: {str(res)[:200]}...") # Truncate large tool results
            content = "\n".join(parts)

        # High-signal extraction
        lines = content.split("\n")
        preserved_lines = []
        for line in lines:
            # We keep lines that are:
            # 1. Technical (match patterns)
            # 2. Short-ish (likely headers or commands)
            # 3. From the User (more likely to contain core instructions)
            if any(p.search(line) for p in TECH_PATTERNS) or len(line) < 120 or role == "user":
                preserved_lines.append(line)
        
        # If we still have too much, we take the head and tail of the message
        if preserved_lines:
            content = "\n".join(preserved_lines)
        
        if len(content) > 1000:
            content = content[:500] + "\n... [TRUNCATED] ...\n" + content[-500:]

        formatted_message = f"[{role.upper()}]: {content}\n"
        if current_length + len(formatted_message) > available_chars:
            break
        
        distilled_parts.insert(0, formatted_message)
        current_length += len(formatted_message)
            
    if not distilled_parts:
        return "[No significant history to distill]"
        
    return "--- Episodic Summary (Technical) ---\n" + "".join(distilled_parts) + "\n----------------------------------"

import re

def get_messages_to_summarize(history: List[Dict[str, Any]], count: int = 0) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Intelligently splits history for summarization while preserving Gemini-required sequences.
    
    Rules:
    1. Keep the FIRST message.
    2. Keep ALL pinned messages.
    3. Keep the LAST ~10 messages.
    4. CRITICAL: Never split a model 'function_call' from its user 'function_response'.
    """
    if len(history) <= 15:
        return [], history

    # Initial split point
    split_idx = len(history) - 10
    
    # Adjust split_idx to ensure we don't break a call/response pair.
    # If history[split_idx] is a 'user' message containing a 'function_response',
    # we MUST move the split back to include the preceding 'model' call in the 'keep' section.
    while split_idx > 1:
        msg = history[split_idx]
        # Check if this message is a tool response
        is_response = False
        if msg.get("role") == "user" and "parts" in msg:
            for part in msg["parts"]:
                if "function_response" in part:
                    is_response = True
                    break
        
        if is_response:
            # We must keep the preceding model call too
            split_idx -= 1
        else:
            # Not a response, safe to split here (the preceding message isn't a call we're orphaned from)
            break

    to_summarize = []
    to_keep_meta = [] # For pinned and first
    
    first_msg = history[0]
    to_keep_meta.append(first_msg)
    
    recent_msgs = history[split_idx:]
    middle_history = history[1:split_idx]
    
    for msg in middle_history:
        if msg.get("pinned"):
            to_keep_meta.append(msg)
        else:
            to_summarize.append(msg)
            
    return to_summarize, to_keep_meta + recent_msgs

def enforce_context_limit(
    history: List[Dict[str, Any]], 
    limit: int, 
    system_instruction: str = "",
    current_tokens: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Enforces the token limit by pruning the history.
    """
    if not limit or limit <= 0:
        return history

    if current_tokens is None:
        current_tokens = estimate_token_count(history) + estimate_token_count(system_instruction)
    
    if current_tokens <= limit:
        return history

    logger.info(f"Context size ({current_tokens}) exceeds limit ({limit}). Pruning...")

    # Strategy:
    # 1. Keep last N messages (KEEP_LAST_MESSAGES)
    # 2. Summarize the rest into available budget
    
    recent_history = history[-KEEP_LAST_MESSAGES:]
    older_history = history[:-KEEP_LAST_MESSAGES]
    
    # Calculate budget for summary
    # budget = limit - system_prompt - recent_messages
    
    sys_tokens = estimate_token_count(system_instruction)
    recent_tokens = estimate_token_count(recent_history)
    
    # Wrapper overhead for summary message ~ 50 tokens
    wrapper_overhead_tokens = 50
    
    available_tokens_for_summary = limit - sys_tokens - recent_tokens - wrapper_overhead_tokens
    
    if available_tokens_for_summary < 0:
        logger.warning("Context limit too small even for recent messages! Truncating recent messages.")
        # If strictly enforcing, we must truncate recent history too.
        # Simple strategy: Keep dropping from the front of recent_history until it fits or is empty.
        while recent_history and (estimate_token_count(recent_history) + sys_tokens > limit):
            recent_history.pop(0)
        
        return recent_history

    # Distill older history into the available token budget
    if not older_history:
        # If we have no older history to summarize but we're still over limit,
        # we must truncate the recent history further.
        logger.warning("Limit exceeded but no older history to summarize. Truncating recent history.")
        while recent_history and (estimate_token_count(recent_history) + sys_tokens > limit):
            recent_history.pop(0)
        return recent_history

    max_summary_chars = max(200, available_tokens_for_summary * 4)
    summary_text = distill(older_history, max_chars=max_summary_chars)
    
    summary_message = {
        "role": "system",
        "content": f"BACKGROUND SUMMARY of previous conversation:\n{summary_text}",
        "pinned": True
    }
    
    new_history = [summary_message] + recent_history
    
    # Check if we are still over the limit (recursive call for safety)
    new_tokens = estimate_token_count(new_history) + sys_tokens
    if new_tokens > limit:
        logger.warning(f"Pruned history ({new_tokens}) still exceeds limit ({limit}). Retrying...")
        return enforce_context_limit(new_history, limit, system_instruction, current_tokens=new_tokens)
    
    logger.info(f"Pruned context size: {new_tokens} tokens (Limit: {limit}).")
    return new_history
