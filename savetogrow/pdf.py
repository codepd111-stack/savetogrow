"""A tiny dependency-free PDF writer for text reports (Courier, A4, paginated)."""
from __future__ import annotations

from pathlib import Path

PAGE_W, PAGE_H = 595, 842
MARGIN_L, MARGIN_T, LEADING, FONT_SIZE = 48, 800, 13, 10
LINES_PER_PAGE = 56


def _escape(s: str) -> str:
    # The standard PDF fonts only know Latin-1, so the rupee sign becomes "Rs" and a bullet becomes "-".
    s = s.replace("₹", "Rs ").replace("•", "-").replace("·", "-").replace("−", "-")
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path: str | Path, title: str, lines: list[str]) -> Path:
    path = Path(path)
    pages = [lines[i:i + LINES_PER_PAGE] for i in range(0, max(1, len(lines)), LINES_PER_PAGE)] or [[]]
    objects: list[bytes] = []  # object bodies, 1-based ids = index + 1

    def add(body: str | bytes) -> int:
        objects.append(body.encode("latin-1") if isinstance(body, str) else body)
        return len(objects)

    font_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    bold_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>")
    pages_id = add("")  # placeholder, filled after page ids are known
    page_ids = []
    for pno, chunk in enumerate(pages, 1):
        ops = [f"BT /F2 {FONT_SIZE + 2} Tf {MARGIN_L} {MARGIN_T + 18} Td ({_escape(title)}) Tj ET"]
        ops.append(f"BT /F1 {FONT_SIZE} Tf {MARGIN_L} {MARGIN_T} Td {LEADING} TL")
        for line in chunk:
            ops.append(f"({_escape(line)}) Tj T*")
        ops.append("ET")
        ops.append(f"BT /F1 8 Tf {MARGIN_L} 30 Td (Savetogrow  -  page {pno} of {len(pages)}) Tj ET")
        stream = "\n".join(ops).encode("latin-1")
        content_id = add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        page_id = add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                      f"/Resources << /Font << /F1 {font_id} 0 R /F2 {bold_id} 0 R >> >> /Contents {content_id} 0 R >>")
        page_ids.append(page_id)
    objects[pages_id - 1] = (f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(page_ids)} >>").encode("latin-1")
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))
    return path
