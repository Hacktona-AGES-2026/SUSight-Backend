import argparse
import json

from .core import parse_date
from .pipeline import treat


def main():
    parser = argparse.ArgumentParser(description='Tratamento reproduzivel do dataset SUSight')
    parser.add_argument('--input-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--reference', default='2026-10-23')
    args = parser.parse_args()
    reference = parse_date(args.reference)
    if not reference:
        parser.error('Referencia invalida; use AAAA-MM-DD')
    try:
        print(json.dumps(treat(args.input_dir, args.output_dir, reference), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Erro: {exc}\n')


if __name__ == '__main__':
    main()
