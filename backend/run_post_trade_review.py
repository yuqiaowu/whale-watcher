import json

from post_trade_review import run_post_trade_review


if __name__ == "__main__":
    result = run_post_trade_review()
    print(json.dumps(result, indent=2, ensure_ascii=False))
