# Member Role Report — Day 9: Multi Agent A2A


## 1. Thông tin cá nhân

| Thông tin       | Nội dung                               |
| --------------- | -------------------------------------- |
| Họ và tên       | Nguyễn Kim Quý                         |
| MSSV            | 2A202601456                             |
| Khóa/Lớp        | K4                                      |
| Vai trò chính   | Orchestration & Coordinator            |
| Ngày hoàn thành | 2026-08-05                             |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm | Input | Output | Trạng thái |
| ------------------ | -------- | ----- | ------ | ---------- |
| Coordinator agent | `src/agents/coordinator.py` (`process`, `_evidence_universe`) | case dict | output JSON + handoff | Hoàn thành |
| Entry point & batch runner | `run.py` (`load_cases`, `main`, `write_metadata`) | `input/` | 50 outputs, metadata | Hoàn thành |
| Kiến trúc & tài liệu | `architecture.md` | thiết kế nhóm | sơ đồ agent + luồng | Hoàn thành |
| Contract dữ liệu giữa agent | `src/schema.py` interface | findings | output đã ráp | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Module | Kết quả |
| --------- | ------ | ------- |
| Chuẩn hóa thứ tự handoff | tất cả agent | mỗi downstream agent luôn có đủ input |
| Dựng evidence universe cho Verifier | Verifier | Verifier kiểm được false positive |

## 3. Kết quả theo vai trò

| Nhiệm vụ | File/artifact | Kết quả | Xác minh |
| -------- | ------------- | ------- | -------- |
| Điều phối 7 agent theo thứ tự cố định | `coordinator.py` | 50 case chạy end-to-end | `python run.py` |
| Ghi trace thật + metadata | `run.py`, `trace.py` | `logging/trace.jsonl` (1400 dòng), `metadata.json` | đếm dòng trace |
| Xử lý order thiếu | `process` | log warning, không crash | test order_id giả |

Output cụ thể: toàn bộ `logging/trace.jsonl` và `logging/metadata.json`, cùng cấu
trúc file `output/EC_*.json` (assembly).

## 4. Giải thích phần kỹ thuật

### Vấn đề
Cần một orchestrator để 6 agent domain trao đổi kết quả (A2A) theo đúng thứ tự phụ
thuộc, ráp thành output đúng schema và verify trước khi ghi.

### Cách triển khai
- `process()` gọi tuần tự Customer → Order&Product → Payment → Delivery → Policy →
  Verifier; mỗi lời gọi nhận findings của bước trước.
- `_evidence_universe()` tái dựng tập evidence id hợp lệ (order/item/payment/seller/
  policy) từ tool để Verifier đối chiếu.
- `run.py` truncate trace mỗi lượt (chỉ giữ run mới nhất), sinh metadata phản ánh
  provider/model/mode thực tế.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | `input/EC_XXX.json` |
| Output | `output/EC_XXX.json` + trace + metadata |
| Phụ thuộc | 6 agent, `assemble_output`, `Tracer`, `LLMClient` |
| Dùng output | grader (output/), báo cáo nhóm (trace/metadata) |
| Điều kiện lỗi | order_id không có → warning + tiếp tục |

### Cách xác minh
```bash
python run.py
python3 -c "import json;print(sum(1 for _ in open('logging/trace.jsonl')))"
```
- **Mong đợi:** 50 output, trace nhiều dòng, mọi `case_end.ok=True`.
- **Thực tế:** 50 output, 1400 dòng trace, 0 verifier failure.
- **Artifact:** `output/`, `logging/`.

## 5. Quyết định kỹ thuật quan trọng

- **Bối cảnh:** dùng framework multi-agent nặng (LangGraph/CrewAI) hay orchestration
  Python tường minh?
- **Phương án:** (1) LangGraph; (2) custom Python explicit handoff.
- **Đã chọn:** custom Python.
- **Lý do:** thời gian thi 4h, cần tái lập tuyệt đối và trace tự kiểm soát; framework
  nặng tốn thời gian setup/debug mà không tăng điểm (điểm đến từ output tất định).
- **Bằng chứng:** toàn pipeline 50 case chạy < 0.1s, trace đầy đủ handoff.

## 6. Lỗi/blocker đã xử lý

- **Triệu chứng:** `ImportError: cannot import name 'ROOT_CAUSE_CODES'` khi khởi động.
- **Tái hiện:** `python run.py` bản đầu.
- **Nguyên nhân gốc:** import hằng số không tồn tại trong `coordinator.py`.
- **Xử lý:** bỏ import thừa, dùng `ROOT_CAUSE` từ `policy_agent`.
- **Xác minh:** `python run.py --only EC_001` chạy sạch.
- **Bài học:** giữ import tối thiểu, để module sở hữu hằng số export rõ ràng.

## 7. Hiểu biết end-to-end

1. Case → output: Coordinator đọc input, điều phối 6 agent, ráp + verify + ghi file.
2. Số liệu do tool tất định tạo; LLM ≤10B chỉ thêm rationale/confidence vào trace.
3. Verifier tái dựng evidence universe + kiểm cap/null/enum trước khi ghi.
4. Cùng EC_POLICY_V2 áp cho 50 case để công bằng & tái lập.
5. Case pass khi `case_end.ok=True` và output đúng schema.

## 8. Cam kết
- [x] Đúng phần việc và mức hiểu của tôi.
- [x] Giải thích được end-to-end.
- [x] Không khai "chạy thành công" cho phần chưa kiểm chứng.
- [x] Không chứa secret.
- [x] Không sao chép nguyên văn báo cáo khác.

**Họ và tên:** Nguyễn Kim Quý

