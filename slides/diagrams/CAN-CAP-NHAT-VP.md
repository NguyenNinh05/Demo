# ⚠️ Cần cập nhật Visual Paradigm

Các ảnh trong `ve-lai/` được **vẽ lại bằng PlantUML** (mã nguồn trong `src/`) vì bản Visual Paradigm
cũ bị sai hoặc chưa có. Đây chỉ là bản tạm: **phải sửa lại trong file Visual Paradigm của nhóm**
để báo cáo và slide thống nhất.

Khi slide còn dùng ảnh vẽ lại, sơ đồ có viền cam và nhãn **"Hình vẽ lại · cần cập nhật Visual Paradigm"**.
Xuất ảnh từ VP (chuột phải vào sơ đồ → Export → PNG), đặt vào `slides/diagrams/<tên>.png`,
nhãn cam sẽ tự biến mất.

Hai ảnh VP cũ bị sai được giữ lại trong `vp-cu/` để đối chiếu.

| Ảnh | Việc cần làm trong Visual Paradigm |
|---|---|
| `component.png` | Sửa chính tả: "Applicaton / Intellgence Layer" → "Application / Intelligence Layer", "RankingServic" → "RankingService", "OrderRepositor" → "OrderRepository". Thêm **RuleParser** (QueryService ⇢ RuleParser) và **TextIndex** (SearchService ⇢ TextIndex). Gộp ProductDatabase và OrderDatabase thành một **PostgreSQL**, vì code dùng chung một database. |
| `erd.png` | Xóa các cột khóa ngoại bị lặp: `Orderorder_id` (Payment, OrderItem), `Productproduct_id` (OrderItem), `Categorycategory_id` (Product). Đổi `path_image` → `image_path` cho khớp code. Quan hệ Order – Payment đổi thành **1 – 0..1** cho khớp Class Diagram, và đặt `payment.order_id` là UNIQUE. |
| `class-input.png` | **Vẽ mới.** Gồm SearchUI, VoiceInput, ImageUpload (`<<boundary>>`); SpeechService, ImageService, QueryService, RuleParser, SearchService (`<<control>>`); Query (`<<entity>>`). SearchUI ◆— VoiceInput, SearchUI ◆— ImageUpload. Chữ ký hàm lấy đúng theo ảnh. |
| `class-search.png` | **Vẽ mới.** Gồm SearchService, RankingService, Candidate (Application Layer); ProductRepository, OrderRepository, TextIndex, VectorIndex, Product (Data Layer). ProductRepository **bỏ** stereotype `<<entity>>`: đây là lớp truy cập dữ liệu, thực thể là Product. |
| `seq-keyword.png` | **Vẽ mới.** Có khối `alt` "không có sản phẩm thỏa mọi điều kiện" → báo "Không tìm thấy sản phẩm phù hợp" (không nới điều kiện). |
| `seq-voice.png` | Thêm VoiceInput và RuleParser. Thay `all_products()` bằng `find(điều kiện, fuzzy_terms)` và `TextIndex.score(...)`. Đổi `top_k=5` → `top_k`. Thêm khối `alt` "không nhận dạng được giọng nói". Bỏ chọn mọi phần tử trước khi xuất (bản cũ bị dính lifeline xám và mũi tên tím). |
| `seq-image.png` | **Vẽ mới.** Có khối `alt` "ảnh không hợp lệ" và `loop` lấy sản phẩm từ ProductRepository. |

Muốn vẽ lại ảnh tạm sau khi sửa file `.puml`:

```bash
java -jar plantuml.jar -charset UTF-8 -tpng -o ../ve-lai slides/diagrams/src/*.puml
```
