import argparse
import json

from .engine import score_queue


def main():
    parser = argparse.ArgumentParser(description="ROR e exportacao da fila SUSight")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--preferences", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(score_queue(args.input_dir, args.preferences, args.output_dir), ensure_ascii=False))
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"Erro: {exc}\n")


if __name__ == "__main__":
    main()
