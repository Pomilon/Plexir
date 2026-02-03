from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Defaults if not specified
DEFAULT_MAX_DISTILLED_CHARS = 1000 
MAX_MESSAGE_LENGTH = 200 
RECENT_MESSAGES_COUNT = 5 
KEEP_LAST_MESSAGES = 4 

def estimate_token_count(content: Any) -> int:
    """
    Estimates the number of tokens in a message or list of messages.
    Uses a rough heuristic of 4 characters per token.
    """
    if isinstance(content, str):
        return len(content) // 4
    
    if isinstance(content, list):
        total = 0
        for item in content:
            if isinstance(item, dict):
                # Check for standard 'content'
                if "content" in item:
                    total += estimate_token_count(item["content"])
                
                # Check for 'parts' (Gemini style)
                if "parts" in item:
                    for part in item["parts"]:
                        if isinstance(part, dict):
                            if "text" in part:
                                total += estimate_token_count(part["text"])
                            elif "thought" in part:
                                total += estimate_token_count(part["thought"])
                            elif "function_call" in part:
                                fc = part["function_call"]
                                total += estimate_token_count(str(fc))
                            elif "function_response" in part:
                                fr = part["function_response"]
                                total += estimate_token_count(str(fr))
                        elif isinstance(part, str):
                            total += estimate_token_count(part)
            elif isinstance(item, str):
                total += estimate_token_count(item)
        return total

    if isinstance(content, dict):
         # Single message dict
        total = 0
        if "content" in content:
            total += estimate_token_count(content["content"])
        if "parts" in content:
            total += estimate_token_count(content["parts"])
        return total

    return len(str(content)) // 4

def distill(history: List[Dict[str, Any]], max_chars: int = DEFAULT_MAX_DISTILLED_CHARS) -> str:
    """
    Distills the conversation history into a concise context summary.
    Respects max_chars to ensure it fits within the token budget.
    """
    distilled_parts = []
    current_length = 0
    
    # Reserve space for wrapper text
    wrapper_overhead = 100 
    available_chars = max(0, max_chars - wrapper_overhead)

    # Iterate through history in reverse to prioritize recent messages within the summary block
    for msg in reversed(history):
        # Extract role and content
        role = msg.get("role", "unknown")
        content = ""

        # Handle different message types
        if "content" in msg:
            content = msg["content"]
        elif "parts" in msg:
            part_texts = []
            for part in msg["parts"]:
                if isinstance(part, dict):
                    if "function_call" in part:
                        fc = part["function_call"]
                        part_texts.append(f"Function Call: {fc['name']}({fc['args']})")
                    elif "function_response" in part:
                        fr = part["function_response"]
                        part_texts.append(f"Function Response: {fr['name']} -> {fr['response']}")
                    else: 
                        part_texts.append(str(part))
                else: 
                    part_texts.append(str(part))
            content = "\n".join(part_texts)

        # Truncate long individual messages
        if len(content) > MAX_MESSAGE_LENGTH:
            content = content[:MAX_MESSAGE_LENGTH] + "... (truncated)"
        
        formatted_message = f"{role.upper()}: {content}\n"
        
        if current_length + len(formatted_message) > available_chars:
            break
        
        distilled_parts.insert(0, formatted_message)
        current_length += len(formatted_message)

        # Stop if we have enough recent messages
        if len(distilled_parts) >= RECENT_MESSAGES_COUNT and current_length > available_chars / 2:
            break
            
    if not distilled_parts:
        return "No relevant recent context available (truncated)."

    return "--- Distilled Previous Context ---\n" + "".join(distilled_parts) + "----------------------------------"

def get_messages_to_summarize(history: List[Dict[str, Any]], count: int) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Splits history into 'to be summarized' and 'to keep' (pinned or recent).
    """
    to_summarize = []
    to_keep = []
    
    # We never summarize the last 10 messages to keep immediate flow
    keep_recent = history[-10:] if len(history) > 10 else history
    history_old = history[:-10] if len(history) > 10 else []

    for msg in history_old:
        if msg.get("pinned"):
            to_keep.append(msg)
        else:
            to_summarize.append(msg)
            
    if len(to_summarize) > count:
        remaining = to_summarize[count:]
        to_summarize = to_summarize[:count]
        to_keep = to_keep + remaining

    return to_summarize, to_keep + keep_recent

def enforce_context_limit(
    history: List[Dict[str, Any]], 
    limit: int, 
    system_instruction: str = ""
) -> List[Dict[str, Any]]:
    """
    Enforces the token limit by pruning the history.
    """
    if not limit or limit <= 0:
        return history

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
    # Convert tokens to chars (approx * 4)
    max_summary_chars = available_tokens_for_summary * 4
    
    summary_text = distill(older_history, max_chars=max_summary_chars)
    summary_message = {
        "role": "user",
        "content": f"[System Note: The beginning of this conversation has been summarized due to length constraints.]\n{summary_text}"
    }
    
    new_history = [summary_message] + recent_history
    
    new_tokens = estimate_token_count(new_history) + sys_tokens
    logger.info(f"Pruned context size: {new_tokens} tokens (Limit: {limit}).")
    
    return new_history
