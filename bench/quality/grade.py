#!/usr/bin/env python3
"""Hidden grader for the quality benchmark. The model never sees these cases.
Usage: grade.py <module_path> <task_id>  ->  prints "pass total" (edge-case coverage)."""
import importlib.util
import sys


def load(path, sym):
    spec = importlib.util.spec_from_file_location("m", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, sym)


def grade_value(fn, cases):
    p = 0
    for inp, exp in cases:
        try:
            if fn(inp) == exp:
                p += 1
        except Exception:
            pass
    return p, len(cases)


def grade_raise(fn, valid, bad):
    p = 0
    for inp, exp in valid:
        try:
            if fn(inp) == exp:
                p += 1
        except Exception:
            pass
    for inp in bad:
        try:
            fn(inp)            # must raise ValueError
        except ValueError:
            p += 1
        except Exception:
            pass               # wrong exception type = fail
    return p, len(valid) + len(bad)


def main():
    path, task = sys.argv[1], sys.argv[2]
    if task == "A":  # slugify — edge cases: collapse, strip, empty, all-symbol, case, underscore
        fn = load(path, "slugify")
        cases = [("Hello World", "hello-world"), ("  a  b  ", "a-b"), ("a---b", "a-b"),
                 ("", ""), ("!!!", ""), ("--hi--", "hi"), ("UPPER", "upper"),
                 ("a_b c", "a-b-c"), ("   ", ""), ("Hello, World!", "hello-world")]
        p, t = grade_value(fn, cases)
    elif task == "B":  # parse_duration — valid combos + invalid-must-raise
        fn = load(path, "parse_duration")
        valid = [("1h30m", 5400), ("45s", 45), ("2h", 7200), ("90m", 5400), ("1h1m1s", 3661)]
        bad = ["", "abc", "1x", "h30m", "1.5h"]
        p, t = grade_raise(fn, valid, bad)
    elif task == "C":  # is_prime — must preserve edge behavior after "optimization"
        fn = load(path, "is_prime")
        cases = [(0, False), (1, False), (2, True), (3, True), (4, False), (-7, False),
                 (17, True), (1000003, True), (1000000, False), (7919, True)]
        p, t = grade_value(fn, cases)
    else:
        print("0 0"); return
    print(f"{p} {t}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("0 0")
