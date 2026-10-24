import argparse
import json

from .artifacts import purge_artifacts

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove apenas saidas geradas e expiradas da demonstracao")
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    print(json.dumps({"removidos": purge_artifacts(args.root)}, ensure_ascii=False))
