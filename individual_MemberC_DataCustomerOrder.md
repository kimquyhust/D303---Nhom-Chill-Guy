# Member Role Report — Day 9: Multi Agent A2A


## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                  |
| --------------- | ----------------------------------------- |
| Họ và tên       | [Họ và tên của bạn]                       |
| MSSV            | [MSSV]                                     |
| Khóa/Lớp        | K4                                         |
| Vai trò chính   | Data Agent — Customer & Order/Product      |
| Ngày hoàn thành | 2026-08-05                                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | --------------- | ---------- |
| Customer Agent | `src/agents/customer_agent.py`; `DataStore.customer_tool` | `claimed_order_id` | `customer_unique_id`, `related_order_ids` | Hoàn thành |
| Order & Product Agent | `src/agents/order_product_agent.py`; `DataStore.order_product_tool`, `_category_name` | `claimed_order_id` | item_ids, seller_ids, product_ids, category_names, item_rows | Hoàn thành |

Hai module này là **nguồn dữ liệu đầu vào bắt buộc** cho Payment Agent (cần
price/freight từ `item_rows`), Delivery Agent (cần `shipping_limit_date` từ
`item_rows`) và Policy Agent (cần cờ multi_item / multi_seller / repeat_customer /
multiple_categories).

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Module được hỗ trợ | Kết quả |
| --------- | ------------------ | ------- |
| Xác minh khớp worked-example EC_002 | Toàn pipeline | EC_002 tái tạo đúng số liệu README (variance 87.39, refund 18.27) |
| Tổng hợp bảng phân bố 50 case | Coordinator/Policy | 8/6/10/10/8/8 theo primary issue, khớp status distribution |

## 3. Kết quả theo vai trò

| Nhiệm vụ | File/artifact | Kết quả bàn giao | Cách xác minh |
| -------- | ------------- | ---------------- | ------------- |
| Resolve customer identity + history | `customer_tool` | `customer_unique_id` + related orders (chỉ vào `customer_context`, KHÔNG vào `affected_entities`) | `python run.py --only EC_001` → kiểm `related_order_ids` |
| Join item→product→seller | `order_product_tool` | item/seller/product/category theo thứ tự nguồn, cap đúng | so output/EC_008 (multi-seller, multi-category) |
| Null-safe cho order 0 item | `order_product_tool` | mảng rỗng cho unavailable orders | output/EC_012 arrays rỗng |

Output cụ thể do phần việc của tôi tạo: `product_context` và các cột
`affected_entities.item_ids/seller_ids/product_ids` của cả 50 file, cùng
`customer_context` (identity + related orders).

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Từ một `claimed_order_id`, phải (a) nhận diện đúng khách hàng và các order lịch sử
của họ, (b) dựng đầy đủ item/seller/product/category của order — nhưng phải tách
bạch order lịch sử (chỉ để tham chiếu) với order đang khiếu nại (mới được đưa vào
`affected_entities`).

### Cách triển khai

- **Identity**: `orders.customer_id → customers.customer_unique_id`. Lịch sử lấy
  bằng cách gom toàn bộ order có cùng `customer_unique_id`, loại chính order đang
  xét, giữ thứ tự xuất hiện trong `orders` (ổn định), cap 5.
- **Composition**: gom `order_items` theo `order_id`, sort theo `order_item_id`,
  dựng `item_ids = "<order_id>:<order_item_id>"`, thu `seller_ids`, `product_ids`,
  `category_names` theo thứ tự xuất hiện, khử trùng lặp giữ thứ tự.
- **Category**: mặc định dùng tên gốc (pt) trong `products.product_category_name`
  để trung thành dữ liệu nguồn; có cờ `USE_ENGLISH_CATEGORY` để chuyển english.
- **Null handling**: order 0 item → mọi mảng rỗng, `n_items = 0`, truyền tín hiệu
  để Payment Agent set expected/difference/reconciled = null.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | `claimed_order_id` (str) |
| Output | dict: `customer_unique_id`, `related_order_ids`; và item/seller/product/category + `item_rows` |
| Module phụ thuộc | `DataStore` (orders, customers, order_items, products, sellers) |
| Module dùng output | Payment Agent, Delivery Agent, Policy Agent |
| Điều kiện lỗi | order_id không có trong data → customer null, mảng rỗng (không crash) |

### Cách xác minh

```bash
python run.py --only EC_001 EC_008 EC_012
python3 -c "import json;o=json.load(open('output/EC_012.json'));print(o['affected_entities'],o['customer_context'])"
```

- **Kết quả mong đợi:** EC_012 (unavailable) có item/seller/product rỗng, vẫn có
  `customer_unique_id` + related orders.
- **Kết quả thực tế:** đúng như mong đợi (arrays rỗng, identity vẫn resolve).
- **Artifact/log:** `output/EC_012.json`, `logging/trace.jsonl` (event customer_tool / order_product_tool).

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** `product_context.category_names` nên dùng tên tiếng Bồ (gốc) hay
  tiếng Anh (bảng translation)?
- **Phương án đã cân nhắc:** (1) giữ nguyên `product_category_name` gốc; (2) map
  sang english qua `product_category_name_translation.csv`.
- **Phương án đã chọn:** giữ tên gốc, đặt sau cờ config `USE_ENGLISH_CATEGORY`.
- **Lý do:** README nhấn mạnh "ưu tiên dữ liệu có thể kiểm chứng"; tên gốc là giá
  trị trực tiếp trên product row, không qua phép biến đổi. Cờ config cho phép lật
  nhanh nếu leaderboard cho thấy grader dùng english.
- **Bằng chứng phù hợp:** category khớp trực tiếp giá trị cột nguồn khi đối chiếu
  `products.csv`.

## 6. Một lỗi đã xử lý

- **Triệu chứng:** evidence_ids item/payment thiếu tiền tố (`<oid>:1` thay vì
  `item:<oid>:1`), sai định dạng theo README §5 → false positive.
- **Bước tái hiện:** chạy bản đầu, xem `output/EC_002.json` evidence_ids.
- **Nguyên nhân gốc:** Policy Agent nối thẳng `item_ids`/`payment_ids` (đã ở dạng
  `oid:seq`) mà không thêm prefix `item:`/`payment:`.
- **Cách xử lý:** đổi thành `[f"item:{i}" ...]`, `[f"payment:{p}" ...]` trong
  `policy_agent.py`.
- **Xác minh sau sửa:** Verifier Agent so evidence với "evidence universe" dựng lại
  từ data — 50/50 case `ok=True`.
- **Điều học được:** phải để một agent độc lập (Verifier) tái dựng tập evidence hợp
  lệ từ nguồn thay vì tin định dạng do agent khác sinh.

## 7. Hiểu biết về luồng end-to-end

1. **Case → output:** Coordinator đọc `input/EC_XXX.json`, lấy `claimed_order_id`,
   lần lượt gọi Customer → Order&Product → Payment → Delivery → Policy → Verifier,
   ráp bằng `assemble_output`, ghi `output/EC_XXX.json`.
2. **Phân vai LLM vs tool (hybrid):** model ≤10B **ra phán quyết** primary issue
   theo EC_POLICY_V2 từ fact sheet; còn **số liệu** (tiền/giờ/count) do tool tất định
   tính để model 7-8B không tự làm sai số học. Phần data của tôi (customer/order/
   product) thuộc lớp tool — cấp dữ kiện chính xác cho LLM quyết định.
3. **Verifier khác gì ghi thẳng:** Verifier tái dựng evidence universe từ data,
   kiểm cap mảng, dải confidence, enum case_status, null handling, định dạng
   timestamp — chặn hard gate trước khi file được ghi.
4. **Vì sao cùng EC_POLICY_V2 cho cả 50 case:** để so sánh công bằng và tái lập;
   luật áp theo strict priority nên mọi case đi qua cùng cây quyết định.
5. **Case pass dựa trên gì:** trace `case_end.ok=True` (Verifier pass) + output khớp
   schema; worked-example EC_002 khớp từng trường với README là bằng chứng chuẩn.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm/thành viên khác.

**Họ và tên:** [Họ và tên của bạn]
**Ngày xác nhận:** 2026-08-05
