"""Draw the retained certificate-cost figure; never execute the measurement runner.

The plotted values come from the current 21-row same-information comparison.
An optional paper CSV must be its exact ordered index/case/ratio projection.
"""

import argparse
from collections import defaultdict
import csv
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import struct
import subprocess


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "results/revision-2026-10-14/same-information"
NUMERIC = (
    "certificate_seconds",
    "projected_no_certificate_seconds",
    "reflexive_no_certificate_seconds",
    "complete_world_seconds",
    "certificate_over_projected_ratio",
)
ARMS = {
    "certificate": "certificate_seconds",
    "projected-no-certificate": "projected_no_certificate_seconds",
    "reflexive-no-certificate": "reflexive_no_certificate_seconds",
    "complete-world": "complete_world_seconds",
}


def checked_rows(projection):
    with (INPUT / "comparison.csv").open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["case", "family", *NUMERIC]:
            raise ValueError("Unexpected comparison.csv columns")
        rows = list(reader)
    summary = json.loads(
        (INPUT / "summary.json").read_text(encoding="utf-8"),
        parse_float=Decimal,
    )
    aggregates = summary["aggregates"]
    if len(rows) != summary["cases"] or len(rows) != len(aggregates):
        raise ValueError("Current comparison and summary case counts differ")
    if summary["trials"] != 5 or summary["arm_executions"] != 420:
        raise ValueError("Unexpected retained measurement protocol")
    recorded = defaultdict(list)
    with (INPUT / "rows.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line, parse_float=Decimal)
            recorded[(row["case"], row["arm"])].append(row)
    if sum(map(len, recorded.values())) != 420 or len(recorded) != 84:
        raise ValueError("Raw measurement rows do not cover 21 cases x four arms")
    if [row["family"] for row in rows] != (
        ["curated"] * 10 + ["selector"] * 4 + ["dead"] * 4 + ["workflow"] * 3
    ):
        raise ValueError("Unexpected fixed-case cohort or order")
    for row, aggregate in zip(rows, aggregates, strict=True):
        if (row["case"], row["family"]) != (aggregate["case"], aggregate["family"]):
            raise ValueError("Comparison and summary case order differ")
        for field in NUMERIC:
            value = Decimal(row[field])
            if not value.is_finite() or value <= 0 or value != aggregate[field]:
                raise ValueError(f"Comparison and summary differ: {row['case']} {field}")
        for arm, field in ARMS.items():
            samples = recorded[(row["case"], arm)]
            if len(samples) != 5 or {sample["trial"] for sample in samples} != set(range(5)):
                raise ValueError(f"Raw trial coverage differs: {row['case']} {arm}")
            median = sorted(sample["total_seconds"] for sample in samples)[2]
            if median != Decimal(row[field]):
                raise ValueError(f"Raw median differs: {row['case']} {arm}")
        ratio = Decimal(row["certificate_over_projected_ratio"])
        if abs(Decimal(row["certificate_seconds"]) /
               Decimal(row["projected_no_certificate_seconds"]) - ratio) > Decimal("1e-12"):
            raise ValueError(f"Median ratio differs: {row['case']}")
    if projection is not None:
        with projection.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ["index", "case", "ratio"]:
                raise ValueError("Unexpected paper projection columns")
            projected = list(reader)
        if len(projected) != len(rows):
            raise ValueError("Paper projection row count differs")
        for index, (row, item) in enumerate(zip(rows, projected, strict=True), 1):
            if (item["index"], item["case"], Decimal(item["ratio"])) != (
                str(index), row["case"], Decimal(row["certificate_over_projected_ratio"])
            ):
                raise ValueError(f"Paper projection differs at index {index}")
    return rows


def tex_file(name):
    result = subprocess.run(
        ["kpsewhich", name], check=True, capture_output=True, text=True
    )
    path = Path(result.stdout.strip())
    if not result.stdout.strip() or not path.is_file():
        raise FileNotFoundError(name)
    return str(path)


def register_libertine():
    from reportlab.pdfbase import pdfmetrics

    class LibertineFace(pdfmetrics.EmbeddedType1Face):
        # Same TFM/PFB metric route as paper/figures/draw_evaluation.py.
        def _loadMetrics(self, tfm_path):
            data = Path(tfm_path).read_bytes()
            lf, lh, bc, ec, nw, nh, nd, ni, nl, nk, ne, np = struct.unpack(
                ">12H", data[:24]
            )
            if len(data) != 4 * lf or not (bc <= 32 and ec >= 126 and np >= 2):
                raise ValueError("Unexpected Libertine T1 metric layout")
            start = 24 + 4 * lh
            widths_start = start + 4 * (ec - bc + 1)
            widths = struct.unpack(
                ">" + "i" * nw, data[widths_start:widths_start + 4 * nw]
            )
            params_start = widths_start + 4 * (nw + nh + nd + ni + nl + nk + ne)
            space = struct.unpack(">i", data[params_start + 4:params_start + 8])[0]
            encoding = pdfmetrics.getEncoding("WinAnsiEncoding")
            self.glyphWidths = {}
            for code in range(32, 127):
                index = data[start + 4 * (code - bc)]
                width = space if code == 32 else widths[index]
                self.glyphWidths[encoding[code]] = 1000 * width / 2**20
            self.glyphNames = sorted(self.glyphWidths)
            header = self._binaryData[:self._length1].decode("ascii")
            self.name = re.search(r"/FontName\s+/(\S+)", header).group(1)
            self.familyName = "Linux Libertine"
            bbox = re.search(r"/FontBBox\s*[\{\[]\s*([^}\]]+)", header).group(1)
            self.bbox = [int(float(v)) for v in bbox.split()]
            self.ascent, self.descent = self.bbox[3], self.bbox[1]
            self.capHeight, self.xHeight, self.stemV = 643, 429, 79
            self.italicAngle = float(
                re.search(r"/ItalicAngle\s+([-\d.]+)", header).group(1)
            )

    face = LibertineFace(
        tex_file("LinLibertineT-lf-t1.tfm"), tex_file("LinLibertineT.pfb")
    )
    pdfmetrics.registerTypeFace(face)
    pdfmetrics.registerFont(pdfmetrics.Font("Body", face.name, "WinAnsiEncoding"))


def draw(rows, output):
    from reportlab.pdfgen import canvas

    register_libertine()
    c = canvas.Canvas(str(output), pagesize=(460, 175), invariant=True,
                      initialFontName="Body")
    c.setTitle("Certificate cost across 21 retained cases")
    left, bottom, width, height = 62, 34, 386, 105
    values = [float(Decimal(row["certificate_over_projected_ratio"])) for row in rows]
    low, high = 0.8, max(3.5, math.ceil((max(values) + 0.1) * 2) / 2)

    def px(index):
        return left + width * (index - 0.5) / len(rows)

    def py(value):
        return bottom + height * (value - low) / (high - low)

    c.setFillGray(0)
    c.setFont("Body", 9.3)
    c.drawCentredString(230, 155, "Five-trial median ratio; dashed line: equal time")
    c.setFont("Body", 8.4)
    for value in (1, 1.5, 2, 2.5, 3, 3.5):
        if value > high:
            continue
        y = py(value)
        c.setStrokeGray(0.82)
        c.setLineWidth(0.3)
        c.line(left, y, left + width, y)
        c.setFillGray(0)
        c.drawRightString(left - 6, y - 2.6, f"{value:g}")
    for boundary in (10.5, 14.5, 18.5):
        x = px(boundary)
        c.setStrokeGray(0.74)
        c.setLineWidth(0.35)
        c.setDash(1.5, 2.5)
        c.line(x, bottom, x, bottom + height)
        c.setDash()
    c.setStrokeGray(0)
    c.setLineWidth(0.6)
    c.rect(left, bottom, width, height, fill=0, stroke=1)
    c.setDash(4, 2.5)
    c.line(left, py(1), left + width, py(1))
    c.setDash()
    for index, value in enumerate(values, 1):
        c.circle(px(index), py(value), 2, stroke=0, fill=1)
    for index in (1, 5, 10, 14, 18, 21):
        c.drawCentredString(px(index), bottom - 14, str(index))
    c.drawCentredString(255, 8, "Case index: 10 curated / 4 selector / 4 dead / 3 workflow")
    c.saveState()
    c.translate(13, 86)
    c.rotate(90)
    c.drawCentredString(0, 0, "Certificate / no-certificate time")
    c.restoreState()
    c.showPage()
    c.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection", type=Path,
                        help="optional paper/figures/certificate-cost.csv to verify")
    parser.add_argument("--output", type=Path, help="vector PDF to generate")
    parser.add_argument("--check", action="store_true", help="validate inputs only")
    args = parser.parse_args()
    if args.check == (args.output is not None):
        parser.error("choose exactly one of --check or --output")
    rows = checked_rows(args.projection)
    if args.output is not None:
        if not args.output.parent.is_dir():
            parser.error("output parent does not exist")
        draw(rows, args.output)
    print(f"validated {len(rows)} retained cases and summary"
          + (" plus paper projection" if args.projection is not None else ""))


if __name__ == "__main__":
    main()
