## Tổng quan sản phẩm & Kiến trúc

### NuFi là gì
NuFi là một nền tảng chat AI được cung cấp dưới dạng hai sản phẩm hướng người dùng cuối phối hợp
với nhau, chia sẻ một lần đăng nhập duy nhất. Trên môi trường production, chúng được phục vụ tại
**https://chat.nufi.me** (NuFi Chat) và **https://console.nufi.me** (NuFi Console):

1. **NuFi Chat** — ứng dụng hội thoại nơi người dùng trò chuyện với các mô hình AI, đính kèm tệp,
   xây dựng Agents với kiến thức tài liệu (RAG), và quản lý các cuộc hội thoại. Đây là một bản fork
   tùy chỉnh của dự án mã nguồn mở LibreChat, được thương hiệu hóa thành *Nufi Chat* và được cấu
   hình để hiển thị một tập hợp các tính năng được chọn lọc của LibreChat.
2. **NuFi Console** — cổng tự phục vụ dành cho nhà phát triển, nơi cùng những người dùng đó quản
   lý **LiteLLM API key** của riêng mình, xem **ngân sách và mức sử dụng**, và có được quyền truy
   cập lập trình vào nền tảng. Console được truy cập từ mục **Console** trong menu tài khoản Chat
   và tin tưởng phiên đăng nhập giống như Chat.

### Mô hình backend duy nhất: "Nufi"
NuFi Chat được cấu hình với đúng một endpoint chat, hiển thị là **Nufi**. Đây là một endpoint tương
thích OpenAI: backend Chat chuyển tiếp các yêu cầu đến một upstream đã cấu hình
(`BACKEND_BASE_URL`) bằng một API key (`BACKEND_API_KEY`). Trong cấu trúc sản xuất, upstream đó là
một proxy **LiteLLM**, cũng là hệ thống mà NuFi Console cấp phát API key và theo dõi ngân sách.
Danh sách các mô hình có thể chọn được tải trực tiếp từ backend đó, vì vậy dropdown mô hình phản
ánh bất cứ điều gì backend hiện đang cung cấp.

Ngoài endpoint **Nufi**, endpoint **Agents** cũng được bật. Agents là nơi khả năng Retrieval-Augmented Generation (RAG) của nền tảng hoạt động — xem bên dưới.

### Cách một tin nhắn chat di chuyển
```
User → NuFi Chat (web UI) → Chat API (Express) → BACKEND_BASE_URL (LiteLLM / OpenAI-compatible) → AI model
                                   ↑ response streamed back token-by-token (SSE) ↑
```

Phản hồi được phát trực tuyến về trình duyệt và hiển thị trực tiếp, từng token một.

### Cách Agents & File Search (RAG) hoạt động
RAG — cho phép mô hình trả lời từ các tài liệu người dùng đã tải lên — **chỉ** khả dụng thông qua
một **Agent** có khả năng **File Search**. Quy trình là:
```
User creates an Agent (on the Nufi model) → enables File Search → uploads documents into the
Agent's Knowledge → documents are sent to the RAG service (rag_api) → embedded into a vector
database (pgvector) → at chat time, relevant passages are retrieved and given to the model.
```

Một sự phân biệt quan trọng mà kiểm thử viên phải nội tâm hóa:

- Tài liệu **Agent Knowledge** là **lâu dài** — chúng thuộc về Agent và khả dụng trong *mọi* cuộc
  hội thoại với Agent đó.
- Một **tệp đính kèm theo tin nhắn** (biểu tượng 📎 paper-clip trên hộp tin nhắn) có **phạm vi
  cuộc hội thoại** — nó là ngữ cảnh chỉ cho chat hiện tại, không tồn tại sang cuộc hội thoại mới,
  và **không** đưa dữ liệu vào cơ sở dữ liệu vector.

**Không có RAG cho chat thông thường**: tải lên tài liệu trên endpoint Nufi thông thường sẽ thêm
nó dưới dạng ngữ cảnh ngắn hạn, không phải kiến thức có thể truy xuất.

### Cách hai sản phẩm chia sẻ một phiên
NuFi Chat phát hành một JSON Web Token (JWT) khi đăng nhập. NuFi Console xác minh JWT đó, vì vậy
người dùng đã đăng nhập vào Chat sẽ được Console tự động nhận dạng. Trong lần đầu tiên người dùng
truy cập Console, một tài khoản LiteLLM tương ứng được tạo tự động (**just-in-time provisioning**).
Nếu khách truy cập đến Console mà không có phiên hợp lệ, họ sẽ thấy trang *unauthorized* (không được
phép) liên kết về trang đăng nhập Chat.

### Hình dạng triển khai (để tham khảo)
NuFi Chat và các dịch vụ hỗ trợ chạy dưới dạng các container/dịch vụ riêng biệt:

- **Chat API + web client** — image fork LibreChat (`ghcr.io/dudaji-vn/nufichat`).
- **MongoDB** — lưu trữ người dùng, cuộc hội thoại, tin nhắn, agents, preset, prompt, v.v.
- **Meilisearch** — hỗ trợ tìm kiếm cuộc hội thoại (tìm kiếm không khả dụng nếu dịch vụ này bị
  tắt).
- **rag_api + pgvector** — nhúng và lưu trữ tài liệu Agent Knowledge cho File Search.
- **NuFi Console** — một dịch vụ riêng biệt (`ghcr.io/dudaji-vn/nufi-console`) kết nối với LiteLLM.

Kiểm thử viên không cần vận hành các dịch vụ này, nhưng biết chúng tồn tại sẽ giải thích một số
hành vi nhất định (ví dụ: *tìm kiếm không trả về kết quả khi Meilisearch bị tắt*, hoặc *kiến thức
đã tải lên không bao giờ có thể truy xuất khi rag_api không tiếp cận được*).

> **Lưu ý.** Tóm tắt kiến trúc này chỉ được cung cấp để định hướng. Hành vi có thẩm quyền, có thể
> kiểm thử nằm trong các phần tính năng cụ thể ở phía sau.
