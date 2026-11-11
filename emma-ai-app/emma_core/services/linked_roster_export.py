"""Formula-linked 17-sheet export from one authenticated roster snapshot.

The analysis profile supplies code semantics, never a server-global customer
workbook. Missing assignments and carry are visibly incomplete, not zero.
"""
from collections import defaultdict
from datetime import timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as col
from openpyxl.workbook.properties import CalcProperties

from ._common import as_date
from .roster_analysis import SHEETS, parse

WEEKS = SHEETS[4:10]


def text(cell, value):
    cell.value = str(value or "")
    cell.data_type = "s"  # preserve literal '=' explanations and prevent formula injection


def render(context, snapshot):
    profile = parse(snapshot["profile"])
    start = as_date(context["period"]["period_start"])
    end = as_date(context["period"]["period_end"])
    if (end-start).days != 41 or start.weekday() != 0:
        raise ValueError("linked export needs 42 days beginning on Monday")
    codes = {c.code: c for c in profile.codes}
    roles = {r.rank: r for r in profile.roles}
    shifts = {s["id"]: s for s in context["shifts"]}
    people = {s["id"]: s for s in context["staff"]}
    cells = {}
    labels = defaultdict(list)
    for task in context["tasks"]:
        if task.get("task_label") and not task.get("suspended_by_leave"):
            labels[task["shift_assignment_id"]].append(task["task_label"])
    for a in context["assignments"]:
        shift = shifts.get(a["shift_id"])
        if not shift or a["staff_id"] not in people:
            raise ValueError("assignment has no scoped shift or staff record")
        day = (as_date(shift["date"])-start).days
        code = codes.get(shift["shift_type"])
        if not 0 <= day < 42 or not code or not code.active:
            raise ValueError("assignment date/code is outside the frozen analysis profile")
        if shift.get("paid_minutes") is not None and shift["paid_minutes"] != code.credit_minutes:
            raise ValueError("assigned credit differs from the frozen analysis dictionary")
        key = (a["staff_id"], day)
        if key in cells:
            raise ValueError("multiple assignments occupy the same staff/day cell")
        cells[key] = (code.code, " / ".join(dict.fromkeys([*(a.get("tasks") or []), *labels[a["id"]]])))
    staff = sorted((s for s in people.values() if s.get("status", "active") == "active" or any(k[0] == s["id"] for k in cells)), key=lambda s: (str(s["rank"]), s["id"]))
    if not staff or len(staff) > 200:
        raise ValueError("linked export supports 1–200 staff rows")
    if any(s["rank"] not in roles for s in staff):
        raise ValueError("staff rank is missing from the frozen analysis profile")
    book = Workbook()
    book.remove(book.active)
    for name in SHEETS:
        sheet = book.create_sheet(name)
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = "C5"
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.column_dimensions["A"].width = 20
        sheet.column_dimensions["B"].width = 24
        sheet.print_title_rows = "1:4"
    guide = book[SHEETS[0]]
    notes = [
        ("版本", f"{context['version']['id']} / {context['version']['status']}"),
        ("更期", f"{start} → {end}"),
        ("分析設定", f"{profile.label} / v{snapshot['version']} / {snapshot['digest']}"),
        ("來源", " | ".join(profile.evidence)),
        ("狀態", "草稿：結轉、PH配對、全部工作任務及人手要求仍須覆核。"),
        ("連動", "更改六張週表的更碼會重算Hours、PH & Off、DO、A/P、C及N；更碼以現行字典查表。"),
        ("空白", "未編齊與未知結轉保留待資料；不當成零。修改後須回系統重新驗證。"),
        ("O / NO", "休班碼不等於已確認普通DO或法定休息日；NO可能仍有前夜更尾段。"),
        ("DO更次數", "Duty Officer當值次數；不是假期日數。"),
        ("工時", "按週列出基準及差額；含AL credit。PH只扣參考工時一次。未認證OT或結轉。"),
    ]
    for r, (label, value) in enumerate(notes, 1):
        text(guide.cell(r, 1), label); text(guide.cell(r, 2), value)
    guide.column_dimensions["B"].width = 110
    for name, note in [(SHEETS[1], "歷史字典沒有隨此分析設定提供；所有新統計查現行字典。"), (SHEETS[3], "覆診地點依個別任務提供；本次未另帶地點參照表。"), (SHEETS[16], "用膳時間已含於更碼工時；個別用膳及替位尚未自動分配。")]:
        text(book[name]["A1"], name); text(book[name]["A3"], note)
        book[name].column_dimensions["A"].width = 100
    dictionary = book[SHEETS[2]]
    headers = ["更碼", "計入工時h", "A", "P", "C", "PH", "N", "DO當值", "AL折日", "工作更", "有效", "Remarks", "來源"]
    dictionary.append(headers)
    for c in profile.codes:
        row = [c.code, c.credit_minutes/60, c.am, c.pm, c.sleepover, c.ph, c.night, c.duty_officer, c.al, int(c.is_working), int(c.active), c.remarks, c.source]
        dictionary.append(row)
        for idx in [1,12,13]:
            text(dictionary.cell(dictionary.max_row, idx), row[idx-1])
        dictionary.cell(dictionary.max_row, 1).fill = PatternFill("solid", fgColor="FFC000" if c.active else "D9C2F0")
    dictionary.column_dimensions["L"].width = 55
    dictionary.column_dimensions["M"].width = 35
    dend = len(profile.codes)+1
    lookup = f"'代號及時數'!$A$2:$M${dend}"
    def ref(row, day):
        return f"'{WEEKS[day//7]}'!{col(4+3*(day%7))}{row}"
    def formula(row, day, field):
        cell = ref(row, day)
        return f'=IF({cell}="","",VLOOKUP({cell},{lookup},{field},FALSE))'
    def officer_formula(row, day):
        if profile.duty_officer_task_code is None:
            return formula(row, day, 8)
        cell=ref(row,day)
        task=f"'{WEEKS[day//7]}'!{col(5+3*(day%7))}{row}"
        marker=profile.duty_officer_task_code.replace('"','""')
        return f'=IF({cell}="","",MAX(VLOOKUP({cell},{lookup},8,FALSE),IF(ISNUMBER(FIND("|{marker}|","|"&SUBSTITUTE({task}," / ","|")&"|")),1,0)))'
    def complete_sum(sheet, row, first, last):
        area = f"{col(first)}{row}:{col(last)}{row}"
        return f'=IF(COUNT({area})={last-first+1},SUM({area}),"未編齊")'
    for w, name in enumerate(WEEKS):
        sheet = book[name]
        text(sheet["A1"], f"{context['facility']['name']} — {name} — 草稿")
        text(sheet["A2"], "用膳／更碼／工作；未填task不代表沒有任務。修改更碼後須重新驗證。")
        sheet["A4"] = "職位"; sheet["B4"] = "員工"
        for d in range(7):
            first = 3+3*d
            sheet.merge_cells(start_row=3, start_column=first, end_row=3, end_column=first+2)
            sheet.cell(3, first, start+timedelta(days=w*7+d)).number_format = "m/d (ddd)"
            for delta, heading in enumerate(["用膳", "更碼", "工作"]):
                sheet.cell(4, first+delta, heading)
                sheet.column_dimensions[col(first+delta)].width = 17 if delta == 1 else 14
        for i, person in enumerate(staff, 5):
            text(sheet.cell(i,1), person["rank"]); text(sheet.cell(i,2), person.get("name") or person.get("name_en") or person["id"])
            for d in range(7):
                item = cells.get((person["id"], w*7+d))
                if item:
                    text(sheet.cell(i,4+3*d), item[0]); text(sheet.cell(i,5+3*d), item[1])
    last = len(staff)+4
    hours, leave = book["Hours"], book["PH & Off"]
    for sheet in [hours, leave, book["DO更次數"], book["C更男女"], book["N更男女"], book["AP更"]]:
        text(sheet["A1"], sheet.title + " — 草稿 / 由週表連動")
        sheet["A4"] = "職位"; sheet["B4"] = "員工"
    for w in range(6):
        for d in range(7):
            for sheet in [hours, leave]:
                sheet.cell(4,3+9*w+d,start+timedelta(days=7*w+d)).number_format="m/d"
            for nm in ["DO更次數","C更男女","N更男女"]:
                book[nm].cell(4,4+8*w+d,start+timedelta(days=7*w+d)).number_format="m/d"
        hours.cell(4,10+9*w,f"W{w+1} h")
        leave.cell(4,10+9*w,f"W{w+1} PH")
    summary = ["上期欠PH h", "本期PH扣減h", "上期差額h", "六週基準h", "應返h", "已編h", "差額h", "本期欠PH/NO h", "候選下期結轉h", "週基準h", "零結轉參考差額h"]
    for c,h in enumerate(summary,58): hours.cell(4,c,h)
    for c,h in enumerate(["上期欠PH日", "本期PH額", "已編PH", "PH餘額", "O", "NO", "AL折日", "原表性別組", "O + NO"],58): leave.cell(4,c,h)
    for person_index, person in enumerate(staff,5):
        r=person_index; role=roles[person["rank"]]
        for sheet in [hours, leave, book["DO更次數"], book["C更男女"], book["N更男女"], book["AP更"]]:
            sheet.cell(r,1,f"='第一週'!A{r}"); sheet.cell(r,2,f"='第一週'!B{r}")
        for day in range(42):
            w,d=divmod(day,7)
            hours.cell(r,3+9*w+d,formula(r,day,2))
            leave.cell(r,3+9*w+d,formula(r,day,6))
            for nm,index in [("DO更次數",8),("C更男女",5),("N更男女",7)]:
                book[nm].cell(r,4+8*w+d,officer_formula(r,day) if nm=='DO更次數' else formula(r,day,index))
            for delta,index in [(0,3),(7,4)]: book["AP更"].cell(r,3+15*w+delta+d,formula(r,day,index))
        for w in range(6):
            hours.cell(r,10+9*w,complete_sum(hours,r,3+9*w,9+9*w))
            leave.cell(r,10+9*w,complete_sum(leave,r,3+9*w,9+9*w))
        totals=','.join(f'{col(10+9*w)}{r}' for w in range(6))
        hours.cell(r,59,sum(start<=h<=end for h in profile.holiday_dates)*role.ph_minutes/60)
        hours.cell(r,61,role.weekly_minutes*6/60)
        hours.cell(r,62,f'=IF(COUNT(BF{r},BH{r})=2,BI{r}-BF{r}-BG{r}-BH{r},"待結轉資料")')
        hours.cell(r,63,f'=IF(COUNT({totals})=6,SUM({totals}),"未編齊")')
        hours.cell(r,64,f'=IF(COUNT(BJ{r},BK{r},BM{r})=3,BK{r}-BJ{r}-BM{r},"待資料")')
        hours.cell(r,66,f'=IF(ISNUMBER(BL{r}),BL{r},"待資料")')
        hours.cell(r,67,role.weekly_minutes/60)
        hours.cell(r,68,f'=IF(ISNUMBER(BK{r}),BK{r}-(BI{r}-BG{r}),"未編齊")')
        for c in [58,60,65]: hours.cell(r,c).fill=PatternFill("solid",fgColor="FFF2CC")
        leave.cell(r,58).fill=PatternFill("solid",fgColor="FFF2CC")
        leave.cell(r,59,sum(start<=h<=end for h in profile.holiday_dates))
        leave.cell(r,60,f'=IF(COUNT({totals})=6,SUM({totals}),"未編齊")')
        leave.cell(r,61,f'=IF(COUNT(BF{r},BG{r},BH{r})=3,BF{r}+BG{r}-BH{r},"待資料")')
        for c,code in [(62,"O"),(63,"NO")]:
            leave.cell(r,c,f'=IF(ISNUMBER(Hours!BK{r}),SUM('+','.join(f'IF({ref(r,d)}="{code}",1,0)' for d in range(42))+'),"未編齊")')
        leave.cell(r,64,f'=IF(ISNUMBER(Hours!BK{r}),SUM('+','.join(f'VLOOKUP({ref(r,d)},{lookup},9,FALSE)' for d in range(42))+'),"未編齊")')
        leave.cell(r,66,f'=IF(COUNT(BJ{r}:BK{r})=2,SUM(BJ{r}:BK{r}),"未編齊")')
        gender=person.get("gender")
        text(leave.cell(r,65),gender if gender in {"M","F","男","女"} else "未有資料")
        for nm in ["C更男女","N更男女"]:
            book[nm].cell(r,3,f"='PH & Off'!BM{r}")
        for nm in ["DO更次數","C更男女","N更男女"]:
            refs=','.join(f'{col(4+8*(d//7)+d%7)}{r}' for d in range(42))
            book[nm].cell(4,52,"六週次數");book[nm].cell(r,52,f'=IF(COUNT({refs})=42,SUM({refs}),"未編齊")')
        for cc,delta,label in [(93,0,"六週A次數"),(94,7,"六週P次數")]:
            refs=','.join(f'{col(3+15*(d//7)+delta+d%7)}{r}' for d in range(42))
            book['AP更'].cell(4,cc,label)
            book['AP更'].cell(r,cc,f'=IF(COUNT({refs})=42,SUM({refs}),"未編齊")')
    # One row per employee/week: no conversion into a calendar-month target.
    audit_start=last+5
    for c,h in enumerate(["員工", "週開始", "週基準h", "本週已排PH扣減h", "參考應返h", "計入工時h", "差額h"],1): hours.cell(audit_start,c,h)
    for i,person in enumerate(staff):
        r=i+5;role=roles[person["rank"]]
        for w in range(6):
            rr=audit_start+1+i*6+w
            hours.cell(rr,1,f"=B{r}");hours.cell(rr,2,start+timedelta(days=7*w)).number_format="yyyy-mm-dd"
            hours.cell(rr,3,role.weekly_minutes/60)
            phcell=f"'PH & Off'!{col(10+9*w)}{r}"
            hours.cell(rr,4,f'=IF(ISNUMBER({phcell}),{phcell}*{role.ph_minutes}/60,"未編齊")')
            hours.cell(rr,5,f'=IF(ISNUMBER(D{rr}),C{rr}-D{rr},"未編齊")')
            hours.cell(rr,6,f'={col(10+9*w)}{r}')
            hours.cell(rr,7,f'=IF(COUNT(E{rr}:F{rr})=2,F{rr}-E{rr},"未編齊")')
    # Month slices report allocations, never a fabricated monthly hours target.
    month_row=last+5
    for c,h in enumerate(["員工", "月份", "涵蓋日數", "AL折日", "已編PH", "O", "NO", "計入工時h", "工作日"],1): leave.cell(month_row,c,h)
    months=sorted({(start+timedelta(days=d)).strftime('%Y-%m') for d in range(42)})
    for i,person in enumerate(staff):
        r=i+5
        for j,month in enumerate(months):
            rr=month_row+1+i*len(months)+j
            days=[d for d in range(42) if (start+timedelta(days=d)).strftime('%Y-%m')==month]
            leave.cell(rr,1,f'=B{r}');leave.cell(rr,2,month);leave.cell(rr,3,len(days))
            for cc,field in [(4,9),(5,6),(8,2),(9,10)]:
                expr=','.join(f'VLOOKUP({ref(r,d)},{lookup},{field},FALSE)' for d in days)
                leave.cell(rr,cc,f'=IF(ISNUMBER(Hours!BK{r}),SUM({expr}),"未編齊")')
            for cc,code in [(6,'O'),(7,'NO')]:
                expr=','.join(f'IF({ref(r,d)}="{code}",1,0)' for d in days)
                leave.cell(rr,cc,f'=IF(ISNUMBER(Hours!BK{r}),SUM({expr}),"未編齊")')
    for nm,index in [("C更男女",5),("N更男女",7)]:
        sheet=book[nm]
        for delta,(label,aliases) in enumerate([("男",["M","男"]),("女",["F","女"]),("未有資料",["未有資料"])]):
            rr=last+3+delta;sheet.cell(rr,2,label)
            for day in range(42):
                cc=col(4+8*(day//7)+day%7)
                sheet.cell(rr,4+8*(day//7)+day%7,'='+ '+'.join(f'SUMIF($C$5:$C${last},"{g}",{cc}5:{cc}{last})' for g in aliases))
    for w in range(6):
        for d in range(7):
            for delta,label in [(0,"A"),(7,"P")]:
                book["AP更"].cell(4,3+15*w+delta+d,f"W{w+1} {label} {d+1}")
    for sheet in book:
        sheet.print_area=sheet.dimensions
        for row in sheet:
            for cell in row:
                cell.font=Font(name="Microsoft JhengHei",size=11)
                cell.alignment=Alignment(vertical="center",wrap_text=True)
                if cell.row==4 and sheet.title not in SHEETS[:4]:
                    cell.fill=PatternFill("solid",fgColor="243A57");cell.font=Font(name="Microsoft JhengHei",size=11,color="FFFFFF",bold=True)
        sheet.row_dimensions[4].height=44
        for c in range(3,sheet.max_column+1):
            if sheet.column_dimensions[col(c)].width==13: sheet.column_dimensions[col(c)].width=14
    book.calculation=CalcProperties(fullCalcOnLoad=True)
    book.properties.title="DRAFT linked roster"
    book.properties.creator="Emma AI"
    output=BytesIO();book.save(output)
    return output.getvalue()
