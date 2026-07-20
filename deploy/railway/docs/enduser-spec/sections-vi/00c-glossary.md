## Bảng thuật ngữ, Vai trò & Quyền truy cập

### Vai trò người dùng (phạm vi người dùng cuối)
Đặc tả này bao gồm **người dùng cuối** — một người có tài khoản thông thường, đăng nhập để chat và
quản lý khóa và mức sử dụng của chính họ. Các vai trò quản trị (bảng điều khiển admin, quản lý
người dùng, cấu hình nền tảng) **nằm ngoài phạm vi** tại đây. Khi một tính năng bị giới hạn bởi
quyền mà người dùng có thể có hoặc không có, điều kiện đó được ghi chú trong phần *Điều kiện tiên
quyết* của tính năng đó.

| Vai trò | Mô tả | Được đề cập ở đây |
|---|---|---|
| **End user** (Người dùng cuối) | Đăng nhập, chat, xây dựng Agents, tải lên tệp, quản lý cuộc hội thoại của mình, quản lý API key và ngân sách của mình trong Console. | **Có** — tài liệu này |
| **Administrator** (Quản trị viên) | Cấu hình nền tảng, quản lý người dùng, đặt giới hạn toàn cục qua bảng điều khiển admin. | Không (tài liệu riêng biệt) |
| **Unauthenticated visitor** (Khách truy cập chưa xác thực) | Không có phiên hợp lệ; chỉ có thể truy cập trang đăng nhập / đăng ký (Chat) hoặc trang *unauthorized* (Console). | Một phần — chỉ hành vi entry/redirect |

### Bảng thuật ngữ
| Thuật ngữ | Ý nghĩa |
|---|---|
| **NuFi Chat** | Ứng dụng chat hướng người dùng cuối; một bản fork của LibreChat được thương hiệu hóa. |
| **NuFi Console** | Cổng tự phục vụ dành cho API key, ngân sách và mức sử dụng. |
| **Endpoint** | Một kết nối nhà cung cấp AI được cấu hình. NuFi cung cấp hai endpoint: **Nufi** (mô hình chat) và **Agents**. |
| **Nufi endpoint** | Endpoint chat tương thích OpenAI duy nhất; định tuyến đến backend đã cấu hình (LiteLLM trong môi trường sản xuất). |
| **Model** (Mô hình) | Một mô hình AI cụ thể có thể chọn trong endpoint Nufi; danh sách được tải trực tiếp từ backend. |
| **Agent** | Một trợ lý được cấu hình và tái sử dụng (mô hình + hướng dẫn + khả năng + Knowledge). Là nơi lưu trú của File Search / RAG trong NuFi. |
| **File Search** | Khả năng của Agent cho phép RAG trên các tài liệu Knowledge đã tải lên của Agent. Là khả năng Agent duy nhất được bật trong NuFi. |
| **Knowledge** (Kiến thức) | Các tài liệu đã tải lên vào một Agent. Lâu dài và được nhúng để truy xuất trong tất cả các cuộc hội thoại với Agent đó. |
| **RAG (Retrieval-Augmented Generation)** | Kỹ thuật trong đó mô hình trả lời bằng cách sử dụng các đoạn văn được truy xuất từ tài liệu đã tải lên thay vì chỉ dựa vào dữ liệu huấn luyện. |
| **Attachment** (Tệp đính kèm) | Một tệp được thêm vào một tin nhắn đơn lẻ qua biểu tượng paper-clip. Có phạm vi cuộc hội thoại; không giống như Knowledge. |
| **Preset** | Một gói đã lưu gồm endpoint + mô hình + cài đặt tham số có thể áp dụng cho các cuộc hội thoại mới. |
| **Prompt (library)** | Một template prompt đã lưu, có thể tái sử dụng, tùy chọn có biến, có thể gọi trong chat. |
| **Bookmark / Tag** (Đánh dấu / Nhãn) | Một nhãn áp dụng cho cuộc hội thoại để tổ chức và lọc. |
| **Multi-conversation (multiConvo)** | Gửi một prompt đến nhiều cuộc hội thoại song song để so sánh. |
| **Temporary chat** (Chat tạm thời) | Một cuộc hội thoại tạm thời **không** được lưu vào lịch sử. |
| **Streaming (SSE)** | Server-Sent Events; cơ chế phân phối phản hồi của mô hình đến trình duyệt từng token một. |
| **JWT** | JSON Web Token; thông tin xác thực đã ký chứng minh người dùng đã đăng nhập. Được chia sẻ giữa Chat và Console. |
| **JIT provisioning** | Tạo tài khoản LiteLLM của người dùng "just-in-time" (đúng lúc) trong lần truy cập Console đầu tiên. |
| **LiteLLM** | Proxy đứng trước các mô hình AI, thực thi API key và ngân sách, và ghi lại mức sử dụng. Console quản lý các khóa đối với nó. |
| **Budget / Spend** (Ngân sách / Chi tiêu) | Giới hạn chi tiêu và chi phí tích lũy của người dùng, được LiteLLM theo dõi và hiển thị trong Console. |
| **Reveal-once** (Hiển thị một lần) | Màn hình hiển thị một lần duy nhất bí mật của API key mới tạo; không thể truy xuất lại sau đó. |
| **Endpoints menu** | Menu Chat để chuyển đổi giữa các endpoint Nufi và Agents. |
| **pgvector / rag_api** | Cơ sở dữ liệu vector và dịch vụ nhúng hỗ trợ File Search. |
| **Meilisearch** | Công cụ tìm kiếm hỗ trợ tìm kiếm cuộc hội thoại. |

### Tóm tắt quyền truy cập (những gì người dùng cuối có thể tiếp cận)
- **Chưa đăng nhập:** trang đăng nhập và đăng ký của Chat; trang *unauthorized* của Console.
  Không có gì khác.
- **Sau khi đăng nhập vào Chat:** tất cả các tính năng chat trong tài liệu này, tùy thuộc vào
  quyền theo từng tính năng.
- **Trong Console (cùng phiên):** hồ sơ, API key, và mức sử dụng chỉ cho **tài khoản của họ**.
