"""Đọc file Excel (.xlsx) và CSV/TXT thuần Python (chỉ dùng thư viện chuẩn, không thêm gói ngoài)."""
import io
import re
import zipfile
from datetime import date, timedelta
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _col_idx(ref):
    """Đổi tên cột Excel (vd 'C12') -> chỉ số 0-based (2)."""
    m = re.match(r"([A-Za-z]+)", ref or "")
    if not m:
        return 0
    idx = 0
    for ch in m.group(1).upper():
        idx = idx * 26 + (ord(ch) - 64)
    return idx - 1


def excel_date_to_iso(val, fallback):
    """Chuyển ngày dạng YYYY-MM-DD, DD/MM/YYYY hoặc số serial Excel sang YYYY-MM-DD."""
    s = str(val or "").strip()
    if not s:
        return fallback
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    # Số serial ngày của Excel (mốc 1899-12-30, thường nằm trong 35000..60000)
    try:
        num = float(s)
        if 35000 <= num <= 65000:
            return (date(1899, 12, 30) + timedelta(days=int(num))).isoformat()
    except ValueError:
        pass
    return fallback


def read_xlsx_rows(raw_bytes):
    """Đọc sheet đầu tiên trong file .xlsx thành danh sách các dòng [ô1, ô2, ...]."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except zipfile.BadZipFile as e:
        raise ValueError("File .xlsx không hợp lệ hoặc bị hỏng") from e

    with zf:
        # Đọc bảng chuỗi dùng chung (sharedStrings.xml) nếu có
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.findall(".//m:t", NS)))

        sheets = sorted(n for n in zf.namelist() if re.match(r"^xl/worksheets/sheet\d+\.xml$", n))
        if not sheets:
            raise ValueError("File Excel không có trang tính (worksheet) nào")

        root = ET.fromstring(zf.read(sheets[0]))
        out = []
        for row in root.findall(".//m:sheetData/m:row", NS):
            cells = {}
            for c in row.findall("m:c", NS):
                ci = _col_idx(c.attrib.get("r", ""))
                ctype = c.attrib.get("t", "")
                val = ""
                if ctype == "s":
                    v = c.find("m:v", NS)
                    if v is not None and v.text and v.text.isdigit():
                        idx = int(v.text)
                        val = shared[idx] if idx < len(shared) else ""
                elif ctype == "inlineStr":
                    val = "".join(t.text or "" for t in c.findall(".//m:t", NS))
                else:
                    v = c.find("m:v", NS)
                    val = (v.text or "") if v is not None else ""
                cells[ci] = val.strip()
            if cells:
                mx = max(cells) + 1
                line = [cells.get(i, "") for i in range(mx)]
                if any(line):
                    out.append(line)
        return out


def extract_text_from_upload(file_storage):
    """Đọc file tải lên (.xlsx, .csv, .txt) và trả về văn bản phân tách bằng dấu phẩy theo từng dòng."""
    name = (file_storage.filename or "").lower()
    raw = file_storage.read()
    if not raw:
        raise ValueError("File tải lên đang trống")
    if name.endswith(".xlsx"):
        grid = read_xlsx_rows(raw)
        # Dùng dấu phẩy làm dấu phân tách; bỏ dấu phẩy thừa trong từng ô
        return "\n".join(", ".join(c.replace(",", " ") for c in r) for r in grid)
    if name.endswith(".xls"):
        raise ValueError("Định dạng .xls cũ chưa được hỗ trợ — hãy lưu file Excel dưới dạng .xlsx hoặc .csv")
    for enc in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Không đọc được bảng mã của file tải lên")
