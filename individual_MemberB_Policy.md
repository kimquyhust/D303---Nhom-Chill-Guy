# Member Role Report — Day 9: Multi Agent A2A


## 1. Thông tin cá nhân

| Thông tin       | Nội dung                        |
| --------------- | ------------------------------- |
| Họ và tên       | [Họ và tên]                     |
| MSSV            | [MSSV]                           |
| Khóa/Lớp        | K4                               |
| Vai trò chính   | Policy / Business-Rules Agent    |
| Ngày hoàn thành | 2026-08-05                       |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm | Input | Output | Trạng thái |
| ------------------ | -------- | ----- | ------ | ---------- |
| Policy rule engine | `src/agents/policy_agent.py` (`PolicyAgent.run`) | findings 4 agent + order status | primary/secondary, refund, evidence, actions, confidence | Hoàn thành |
| Bảng ánh xạ chính sách | `ROOT_CAUSE`, `PRIMARY_ACTION`, `CONFIDENCE` | EC_POLICY_V2 | hằng số taxonomy | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Module | Kết quả |
| --------- | ------ | ------- |
| Đối chiếu worked-example README | toàn pipeline | EC_002 khớp từng trường (actions, refund) |
| Rà thứ tự secondary/actions | Coordinator | thứ tự cố định đúng spec |

## 3. Kết quả theo vai trò

| Nhiệm vụ | File/artifact | Kết quả | Xác minh |
| -------- | ------------- | ------- | -------- |
| Encode 6 primary issue theo strict priority | `policy_agent.py` | phân loại đúng 50 case | bảng phân bố 8/6/10/10/8/8 |
| Refund theo loại issue | `policy_agent.py` | full payment / freight / 0 | so `financial_resolution` |
| Thứ tự actions + loại trừ | `policy_agent.py` | khớp README | EC_002/EC_022/EC_012 |

Output cụ thể: trường `case_assessment`, `root_cause_analysis`,
`financial_resolution`, `resolution_actions`, `evidence_ids` của cả 50 case.

## 4. Giải thích phần kỹ thuật

### Vấn đề
Áp `EC_POLICY_V2` chính xác: **để agent LLM (≤10B) ra phán quyết** primary issue
theo strict priority (không dùng if/else làm bộ quyết định chính), trong khi vẫn
giữ tiền/evidence/id chính xác — đây là phần dễ bị hard gate nhất.

### Cách triển khai (hybrid: LLM quyết định, tool cấp số)
- **LLM ra quyết định:** Policy Agent dựng một *fact sheet* từ tool (order_status,
  paid, delivered_late, late_handoff_seller_ids, n_payments, reconciled, counts)
  rồi gọi model ≤10B với bảng EC_POLICY_V2 trong system prompt; model trả JSON
  `{primary_issue, confidence, reason}`. Đây là phán quyết cốt lõi (drive
  case_status, root cause, refund, responsible, actions).
- **Fallback + guardrail:** nếu không có endpoint hoặc reply sai định dạng →
  rule engine tất định `_rule_primary` đỡ (log `source=rule_fallback`). Cờ
  `POLICY_GUARDRAIL=1` cho phép ép rule engine khi LLM lệch (mặc định tắt; luôn
  log `llm_vs_rule_disagreements` để đo độ chính xác model).
- **Hệ quả cơ học (từ tool, không phải judgment):** refund = full payment/freight/0
  lấy số từ Payment; responsible ids từ `late_handoff_seller_ids`; evidence =
  order+item+payment+responsible seller+policy; actions theo thứ tự cố định.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | order status, findings customer/op/pay/delivery |
| Output | dict assessment/refund/evidence/actions |
| Phụ thuộc | Delivery (late flags), Payment (reconciled), Order&Product (counts) |
| Dùng output | `assemble_output`, Verifier |
| Điều kiện lỗi | order 0 item (reconciled=None) → không rơi nhầm valid_split |

### Cách xác minh
```bash
python run.py --only EC_002 EC_022 EC_012
```
- **Mong đợi:** EC_002 actions `[refund_freight, review_seller_handoff, verify_payment_allocation]`; EC_022 chỉ `[explain_valid_split_payment]`; EC_012 full refund.
- **Thực tế:** đúng cả ba.
- **Artifact:** `output/EC_002.json`, `EC_022.json`, `EC_012.json`.

## 5. Quyết định kỹ thuật quan trọng

- **Bối cảnh:** điều kiện thêm `verify_refund_completion` — mọi refund hay chỉ
  full-refund?
- **Phương án:** (1) thêm khi refund>0 (mọi refund); (2) chỉ khi `issue_full_refund`.
- **Đã chọn:** chỉ full-refund (canceled/unavailable).
- **Lý do:** worked-example EC_002 (refund freight) KHÔNG có `verify_refund_completion`
  → chứng minh nó gắn với full refund, không gắn refund freight.
- **Bằng chứng:** EC_002 tái tạo đúng chuỗi action như README.

## 6. Lỗi/blocker đã xử lý

- **Triệu chứng:** ban đầu định thêm `verify_refund_completion` cho mọi action_required
  → lệch example.
- **Tái hiện:** so EC_002 với README.
- **Nguyên nhân gốc:** hiểu sai điều kiện trigger action bổ sung.
- **Xử lý:** gắn `verify_refund_completion` chỉ cho primary full-refund.
- **Xác minh:** EC_002 actions khớp README chính xác.
- **Bài học:** dùng worked-example làm oracle để chốt các điều kiện mơ hồ.

## 7. Hiểu biết end-to-end

1. Case → output qua 6 agent do Coordinator điều phối.
2. Policy Agent để **LLM ≤10B ra phán quyết** primary issue từ fact sheet; tool cấp
   số chính xác; rule engine chỉ là fallback/guardrail (log lại độ lệch).
3. Verifier kiểm evidence/cap/null trước khi ghi.
4. Cùng EC_POLICY_V2 cho 50 case → công bằng, tái lập.
5. Case pass khi Verifier `ok=True` và khớp schema.

## 8. Cam kết
- [x] Đúng phần việc và mức hiểu.
- [x] Giải thích được end-to-end.
- [x] Không khai khống.
- [x] Không secret.
- [x] Không sao chép nguyên văn.

**Họ và tên:** [Họ và tên]
**Ngày xác nhận:** 2026-08-05
