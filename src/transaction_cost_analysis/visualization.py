from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


COLORS = ("#1d4ed8", "#f59e0b", "#ef4444", "#7c3aed")
_FONT = {
    "A": ("01110","10001","10001","11111","10001","10001","10001"), "B": ("11110","10001","10001","11110","10001","10001","11110"),
    "C": ("01111","10000","10000","10000","10000","10000","01111"), "D": ("11110","10001","10001","10001","10001","10001","11110"),
    "E": ("11111","10000","10000","11110","10000","10000","11111"), "F": ("11111","10000","10000","11110","10000","10000","10000"),
    "G": ("01111","10000","10000","10111","10001","10001","01111"), "H": ("10001","10001","10001","11111","10001","10001","10001"),
    "I": ("11111","00100","00100","00100","00100","00100","11111"), "J": ("00111","00010","00010","00010","10010","10010","01100"),
    "K": ("10001","10010","10100","11000","10100","10010","10001"), "L": ("10000","10000","10000","10000","10000","10000","11111"),
    "M": ("10001","11011","10101","10101","10001","10001","10001"), "N": ("10001","11001","10101","10011","10001","10001","10001"),
    "O": ("01110","10001","10001","10001","10001","10001","01110"), "P": ("11110","10001","10001","11110","10000","10000","10000"),
    "Q": ("01110","10001","10001","10001","10101","10010","01101"), "R": ("11110","10001","10001","11110","10100","10010","10001"),
    "S": ("01111","10000","10000","01110","00001","00001","11110"), "T": ("11111","00100","00100","00100","00100","00100","00100"),
    "U": ("10001","10001","10001","10001","10001","10001","01110"), "V": ("10001","10001","10001","10001","10001","01010","00100"),
    "W": ("10001","10001","10001","10101","10101","10101","01010"), "X": ("10001","10001","01010","00100","01010","10001","10001"),
    "Y": ("10001","10001","01010","00100","00100","00100","00100"), "Z": ("11111","00001","00010","00100","01000","10000","11111"),
    "0": ("01110","10001","10011","10101","11001","10001","01110"), "1": ("00100","01100","00100","00100","00100","00100","01110"),
    "2": ("01110","10001","00001","00010","00100","01000","11111"), "3": ("11110","00001","00001","01110","00001","00001","11110"),
    "4": ("00010","00110","01010","10010","11111","00010","00010"), "5": ("11111","10000","10000","11110","00001","00001","11110"),
    "6": ("01110","10000","10000","11110","10001","10001","01110"), "7": ("11111","00001","00010","00100","01000","01000","01000"),
    "8": ("01110","10001","10001","01110","10001","10001","01110"), "9": ("01110","10001","10001","01111","00001","00001","01110"),
    "-": ("00000","00000","00000","11111","00000","00000","00000"), ".": ("00000","00000","00000","00000","00000","00110","00110"),
    ":": ("00000","00110","00110","00000","00110","00110","00000"), "/": ("00001","00010","00010","00100","01000","01000","10000"),
    "%": ("11001","11010","00100","01000","10110","00110","00000"), "+": ("00000","00100","00100","11111","00100","00100","00000"),
}


class _Raster:
    def __init__(self, width: int = 1200, height: int = 700) -> None:
        self.width, self.height = width, height
        self.data = bytearray([255] * width * height * 3)

    def pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            offset = (y * self.width + x) * 3
            self.data[offset:offset + 3] = bytes(color)

    def rect(self, x: int, y: int, width: int, height: int, color: tuple[int, int, int]) -> None:
        for yy in range(max(0, y), min(self.height, y + max(0, height))):
            start = (yy * self.width + max(0, x)) * 3
            end = (yy * self.width + min(self.width, x + width)) * 3
            if end > start:
                self.data[start:end] = bytes(color) * ((end - start) // 3)

    def text(self, x: int, y: int, value: str, color: tuple[int, int, int], scale: int = 2) -> None:
        for char in value.upper():
            glyph = _FONT.get(char)
            if glyph:
                for row, bits in enumerate(glyph):
                    for col, bit in enumerate(bits):
                        if bit == "1":
                            self.rect(x + col * scale, y + row * scale, scale, scale, color)
            x += 6 * scale

    def png(self, path: Path) -> None:
        raw = b"".join(b"\x00" + self.data[y * self.width * 3:(y + 1) * self.width * 3] for y in range(self.height))
        def chunk(tag: bytes, payload: bytes) -> bytes:
            return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff)
        encoded = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", self.width, self.height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
        path.write_bytes(encoded)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[index:index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def _svg(title: str, subtitle: str, body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="700" viewBox="0 0 1200 700">
<rect width="1200" height="700" fill="#ffffff"/><text x="64" y="72" font-family="Arial,sans-serif" font-size="30" font-weight="700" fill="#111827">{escape(title)}</text>
<text x="64" y="108" font-family="Arial,sans-serif" font-size="15" fill="#64748b">{escape(subtitle)}</text>{body}
<text x="64" y="670" font-family="Arial,sans-serif" font-size="12" fill="#64748b">Synthetic illustrative inputs · positive cost is adverse · not causal impact estimation</text></svg>"""


def render_overview_svg(report: dict[str, Any]) -> str:
    parts = [("Explicit fees", "explicit_cost"), ("Delay", "delay_cost"), ("Market impact", "market_impact"), ("Opportunity", "opportunity_cost")]
    values = [report["totals"][key] for _, key in parts]
    maximum = max(1.0, max(abs(value) for value in values))
    body = ['<text x="64" y="160" font-family="Arial" font-size="15" fill="#334155">Implementation shortfall components (' + escape(report["currency"]) + ')</text>']
    for index, ((label, _), value) in enumerate(zip(parts, values)):
        y = 205 + index * 95
        width = abs(value) / maximum * 720
        x = 270 if value >= 0 else 270 - width
        body.append(f'<text x="64" y="{y+26}" font-family="Arial" font-size="16" fill="#334155">{escape(label)}</text><rect x="{x:.1f}" y="{y}" width="{max(2,width):.1f}" height="36" rx="6" fill="{COLORS[index]}"/><text x="{max(275,x+width+12):.1f}" y="{y+25}" font-family="Arial" font-size="15" fill="#334155">{value:,.2f}</text>')
    body.append(f'<line x1="270" y1="185" x2="270" y2="580" stroke="#94a3b8"/><text x="64" y="590" font-family="Arial" font-size="18" font-weight="700" fill="#0f172a">TOTAL  {report["totals"]["total_shortfall"]:,.2f} {escape(report["currency"])}  ·  {report["totals"]["shortfall_bps"]:.1f} bps</text>')
    return _svg("Execution cost overview", "Arrival-price shortfall decomposition across the sample orders", "".join(body))


def render_flow_svg(report: dict[str, Any]) -> str:
    venues = report["by_venue"]
    items = list(venues.items())
    maximum = max(1.0, max((abs(row["execution_shortfall"]) for _, row in items), default=0))
    body = ['<text x="64" y="160" font-family="Arial" font-size="15" fill="#334155">Execution shortfall by venue · fees + arrival-to-fill impact</text>']
    for index, (venue, data) in enumerate(items[:5]):
        y = 210 + index * 76
        width = abs(data["execution_shortfall"]) / maximum * 670
        color = "#ef4444" if data["execution_shortfall"] >= 0 else "#16a34a"
        body.append(f'<text x="64" y="{y+25}" font-family="Arial" font-size="15" fill="#334155">{escape(venue)}</text><rect x="260" y="{y}" width="{max(2,width):.1f}" height="32" rx="5" fill="{color}"/><text x="{max(275,272+width):.1f}" y="{y+23}" font-family="Arial" font-size="14" fill="#334155">{data["execution_shortfall"]:,.2f}</text>')
    if not items:
        body.append('<text x="64" y="230" font-family="Arial" font-size="16" fill="#64748b">No executions in the sample</text>')
    body.append(f'<text x="64" y="610" font-family="Arial" font-size="16" font-weight="700" fill="#0f172a">Filled {report["totals"]["filled_quantity"]:,.0f} / {report["totals"]["order_quantity"]:,.0f} shares  ·  {len(report["by_instrument"])} instruments</text>')
    return _svg("Execution flow & venue view", "Where the filled shares traded and venue-level shortfall (unfilled opportunity excluded)", "".join(body))


def _render_png(report: dict[str, Any], path: Path, flow: bool) -> None:
    canvas = _Raster()
    navy, gray = _rgb("#111827"), _rgb("#64748b")
    canvas.text(64, 42, "EXECUTION FLOW AND VENUE VIEW" if flow else "EXECUTION COST OVERVIEW", navy, 4)
    canvas.text(64, 103, "SYNTHETIC SAMPLE - ARRIVAL PRICE BENCHMARK", gray, 2)
    if flow:
        values = [(name, item["execution_shortfall"]) for name, item in report["by_venue"].items()]
        canvas.text(64, 165, "VENUE EXECUTION SHORTFALL (FEES + IMPACT)", navy, 2)
        maximum = max(1.0, max((abs(value) for _, value in values), default=0))
        for index, (name, value) in enumerate(values[:6]):
            y = 220 + index * 58
            canvas.text(64, y + 5, name[:14], gray, 2)
            width = int(abs(value) / maximum * 640)
            canvas.rect(290, y, max(2, width), 30, _rgb("#ef4444" if value >= 0 else "#16a34a"))
            canvas.text(min(960, 310 + width), y + 7, f"{value:.0f}", navy, 2)
        canvas.text(64, 600, f"FILLED {report['totals']['filled_quantity']:.0f} / {report['totals']['order_quantity']:.0f} SHARES", navy, 2)
    else:
        components = [("EXPLICIT", "explicit_cost", "#1d4ed8"), ("DELAY", "delay_cost", "#f59e0b"), ("IMPACT", "market_impact", "#ef4444"), ("OPPORTUNITY", "opportunity_cost", "#7c3aed")]
        maximum = max(1.0, max(abs(report["totals"][key]) for _, key, _ in components))
        canvas.text(64, 165, f"COMPONENT COST ({report['currency']})", navy, 2)
        for index, (label, key, color) in enumerate(components):
            y = 225 + index * 78
            value = report["totals"][key]
            canvas.text(64, y + 6, label, gray, 2)
            width = int(abs(value) / maximum * 670)
            canvas.rect(300 if value >= 0 else 300 - width, y, max(2, width), 34, _rgb(color))
            canvas.text(min(1010, 320 + width), y + 8, f"{value:.0f}", navy, 2)
        canvas.text(64, 585, f"TOTAL {report['totals']['total_shortfall']:.0f} {report['currency']}  |  {report['totals']['shortfall_bps']:.1f} BPS", navy, 2)
    canvas.text(64, 660, "POSITIVE COST IS ADVERSE - ILLUSTRATIVE ONLY - NOT CAUSAL", gray, 2)
    canvas.png(path)


def write_reports(report: dict[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for stem, render, flow in (
        ("overview", render_overview_svg, False),
        ("flow", render_flow_svg, True),
    ):
        (directory / f"{stem}.svg").write_text(render(report), encoding="utf-8")
        _render_png(report, directory / f"{stem}.png", flow)
