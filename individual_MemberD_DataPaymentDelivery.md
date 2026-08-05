# Member Role Report — Day 9: Multi Agent A2A


## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                 |
| --------------- | ---------------------------------------- |
| Họ và tên       | Nguyễn Văn Quân                           |
| MSSV            | 2A202601544                               |
| Khóa/Lớp        | K4                                        |
| Vai trò chính   | Data Agent — Payment & Delivery           |
| Ngày hoàn thành | 2026-08-05                                |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm | Input | Output | Trạng thái |
| ------------------ | -------- | ----- | ------ | ---------- |
| Payment Agent | `src/agents/payment_agent.py`; `DataStore.payment_tool` | item/freight totals | payment totals, difference, reconciled, payment_types | Hoàn thành |
| Delivery Agent | `src/agents/delivery_agent.py`; `DataStore.delivery_tool` | item_rows, order timestamps | delivery_variance, seller_handoff_analysis, late_handoff_seller_ids | Hoàn thành |
| Rounding chuẩn | `data_store.round2`, `_hours_between` | float/timestamp | làm tròn half-up 2dp | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Module | Kết quả |
| --------- | ------ | ------- |
| Xác định late_delivery_seller vs logistics | Policy | cung cấp `late_handoff_seller_ids` chính xác |
| Chuẩn hóa -0.0 → 0.0 | toàn output | difference_brl luôn 0.0 sạch |

## 3. Kết quả theo vai trò

| Nhiệm vụ | File/artifact | Kết quả | Xác minh |
| -------- | ------------- | ------- | -------- |
| Đối soát payment vs item+freight (sai số 0.10) | `payment_tool` | reconciled đúng, diff 0.0 cho 44 case có item | so `payment_reconciliation` |
| delivery_variance & handoff per seller | `delivery_tool` | EC_002: variance 87.39, handoff 1.04 | khớp README |
| Null cho order 0 item | `payment_tool` | expected/diff/reconciled=null | EC_012 |

Output cụ thể: toàn bộ `payment_reconciliation` và `delivery_analysis` của 50 case.

## 4. Giải thích phần kỹ thuật

### Vấn đề
Tính chính xác số tiền (đối soát) và số giờ (giao trễ, bàn giao trễ) — làm tròn 2dp,
xử lý timestamp null, và xác định seller nào bàn giao sau `shipping_limit_date`.

### Cách triển khai
- **Payment:** tổng `payment_value` theo order, so `expected = Σprice + Σfreight`,
  `reconciled = |diff| ≤ 0.10`. `payment_types` theo thứ tự `payment_sequential`.
- **Delivery:** `delivery_variance = delivered − estimated` (giờ). Với mỗi seller
  lấy `shipping_limit_date` **sớm nhất của seller đó**, `handoff_variance =
  carrier_handoff − shipping_limit`, `late_handoff = variance > 0`.
- **Rounding:** `Decimal` ROUND_HALF_UP 2dp, chuẩn hóa `-0.0 → 0.0`; null-safe khi
  timestamp thiếu (canceled/unavailable).

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | item_rows (price/freight/shipping_limit), order timestamps |
| Output | payment_reconciliation + delivery_analysis dicts |
| Phụ thuộc | Order&Product (item_rows) |
| Dùng output | Policy (late flags, reconciled), assemble_output |
| Điều kiện lỗi | delivered/carrier null → variance null, late=false |

### Cách xác minh
```bash
python run.py --only EC_002 EC_012
python3 -c "import json;o=json.load(open('output/EC_002.json'));print(o['delivery_analysis']['delivery_variance_hours'],o['payment_reconciliation']['expected_total_brl'])"
```
- **Mong đợi:** EC_002 → 87.39 và 212.27 (khớp README); EC_012 → variance null, expected null.
- **Thực tế:** đúng.
- **Artifact:** `output/EC_002.json`, `EC_012.json`.

## 5. Quyết định kỹ thuật quan trọng

- **Bối cảnh:** chọn `shipping_limit_date` nào cho mỗi seller khi seller có nhiều
  item?
- **Phương án:** (1) sớm nhất của seller; (2) muộn nhất.
- **Đã chọn:** sớm nhất.
- **Lý do:** README định nghĩa `handoff_variance = carrier − shipping_limit sớm nhất
  của seller`, và luật "carrier nhận sau ít nhất một shipping_limit" → dùng sớm nhất
  bắt được vi phạm sớm nhất.
- **Bằng chứng:** EC_002 handoff 1.04h, late_handoff=true khớp README.

## 6. Lỗi/blocker đã xử lý

- **Triệu chứng:** `difference_brl` đôi khi ra `-0.0`.
- **Tái hiện:** đối soát order khớp tuyệt đối.
- **Nguyên nhân gốc:** phép trừ float ra âm-zero.
- **Xử lý:** `round2` chuẩn hóa `-0.0 → 0.0`.
- **Xác minh:** mọi case reconciled hiển thị `0.0`.
- **Bài học:** chuẩn hóa zero khi so khớp/serialize JSON.

## 7. Hiểu biết end-to-end

1. Case → output qua 6 agent (Coordinator điều phối).
2. Số liệu (tiền/giờ) do tool tất định tính; LLM ≤10B chỉ annotate.
3. Verifier kiểm null/format/cap/evidence trước khi ghi.
4. Cùng EC_POLICY_V2 cho 50 case → công bằng, tái lập.
5. Case pass khi Verifier `ok=True` + đúng schema.

## 8. Cam kết
- [x] Đúng phần việc và mức hiểu.
- [x] Giải thích được end-to-end.
- [x] Không khai khống.
- [x] Không secret.
- [x] Không sao chép nguyên văn.

**Họ và tên:** Nguyễn Văn Quân
**Ngày xác nhận:** 2026-08-05
