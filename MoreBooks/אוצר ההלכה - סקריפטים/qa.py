"""Cross-check every volume: numbering runs, footnotes, links, file shape."""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from structure import parse, entries, gematria
from notes import notes_of
from render import band_style, classify, render_entry

OUT = sys.argv[1] if len(sys.argv) > 1 else '/Users/david/otzar-out2'
VOLS = 'אגדהו'
NOTES_PREFIX = 'הערות על '


def seq_report(nums):
    breaks = [(nums[i - 1], nums[i]) for i in range(1, len(nums))
              if nums[i] != nums[i - 1] + 1]
    return breaks


def check_volume(vol):
    src = '/Users/david/Downloads/אוצר ההלכה שבת %s.pdf' % vol
    doc, pages, unres = parse(src)
    body_font, body_size = band_style(pages)
    notes, by_page, order = notes_of(pages)
    ents = entries(pages)

    per_siman = collections.OrderedDict()
    for e in ents:
        key = e['siman'] + ('/' + e['section'] if e['section'] else '')
        per_siman.setdefault(key, []).append(e['n'])
    ent_breaks = {s: seq_report(v) for s, v in per_siman.items()}
    note_breaks = {s: seq_report(v) for s, v in order.items()}

    counts = collections.Counter()
    called = set()
    for e in ents:
        render_entry(e, notes, by_page, body_font, body_size, counts, called)
    defined = {(s, n) for s in notes for n in notes[s]}
    orphan_calls = counts['orphan_call']
    never_called = sorted(k for k in defined if k not in called)

    print('\n=== כרך %s  (%d עמודים)' % (vol, doc.page_count))
    print('  simanim              : %s' % ' '.join(per_siman))
    print('  sub-list markers ignored: %d   misprinted numbers fixed: %d'
          % (len(getattr(entries, 'rejected', [])),
             len(getattr(entries, 'misprint', []))))
    print('  entries              : %d   sequence breaks: %d'
          % (len(ents), sum(len(v) for v in ent_breaks.values())))
    for s, b in ent_breaks.items():
        if b:
            print('      %s -> %s' % (s, b[:5]))
    print('  notes                : %d   sequence breaks: %d'
          % (sum(len(v) for v in notes.values()),
             sum(len(v) for v in note_breaks.values())))
    for s, b in note_breaks.items():
        if b:
            print('      %s -> %s' % (s, b[:5]))
    print('  footnote calls       : %d   orphaned: %d   never called: %d'
          % (counts['calls'], orphan_calls, len(never_called)))
    if never_called[:5]:
        print('      never called: %s' % never_called[:5])
    print('  undecoded characters : %d  %s'
          % (sum(unres.values()), unres.most_common(4)))
    return doc.page_count


def check_files():
    print('\n=== קבצי הפלט')
    sa = {}
    for f in sorted(os.listdir(OUT)):
        if not f.endswith('.txt'):
            continue
        title = os.path.splitext(f)[0]
        # the notes volume has no sidecar of its own: its records live in the
        # base volume's file, keyed by "Conection Type"
        companion = title.startswith(NOTES_PREFIX)
        raw = open(os.path.join(OUT, f), 'rb').read()
        text = raw.decode('utf-8')
        lines = text.split('\n')[:-1]
        bom = raw[:3] == b'\xef\xbb\xbf'
        crlf = b'\r\n' in raw
        md = [i for i, l in enumerate(lines, 1) if re.match(r'^#{1,6}\s', l)]
        h1 = lines[0]
        levels = [int(m.group(1)) for l in lines
                  for m in [re.match(r'^<h([1-6])>', l)] if m]
        jumps = [(levels[i - 1], levels[i]) for i in range(1, len(levels))
                 if levels[i] > levels[i - 1] + 1]
        unbal = [i for i, l in enumerate(lines, 1)
                 if l.count('<b>') != l.count('</b>')
                 or l.count('<i class="footnote">') != l.count('</i>')
                 or l.count('<sup class="footnote-marker">') != l.count('</sup>')]
        links = [] if companion else json.load(
            open(os.path.join(OUT, title + '_links.json'), encoding='utf-8'))
        src = [k for k in links if k['Conection Type'] == 'source']
        foot = [k for k in links if k['Conection Type'] == 'footnotes']
        bad_ref = [k for k in src
                   if not re.fullmatch(r'Shulchan Arukh, Orach Chayim \d+:\d+',
                                       k.get('ref_2', ''))]
        # a local target must NOT carry ref_2 -- the weekly sync rejects it
        stray_ref = [k for k in foot if 'ref_2' in k]
        on_heading = [k for k in links
                      if lines[k['line_index_1'] - 1].startswith('<h')]
        oob = [k for k in links if not 1 <= k['line_index_1'] <= len(lines)]
        wrong_key = [k for k in links if 'Connection Type' in k]
        print('  %s' % title)
        print('     lines=%-5d source=%-5d footnotes=%-5d BOM=%s CRLF=%s '
              'markdown-headings=%d'
              % (len(lines), len(src), len(foot), bom, crlf, len(md)))
        print('     h1=%r  heading-level jumps=%d  unbalanced tags=%d'
              % (h1[:40], len(jumps), len(unbal)))
        print('     bad ref_2=%d  ref_2 on local target=%d  link on heading=%d'
              '  line out of range=%d  misspelled key=%d'
              % (len(bad_ref), len(stray_ref), len(on_heading), len(oob),
                 len(wrong_key)))
        if not companion:
            sa[title] = src
    return sa


def check_sa(sa):
    from build_all import SA_PATH, SA_TITLE
    salines = open(SA_PATH, encoding='utf-8').read().split('\n')
    print('\n=== אימות יעדי הקישור בשו"ע')
    bad = 0
    checked = 0
    for title, links in sa.items():
        for k in links:
            n = k['line_index_2']
            if not 1 <= n <= len(salines):
                bad += 1
                continue
            if not salines[n - 1].startswith('('):
                bad += 1
            checked += 1
    print('  link targets checked: %d   not a se\'if line: %d' % (checked, bad))
    seen = set()
    for title, links in sa.items():
        for k in links:
            seen.add(k['ref_2'])
    print('  distinct Shulchan Aruch se\'ifim covered: %d' % len(seen))


if __name__ == '__main__':
    total = 0
    for v in VOLS:
        total += check_volume(v)
    print('\npages processed: %d' % total)
    sa = check_files()
    check_sa(sa)
    import merge_contract
    print('\n=== חוזה המיזוג של ספרי ההערות')
    merge_contract.main()
