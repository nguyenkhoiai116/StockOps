# Cập nhật bản chạy thật (E:\StockOps-live) lên code mới nhất của nhánh main trong thư mục dev.
# Chạy: bấm đúp capnhat.bat trong E:\StockOps-live (không cần quyền Admin).
# Các bước: lấy code -> cài thư viện -> chạy test -> sao lưu database -> khởi động lại -> kiểm tra.
# Server không lên được thì tự lùi về code cũ và khởi động lại.
param(
    [string]$Branch = "main",   # nhánh lấy code
    [switch]$NoTest,            # bỏ bước chạy test (nhanh hơn, kém an toàn hơn)
    [switch]$Restart            # chỉ khởi động lại server, không lấy code mới (vd sau khi sửa .env)
)
$ErrorActionPreference = "Continue"   # lỗi của git/python xét bằng $LASTEXITCODE; "Stop" làm PowerShell 5.1 dừng khi chương trình chỉ in cảnh báo ra stderr
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$task = "StockOps server"
$env:PYTHONIOENCODING = "utf-8"

function Say($m, $c = "Gray") { Write-Host $m -ForegroundColor $c }
function Stop-Here($m) { Say $m Red; exit 1 }

# Chỉ chạy ở bản chạy thật: file .live do bước cài đặt tạo ra, không có trong git
if (-not (Test-Path ".live")) { Stop-Here "Đây không phải thư mục chạy thật (thiếu file .live). Hãy chạy capnhat.bat trong E:\StockOps-live." }

$port = 5000   # cổng lấy từ .env, giống server.py
$m = Select-String -Path ".env" -Pattern '^\s*PORT\s*=\s*(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($m) { $port = [int]$m.Matches[0].Groups[1].Value }

function Test-Up {
    # Đợi tối đa 40 giây cho server trả lời
    for ($i = 0; $i -lt 40; $i++) {
        try {
            $r = Invoke-WebRequest "http://localhost:$port/api/me" -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $true }
        } catch {}
        Start-Sleep 1
    }
    return $false
}

function Restart-Server {
    # /End dừng đúng tiến trình python do task chạy; dừng bằng tay nên task không tự chạy lại
    schtasks /End /TN $task 2>$null | Out-Null
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { break }
        Start-Sleep 1
    }
    schtasks /Run /TN $task | Out-Null
    return (Test-Up)
}

if ($Restart) {
    Say "Khởi động lại server ..."
    if (Restart-Server) { Say "Xong: server đang chạy ở cổng $port." Green; exit 0 }
    Stop-Here "Server không lên. Xem logs\server.log"
}

if (git status --porcelain --untracked-files=no) { Stop-Here "Có file code bị sửa trực tiếp trong thư mục chạy thật. Hãy sửa ở thư mục dev rồi commit." }

Say "[1/6] Lấy code nhánh $Branch ..."
git fetch -q origin $Branch
if ($LASTEXITCODE) { Stop-Here "Không lấy được code (git fetch lỗi)." }
$old = git rev-parse HEAD
$new = git rev-parse "origin/$Branch"
if ($old -eq $new) { Say "Không có gì mới: bản chạy thật đã ở commit mới nhất của $Branch." Green; exit 0 }
Say "Các thay đổi sẽ cập nhật:"
git log --oneline "$old..$new"
git merge -q --ff-only "origin/$Branch"
if ($LASTEXITCODE) { Stop-Here "Không cập nhật được: lịch sử nhánh $Branch bị viết lại. Không tự xử lý, hãy hỏi người lập trình." }

function Undo($why) {
    Say "$why -> lùi về code cũ ($($old.Substring(0, 7)))" Yellow
    git reset -q --hard $old
    & $py -m pip install -q -r requirements.txt
}

Say "[2/6] Cài thư viện ..."
& $py -m pip install -q -r requirements.txt
if ($LASTEXITCODE) { Undo "Cài thư viện lỗi"; Stop-Here "Đã lùi về code cũ, server chưa bị đụng tới." }

if (-not $NoTest) {
    Say "[3/6] Chạy test (khoảng 1 phút, dùng database tạm) ..."
    & $py -m unittest discover -q tests 2>&1 | ForEach-Object { "$_" } | Select-Object -Last 5
    if ($LASTEXITCODE) { Undo "Test lỗi"; Stop-Here "Đã lùi về code cũ, server chưa bị đụng tới." }
} else { Say "[3/6] Bỏ qua test (-NoTest)" Yellow }

Say "[4/6] Sao lưu database ..."
$bak = & $py database.py backup
if ($LASTEXITCODE) { Undo "Sao lưu lỗi"; Stop-Here "Đã lùi về code cũ, server chưa bị đụng tới." }
Say "  $bak"

Say "[5/6] Khởi động lại server (người dùng bị gián đoạn vài giây) ..."
if (Restart-Server) {
    Say "[6/6] Xong: server chạy bản $($new.Substring(0, 7))." Green
    exit 0
}

Undo "Server mới không lên được"
if (Restart-Server) {
    Say "Server đã chạy lại bằng code cũ. Nếu bản mới có migration, database có thể đã đổi: bản sao lưu ở trên." Yellow
} else {
    Say "Server cũ cũng không lên. Xem logs\server.log; bản sao lưu ở trên." Red
}
Say "Log cuối:"
Get-Content "logs\server.log" -Tail 15 -Encoding utf8
exit 1
