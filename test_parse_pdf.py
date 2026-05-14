# -*- coding: utf-8 -*-
"""Однократная проверка парсера на PDF. Запуск: python test_parse_pdf.py"""
import os
import sys

def main():
    pdf_path = r"c:\Users\Teacher\Downloads\Расписание_2026-02-13.pdf"
    if not os.path.isfile(pdf_path):
        # Альтернатива: первый PDF из папки бота
        for root, _, files in os.walk(os.path.dirname(os.path.abspath(__file__))):
            for f in files:
                if f.endswith(".pdf") and "Расписание" in f:
                    pdf_path = os.path.join(root, f)
                    break
            else:
                continue
            break
    from schedule_parser import parse_schedule_pdf
    d, groups_lessons = parse_schedule_pdf(pdf_path)
    print("Date:", d)
    print("Groups:", len(groups_lessons))
    for gr, les in groups_lessons[:12]:
        print(f"  {gr}: {len(les)} lessons")
        if les:
            first = les[0]
            print(f"    first: {first.get('num')} {first.get('time_start')}-{first.get('time_end')} {first.get('room')} {first.get('discipline')} {first.get('teacher')}")
    # Петренко
    print("\nPetrenko lessons:")
    for gr, les in groups_lessons:
        for l in les:
            if l.get("teacher") and "Петренко" in (l.get("teacher") or ""):
                print(f"  {gr}: {l.get('num')} {l.get('discipline')} {l.get('teacher')}")

if __name__ == "__main__":
    main()
