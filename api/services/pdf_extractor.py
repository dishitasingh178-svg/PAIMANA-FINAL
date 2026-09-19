"""PDF extraction adapter using the supplied CUF parser logic verbatim.

The parser's extraction rules are intentionally not rewritten here because the
existing PAIMANA database was built from this parser and the supplied May 2014
PDF must produce the same 735 records.
"""

import argparse
import csv
import re
import zipfile
from pathlib import Path

import fitz  # PyMuPDF

COLUMNS = [
    'report_month', 'sector', 'serial_no', 'project_id', 'project_name',
    'implementing_agency', 'state', 'date_of_approval',
    'original_cost_crore', 'revised_cost_crore', 'anticipated_cost_crore',
    'cumulative_expenditure_crore', 'original_commissioning_date',
    'revised_commissioning_date', 'anticipated_commissioning_date',
    'delay_original_months', 'delay_revised_months',
    'milestones_achieved', 'milestones_total', 'source_file', 'source_page'
]

MONTHS = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
    'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
    'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9, 'oct': 10,
    'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
}

ID_RE = re.compile(r'\[([Nn]?\d{8,10})\]')
DATE_RE = re.compile(r'^\d{1,2}/\d{4}$')
MONEY_RE = re.compile(r'^[+-]?(?:\d[\d,]*\.?\d*|\.\d+)$')
DELAY_RE = re.compile(r'^(-?\d+(?:\.\d+)?)\(([OR])\)$', re.I)
MILE_RE = re.compile(r'^(\d+)\s*/\s*(\d+)$')


def clean(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def money(s):
    s = clean(s).replace('₹', '')
    if not s or s in {'-', '--', '—'}:
        return None
    if not MONEY_RE.fullmatch(s):
        return None
    try:
        return float(s.replace(',', ''))
    except ValueError:
        return None


def report_month(filename, text=''):
    name = Path(filename).stem.lower()
    year_m = re.search(r'20\d{2}', name)
    year = int(year_m.group()) if year_m else None
    month = None
    for token in sorted(MONTHS, key=len, reverse=True):
        if re.search(rf'(?<![a-z]){re.escape(token)}(?![a-z])', name):
            month = MONTHS[token]
            break
    # Filename is expected to carry the month. Fall back to report heading.
    if year and month:
        return f'{year:04d}-{month:02d}'
    m = re.search(r'\((January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\)', text, re.I)
    if m:
        return f'{int(m.group(2)):04d}-{MONTHS[m.group(1).lower()]:02d}'
    return ''


def is_target_page(text):
    low = re.sub(r'\s+', ' ', text.lower())
    return ('si.no project' in low and 'date of approval' in low
            and 'cumulative' in low and 'antici' in low
            and ('miles' in low or 'milestones' in low))


def find_section_pages(doc):
    first = None
    for i, page in enumerate(doc):
        text = page.get_text('text')
        if is_target_page(text):
            first = i
            break
    if first is None:
        return []

    # The project table is followed by a summary/annexure. Some reports have
    # intermediate sector-level Grand Total rows, so we must NOT stop at the
    # first Grand Total. Use the first clear section marker after the table.
    end = len(doc) - 1
    markers = ('summary of projects in the flash report', 'annexure')
    for i in range(first + 1, len(doc)):
        text = doc[i].get_text('text').lower()
        if any(m in text for m in markers):
            end = i - 1
            break
    return list(range(first, end + 1))


def sector_candidate(line):
    s = clean(line)
    if not s or len(s) > 90 or any(ch.isdigit() for ch in s):
        return False
    bad = {'project', 'date of approval', 'total', 'grand total', 'flash report', 'ocms', 'mospi', 'annexure'}
    if s.lower() in bad:
        return False
    # Sector labels in these reports are short uppercase text labels.
    # Exclude punctuation-only artifacts and long all-caps project-name lines.
    return bool(re.fullmatch(r'[A-Z &]+', s)) and len(s.split()) <= 6


def parse_block(block, serial, sector, report_month_value, source_file, page_no):
    joined = ' '.join(clean(x) for x in block)
    idm = ID_RE.search(joined)
    if not idm:
        return None

    project_id = idm.group(1)
    prefix = joined[:idm.start()]
    # Remove the serial and tidy the project name.
    prefix = re.sub(r'^\s*\d+\s+', '', prefix)
    project_name = clean(prefix).strip(' -')

    after_id = joined[idm.end():]
    parts = [clean(x) for x in after_id.split(' ') if clean(x)]
    # Agency/state come from the first comma-separated text after the ID.
    after_id_clean = clean(after_id).strip(' ,.-')
    meta_parts = [clean(x) for x in after_id_clean.split(',') if clean(x)]
    agency = meta_parts[0] if meta_parts else ''
    state = meta_parts[1] if len(meta_parts) > 1 else ''

    # Work with individual lines after the ID. The PDF text extraction puts
    # table cells on separate lines, which makes this considerably more stable
    # than relying on visual column spacing.
    id_line_idx = next(i for i, x in enumerate(block) if ID_RE.search(str(x)))
    tail = [clean(x) for x in block[id_line_idx + 1:] if clean(x)]
    if not tail:
        return None

    # Find approval date first. Then tokenize the remaining table cells.
    # Some older PDFs place two adjacent cells on one visual line, so parsing
    # whole lines is not reliable. Tokenizing dates, money, delays and the
    # milestone fraction handles both old and new layouts.
    id_line_idx = next(i for i, x in enumerate(block) if ID_RE.search(str(x)))
    tail_text = ' '.join(clean(x) for x in block[id_line_idx + 1:] if clean(x))
    aidx = re.search(r'\b\d{1,2}/\d{4}\b', tail_text)
    if not aidx:
        return None
    tail_text = tail_text[aidx.start():]
    token_re = re.compile(r'\d+\s*/\s*\d+|\d{1,2}/\d{4}|-?\d[\d,]*(?:\.\d+)?(?:\([OR]\))?|-')
    vals = token_re.findall(tail_text)
    if len(vals) < 8:
        return None

    approval = vals[0]
    idx = 1
    if idx >= len(vals): return None
    original_cost = money(vals[idx]); idx += 1
    if idx >= len(vals): return None
    revised_cost = money(vals[idx]); idx += 1
    if idx >= len(vals): return None
    anticipated_cost = money(vals[idx]); idx += 1
    if idx >= len(vals): return None
    expenditure = money(vals[idx]); idx += 1
    if original_cost is None or anticipated_cost is None:
        return None

    # Commissioning: original, revised, anticipated.
    comm = []
    for _ in range(3):
        if idx < len(vals) and (DATE_RE.fullmatch(vals[idx]) or vals[idx] == '-'):
            comm.append(None if vals[idx] == '-' else vals[idx])
            idx += 1
        else:
            break
    if len(comm) < 3:
        return None
    original_comm, revised_comm, anticipated_comm = comm

    delay_original = None
    delay_revised = None
    while idx < len(vals):
        m = DELAY_RE.fullmatch(vals[idx])
        if m:
            if m.group(2).upper() == 'O': delay_original = float(m.group(1))
            else: delay_revised = float(m.group(1))
            idx += 1
            continue
        mm = MILE_RE.fullmatch(vals[idx])
        if mm:
            return {
                'report_month': report_month_value,
                'sector': sector,
                'serial_no': int(serial),
                'project_id': project_id,
                'project_name': project_name,
                'implementing_agency': agency,
                'state': state,
                'date_of_approval': approval,
                'original_cost_crore': original_cost,
                'revised_cost_crore': revised_cost,
                'anticipated_cost_crore': anticipated_cost,
                'cumulative_expenditure_crore': expenditure,
                'original_commissioning_date': original_comm,
                'revised_commissioning_date': revised_comm,
                'anticipated_commissioning_date': anticipated_comm,
                'delay_original_months': delay_original,
                'delay_revised_months': delay_revised,
                'milestones_achieved': int(mm.group(1)),
                'milestones_total': int(mm.group(2)),
                'source_file': Path(source_file).name,
                'source_page': page_no,
            }
        idx += 1
    return None


def extract_pdf(pdf_path):
    pdf_path = Path(pdf_path)
    doc = fitz.open(pdf_path)
    pages = find_section_pages(doc)
    if not pages:
        doc.close()
        return [], [], ['Target project-detail section was not found']

    month = report_month(pdf_path.name, doc[pages[0]].get_text('text'))
    rows, errors = [], []
    current_sector = ''

    for pi in pages:
        lines = [x.strip() for x in doc[pi].get_text('text').splitlines()]
        i = 0
        while i < len(lines):
            line = clean(lines[i])
            if sector_candidate(line):
                current_sector = line
                i += 1
                continue
            # Project rows occur in two layouts:
            #   123  PROJECT NAME ...
            # or
            #   123
            #   PROJECT NAME ...
            # Accept both, but require a project ID nearby so header numbers
            # such as 1..10 are ignored.
            same_line_match = re.match(r'^(\d+)\s+(.+)$', line)
            standalone = re.fullmatch(r'\d+', line)
            if same_line_match or standalone:
                serial = int(same_line_match.group(1)) if same_line_match else int(line)
                first_piece = same_line_match.group(2) if same_line_match else None
                look_start = i if first_piece else i + 1
                look = ' '.join(clean(x) for x in lines[look_start:look_start+21])
                if not ID_RE.search(look):
                    i += 1
                    continue
                j = i + 1
                block = [first_piece] if first_piece else []
                while j < len(lines):
                    nxt = clean(lines[j])
                    if nxt.lower() in {'total', 'grand total'}:
                        break
                    # Newer/older report pages sometimes put the serial number
                    # and project name on the SAME line. Detect that as a new row too.
                    same_line = re.match(r'^(\d+)\s+(.+)$', nxt)
                    if same_line and not re.fullmatch(r'\d+', nxt) and ID_RE.search(' '.join(block)):
                        look_lines = [nxt] + [clean(x) for x in lines[j+1:j+21] if clean(x)]
                        if ID_RE.search(' '.join(look_lines)):
                            break
                    if re.fullmatch(r'\d+', nxt):
                        # A standalone 0 is often the revised-delay placeholder,
                        # so do not mistake it for the next project number.
                        look_lines = [clean(x) for x in lines[j+1:j+21] if clean(x)]
                        next_text = look_lines[0] if look_lines else ''
                        looks_like_project = bool(next_text) and not (
                            DATE_RE.fullmatch(next_text) or
                            MONEY_RE.fullmatch(next_text) or
                            MILE_RE.fullmatch(next_text) or
                            DELAY_RE.fullmatch(next_text) or
                            next_text == '-'
                        )
                        if looks_like_project and ID_RE.search(' '.join(look_lines)):
                            break
                    block.append(lines[j])
                    j += 1
                if ID_RE.search(' '.join(block)):
                    rec = parse_block(block, serial, current_sector, month, pdf_path, pi + 1)
                    if rec:
                        rows.append(rec)
                    else:
                        errors.append(f'page {pi+1}, serial {serial}: parse failed')
                    i = j
                    continue
            i += 1

    doc.close()
    return rows, pages, errors

