"""
Prompt loading utilities for Template Service agents.

Loads system prompts from text files in the prompts/ directory.
"""

from pathlib import Path

from workflow.utils.logging import get_logger

logger = get_logger(__name__)

# Prompts directory within the package
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(agent_name: str, fallback: str | None = None) -> str:
    """
    Load system prompt for an agent from file.

    Args:
        agent_name: Name of the agent (e.g., 'orchestrator', 'worker')
        fallback: Optional fallback prompt if file not found

    Returns:
        System prompt content

    Raises:
        FileNotFoundError: If prompt file not found and no fallback provided
    """
    prompt_file = PROMPTS_DIR / f"{agent_name}_system.md"

    try:
        prompt = prompt_file.read_text(encoding="utf-8")
        logger.info(f"Loaded prompt for {agent_name} from {prompt_file}")
        return prompt.strip()
    except FileNotFoundError:
        if fallback:
            logger.warning(f"Prompt file {prompt_file} not found, using fallback for {agent_name}")
            return fallback
        logger.error(f"Prompt file {prompt_file} not found and no fallback provided")
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_file}. Expected prompt at {prompt_file.absolute()}"
        )
