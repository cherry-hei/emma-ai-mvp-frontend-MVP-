"""Read back the XLSX actually saved by the synthetic browser journey."""
import json
from pathlib import Path
from zipfile import ZipFile

from openpyxl import load_workbook

root = Path(__file__).resolve().parents[2]
output = root / '.codex-temp/browser-evidence'
report = json.loads((output / 'result.json').read_text(encoding='utf-8'))
assert report['status'] == 'passed'
path = output / report['filename']
with ZipFile(path) as archive:
    assert archive.testzip() is None
book = load_workbook(path)
selected = next(o['roster_version_id'] for o in report['job']['result_json']['roster_options'] if o['plan_mode'] == 'C')
assert 'version_id=' + selected in report['exportUrl']
assert selected in book.worksheets[0]['B1'].value
assert f"v{report['savedConfig']['version']} /" in book.worksheets[0]['B3'].value
assert len(book.sheetnames) == 17
assert sum(bool(book[name].cell(row, 4 + day * 3).value)
           for name in book.sheetnames[4:10] for row in range(5, 7) for day in range(7)) == 84
assert book['Hours']['BF5'].value is None
assert book['Hours']['BO5'].value == 44
print('Downloaded ZIP integrity, selected C/config version, 17 sheets, all 84 cells, unknown carry and weekly reference verified')
