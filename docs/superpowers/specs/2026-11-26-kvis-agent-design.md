# Kvis thành agent: tool đọc dữ liệu, RAG tài liệu, đề xuất hành động

Nhánh A trong kế hoạch AI ngày 2026-11-26. Chủ dự án chọn **làm agent trước**, làm nhánh dữ liệu mô phỏng → ML (Phase 1–4 trong `docs/architecture.md`) sau.
Tài liệu này gộp Phase 5, 6, 7 của `docs/architecture.md`, cộng thêm một bước dọn nền mà các phase đó cần.

## Mục đích
Hiện tại Kvis chỉ trả lời dựa trên một "ảnh chụp" số liệu (`prompts.snapshot`) dán vào prompt. Kvis không tự tra thêm được, không biết quy trình kho và không làm được gì.
Sau thay đổi này, Kvis phải:
1. **Tự tra số liệu sống** bằng tool đọc (tồn, lô, cảnh báo, KPI, khu, đơn, PO), chỉ trong phạm vi quyền của người đang hỏi.
2. **Trả lời câu hỏi quy trình** (bảo quản lạnh, FEFO, nhận hàng, định nghĩa KPI, cách dùng web) từ tài liệu trong `knowledge/`, có ghi nguồn.
3. **Đề xuất** tạo PO hoặc điều chỉnh tồn dưới dạng thẻ trong chat. Người có quyền bấm "Xác nhận" thì nghiệp vụ trong `core.py` mới chạy.

Vì sao làm trước nhánh dữ liệu: cả 3 việc trên đều chạy được trên dữ liệu đang có (10 SKU, 4 khu, đơn, PO), không cần simulator hay ML, nên sớm có kết quả để xem. Sau này tool dự báo (`forecast_demand`, `temp_risk`) chỉ việc cắm thêm vào cùng một danh sách tool.

## Mục tiêu (tiêu chí xong, lấy từ `docs/architecture.md`)
- Bộ 20 câu hỏi số liệu: ≥ 16 câu đúng số, mỗi câu ≤ 5 bước tool.
- Bộ 15 câu hỏi tài liệu: tài liệu đúng nằm trong 5 kết quả tìm đầu tiên ở ≥ 80% số câu (đo không cần LLM).
- Admin hỏi "nên nhập gì?" → hiện thẻ PO đúng SKU và số lượng gợi ý. Bấm Xác nhận → PO xuất hiện ở trang Nhập hàng.
- `python -m unittest discover tests` xanh. Test mới không gọi mạng, không cần PyTorch.

## Không làm
- Dự báo, ML, simulator, dữ liệu theo thời gian (nhánh B).
- Hiện câu trả lời từng chữ (streaming). Chat vẫn chờ trả lời xong rồi hiện một lần.
- Lưu lịch sử chat trên giao diện qua lần tải lại trang. `chat_logs` chỉ để chấm điểm và theo dõi chi phí.
- Trang riêng cho lịch sử đề xuất. Thẻ đề xuất đang chờ sẽ hiện lại khi mở khung chat.
- Nhiều agent, framework agent, vector DB, để LLM tự viết SQL.
- Gom nốt nhận PO (`do_receive`) và giao hàng (`do_deliver`) vào `core.py`. Agent không dùng tới hai việc này, nên để thành việc riêng.
- Đổi sang công thức ROP (thuộc nhánh B). Công thức `safety*2 - av` chỉ được chuyển sang `core.py` và trừ thêm PO đang chờ nhận (đã chốt, xem cuối tài liệu).

## Điều không được xảy ra (dù chạy được)
- **Kvis bịa số**, hoặc đưa ra một con số không lấy từ kết quả tool.
- **Kvis thành đường vòng qua quyền.** Ví dụ role `picking` không có `po.view` thì hỏi Kvis cũng không được thấy PO.
- **LLM tự ghi dữ liệu.** Chỉ `propose_*` được ghi, và chỉ ghi vào `agent_actions`.
- **Giữ khóa ghi database trong lúc chờ LLM.** Một lần hỏi có thể mất tới 5 × 60 giây. Nếu giữ khóa trong lúc đó, mọi thao tác ghi khác của kho sẽ bị chặn.
- Hết lượt model miễn phí mà người dùng chỉ thấy lỗi khó hiểu.
- Cài app cơ bản bị bắt cài thêm PyTorch: app phải chạy được kể cả khi chưa cài `sentence-transformers`.

## Ràng buộc
Lấy từ `CLAUDE.md` và `docs/architecture.md`:
- Mọi lần gọi LLM đi qua `wms/ai/llm.py`, dùng `requests` tới `/chat/completions` (OpenRouter mặc định). Không dùng LangChain, LlamaIndex, CrewAI, AutoGen.
- Tool chỉ đọc, trừ `propose_*` chỉ ghi `agent_actions`. Không có SQL tự do.
- Số liệu sống chỉ lấy từ tool. `search_docs` chỉ dùng cho `knowledge/`.
- Embedding chạy local bằng sentence-transformers, lưu trong SQLite, tìm bằng numpy cosine.
- Route `/api/*` mới phải khai trong `wms/roles.py` (`PERMS`). `guard()` mặc định chặn. Nút hành động dùng `can()`.
- Mọi lệnh ghi chạy trong transaction có `lock(con)` (`BEGIN IMMEDIATE`) hoặc qua `core.run()`.
- Đổi schema bằng file migration mới có số thứ tự. Số migration đã dùng tới 008 (`008_login_fails.sql`, cập nhật 2026-11-27), nên migration của AI là **`009_ai.sql`**.
- Comment viết bằng tiếng Việt. Tên biến ngắn theo code cũ (`con`, `rows`, `day`, `bad`, `log`).
- Python 3.11 trên Windows. Ngân sách: miễn phí.

**Phụ thuộc vào việc khác:** cần bản sửa lỗi bấm 2 lần (`db.lock()`, `run()` bắt `IntegrityError`, `004_unique_order_no.sql`, `tests/test_race.py`). Bản đó đã commit ở `e0df881`. Thiết kế này dùng `lock()` của nó.

## Các cách đã cân nhắc

**Thứ tự làm**
| Cách | Được | Mất |
|---|---|---|
| **Agent trước (đã chọn)** | Sớm có kết quả, chạy trên dữ liệu có sẵn, không cần simulator | Tool dự báo phải chờ nhánh B |
| Dữ liệu → ML → agent (thứ tự gốc) | Agent có ngay tool dự báo | 8–10 buổi đầu chưa thấy gì ở chat |

**Cách để LLM tra dữ liệu**
| Cách | Được | Mất |
|---|---|---|
| **Tool calling chuẩn OpenAI (`tools` / `tool_calls`), có đường lui (đã chọn)** | Có sẵn ở OpenRouter, LM Studio; dễ đọc log; dễ thêm tool | Model không hỗ trợ tool thì không dùng được → lui về snapshot |
| Bảo LLM tự trả JSON trong câu chữ | Chạy với mọi model | Model nhỏ hay viết sai JSON, phải tự viết bộ đọc |
| Giữ snapshot, dán thêm nhiều số liệu hơn | Không phải viết gì mới | Prompt phình ra, không lọc được theo quyền, không đề xuất được |

**Độ "to" của tool:** chọn khoảng 10 tool cụ thể, tham số rõ ràng, thay vì 1–2 tool chung kiểu "query(bảng, điều kiện)". Tool cụ thể dễ kiểm quyền và dễ viết mô tả để LLM chọn đúng. Số tool vẫn dưới ngưỡng 15 của ADR-003.

## Thiết kế

### Phần 0. Gom các luật agent cần dùng vào `core.py`
Chỉ gom những gì tool hoặc nút xác nhận gọi lại. Cách chạy giữ nguyên, test cũ phải xanh.
Trước khi chuyển, viết `tests/test_core.py` kiểm các luật đang có (FEFO chia lô, bỏ lô hết hạn, thiếu hàng, xe lạnh, 3 luật điều chỉnh tồn) và cho chạy xanh trên code cũ. 35 test cũ không kiểm các luật này.
- `zone_status(con)` → danh sách khu có `code, name, storage, cap, used, pct, bins, temp, tmin, tmax`. Thay cho phép tính % lấp đầy đang lặp ở `dashboard.py`, `layout.py`, `analytics.py` và `get_alerts()`.
- `reorder_qty(av, safety, pending=0)` → `max(0, safety*2 - av - pending)`, với `pending` là tổng PO đang chờ nhận của SKU. Lấy ra từ `dashboard.py`.
- `create_po(con, pid, qty, eta)` → trả về `po_no`. Chuyển từ `inbound.api_po_add`.
- `do_adjust(con, bid, delta, note)` → chuyển từ `inventory.api_adjust`, giữ đủ 3 luật: không âm, không thấp hơn phần đã giữ, không vượt sức chứa khu.

Hai hàm ghi này **không tự gọi `lock(con)`**. Nơi gọi (`core.run()` hoặc route xác nhận đề xuất) giữ khóa, vì `BEGIN IMMEDIATE` không gọi lồng được.
Route chỉ còn đọc request rồi gọi các hàm này.

### Phần A1. Agent và tool đọc

**Migration `009_ai.sql`**
```sql
chat_logs(id, ts, user_id, question, reply, model, mode,   -- mode: 'agent' | 'snapshot'
          steps, tools,            -- tools: JSON [{name, args, ok}]
          tok_in, tok_out, ms, error)
agent_actions(id, ts, user_id, chat_id,
              kind CHECK (kind IN ('po','adjust')),
              payload,             -- JSON: po {product_id, sku, qty, eta}; adjust {batch_id, batch_no, delta}
              summary,             -- câu tiếng Việt hiện trên thẻ
              reason,              -- lý do do Kvis đưa
              status CHECK (status IN ('proposed','confirmed','rejected')) DEFAULT 'proposed',
              decided_by, decided_at, result)   -- result: vd "PO-012" hoặc thông báo lỗi lần bấm cuối
doc_chunks(id, doc, title, heading, text, emb BLOB, model, built_at)
```
Thêm index `agent_actions(user_id, status)`.

**`wms/ai/llm.py`**
- `chat(msgs, tools=None, temp=0.3, max_out=800)` trả về dict `{text, calls, model, usage}`. `calls` là danh sách `tool_calls` của API, giữ nguyên `id`, `name` và chuỗi `arguments`.
- Có `tool_calls` thì câu trả lời được phép rỗng. Lỗi "trả lời rỗng" chỉ báo khi không có cả chữ lẫn tool call.
- Nhận ra lỗi "model không hỗ trợ tool" (OpenRouter thường trả 404/400 kèm chữ "tool") và báo bằng `LLMError` riêng, vd `NoTools`, để agent lui về cách cũ.
- `chat.py` là nơi duy nhất đang gọi `chat()`, nên sửa nó cùng lúc.

**`wms/ai/tools.py`**: danh sách tool, mỗi tool gồm `(quyền, schema JSON, hàm)`.
- `specs(role)` → chỉ trả schema của các tool mà `can(role, quyền)` cho phép. LLM không biết tới các tool còn lại.
- `call(con, user, name, args_json)` → kiểm lại quyền, đọc và kiểm tham số (kiểu, danh sách giá trị cho phép, độ dài), chạy hàm, trả về dict JSON được.
  - Lỗi được trả về dưới dạng `{"error": "..."}` cho LLM đọc, không raise.
  - Kết quả bị cắt: danh sách tối đa 50 dòng, JSON tối đa khoảng 4.000 ký tự, kèm `"truncated": true`.

| Tool | Tham số | Quyền | Lấy từ |
|---|---|---|---|
| `get_kpis` | — | `dash.view` | `core.get_kpis` |
| `get_alerts` | `kind?` (temp, cap, expiry, stock) | `dash.view` | `core.get_alerts` |
| `get_stock` | `sku?`, `q?` (tìm theo tên, không dấu) | `sku.view` | `core.stock_by_sku` + `stock_status` |
| `get_lots` | `sku?`, `zone?`, `near_days?` | `inv.view` | bảng `batches` (số lô, hạn, vị trí, có, đã giữ) |
| `get_zone_status` | `zone?` | `map.view` | `core.zone_status` |
| `get_orders` | `status?`, `sku?`, `customer?` | `so.view` | bảng `sos` |
| `get_pos` | `status?`, `sku?` | `po.view` | bảng `pos` |
| `get_reorder` | — | `dash.view` | SKU dưới tồn an toàn + `core.reorder_qty`, đã trừ PO đang chờ nhận (như mục gợi ý trên Dashboard) |
| `search_docs` (A2) | `query` | `chat.use` | `rag.search` |
| `propose_po` (A3) | `sku`, `qty`, `reason`, `eta?` | `po.create` | ghi `agent_actions` |
| `propose_adjust` (A3) | `batch_no`, `delta`, `reason` | `inv.adjust` | ghi `agent_actions` |

**`wms/ai/agent.py`**: `ask(user, text, hist)` → `{reply, model, mode, tools, actions, sources}`.
1. Mở 1 kết nối đọc. Không mở transaction trong suốt vòng lặp. Ghi trước 1 dòng `chat_logs` (transaction ngắn) để có `chat_id` cho `agent_actions`.
2. `msgs` = lời dặn hệ thống + 6 tin gần nhất (chỉ chữ của user/assistant, như hiện tại) + câu hỏi. Lời dặn có thêm ngày hôm nay, tên và role người hỏi.
3. Lặp tối đa `MAX_STEPS = 5` lần:
   - Gọi `llm.chat(msgs, tools=specs(role))`.
   - Không có tool call → đó là câu trả lời, dừng.
   - Có tool call → chạy từng cái bằng `tools.call`, thêm tin `role: "tool"` (kèm `tool_call_id`) vào `msgs`.
4. Hết 5 bước mà chưa có câu trả lời → gọi thêm 1 lần không kèm tool, nhắc "trả lời bằng những gì đã tra được".
5. Cập nhật dòng `chat_logs` (câu trả lời, tool, token, thời gian) trong một transaction ngắn ở cuối, kể cả khi lỗi.
6. **Đường lui:** khi `LLM_TOOLS=0` trong `.env` hoặc gặp `NoTools` → dùng lại cách snapshot hiện tại (`mode = 'snapshot'`), và báo một dòng ở cuối câu trả lời.

**Lời dặn hệ thống (`prompts.py`, thêm `AGENT`)**, giữ các quy tắc cũ (tiếng Việt, không markdown, đơn vị thùng/VND, 2–8°C, −18°C, FEFO) và thêm:
- Mọi con số phải lấy từ kết quả tool trong lượt này. Không có tool phù hợp thì nói thẳng là không tra được.
- Tool trả về "không có quyền" thì nói người dùng không có quyền xem, không đoán.
- Lời dặn liệt kê ngắn những nhóm dữ liệu role này **không** được xem (tính từ `PERMS`, vd "PO, đơn bán"). Vì `specs(role)` giấu hẳn các tool đó, nên không có dòng này thì Kvis chỉ biết nói "không tra được" chứ không biết là do quyền.
- `get_kpis` và `get_alerts` vẫn có `po_wait`, `so_open` cho mọi role, giống Dashboard hiện tại. Đây không phải lộ thêm dữ liệu.
- Câu hỏi quy trình thì dùng `search_docs` và ghi tên tài liệu đã dùng.
- Chỉ đề xuất khi người dùng hỏi nên làm gì hoặc nhờ làm, và luôn nói rõ cần bấm xác nhận.

`SYSTEM` và `snapshot()` cũ giữ lại để làm đường lui.

**`/api/chat`** (`features/chat.py`) gọi `agent.ask`. Trả lời có thêm:
- `tools`: tên tiếng Việt của các tool đã gọi.
- `actions`: thẻ đề xuất `{id, kind, summary, status}`.
- `sources`: `{doc, heading}` của các đoạn tài liệu đã dùng.

**Giao diện (`static/js/chat.js`)**
- Dưới mỗi câu trả lời hiện một dòng nhỏ "Đã tra: Tồn kho, Cảnh báo".
- Có nguồn thì hiện "Nguồn: …".
- Có `actions` thì vẽ thẻ (xem A3).

**Kiểm tra**
- `tests/test_agent.py`: thay `llm.chat` bằng hàm giả trả lời theo kịch bản, không gọi mạng. Các trường hợp:
  - 1 tool call rồi trả lời;
  - chạm giới hạn 5 bước;
  - LLM gọi tool ngoài quyền → nhận `error`, không có dữ liệu;
  - tham số JSON hỏng;
  - lui về snapshot khi gặp `NoTools`;
  - luôn có dòng `chat_logs`.
- `tests/test_tools.py`: chạy mọi tool trên database tạm (dữ liệu mẫu), kết quả JSON được; với từng role, `specs(role)` đúng bằng các tool role đó có quyền.

**Bộ chấm điểm (chạy tay, có gọi LLM thật)**
- `tests/ai_eval/questions.json` chứa 20 câu, mỗi câu gồm role hỏi và tên hàm tính đáp án.
- Dữ liệu mẫu tính ngày theo hôm nay, nên đáp án không ghi cứng. `scripts/eval_agent.py` tính đáp án từ database qua `core` lúc chạy, rồi kiểm câu trả lời có chứa đúng các con số đó không (chấp nhận cả `1.200` và `1200`) và số bước có ≤ 5 không.
- Có ít nhất 3 câu hỏi bằng role không có quyền. Đạt khi câu trả lời từ chối có nhắc tới quyền và không chứa con số nào của dữ liệu bị cấm.
- Có tham số `--only` và có nghỉ giữa các câu để không vượt giới hạn lượt gọi.
- Kết quả từng câu được lưu vào file. `--resume` chạy tiếp các câu chưa chấm, để bộ 20 câu chạy rải được qua nhiều ngày nếu hạn mức miễn phí thấp.

**Model:** đổi `.env.example` từ `openrouter/free` (OpenRouter chọn ngẫu nhiên, có model không hỗ trợ tool) sang một model `:free` cố định có hỗ trợ tool.
- Danh sách model của OpenRouter ngày 2026-11-26 có, ví dụ, `google/gemma-4-31b-it:free` và `nvidia/nemotron-3-ultra-550b-a55b:free`.
- Chọn model nào thì dựa vào kết quả bộ 20 câu.

### Phần A2. RAG tài liệu
- **`knowledge/*.md`**: 8–15 tài liệu tiếng Việt, mỗi tài liệu 1 chủ đề, chia mục bằng `##`. Nội dung là **bản mẫu tự soạn** từ luật trong code cộng thông lệ kho FMCG; đầu mỗi tài liệu ghi rõ là tài liệu mẫu. Dự kiến gồm:
  - bảo quản lạnh và đông;
  - FEFO, xử lý hàng cận date và hết hạn;
  - nhận hàng (kiểm lô, hạn dùng, hàng hỏng, cách ly);
  - soạn hàng và xuất kho (xe lạnh);
  - điều chỉnh tồn và kiểm kê;
  - định nghĩa KPI, viết khớp đúng công thức trong `core.get_kpis`;
  - role và quyền (từ `docs/roles.md`);
  - hướng dẫn dùng từng trang;
  - xử lý sự cố nhiệt độ.
- **Cắt đoạn:** mỗi mục `##` là 1 đoạn, dài thì cắt tiếp, mỗi đoạn tối đa khoảng 2.500 ký tự. Văn bản đem đi embedding có ghi kèm tên tài liệu và tên mục.
- **Embedding:** `intfloat/multilingual-e5-small` (384 chiều), thêm tiền tố `passage: ` cho đoạn tài liệu và `query: ` cho câu hỏi, chuẩn hóa vector để tích vô hướng chính là cosine. Lưu float32 dạng BLOB trong `doc_chunks`, kèm tên model.
- **`scripts/build_index.py`**: chạy tay sau khi sửa `knowledge/`. Xóa rồi nạp lại toàn bộ `doc_chunks` trong 1 transaction có `lock(con)`.
- **`wms/ai/rag.py`**
  - `search(con, q, k=4)` → `[{doc, title, heading, text, score}]`.
  - Model nạp lười ở lần tìm đầu tiên. Ma trận embedding được giữ trong bộ nhớ, nạp lại khi `built_at` thay đổi.
  - Hàm `embed(texts, kind)` thay được trong test, để test không cần PyTorch.
  - Chưa cài thư viện hoặc chưa có chỉ mục → tool trả `error` có hướng dẫn chạy `scripts/build_index.py`.
- **Thư viện:** để `sentence-transformers` (có pin version) trong file riêng **`requirements-rag.txt`**, không để trong `requirements.txt`. Lý do: `chay.bat` cài `requirements.txt` mỗi lần cài mới, nên để chung thì ai cũng bị cài PyTorch. Chỉ import bên trong `rag.py` lúc cần, nên app vẫn chạy khi chưa cài.
- **Kiểm tra**
  - `tests/test_rag.py` dùng embedder giả, kiểm cắt đoạn và thứ tự kết quả.
  - `tests/ai_eval/docs.json` chứa 15 câu hỏi kèm tài liệu đúng. `scripts/eval_rag.py` đo tỉ lệ tài liệu đúng nằm trong 5 kết quả đầu, không cần LLM.

### Phần A3. Đề xuất hành động
- **`propose_po(sku, qty, reason, eta?)`**
  - Kiểm SKU có tồn tại và `1 ≤ qty ≤ 10000`.
  - Ghi `agent_actions` trong 1 transaction ngắn có `lock(con)`, rồi trả `{action_id, summary}`.
  - **Không** tạo PO.
- **`propose_adjust(batch_no, delta, reason)`**
  - Tìm lô theo số lô. Trùng số lô thì báo lỗi, bảo hỏi kèm SKU.
  - Kiểm sơ bộ `qty + delta ≥ reserved`, rồi ghi như trên.
  - Payload lưu thêm `qty` của lô lúc đề xuất. Lúc xác nhận, nếu `qty` của lô đã khác thì từ chối: "Lô đã thay đổi từ lúc đề xuất, hãy hỏi lại Kvis". Như vậy không có chuyện áp một `delta` cũ lên số lượng mới.
- **Hết hạn:** đề xuất quá 24 giờ thì không hiện lại và không xác nhận được nữa.
- **Giới hạn**
  - Tối đa 3 đề xuất cho mỗi câu hỏi.
  - Đã có đề xuất `proposed` giống hệt (cùng người, cùng loại, cùng payload) thì trả lại đề xuất cũ, không tạo thêm.
- **Quyền mới** `agent.act` "Xác nhận đề xuất của Kvis", cho `{admin, storage}`: đó là các role có `po.create` hoặc `inv.adjust`.
- **API mới (khai trong `PERMS`)**

  | API | Quyền | Làm gì |
  |---|---|---|
  | `GET /api/agent/actions` | `chat.use` | Đề xuất `proposed` của **chính người hỏi** (10 cái mới nhất) |
  | `POST /api/agent/actions/<int:aid>/confirm` | `agent.act` | Kiểm thêm theo loại (`po` cần `po.create`, `adjust` cần `inv.adjust`) và đúng chủ đề xuất. Rồi trong **cùng 1 transaction có `lock(con)`**: kiểm lại `status='proposed'`, gọi `core.create_po` hoặc `core.do_adjust`, chuyển sang `confirmed`, ghi `result` |
  | `POST /api/agent/actions/<int:aid>/reject` | `chat.use` | Chủ đề xuất chuyển sang `rejected` |

  - Nghiệp vụ báo lỗi (vd vượt sức chứa) → transaction quay lui, đề xuất vẫn ở `proposed`, giao diện hiện lý do. `result` ghi lý do trong **một transaction thứ hai**, vì transaction chính đã quay lui.
  - Bấm đúp "Xác nhận" chỉ tạo 1 PO, nhờ `lock(con)` và bước kiểm lại `status`.
  - Điều chỉnh tồn theo đề xuất ghi vào sổ `txs` với ghi chú "Theo đề xuất Kvis #<id>: <lý do>".
- **Thẻ trong chat**
  - Hiện câu tóm tắt, lý do, và 2 nút Xác nhận / Từ chối. Nút chỉ hiện khi `can("agent.act")` và có quyền theo loại; backend vẫn kiểm lại.
  - Xác nhận xong, thẻ chuyển thành "Đã tạo PO-012" hoặc "Đã điều chỉnh".
  - Mở khung chat thì gọi `GET /api/agent/actions` để hiện lại các thẻ còn chờ.
- **Kiểm tra (`tests/test_actions.py`)**
  - đề xuất rồi xác nhận → PO có thật;
  - từ chối;
  - người khác bấm → bị chặn;
  - role không có quyền theo loại → bị chặn;
  - xác nhận 2 lần song song → 1 PO (dùng kiểu `twice()` của `test_race.py`);
  - nghiệp vụ lỗi → đề xuất vẫn `proposed`.

### Tài liệu cần cập nhật
- `docs/architecture.md`
  - Ghi vào changelog.
  - Sửa lộ trình (agent làm trước nhánh dữ liệu; số migration 005).
  - Thêm ADR-016 (ADR-015 đã dùng cho `BEGIN IMMEDIATE`): tool của agent lọc theo quyền role; nút xác nhận dùng quyền của người bấm.
- `docs/roles.md`: tạo lại bằng `python -m wms.roles`.
- `.env.example`: thêm `LLM_TOOLS` và đổi model mặc định.
- `README`: thêm cách build chỉ mục và cách chạy bộ chấm điểm.

## Thứ tự và công sức
0 → A1 → (A2, A3). A2 và A3 chỉ phụ thuộc A1, không phụ thuộc nhau.

| Phần | Công |
|---|---|
| 0 | 1 buổi |
| A1 | 2–3 buổi |
| A2 | 2 buổi |
| A3 | 1–2 buổi |

## Rủi ro
- **Giới hạn lượt của model miễn phí.** Theo những gì mình biết về OpenRouter (cần kiểm lại ở trang Limits), model `:free` bị giới hạn khoảng 20 lượt/phút, và 50 lượt/ngày nếu tài khoản nạp dưới 10 USD.
  - Một câu hỏi agent tốn 2–3 lượt, nên chạy 1 lần bộ 20 câu có thể dùng hết hạn mức của cả ngày.
  - Bộ chấm điểm phải có `--only` và nghỉ giữa các câu.
  - Nếu cần chạy nhiều, dùng LM Studio local.
  - Lỗi 429 đã có câu giải thích trong `llm.py`.
- **Model nhỏ gọi tool kém** (ghi chú trong `docs/architecture.md`). Khi kết quả thấp, thử một model lớn hơn trước khi sửa thiết kế.
- **PyTorch nặng**: vài trăm MB, cộng khoảng 0,5 GB tải model ở lần đầu. Chỉ người dùng RAG mới cần cài.
- **Test in tiếng Việt lỗi trên console Windows** (review mục 4): chạy test với `PYTHONUTF8=1`.

## Câu hỏi đã chốt (chủ dự án, 2026-11-26)
1. **"Nên nhập gì?" trừ PO đang chờ nhận.** `core.reorder_qty` dùng chung nên Dashboard đổi theo. Trong dữ liệu mẫu, SKU-004 và SKU-007 về 0 vì PO-001 (300 thùng, gợi ý cũ 280) và PO-002 (100 thùng, gợi ý cũ 55) đã đủ bù. Khi làm A3, thêm vào `seed.py` 1 SKU dưới tồn an toàn chưa có PO để demo được thẻ PO.
2. **`knowledge/` là bản mẫu tự soạn** từ luật trong code cộng thông lệ kho FMCG, ghi rõ là tài liệu mẫu.
3. **Phần 0 viết test trước:** `tests/test_core.py` cho luật đang có phải xanh trên code cũ, rồi mới chuyển luật vào `core.py`.

## Quyết định chốt sau khi đọc thử (người thiết kế tự chốt, chủ dự án sửa được)
- `sentence-transformers` nằm trong `requirements-rag.txt` riêng.
- Lời dặn hệ thống liệt kê nhóm dữ liệu role không được xem. Câu hỏi về quyền đạt khi Kvis từ chối có nhắc tới quyền và không lộ số.
- Đề xuất điều chỉnh lưu `qty` lúc đề xuất và bị từ chối nếu lô đã đổi. Mọi đề xuất hết hạn sau 24 giờ.
- Bộ chấm điểm lưu kết quả và chạy tiếp được (`--resume`).
- `chat_logs` ghi trước để có `chat_id`; `result` của lần xác nhận lỗi ghi ở transaction thứ hai; `create_po` / `do_adjust` không tự khóa.
- ADR mới là ADR-016.

## Phần để người làm tự quyết
- Câu chữ cụ thể của lời dặn hệ thống và mô tả từng tool.
- Schema tham số chi tiết của từng tool, tên tiếng Việt hiện ở dòng "Đã tra".
- Nội dung 20 câu hỏi số liệu và 15 câu hỏi tài liệu (đúng các nhóm đã nêu).
- Kích thước đoạn tài liệu sau khi đo, CSS của thẻ đề xuất.
- Cách nhận ra lỗi "không hỗ trợ tool" của từng nhà cung cấp.
