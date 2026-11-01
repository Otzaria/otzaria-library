"""Apply te_convert.marks() to the Torat Emet books already in the library.

te_convert now writes every book without the faults its sources share (see marks() there):
quotation marks typed as two apostrophes, a space before punctuation, a bold word cut by its own
gershayim, bold on a punctuation mark alone, and bold runs split by a space. The books in the
library were converted before that and fixed by hand since, so this script does not convert them
again: it runs the same line tidy te_reapply.py ends with (te_reapply.tidy = marks + empty tags,
spaces outside tags, one space) on every line of every packaged Torat Emet book, the books that
were not converted by te_convert (ריבבן על שקלים, הערות על וביום השבת) included.

--check prints what would change per book, and fails when a change would touch anything but
punctuation, quotation marks, spaces and tags (the letters and digits of every line must stay),
nest a tag in itself, or not be stable (a second run must change nothing). --write writes the
books that pass.

Usage (from the repo root):
    python ToratEmetToOtzaria/סקריפטים/te_tidy.py --check
    python ToratEmetToOtzaria/סקריפטים/te_tidy.py --write [--only חברותא]
"""
import argparse
import collections
import os
import re
import sys

import te_reapply as RA

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, '..', 'ספרים', 'אוצריא')
COUNTED = {
    "''": re.compile(r"''"),
    'space before punctuation': re.compile(r'(?<=[א-ת֑-ׇ"\')\]]) +(?:[,;:]|\.(?!\.))(?:\s|"|<|$)'),
    'bold cut by gershayim': re.compile(r'[א-ת]</b>(?:["\']|\'\')<b>[א-ת]'),
    'lone bold mark': re.compile(r'<b>(?:["\'״;,.:]|\'\')</b>'),
    '</b> <b>': re.compile(r'</b> <b>'),
}


def tidy(line):
    if not line.strip():
        return line
    return RA.tidy(line)


def nested(line):
    return any(re.search(r'<%s>(?:(?!</%s>).)*<%s>' % (t, t, t), line) for t in ('b', 'i', 'u'))


def books(only):
    for dp, _, fn in os.walk(LIB):
        for f in sorted(fn):
            if f.endswith('.txt') and (not only or only in os.path.join(dp, f)):
                yield os.path.join(dp, f)


def run(write, only):
    bad, total = False, collections.Counter()
    for path in books(only):
        lines = open(path, encoding='utf-8').read().split('\n')
        new, stats, problems = [], collections.Counter(), []
        for n, line in enumerate(lines):
            out = tidy(line)
            if out != line:
                stats['lines'] += 1
                for k, rx in COUNTED.items():
                    stats[k] += len(rx.findall(line))
                if RA.key(out) != RA.key(line):
                    problems.append(f'line {n + 1}: letters would change')
                if nested(out) and not nested(line):
                    problems.append(f'line {n + 1}: a tag nested in itself')
                if tidy(out) != out:
                    problems.append(f'line {n + 1}: a second run would change it again')
            new.append(out)
        if not stats and not problems:
            continue
        name = os.path.relpath(path, LIB)
        print(f'{name}: ' + ', '.join(f'{k} {v}' for k, v in stats.items()))
        total.update(stats)
        for p in problems[:10]:
            print('   FAIL', p)
        if problems:
            bad = True
        elif write:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(new))
    print('total: ' + ', '.join(f'{k} {v}' for k, v in total.items()))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--check', action='store_true')
    g.add_argument('--write', action='store_true')
    ap.add_argument('--only', help='a part of the book path')
    a = ap.parse_args()
    sys.exit(run(a.write, a.only))


if __name__ == '__main__':
    main()
