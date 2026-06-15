## Giới thiệu

### Mục đích của tài liệu này
Tài liệu này là **đặc tả chức năng** (functional specification) cho các giao diện hướng đến người dùng cuối của
nền tảng **NuFi**: ứng dụng **NuFi Chat** (một bản fork tùy chỉnh của LibreChat) và
**NuFi Console** (cổng tự phục vụ để quản lý API key và theo dõi mức sử dụng). Tài liệu mô tả,
theo từng tính năng, những gì mỗi phần của sản phẩm được kỳ vọng thực hiện, giao diện người dùng
mà nó hiển thị, và các tiêu chí chấp nhận dùng để đánh giá hành vi đúng đắn.

Tài liệu này ra đời vì dự án được khởi động mà không có đặc tả bằng văn bản. Mục tiêu là trở thành
tài liệu tham chiếu chung duy nhất mà bộ phận QA / kiểm thử sử dụng để hiểu sản phẩm, thiết kế
các ca kiểm thử, và đánh giá liệu một bản build có hoạt động đúng hay không.

### Đối tượng sử dụng
- **Chính:** Kỹ sư QA / kiểm thử viên cần tìm hiểu sản phẩm và xác minh hành vi của nó.
- **Phụ:** Nhân viên thuộc bộ phận sản phẩm, hỗ trợ, và kỹ thuật cần một mô tả có thẩm quyền về
  hành vi được kỳ vọng.

Không yêu cầu kiến thức trước về LibreChat. Khi một hành vi được kế thừa từ LibreChat upstream,
nó được mô tả từ góc nhìn của người dùng cuối thay vì tham chiếu đến dự án upstream.

### Phạm vi
**Trong phạm vi** — các tính năng được *bật trong triển khai NuFi*:

- NuFi Chat: xác thực & truy cập tài khoản, chat cốt lõi (soạn / phát trực tuyến / chỉnh sửa /
  tái tạo / fork), lựa chọn endpoint & mô hình và các tham số cuộc hội thoại,
  **Agents & File Search (RAG)**, tải lên tệp theo từng tin nhắn, quản lý cuộc hội thoại (thanh
  bên, tìm kiếm, đổi tên, xóa, lưu trữ, đánh dấu trang, chia sẻ, xuất, multi-conversation,
  temporary chat), thư viện Prompts, và menu / cài đặt tài khoản (bao gồm liên kết đến Console).
- NuFi Console: xác thực & cấp phép just-in-time, trang hồ sơ, vòng đời API key
  (liệt kê, tạo, hiển thị một lần, thu hồi), và hiển thị ngân sách / mức sử dụng.

**Ngoài phạm vi** — các tính năng LibreChat upstream **không được bật** trong cấu hình NuFi,
bao gồm tìm kiếm web, trình thông dịch mã, giọng nói (TTS/STT), đăng nhập mạng xã hội / OAuth qua các
nhà cung cấp **khác ngoài Google** (GitHub, Discord, Facebook, Apple, OpenID, SAML — riêng đăng nhập
bằng Google thì **có** được bật và nằm trong phạm vi), và bất kỳ endpoint nào khác ngoài endpoint
**Nufi** tùy chỉnh duy nhất và endpoint **Agents**.
Khi một tính năng như vậy hiển thị trong code nhưng bị vô hiệu hóa qua cấu hình, nó sẽ được bỏ
qua hoặc được đánh dấu rõ ràng là *không được bật trong NuFi*.

### Cách đọc đặc tả này
Mỗi tính năng được tài liệu hóa theo một cấu trúc nhất quán để có thể đọc và kiểm thử đồng đều:

- **Mục đích** — một câu mô tả tính năng đó dùng để làm gì.
- **Điều kiện tiên quyết / truy cập** — những gì phải đúng (cấu hình, xác thực, trạng thái trước)
  trước khi tính năng có thể truy cập được.
- **Thành phần giao diện** — các điều khiển, trường nhập liệu, nhãn và biểu tượng người dùng thấy.
  Các nhãn thực tế và, khi hữu ích, các định danh bên dưới (translation key, `data-testid`) được
  trích dẫn để kiểm thử viên có thể xác định chính xác các phần tử.
- **Hành vi chức năng** — các phát biểu **FR-n** được đánh số mô tả chính xác những gì hệ thống thực hiện.
- **Trạng thái, trường hợp đặc biệt, kiểm tra hợp lệ & lỗi** — trạng thái trống, lỗi, giới hạn,
  và thông báo lỗi.
- **Tiêu chí chấp nhận** — các phát biểu **AC-n** được đánh số theo dạng *Giả sử / Khi / Thì*.
  Đây là các điều kiện có thể kiểm thử mà một bản build phải thỏa mãn.

> **Quy ước — các dấu hiệu "(verify: …)".** Bất cứ khi nào một chi tiết không thể xác nhận chắc
> chắn từ mã nguồn tại thời điểm viết, nó được chú thích `(verify: …)`. Đây là các cờ hiệu có
> chủ ý để kiểm thử viên xác minh với sản phẩm đang chạy, không phải các khẳng định thực tế.
> Hãy coi mỗi dấu hiệu như vậy là một nhiệm vụ kiểm thử nhỏ.

### Nguồn đáng tin cậy và phiên bản hóa
Hành vi được mô tả ở đây được suy ra từ các kho mã nguồn NuFi:

- **NuFi Chat** — bản fork LibreChat `dudaji-vn/nufichat`, nhánh release `fork/main`.
- **NuFi Console** — `dudaji-vn/nufi-console`, nhánh `develop`.
- **Cấu hình triển khai** — wrapper triển khai `nufi-chat` (`librechat.yaml`,
  `docker-compose.yml`, `.env`), xác định chính xác những tính năng nào được bật.

Do sản phẩm đang trong quá trình phát triển tích cực, đặc tả này là một **tài liệu sống**. Khi
hành vi thay đổi, phần tính năng liên quan và các tiêu chí chấp nhận của nó phải được cập nhật.
Mỗi bản release nên ghi lại phiên bản sản phẩm mà tài liệu mô tả.

### Tài liệu tham khảo
- Cấu hình triển khai NuFi Chat: `librechat.yaml`, `.env.example` trong kho `nufi-chat`.
- Tài liệu LibreChat (tài liệu tham khảo hành vi upstream): https://www.librechat.ai/docs
- Kiến trúc NuFi Console: `nufi-console/README.md`.
