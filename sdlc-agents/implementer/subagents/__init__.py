from pathlib import Path

def get_prompts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "prompts"

def load_prompt(name: str) -> str:
    prompt_file = get_prompts_dir() / f"{name}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
    return prompt_file.read_text(encoding="utf-8")
