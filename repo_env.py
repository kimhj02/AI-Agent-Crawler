"""저장소 루트의 `.env`를 로드해 `os.environ`에 반영합니다."""

from pathlib import Path


def load_dotenv_from_repo_root() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")
