"""Manual check that the configured LLM answers. Run: python -m scripts.check_llm"""
import config
from app.llm import generate


def main() -> None:
    print(f"provider={config.LLM_PROVIDER} model={config.LLM_MODEL}")
    print(generate("Reply with exactly: pong", system="You are a terse test bot."))


if __name__ == "__main__":
    main()
