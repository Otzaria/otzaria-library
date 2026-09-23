# Build structure_plan.json for שו"ת משנה הלכות א-יז.
# Inputs: /Users/david/Downloads/משנה הלכות/*.txt (read only), scratchpad/pdf/txt/mhN.jsonl + heads.json,
#         scratchpad/site/raw/17/*.html, scratchpad/reports/longlong_breaks.json
# Helpers: lib.py (loaders), part_map.py (siman map / splits / subject lines), part_join.py (paragraph joins)
# Nothing here prints book text.
import sys, json, re, collections, difflib
sys.path.insert(0, '/private/tmp/claude-501/-Users-david-Documents-otzaria-books-otzaria-library/4c8380de-bafb-4867-b3cc-dae974308691/scratchpad/build')
from lib import *
from part_map import build, where, LOST, MISSING, NONEXIST
from part_join import classify, br_candidates

OUT = f'{S}/build/structure_plan.json'
LONGLONG = json.load(open(f'{S}/reports/longlong_breaks.json'))

SPACED = {'שאלותותשובות': 'שאלות ותשובות', 'משנההלכות': 'משנה הלכות', 'אורחחיים': 'אורח חיים',
          'יורהדעה': 'יורה דעה', 'אבןהעזר': 'אבן העזר', 'חושןמשפט': 'חושן משפט',
          'קונטרסשביליאמונה': 'קונטרס שבילי אמונה', 'עניניקדשים': 'עניני קדשים', 'מקדשוקדשיו': 'מקדש וקדשיו'}
TITLE = {'אורחחיים': 'חלק אורח חיים', 'יורהדעה': 'חלק יורה דעה', 'אבןהעזר': 'חלק אבן העזר',
         'חושןמשפט': 'חלק חושן משפט', 'קונטרסשביליאמונה': 'קונטרס שבילי אמונה',
         'עניניקדשים': 'עניני קדשים', 'מקדשוקדשיו': 'מקדש וקדשיו'}
ORD = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'ששי', 'שביעי', 'שמיני', 'תשיעי', 'עשירי', 'אחדעשר',
       'שניםעשר', 'שלשהעשר', 'ארבעהעשר', 'חמשהעשר', 'ששהעשר', 'שבעהעשר']
def spaced_chelek(t):
    t = t.replace(' ', '')
    if not t.startswith('חלק'): return t
    rest = t[3:]
    rest = re.sub(r'^(אחד|שנים|שלשה|ארבעה|חמשה|ששה|שבעה)עשר$', r'\1 עשר', rest)
    return 'חלק ' + rest
SINGLE = {8, 11, 15, 16}

# ---------------- sections (from the printed inner title pages) ----------------
def sections_for(vi, L, P):
    hdry = collections.defaultdict(set)
    for x in L:
        if x['size'] == 22.8: hdry[x['p']].add(x['y'])
    out = []
    for p in P:
        k = p['k']
        for j in range(k - 1, max(k - 4, -1), -1):
            x = L[j]; t = x['t'].replace(' ', '')
            if (x['font'] == 'DWVilna,Bold' and x['size'] in (15.8, 17.8) and not t.startswith('סימן')
                    and 'שאלותותשובות' not in t and not any(abs(x['y'] - y) < 12 for y in hdry[x['p']])
                    and len(t) < 25 and not t.startswith('חלק')):
                if t not in TITLE: break
                chelek = [y['t'] for y in L[max(0, j-4):j] if y['p'] == x['p'] and y['size'] == 14.9 and y['t'].replace(' ', '').startswith('חלק')]
                pt = (spaced_chelek(chelek[-1]) + ' - ' if chelek else '') + SPACED[t]
                out.append({'before_printed': p['n'], 'title': TITLE[t], 'printed_text': pt[:40], 'pdf_page': x['p']})
                break
    return out

# ---------------- title-page remnant lines in the file ----------------
TOK = [norm(x) for x in ['שאלות ותשובות', 'משנה הלכות', 'מדור התשובות ח"ט', 'חושן המשפט'] + list(SPACED.values())] + \
      [norm('חלק' + o) for o in ORD] + ['חלק']
def is_title_remnant(t):
    if not t: return False
    s = t
    while s:
        for k in sorted(TOK, key=len, reverse=True):
            if s.startswith(k):
                s = s[len(k):]; break
        else:
            return False
    return True

def main():
    plan = {'_meta': {
        'generated_by': 'build/make_plan.py', 'line_numbers': '1-based, as in the Downloads files split with splitlines()',
        'files': D, 'semantics': {
            'siman_map': 'every existing <h2> in file order; printed = number in the printed volume',
            'splits': 'insert a new siman heading (printed) immediately BEFORE file_line',
            'sections': 'insert a section heading before the siman whose printed number is before_printed',
            'delete_lines': 'delete these original lines',
            'line_edits': 'strip the given literal prefix from the line',
            'joins': 'join line L with L+1 (single space); decided from the printed layout',
            'joins_extra': 'NOT in the requested candidate lists; found by a full scan of every adjacent line pair, same criteria. Optional.',
            'subject_line': 'line = the file line that equals the printed topic line; lines = topic spread over several lines; partial = line holds topic + more text (do not use)'}}}
    summary = {}
    for vi in range(1, 18):
        v = VOLS[vi-1]
        r = build(vi); lines = r['lines']; h2 = r['h2']; P = r['P']
        L = [json.loads(x) for x in open(f'{S}/pdf/txt/mh{vi}.jsonl')]
        pn = {p['n']: p for p in P}
        h2lines = {h['line'] for h in h2}
        vol = {'file': f'משנה הלכות חלק {v}.txt'}
        # --- siman map ---
        sm = r['siman_map']
        if vi == 17:
            for e in sm:
                if e['printed'] == 117:
                    e['note'] = 'בדפוס אין כותרת קיז: הטקסט נמצא בתוך סימן קטז המודפס. נשמר כסימן נפרד לפי ההנחיה'
        vol['siman_map'] = sm
        vol['printed_missing_in_file'] = MISSING.get(vi, [])
        if NONEXIST.get(vi): vol['printed_numbers_skipped_by_print'] = NONEXIST[vi]
        vol['splits'] = r['splits']
        ov = r['overlap']
        mn = min(ov, key=lambda o: o['overlap'])
        inv = collections.defaultdict(set)
        for p_ in P:
            for g in grams(stream(p_['lines'])[0]): inv[g].add(p_['n'])
        disagree = []
        for a, b, n in r['segs']:
            c = collections.Counter()
            for g in grams(norm(''.join(lines[a-1:b]))):
                for q in inv.get(g, ()): c[q] += 1
            best = c.most_common(1)[0][0] if c else None
            exp = 116 if (vi == 17 and n == 117) else n
            if best != exp: disagree.append({'printed': n, 'best_match': best})
        vol['overlap'] = {'best_match_disagreements': disagree, 'metric': 'share of the file segment 8-letter n-grams found in the mapped printed siman',
                          'min': mn['overlap'], 'min_printed': mn['printed'],
                          'below_0.8': [{'printed': o['printed'], 'overlap': o['overlap']} for o in ov if o['overlap'] < 0.8],
                          'mean': round(sum(o['overlap'] for o in ov) / len(ov), 3)}
        # --- sections ---
        secs = sections_for(vi, L, P)
        if vi in SINGLE:
            vol['single_section'] = secs[0] if secs else None
            vol['sections'] = []
        else:
            vol['sections'] = secs
        # --- delete lines ---
        dels = {}
        def add_del(ln, reason):
            dels.setdefault(ln, reason)
        if vi == 17:
            for h in h2:
                for k in range(h['line'] + 1, min(h['end'], h['line'] + 3) + 1):
                    l = lines[k-1]
                    m = re.fullmatch(r'סימ[ןו] ([א-ת]+)', l)
                    if m:
                        if gval(m.group(1)) == h['val']:
                            add_del(k, f'שורת "סימן" כפולה ל-h2 ({h["label"]})' + (' — עם שגיאת כתיב' if not l.startswith('סימן') else ''))
                        break
        for e in r['extra_del']:
            add_del(e['line'], e['reason'])
        if vi == 12:
            for i, l in enumerate(lines, 1):
                if l.startswith('סימן תג **'):
                    add_del(i, 'הערת האתר על סימן תג החסר (אינה חלק מהספר; בדפוס קיים סימן תג)')
        section_starts = {s['before_printed'] for s in (secs if vi not in SINGLE else [])}
        seg_of = {}
        for a, b, n in r['segs']:
            for ln in range(a, b + 1): seg_of[ln] = n
        for i, l in enumerate(lines, 1):
            if i <= 2 or i in h2lines: continue
            t = norm(l)
            if len(t) > 60 or not is_title_remnant(t): continue
            # must sit in a block right before an h2, or right after one
            k = i
            while k + 1 <= len(lines) and k + 1 not in h2lines and is_title_remnant(norm(lines[k])): k += 1
            before = (k + 1) in h2lines
            after = (i - 1) in h2lines or ((i - 2) in h2lines and is_title_remnant(norm(lines[i-2])))
            if not (before or after): continue
            nxt = [h for h in h2 if h['line'] > i][0] if before else [h for h in h2 if h['line'] < i][-1]
            nprinted = [e['printed'] for e in sm if e['file_line'] == nxt['line']][0]
            ok = nprinted in section_starts
            add_del(i, 'שם מדור/שער פנימי שנתקע ' + (f'בסוף הסימן שלפני סימן {nprinted} בדפוס' if before else f'בתחילת סימן {nprinted} בדפוס') +
                    (' (תחילת מדור בדפוס)' if ok else ' (לא תחילת מדור לפי הדפוס!)'))
        vol['delete_lines'] = [{'line': k, 'reason': dels[k]} for k in sorted(dels)]
        # --- line edits ---
        edits = []
        if vi == 17:
            for i, l in enumerate(lines, 1):
                m = re.match(r'(סימן ([א-ת]+)<\?+>)', l)
                if m and (i - 1) in h2lines and gval(m.group(2)) == [h for h in h2 if h['line'] == i-1][0]['val']:
                    edits.append({'line': i, 'action': 'strip_prefix', 'prefix': m.group(1),
                                  'reason': 'שורת "סימן" כפולה שנדבקה לשורת הנושא עם תווים שאבדו; השארית זהה לנושא בדפוס'})
        vol['line_edits'] = edits
        deleted = set(dels)
        # --- joins ---
        cands = [(l, 'longlong_breaks') for l in LONGLONG[v]]
        brstats = None
        if vi == 17:
            br, brstats = br_candidates(lines, h2)
            cands += [(l, 'site_br') for l in br]
        segd = {}
        for a, b, n in r['segs']:
            for ln in range(a, b + 1): segd[ln] = (a, b, n)
        stream_cache = {}
        def st_for(n):
            n2 = 116 if (vi == 17 and n == 117) else n
            if n2 not in stream_cache:
                sl = pn[n2]['lines']; st, own = stream(sl); stream_cache[n2] = (sl, st, own)
            return stream_cache[n2]
        joins, keep, und, moot = [], [], [], []
        seen = set()
        for Lnum, src in cands:
            if (Lnum, src) in seen: continue
            seen.add((Lnum, src))
            a, b, n = segd.get(Lnum, (0, 0, None))
            if n is None or Lnum + 1 > b:
                keep.append({'line': Lnum, 'source': src, 'why': 'crosses_siman_boundary'}); continue
            if Lnum in deleted or (Lnum + 1) in deleted:
                moot.append({'line': Lnum, 'source': src, 'why': 'one_of_the_lines_is_deleted'}); continue
            sl, st, own = st_for(n)
            d, why, info = classify(vi, lines, Lnum, sl, st, own)
            e = {'line': Lnum, 'source': src, 'why': why}
            if info: e['pdf_page'] = info['X'][0]
            (joins if d == 'join' else keep if d == 'keep' else und).append(e)
        # full scan for other broken paragraphs (reported separately)
        cand_lines = {c[0] for c in cands}
        extra = []
        scan = collections.Counter()
        for a, b, n in r['segs']:
            sl, st, own = st_for(n)
            for Lnum in range(a, b):
                if Lnum in cand_lines or Lnum in deleted or (Lnum + 1) in deleted: continue
                d, why, info = classify(vi, lines, Lnum, sl, st, own)
                scan[d] += 1
                if d == 'join':
                    A = lines[Lnum-1].rstrip()
                    kind = ('greeting_line' if len(A) < 40 and A.endswith(',') else
                            'after_sentence_end' if A[-1:] in '.:?!' else 'mid_sentence')
                    extra.append({'line': Lnum, 'why': why, 'pdf_page': info['X'][0], 'kind': kind})
        vol['joins'] = sorted(joins, key=lambda e: e['line'])
        vol['joins_extra'] = extra
        vol['joins_not_applied'] = {'keep': keep, 'undecided': und, 'moot': moot}
        # --- subject lines ---
        jset = {e['line'] for e in joins}
        subj = []
        edit_lines = {e['line'] for e in edits}
        for s in r['subject_line']:
            s = dict(s)
            if s.get('match') == 'multi_line' and all(l in jset for l in s['lines'][:-1]):
                s = {'printed': s['printed'], 'line': s['lines'][0], 'match': 'multi_line_joined', 'lines_before_join': s['lines']}
            if s.get('match') == 'fuzzy':
                t = norm(lines[s['line']-1]); top = norm(''.join(x['t'] for x in pn[s['printed']]['topic']))
                ops = [o for o in difflib.SequenceMatcher(None, top, t).get_opcodes() if o[0] != 'equal']
                if len(ops) == 1 and ops[0][0] == 'insert' and ops[0][1] == 0:
                    s['extra_prefix_letters'] = ops[0][4] - ops[0][3]
                    s['note'] = 'בקובץ יש לפני הנושא תוספת קצרה (בדפוס שורה נפרדת שאינה מודגשת)'
            if s.get('line') in edit_lines:
                ed = [e for e in edits if e['line'] == s['line']][0]
                top = norm(''.join(x['t'] for x in pn[s['printed']]['topic']))
                if norm(lines[s['line']-1][len(ed['prefix']):]) == top:
                    s = {'printed': s['printed'], 'line': s['line'], 'match': 'exact_after_line_edit'}
            subj.append(s)
        vol['subject_line'] = subj
        plan[v] = vol
        # --- summary ---
        sc = collections.Counter()
        for s in subj:
            sc['partial' if s.get('partial') else (s.get('match') or s.get('reason'))] += 1
        summary[v] = {'h2': len(h2), 'printed': len(P), 'splits': [s['printed'] for s in r['splits']],
                      'overlap_min': vol['overlap']['min'], 'overlap_min_printed': vol['overlap']['min_printed'],
                      'overlap_below_0.8': vol['overlap']['below_0.8'],
                      'sections': [(s['before_printed'], s['title']) for s in vol['sections']],
                      'single_section': vol.get('single_section', {}) and vol['single_section']['title'],
                      'delete': len(vol['delete_lines']), 'edits': len(edits),
                      'cands': len(cands), 'join': len(joins), 'keep': len(keep), 'undecided': len(und), 'moot': len(moot),
                      'join_reasons': dict(collections.Counter(e['why'] for e in joins)),
                      'keep_reasons': dict(collections.Counter(e['why'] for e in keep)),
                      'undecided_lines': [e['line'] for e in und],
                      'extra_joins': len(extra), 'extra_kinds': dict(collections.Counter(e['kind'] for e in extra)), 'disagree': vol['overlap']['best_match_disagreements'], 'extra_reasons': dict(collections.Counter(e['why'] for e in extra)),
                      'scan': dict(scan), 'subject': dict(sc), 'br': dict(brstats) if brstats else None}
        print(v, json.dumps(summary[v], ensure_ascii=False))
    json.dump(plan, open(OUT, 'w'), ensure_ascii=False, indent=1)
    json.dump(summary, open(f'{S}/build/summary.json', 'w'), ensure_ascii=False, indent=1)

if __name__ == '__main__':
    main()
