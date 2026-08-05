# Member Role Report — Day 9: Multi Agent A2A


## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                |
| --------------- | --------------------------------------- |
| Họ và tên       | Nguyễn Vũ Việt Anh                      |
| MSSV            | 2A202601742                             |
| Khóa/Lớp        | K4 / D303                               |
| Vai trò chính   | Verifier / QA / Submission Lead         |
| Ngày hoàn thành | 2026-08-05                              |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm | Input | Output | Trạng thái |
| ------------------ | -------- | ----- | ------ | ---------- |
| Verifier Agent | `src/agents/verifier_agent.py` (`VerifierAgent.run`) | output đã ráp + evidence universe | `ok`, `issues[]` | Hoàn thành |
| Array-limit caps | `src/schema.py` (`cap`, `LIMITS`) | mảng thô | mảng đã cap | Hoàn thành |
| Đóng gói nộp bài | quy trình zip `output/` | 50 JSON | zip 50 file | Hoàn thành (hướng dẫn) |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Module | Kết quả |
| --------- | ------ | ------- |
| Rà null-handling unavailable | Payment/Delivery | phát hiện & chốt quy tắc null |
| Kiểm định dạng timestamp | Delivery | regex `YYYY-MM-DD HH:MM:SS` |

## 3. Kết quả theo vai trò

| Nhiệm vụ | File/artifact | Kết quả | Xác minh |
| -------- | ------------- | ------- | -------- |
| Kiểm schema/cap/enum/confidence | `verifier_agent.py` | 50/50 `ok=True` | grep trace `case_end` |
| Chống false-positive evidence | `verifier_agent.py` | mọi evidence ∈ universe từ data | trace `verify` |
| Đảm bảo zip đúng 50 file | quy trình nộp | không file lạ | `unzip -l` |

Output cụ thể: các event `verify` trong `logging/trace.jsonl` và tính hợp lệ toàn
bộ `output/`.

## 4. Giải thích phần kỹ thuật

### Vấn đề
Trước khi ghi file phải đảm bảo output không dính hard gate: sai schema, vượt cap
mảng, evidence không tồn tại, sai null-handling, sai định dạng timestamp, mâu thuẫn
tài chính với `case_status`.

### Cách triển khai
- Nhận `evidence_universe` (tập id hợp lệ tái dựng từ data) từ Coordinator; mọi
  evidence ngoài tập → issue.
- Kiểm cap từng mảng theo `LIMITS`; `confidence ∈ [0,1]`; `case_status ∈
  {action_required, no_action}`; refund nhất quán với status.
- Null-handling: nếu `expected=null` thì `difference`, `reconciled` cũng null và
  seller_handoff rỗng khi order không có item.
- Regex timestamp; trả `(ok, issues)` và ghi trace `verify`.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | output dict + evidence universe |
| Output | `(ok: bool, issues: list)` |
| Phụ thuộc | Coordinator (universe), tất cả agent (output) |
| Dùng output | Coordinator (quyết định ghi/log) |
| Điều kiện lỗi | mọi vi phạm được liệt kê thay vì crash |

### Cách xác minh
```bash
python run.py
python3 -c "import json;print(sum(1 for l in open('logging/trace.jsonl') if json.loads(l).get('event')=='case_end' and not json.loads(l)['ok']))"
```
- **Mong đợi:** 0 case fail.
- **Thực tế:** 0 case fail (50/50 pass).
- **Artifact:** `logging/trace.jsonl` event `verify`/`case_end`.

## 5. Quyết định kỹ thuật quan trọng

- **Bối cảnh:** kiểm evidence theo định dạng regex hay theo sự tồn tại thật trong data?
- **Phương án:** (1) chỉ regex format; (2) tái dựng universe từ data và so tập.
- **Đã chọn:** tái dựng universe từ data.
- **Lý do:** README coi evidence không tồn tại trong CSV là false positive; chỉ
  kiểm format sẽ bỏ sót id sai. Tái dựng universe bắt được cả sai format lẫn sai tồn tại.
- **Bằng chứng:** bug thiếu prefix `item:`/`payment:` bị bắt ngay khi so universe.

## 6. Lỗi/blocker đã xử lý

- **Triệu chứng:** evidence item/payment sai định dạng ở bản đầu.
- **Tái hiện:** chạy bản đầu, so evidence với universe.
- **Nguyên nhân gốc:** Policy nối id thiếu prefix `item:`/`payment:`.
- **Xử lý:** phối hợp Policy thêm prefix; Verifier xác nhận lại.
- **Xác minh:** 50/50 `ok=True` sau sửa.
- **Bài học:** khâu verify độc lập bắt lỗi mà agent sinh dữ liệu không tự thấy.

## 7. Hiểu biết end-to-end

1. Case → output qua 6 agent, Coordinator điều phối, Verifier gác cổng.
2. Số liệu do tool tất định; LLM ≤10B chỉ annotate rationale/confidence.
3. Verifier khác việc ghi thẳng: kiểm cap/null/enum/evidence để chặn hard gate.
4. Cùng EC_POLICY_V2 cho 50 case → công bằng, tái lập.
5. Case pass khi `verify.ok=True` + đúng schema; nộp = zip đúng 50 JSON, không file lạ.

## 8. Cam kết
- [x] Đúng phần việc và mức hiểu.
- [x] Giải thích được end-to-end.
- [x] Không khai khống.
- [x] Không secret.
- [x] Không sao chép nguyên văn.

**Họ và tên:** Nguyễn Vũ Việt Anh
**Ngày xác nhận:** 2026-08-05
