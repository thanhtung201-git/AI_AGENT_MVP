# Kịch bản thuyết trình — AI Agent MVP
### Dành cho đối tác không có kỹ thuật

---

## MỤC LỤC

1. [Chuẩn bị trước khi thuyết trình](#1-chuẩn-bị)
2. [Phần mở đầu — Bài toán của mình](#2-mở-đầu)
3. [Giới thiệu giải pháp](#3-giới-thiệu-giải-pháp)
4. [Demo từng tab](#4-demo-từng-tab)
5. [Luồng chạy Tab Tạo Trim List](#5-luồng-chạy-chi-tiết)
6. [So sánh con số](#6-so-sánh-con-số)
7. [Xử lý tình huống bất ngờ](#7-xử-lý-tình-huống-bất-ngờ)
8. [Câu hỏi khó — Trả lời sẵn](#8-câu-hỏi-khó)
9. [Câu kết](#9-câu-kết)

---

## 1. CHUẨN BỊ

**Trước khi thuyết trình 10 phút:**
- Mở sẵn trình duyệt vào `localhost:3000`
- Để sẵn 1 file PO chưa xử lý trong folder scan
- Tắt hết thông báo máy tính
- Chuẩn bị 1 địa chỉ email thật để demo gửi mail
- Không mở màn hình ngay — nói phần mở đầu trước

---

## 2. MỞ ĐẦU — Bài toán của mình
*Chưa mở máy tính. Nhìn thẳng vào đối tác.*

---

> *"Tôi xin bắt đầu bằng một câu chuyện thực tế từ chính công ty chúng tôi."*

> *"Trước đây, mỗi khi nhận được file đơn đặt hàng từ khách — nhân viên phải mở file ra, đọc từng dòng, rồi tự nhập lại vào Excel để tạo danh sách nguyên phụ liệu. Sau đó soạn email gửi cho từng nhà cung cấp."*

> *"Một file mất 20–30 phút. Tuần cao điểm có 10 đơn — tức là 2–3 tiếng mỗi tuần chỉ để nhập liệu. Không tạo ra giá trị gì, chỉ là copy từ chỗ này sang chỗ khác."*

> *"Nhưng vấn đề lớn hơn không phải là mất thời gian — mà là nhập tay thì nhầm. Và chúng tôi đã từng nhầm. Một lần nhập sai số lượng trong bảng size, nhà cung cấp cắt thiếu vải, cả lô hàng bị chậm giao, phải đền hợp đồng."*

> *"Từ đó chúng tôi đặt câu hỏi: có cách nào để máy làm phần việc này thay người không?"*

> *"Và đây là thứ chúng tôi xây dựng ra để giải quyết đúng bài toán đó."*

*(Mở màn hình)*

---

## 3. GIỚI THIỆU GIẢI PHÁP

> *"Hệ thống này làm được 3 việc chính:"*

> *"Một — đọc file đơn hàng tự động, không cần nhân viên nhập tay."*

> *"Hai — tạo ra danh sách nguyên phụ liệu đúng chuẩn, đúng format công ty đang dùng."*

> *"Ba — gửi thẳng cho nhà cung cấp qua email hoặc Telegram, một nút bấm."*

> *"Tôi sẽ chạy thật ngay bây giờ — không phải video quay sẵn."*

---

## 4. DEMO TỪNG TAB

---

### TAB 1 — DASHBOARD

*(Bấm vào Dashboard)*

> *"Đây là màn hình tổng quan — nơi đầu tiên nhân viên nhìn vào mỗi sáng khi mở hệ thống lên."*

> *"Nhìn vào 5 giây là biết hôm nay công việc đang ở đâu — bao nhiêu file đã xử lý, bao nhiêu file cần xem lại. Không cần mở từng file ra kiểm tra."*

---

### TAB 2 — TẠO TRIM LIST

*(Bấm vào Tạo Trim List)*

> *"Đây là tab quan trọng nhất — nơi diễn ra toàn bộ quá trình xử lý tự động."*

**Folder đang theo dõi:**
> *"Ô này hiển thị folder mà hệ thống đang theo dõi. Nhân viên chỉ cần bỏ file PO vào đúng folder này — hệ thống tự biết có file mới."*

**3 con số tổng quan:**
> *"Ba con số này cho biết: tổng file trong folder, đã xử lý bao nhiêu, và có bao nhiêu file mới chưa xử lý. Nếu File mới lớn hơn 0 — có việc cần làm."*

**Nút Quét lại:**
> *"Nhân viên bấm nút này để hệ thống đọc và xử lý file mới. Hệ thống cũng tự kiểm tra mỗi 30 giây — đôi khi chưa kịp bấm thì nó đã tự chạy rồi."*

**Kết quả lần quét:**
> *"Sau khi quét xong, kết quả hiện ra ngay — file nào thành công hiện xanh, file nào có vấn đề hiện đỏ kèm lý do cụ thể."*

**Bảng lịch sử:**
> *"Phía dưới là toàn bộ lịch sử — mỗi dòng là một file đã xử lý với đầy đủ: số PO, style, số lượng, số loại trim, thời gian xử lý."*

> *"Mỗi dòng có các nút: tải PO gốc, tải Trim List Excel, tải PDF, gửi Email, gửi Telegram, và reset để xử lý lại nếu cần."*

---
## 5. LUỒNG CHẠY CHI TIẾT — TAB TẠO TRIM LIST

---

**Giải thích trước khi demo:**

> *"Hệ thống cần 2 loại file để hoạt động."*

> *"Loại thứ nhất là file PO — đơn đặt hàng từ khách. Có: số PO, tên style, số lượng, màu sắc, size."*

> *"Loại thứ hai là file Techpack — tài liệu kỹ thuật sản phẩm. Có: danh sách toàn bộ nguyên phụ liệu cần dùng."*

> *"Hệ thống đọc cả hai, kết hợp lại, tạo ra Trim List hoàn chỉnh."*

---

### BƯỚC 1 — Nhân viên bỏ file vào folder

> *"Nhân viên nhận file PO từ email khách hàng — kéo thả vào folder chỉ định. Xong. Không cần làm gì thêm. Folder này giống hòm thư đến — bỏ vào đó là hệ thống tự biết."*

---

### BƯỚC 2 — Hệ thống phát hiện file mới

> *"Cứ 30 giây hệ thống tự kiểm tra folder một lần. Khi có file mới — badge đỏ hiện lên ngay, không cần reload trang. Nhân viên bấm Quét lại để bắt đầu."*

---

### BƯỚC 3 — Đọc file PO

> *"Hệ thống đọc file tùy loại: PDF có chữ thì đọc thẳng text, Word/Excel thì đọc từng ô, ảnh chụp hoặc PDF scan thì dùng AI nhận dạng chữ viết — giống như con người đọc ảnh vậy."*

---

### BƯỚC 4 — AI trích xuất thông tin

> *"Hệ thống đưa nội dung vào AI — AI phân tích và tìm ra: số PO, tên style, tổng số lượng, bảng size, ngày giao hàng."*

> *"AI làm việc này giống nhân viên có kinh nghiệm đọc hợp đồng — biết chỗ nào quan trọng, chỗ nào bỏ qua. Nếu không chắc thông tin nào — không tự điền bừa, báo lại để nhân viên kiểm tra."*

---

### BƯỚC 5 — Kiểm tra tự động

> *"Trước khi đi tiếp, hệ thống tự kiểm tra 2 thứ:"*

> *"Một: tổng size cộng lại có bằng tổng số lượng đơn không. S 100 + M 150 + L 100 phải bằng đúng 350. Nếu không khớp — báo đỏ ngay."*

> *"Hai: đơn giá nhân số lượng có bằng thành tiền không. Lệch dù 1 đồng — hệ thống phát hiện."*

---

### BƯỚC 6 — Tìm file Techpack

> *"Hệ thống lấy mã style từ PO vừa đọc, so khớp với tên file trong thư mục Techpack. Nếu tìm thấy — tiếp tục. Nếu không — lưu kết quả PO lại và báo: chưa có Techpack, cần bổ sung."*

---

### BƯỚC 7 — Đọc và trích xuất trim từ Techpack

> *"AI đọc Techpack và tìm ra: từng loại trim cần gì, thông số kỹ thuật, nhà cung cấp, đơn vị, số lượng cần bao nhiêu. Số lượng trim được tính tự động dựa trên tổng số lượng đơn hàng — không nhập tay."*

---

### BƯỚC 8 — Xử lý trùng lặp

> *"Cùng một loại trim xuất hiện nhiều lần trong Techpack — hệ thống tự nhận ra và gộp thành một dòng. Không để danh sách bị rối hoặc đặt hàng trùng."*

---

### BƯỚC 9 — Tạo file Excel Trim List

> *"Hệ thống xuất ra file Excel đúng format chuẩn của công ty: header đầy đủ thông tin PO, bảng trim items với đầy đủ cột, dòng tổng cộng ở cuối. File này sẵn sàng gửi cho nhà cung cấp — không cần chỉnh sửa gì thêm."*

---

### BƯỚC 10 — Lưu vào hệ thống

> *"Toàn bộ kết quả được lưu vào database. Tắt máy, mất điện, reload trang — dữ liệu vẫn còn nguyên."*

---

### BƯỚC 11 — Nhân viên xác nhận và gửi

> *"Nhân viên xem qua kết quả, xác nhận đúng, bấm gửi Email hoặc Telegram — một nút duy nhất."*

---

### TAB 3 — RECAP TRIM

*(Bấm vào Recap Trim)*

> *"Tab này giải quyết bài toán khác — không phải xử lý từng file, mà tổng hợp nhiều đơn hàng lại với nhau."*

> *"Thực tế trong một tuần có thể có 5–10 đơn từ các khách khác nhau, nhưng đều cần cùng loại nguyên phụ liệu. Nếu đặt từng đơn riêng lẻ thì vừa tốn công, vừa không được giá tốt."*

**Phần chọn sessions:**
> *"Nhân viên tick chọn những đơn muốn gộp lại — theo tuần, theo khách hàng, hoặc theo nhà cung cấp."*

**Nút Tổng hợp Trim:**
> *"Bấm nút này, hệ thống tự tìm trim giống nhau từ các đơn đã chọn và cộng dồn số lượng. Cúc 4 lỗ xuất hiện trong 3 đơn — gộp thành 1 dòng với tổng số lượng."*

**Kết quả:**
> *"Bảng kết quả đầy đủ: tên trim, thông số, nhà cung cấp, tổng số lượng từ tất cả đơn đã chọn. Tải Excel về hoặc gửi thẳng cho nhà cung cấp."*

**Lịch sử Recap:**
> *"Mỗi lần tổng hợp đều được lưu lại — tuần sau mở ra vẫn còn, không cần làm lại."*

---

### TAB 4 — LỊCH SỬ

*(Bấm vào Lịch sử)*

> *"Tab này là kho lưu trữ toàn bộ những gì hệ thống đã làm từ trước đến nay."*

**Ô tìm kiếm:**
> *"Gõ vào đây bất kỳ thứ gì — số PO, tên style, tên file — hệ thống lọc ra ngay. Gõ một phần cũng tìm được."*

**Lọc theo ngày:**
> *"Chọn ngày cụ thể — chỉ hiện file xử lý trong ngày đó."*

**Bảng lịch sử:**
> *"Từ đây tải lại file bất kỳ lúc nào — Trim List Excel, PDF, hoặc gửi lại email nếu nhà cung cấp báo chưa nhận được."*

---

### TÓM TẮT 4 TAB

> *"Tóm lại: Dashboard để nhìn tổng quan — Tạo Trim List để xử lý file mới — Recap Trim để gộp nhiều đơn lại — Lịch sử để tra cứu bất kỳ lúc nào. Bốn tab, mỗi tab làm đúng một việc, không thừa không thiếu."*

---


### TÓM TẮT LUỒNG — NÓI 1 PHÚT

> *"Luồng có 4 giai đoạn:"*

> *"Giai đoạn 1 — Đầu vào: nhân viên bỏ file PO vào folder."*

> *"Giai đoạn 2 — AI đọc và hiểu: đọc file, trích xuất thông tin, kiểm tra số liệu."*

> *"Giai đoạn 3 — Tạo kết quả: tìm Techpack, đọc danh sách trim, tính số lượng, xuất Excel."*

> *"Giai đoạn 4 — Đầu ra: nhân viên xem — xác nhận — gửi."*

> *"Giai đoạn 2 và 3 diễn ra tự động trong 30–60 giây. Nhân viên chỉ làm giai đoạn 1 và 4 — tổng cộng chưa đến 3 phút."*

---

## 6. SO SÁNH CON SỐ

*Để màn hình sang một bên. Nhìn đối tác.*

| | Làm tay | Hệ thống |
|---|---|---|
| Xử lý 1 file PO | 20–30 phút | 30–40 giây |
| Tổng hợp 10 đơn/tuần | 2–3 tiếng | 2 phút |
| Tìm lại đơn cũ | Mở từng file | Gõ tên, ra ngay |
| Khả năng nhầm số | Có thể xảy ra | Hệ thống tự kiểm tra |
| Chi phí AI/tháng | — | Dưới 200 nghìn đồng |

> *"Với 10 đơn mỗi tuần, hệ thống tiết kiệm 10–15 tiếng làm việc mỗi tuần. Nhân viên đó có thể làm việc có giá trị hơn thay vì ngồi nhập liệu."*

---

## 7. XỬ LÝ TÌNH HUỐNG BẤT NGỜ

---

**Hệ thống xử lý chậm hơn bình thường:**
> *"AI đang đọc — tùy độ phức tạp của file, đôi khi cần thêm 30 giây. Thực tế nhân viên bấm rồi đi làm việc khác, quay lại là có kết quả."*

**File bị lỗi không xử lý được:**
> *"File này hệ thống báo không đọc được — có thể file bị hỏng hoặc không phải file đơn hàng. Hệ thống báo rõ để nhân viên biết kiểm tra lại, không im lặng cho qua."*

**Đối tác hỏi về độ chính xác:**
> *"AI đọc ra kết quả, nhân viên xem trước rồi mới gửi — không tự động hoàn toàn. Người vẫn là người quyết định cuối cùng."*

**Đối tác hỏi làm sao xác minh Trim List đúng:**
> *"Ba lớp kiểm tra: một là hệ thống tự kiểm tra số học, hai là nhân viên xem trước khi gửi, ba là anh/chị có thể mở Techpack gốc đối chiếu từng dòng ngay lúc này."*

---

## 8. CÂU HỎI KHÓ — TRẢ LỜI SẴN

---

**"AI có đọc sai không?"**
> *"Có thể sai với file quá mờ hoặc format lạ. Nhưng hệ thống luôn cho nhân viên xem kết quả trước khi gửi — họ xác nhận rồi mới gửi. Phần kiểm tra chỉ mất 1–2 phút thay vì 30 phút nhập tay."*

**"Dữ liệu có bị lộ không?"**
> *"Hệ thống chạy trên máy tính của công ty. Chỉ nội dung text bên trong file được gửi lên AI để đọc — không gửi file gốc, không lưu ở nước ngoài lâu dài."*

**"Nhân viên lớn tuổi có dùng được không?"**
> *"Hai thao tác: bỏ file vào folder, bấm Quét. Tập 15 phút là dùng được. Giao diện tiếng Việt hoàn toàn."*

**"Hệ thống sập thì sao?"**
> *"Nhân viên vẫn làm việc bình thường như trước — file vẫn còn đó, chỉ là xử lý tay thay vì tự động. Không có rủi ro mất dữ liệu."*

**"Chi phí hàng tháng bao nhiêu?"**
> *"Khoảng vài nghìn đồng mỗi file. Với 10 file/tuần, tổng chi phí AI dưới 200 nghìn/tháng — rẻ hơn 1 tiếng lương nhập liệu."*

**"Triển khai mất bao lâu?"**
> *"Chạy được trên máy tính Windows thông thường — không cần mua server. Triển khai và cấu hình 1–2 ngày. Tuần đầu có hỗ trợ trực tiếp."*

**"Muốn thêm tính năng sau này thì sao?"**
> *"Hệ thống xây theo kiến trúc module — thêm tính năng không ảnh hưởng phần đang chạy. Kết nối ERP, xuất báo cáo tự động, gửi Zalo đều làm được. Thời gian tùy tính năng, thường 1–3 tuần."*

**"Làm sao xác minh Trim List hoàn toàn hợp lý?"**
> *"Hệ thống lưu lại nguồn gốc từng trim lấy từ file Techpack nào. Anh/chị mở Techpack gốc và Trim List cạnh nhau đối chiếu từng dòng — AI chỉ đọc từ file đó ra, không thể bịa thêm."*

**"Tôi dùng thử trước được không?"**
> *"Được. Đưa cho tôi 1 file PO thật của công ty, tôi chạy ngay bây giờ và anh/chị tự đối chiếu kết quả với bản làm tay. Nếu khớp thì anh/chị tự tin, nếu không khớp thì mình biết cần điều chỉnh chỗ nào."*

---

## 9. CÂU KẾT

*Tắt màn hình. Nhìn thẳng đối tác.*

> *"Tóm lại — hệ thống này không thay thế nhân viên. Nó thay thế phần công việc nhàm chán nhất và dễ sai nhất: nhìn file rồi gõ lại."*

> *"Nhân viên vẫn là người quyết định — họ xem kết quả, xác nhận, rồi gửi. Nhưng thay vì mất 30 phút mỗi đơn, họ chỉ cần 2 phút kiểm tra."*

> *"Chúng tôi xây hệ thống này để giải quyết bài toán của chính mình. Nó đang chạy thực tế, không phải demo trên giấy."*

> *"Anh/chị có muốn thử với 1 file PO thật của công ty ngay bây giờ không?"*

---

## NGUYÊN TẮC QUAN TRỌNG NHẤT

> **Đừng nói về công nghệ — hãy nói về thời gian họ tiết kiệm được và lỗi họ tránh được.**

> **Đừng hỏi "công ty anh/chị đang gặp vấn đề gì" — mà kể "chúng tôi đã gặp vấn đề này và đây là cách chúng tôi giải quyết". Đối tác tự liên hệ với bài toán của họ mà không cảm thấy bị chỉ ra điểm yếu.**

---

*Tài liệu nội bộ — MCNA Garment AI Agent MVP*
