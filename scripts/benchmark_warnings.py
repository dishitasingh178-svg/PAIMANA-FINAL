"""Read-only HTTP benchmark; run against a running PAIMANA API."""
import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--samples', type=int, default=6)
    args = parser.parse_args()
    if args.samples < 2:
        parser.error('--samples must be at least 2')

    def read(path):
        start = time.perf_counter()
        with urlopen(args.base_url + '/api/v1/alerts/' + path, timeout=20) as response:
            payload = response.read()
        return round((time.perf_counter() - start) * 1000, 2), len(payload)

    output = {}
    for name in ('summary', 'cases', 'priority', 'workspace?status=NEW'):
        results = [read(name) for _ in range(args.samples)]
        output[name] = {'first_ms': results[0][0], 'median_ms': statistics.median(r[0] for r in results[1:]),
                        'bytes': results[-1][1], 'samples_ms': [r[0] for r in results]}
    cycles = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for _ in range(args.samples):
            start = time.perf_counter()
            results = list(pool.map(read, ('cases?status=NEW', 'summary', 'priority?limit=5')))
            cycles.append(round((time.perf_counter() - start) * 1000, 2))
    output['legacy_three_request_cycle'] = {'median_ms': statistics.median(cycles[1:]),
                                           'bytes': sum(r[1] for r in results), 'samples_ms': cycles}
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
