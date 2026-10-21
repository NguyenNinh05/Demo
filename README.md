# SnapShop — Multimodal Search System for E-Commerce

Website thời trang (áo và quần H&M, khoảng 500 sản phẩm) có tìm kiếm bằng **chữ**, **giọng nói**,
**hình ảnh** và **chữ + ảnh**. Hệ thống hiểu ý định tiếng Việt ("áo phông dưới 100k",
"áo khoác 1tr5 đổ lại", "cho tui coi quần đùi hông quá 300 ngàn") và được tổ chức theo
kiến trúc 3 tầng như trong báo cáo.

## Cài đặt (macOS, Python 3.13, PostgreSQL 16)

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env             # điền GEMINI_API_KEY nếu có (không bắt buộc)
.venv/bin/python main.py --init-db       # tạo database "snapshop" + dữ liệu mẫu
.venv/bin/python main.py                 # mở http://127.0.0.1:8000
```

Lần chạy đầu sẽ tải các model CLIP (khoảng 1 GB) và tính vector cho ảnh sản phẩm (khoảng 1 phút).
Vector được cache trong `data/catalog/image_vectors.npz`.

| Lệnh | Việc |
|---|---|
| `python main.py` | Web shop + API docs tại `/docs` |
| `python main.py --text "áo phông dưới 100k"` | Tìm bằng chữ (console) |
| `python main.py --voice "cho tui coi quần đùi hông quá 300 ngàn"` | Giọng nói, transcript gõ tay |
| `python main.py --audio ghi_am.wav` | Giọng nói thật (Gemini STT) |
| `python main.py --image data/query_images/heldout_01_ao_ni.jpg` | Tìm bằng ảnh |
| `python main.py --text "màu đen" --image anh.jpg` | Chữ + ảnh |
| `python main.py --evaluate` | Chạy bộ đánh giá, ghi `results/evaluation.md` |
| `python main.py --build-index` | Tính lại vector ảnh |
| `python tools/export_erd.py` | Sinh ERD (Mermaid) từ database vào `docs/erd.md` |
| `python tools/label_occasions.py --single` | Gắn lại nhãn dịp cho sản phẩm bằng Gemini (sau đó `--init-db`) |

## Kiến trúc 3 tầng

```
presentation/   SearchUI (console), WebSearchUI (FastAPI) + templates/, static/
application/    QueryService      mọi đầu vào -> một biểu diễn truy vấn chung
                RuleParser        hiểu tiếng Việt bằng luật (~1 ms): giá, loại, màu, giới tính,
                                  chất liệu, họa tiết, kiểu dáng, dịp mặc, từ địa phương, lỗi gõ
                GeminiIntentParser  chỉ gọi khi luật không chắc chắn (câu mơ hồ)
                SpeechService     Soniox (realtime, key tạm cho trình duyệt) hoặc Gemini (dự phòng)
                SonioxClient      tạo key tạm, cấu hình stream, nhận dạng file ghi âm
                ImageService      CLIP: ảnh -> vector, câu tiếng Việt -> vector (cùng không gian)
                SearchService     điều phối: lọc SQL, BM25, fuzzy, ngữ nghĩa, ảnh; không có kết
                                  quả thì báo "Không tìm thấy", không tự bỏ điều kiện
                RankingService    S = α·S_text + β·S_image + γ·S_business
data/           ProductRepository, OrderRepository (PostgreSQL), TextIndex (BM25),
                VectorIndex (NumPy), schema.sql, catalog/ (ảnh + seed), query_images/
shared/         xử lý chuỗi tiếng Việt (bỏ dấu, tách từ) dùng chung
tools/          prepare_catalog.py, init_db.py, export_erd.py
```

Tầng Presentation chỉ gọi `SpeechService`, `ImageService`, `SearchService` và không bao giờ
import package `data`.

## Soniox — giọng nói realtime (tùy chọn)

Tạo API key tại https://console.soniox.com (cần gắn phương thức thanh toán, khoảng $0,12 cho mỗi
giờ âm thanh) rồi điền `SONIOX_API_KEY` vào `.env`. Khi có key, nút micro stream âm thanh thẳng
lên Soniox bằng key tạm do server cấp: chữ hiện ngay trong lúc nói (chữ đậm là đã chốt, chữ xám là
tạm) và tự dừng khi bạn ngừng nói. Không có key thì dùng Gemini (chữ hiện sau khi nói xong).

## DeepSeek — hiểu câu khó (tùy chọn, ưu tiên hơn Gemini)

Điền `DEEPSEEK_API_KEY` vào `.env`. Câu mà rule parser không chắc (độ tin cậy < 0,6) sẽ được
DeepSeek (`deepseek-flash`, chế độ suy nghĩ tắt) phân tích. Đo trên 33 câu: trung bình ~1,1 s,
chậm nhất ~1,6 s (Gemini free tier: trung bình ~4 s, có lúc 17 s). Chi phí khoảng $0,0002/câu.

## Gemini (tùy chọn)

Lấy key miễn phí tại https://aistudio.google.com/apikey rồi điền vào `.env`.

* **Không có key:** phần hiểu ý định dùng RuleParser (đủ cho hầu hết câu). Giọng nói dùng nhận dạng
  của trình duyệt (Chrome/Edge, vi-VN).
* **Có key:** câu khó ("đồ mặc đi biển", "quà cho bạn trai thích thể thao") được Gemini phân tích.
  Giọng nói được Gemini chép lời và chuẩn hóa từ địa phương.

## Dữ liệu

Ảnh và thông tin sản phẩm lấy từ bộ dữ liệu công khai H&M (Hugging Face
`tomytjandra/h-and-m-fashion-caption` + bảng articles của H&M), chỉ dùng cho mục đích học tập.
Giá (theo mức H&M Việt Nam), tồn kho, độ phổ biến, khách hàng và đơn hàng là dữ liệu mẫu.
Muốn tạo lại catalogue: `python tools/prepare_catalog.py --articles <articles.parquet>`.

**Dịp phù hợp** (đi làm, đi biển, trời lạnh, đi tiệc, tập thể thao…) không suy ra từ loại sản
phẩm mà được gắn sẵn cho từng sản phẩm: `tools/label_occasions.py` gửi Gemini ảnh, tên, chất liệu
và mô tả gốc của H&M kèm định nghĩa từng dịp, rồi áp các điều "KHÔNG gắn cho…" của định nghĩa thành
luật cứng (ví dụ áo sát nách không bao giờ là "đi làm"). Nhãn và lý do nằm trong
`data/catalog/occasions.json`; tìm "đồ đi biển" sẽ lọc theo nhãn này.

## Xem ERD

* `docs/erd.md` (Mermaid, sinh tự động từ database), hoặc
* DBeaver / pgAdmin: kết nối `snapshop`, chọn *View Diagram*, hoặc
* Visual Paradigm: *Tools → DB Modeling → Reverse Database* (PostgreSQL).
