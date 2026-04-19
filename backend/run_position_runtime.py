import json

from okx_executor import OKXExecutor
from position_runtime import run_in_position_runtime


def main() -> None:
    executor = OKXExecutor()
    result = run_in_position_runtime(executor)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
