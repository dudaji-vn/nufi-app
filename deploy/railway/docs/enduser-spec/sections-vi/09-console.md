## NuFi Console

### Tổng quan & truy cập

NuFi Console là cổng thông tin tự phục vụ dành cho nhà phát triển, tách biệt hoàn toàn với ứng dụng chat, cho phép người dùng cuối tự quản lý các API key LiteLLM của mình, theo dõi chi tiêu và xem phân tích mức sử dụng. Trên môi trường production, nó được phục vụ tại **https://console.nufi.me** (cần xác minh thủ công trên sản phẩm đang chạy: tên miền được gắn kết ở tầng triển khai, không được cấu hình cứng trong mã nguồn). (Về mặt nội bộ, đây là một dịch vụ container đơn — Hono + Vite SPA — được triển khai cùng NuFi Chat; người kiểm thử chỉ cần URL công khai này.)

**Cách người dùng truy cập:** Liên kết "Console" trong menu tài khoản LibreChat sẽ mở trực tiếp trình duyệt đến nguồn gốc của console. Vì LibreChat đặt cookie `refreshToken` trên domain cha chung (ví dụ: `localhost`), cookie này tự động có mặt trên cổng console — người dùng chat đã xác thực không cần đăng nhập thêm bước nào.

**Mô hình xác thực:** Console tin tưởng JWT do LibreChat cấp. Nó chấp nhận hai nguồn token theo thứ tự: (1) Header `Authorization: Bearer <access_token>` được xác minh bằng `JWT_SECRET` (HS256) — dùng cho các client dịch vụ; (2) cookie `refreshToken` được xác minh bằng `JWT_REFRESH_SECRET` (HS256) — đây là luồng thông thường qua trình duyệt. `id` LibreChat của người dùng được trích xuất từ payload JWT trở thành danh tính chuẩn xuyên suốt các bản ghi LiteLLM và Langfuse. Một token hợp lệ tạo ra đối tượng `AuthedUser` với `id`, `email` (tùy chọn) và `role` (`USER` hoặc `ADMIN`).

**JIT provisioning (cấp phát tức thời):** Ở lần gọi API đầu tiên mà console thực hiện thay mặt người dùng mới được xác thực, nó gọi `ensureLiteLLMUser`. Hàm này kiểm tra bản ghi Internal-User LiteLLM tương ứng qua `GET /user/info?user_id=…`. Nếu không tìm thấy, nó gọi `POST /user/new` để tạo mới với các giới hạn mặc định: `max_budget = $10`, `budget_duration = 30d`, `tpm_limit = 10 000`, `rpm_limit = 60` (tất cả có thể ghi đè qua biến môi trường). Thao tác này là idempotent — an toàn khi gọi ở mỗi request.

**Luồng truy cập không được phép:** Khi bất kỳ lệnh gọi API nào trả về HTTP 401, SPA chuyển hướng đến route `/unauthorized`, hiển thị thông báo "Sign in required" kèm nội dung giải thích và nút "Open chat" liên kết sâu đến URL LibreChat (cấu hình qua `VITE_LIBRECHAT_URL`, mặc định là `http://localhost:3080`).

**Điều hướng:** Thanh header cố định chứa logo NUFI, tên ứng dụng "NUFI Console" và ba liên kết điều hướng: **Profile** (Hồ sơ), **Usage** (Mức sử dụng) và **API keys**. Nút chuyển giao diện sáng/tối xuất hiện ở bên phải. Thông báo Toast xuất hiện ở góc dưới bên phải.

---

### Xác thực & Phiên làm việc

**Mục đích:** Xác minh người dùng có phiên làm việc LibreChat đang hoạt động trước khi cho phép truy cập bất kỳ tính năng console nào. Ngăn chặn truy cập dữ liệu chéo giữa các người dùng.

**Điều kiện tiên quyết / truy cập:** Người dùng phải đã đăng nhập vào LibreChat trước đó, thao tác này đặt cookie `refreshToken` trên domain chung.

**Thành phần giao diện:** Không có form đăng nhập nào trong bản thân console. Trang `/unauthorized` hiển thị: tiêu đề "Sign in required"; đoạn văn "The console reuses your chat session. Sign in there first, then come back to this tab."; nút "Open chat".

**Hành vi chức năng:**

- FR-1. Tại mỗi request `/rpc/*`, middleware phía server đọc header `Authorization` trước. Nếu Bearer token hợp lệ và có thể xác minh bằng `JWT_SECRET` thì request được xác thực theo luồng access-token.
- FR-2. Nếu không tìm thấy Bearer token hợp lệ, middleware đọc cookie `refreshToken` và xác minh bằng `JWT_REFRESH_SECRET`. Nếu hợp lệ, request được xác thực theo luồng refresh-token.
- FR-3. Nếu không có token nào hoặc cả hai đều không qua xác minh mật mã, server trả về HTTP 401 `{"error":"unauthorized"}`.
- FR-4. Server trích xuất `id` người dùng từ các key claim JWT theo thứ tự: `id`, `userId`, `_id`, hoặc `sub`. Nếu không có key nào phân giải thành chuỗi khác rỗng thì trả về 401.
- FR-5. `role` của người dùng chỉ được đặt thành `ADMIN` nếu claim `role` trong JWT bằng `"ADMIN"`; tất cả các giá trị khác (kể cả vắng mặt) mặc định là `USER`.
- FR-6. SPA phát hiện các phản hồi 401 qua `isUnauthorized` (kiểm tra `err instanceof ORPCError && err.code === 'UNAUTHORIZED'`) và điều hướng đến `/unauthorized`. Kiểm tra này áp dụng trên mọi trang: Profile, API Keys và Usage. Với các lỗi 401 được ném trong handler oRPC, ánh xạ là trực tiếp; việc phản hồi HTTP 401 thuần túy từ middleware Hono có được `@orpc/client` ánh xạ thành `ORPCError.code === 'UNAUTHORIZED'` hay không (cần xác minh thủ công trên sản phẩm đang chạy: xác nhận luồng 401 ở tầng Hono xuất hiện là `isUnauthorized === true` trong SPA).
- FR-7. Trên trang `/unauthorized`, nhấn "Open chat" sẽ điều hướng trình duyệt (tải trang đầy đủ) đến URL LibreChat. Sau khi đăng nhập, người dùng có thể quay lại tab console, tab này sẽ thử lại bằng cookie mới được đặt.

**Trạng thái & trường hợp đặc biệt:**

- Thiếu JWT secrets trên server: trả về HTTP 500 `{"error":"server_misconfigured","detail":"JWT secrets missing"}` — người dùng thấy lỗi chung, không phải trang unauthorized.
- Access token hết hạn nhưng refresh token còn hợp lệ: luồng refresh xác thực phiên bình thường. (Lưu ý: refresh token không được xoay vòng hay tái xác thực với session store của LibreChat trong phiên bản này — độ trễ thu hồi quyền là giới hạn đã biết.)
- Cả hai token đều thiếu (trình duyệt hoàn toàn mới / chế độ ẩn danh chưa từng đăng nhập LibreChat): chuyển hướng ngay đến `/unauthorized`.

**Tiêu chí chấp nhận:**

- AC-1. Giả sử trình duyệt đã đăng nhập LibreChat trước đó (cookie có mặt), khi người dùng mở console, thì trang Profile tải mà không có chuyển hướng.
- AC-2. Giả sử không có cookie `refreshToken` và không có header Authorization, khi người dùng mở bất kỳ trang console nào, thì trình duyệt được chuyển hướng đến `/unauthorized` và nút "Open chat" hiển thị.
- AC-3. Giả sử `JWT_SECRET` chưa được cấu hình trên server, khi console thực hiện bất kỳ lệnh gọi API nào, thì server trả về HTTP 500 và không có dữ liệu người dùng nào bị lộ.
- AC-4. Giả sử JWT chứa role `ADMIN`, khi người dùng tải bất kỳ trang nào, thì badge `role` trên trang Profile hiển thị "ADMIN".

---

### Cấp phát lần đầu (JIT)

**Mục đích:** Tự động tạo tài khoản LiteLLM cho mỗi người dùng LibreChat ngay lần đầu họ truy cập console, không cần quản trị viên cấu hình thủ công.

**Điều kiện tiên quyết / truy cập:** Người dùng đã được xác thực. Chưa có bản ghi LiteLLM nào tồn tại cho người dùng này.

**Thành phần giao diện:** Không có giao diện chuyên biệt — việc cấp phát diễn ra ẩn. Trang Profile tải ra với các giá trị đã cấp phát hiển thị ngay lập tức.

**Hành vi chức năng:**

- FR-1. Thủ tục `me.get` gọi `ensureLiteLLMUser` đồng bộ (song song với các lời gọi `getCustomer` và `listKeysForUser`) mỗi lần tải trang Profile.
- FR-2. `ensureLiteLLMUser` gọi `GET /user/info?user_id=<id>`. Nếu LiteLLM API trả về HTTP 404, hoặc HTTP 400 với body chứa từ "not found" (biến thể thấy ở một số phiên bản LiteLLM), người dùng được xem là mới.
- FR-3. Với người dùng mới, `POST /user/new` được gọi với: `user_id` = LibreChat `id`; `user_email` = email từ JWT (nếu có); `user_role` = `proxy_admin` cho người dùng có role ADMIN, `internal_user` cho người dùng có role USER; `max_budget = $10` (env: `DEFAULT_USER_BUDGET`); `budget_duration = 30d` (env: `DEFAULT_BUDGET_DURATION`); `tpm_limit = 10 000` (env: `DEFAULT_TPM_LIMIT`); `rpm_limit = 60` (env: `DEFAULT_RPM_LIMIT`).
- FR-4. `LiteLLMUserInfo` được trả về dùng trực tiếp cho các trường `limits.*` trong phản hồi của `me.get`; không có chuyến đi vòng thứ hai.
- FR-5. Lời gọi là idempotent: nếu người dùng đã tồn tại trong LiteLLM, `getUser` trả về bản ghi hiện có và `createUser` không bao giờ được gọi.

**Trạng thái & trường hợp đặc biệt:**

- LiteLLM không khả dụng trong quá trình cấp phát: lời gọi `me.get` ném lỗi; trang Profile hiển thị "Error: \<message\>". Không có trạng thái nào được ghi một phần.
- Cấp phát thành công nhưng `user_email` vắng mặt trong JWT: bản ghi LiteLLM được tạo không có email; trang Profile hiển thị user ID như chuỗi định danh.
- Cấp phát đồng thời (hai tab mở cùng lúc trong lần truy cập đầu tiên): cả hai lời gọi đến `getUser` trước khi bất kỳ `createUser` nào hoàn tất; một có thể tạo bản sao. Hành vi idempotent của `POST /user/new` trong LiteLLM sẽ quyết định kết quả (cần xác minh: hành vi phụ thuộc vào phiên bản LiteLLM).

**Tiêu chí chấp nhận:**

- AC-1. Giả sử người dùng LibreChat chưa bao giờ mở console, khi họ điều hướng đến trang Profile, thì không có lỗi nào hiển thị và phần ngân sách/giới hạn hiển thị các giá trị mặc định (`$10` ngân sách tối đa, chu kỳ `30d`, `10K` tok/min, `60` req/min).
- AC-2. Giả sử người dùng đã có tài khoản LiteLLM, khi họ mở trang Profile, thì các giá trị ngân sách và chi tiêu hiện có được hiển thị (không bị đặt lại về mặc định).
- AC-3. Giả sử LiteLLM đang ngừng hoạt động, khi trang Profile tải, thì một thông báo lỗi được hiển thị và không có thẻ ngân sách nào xuất hiện.

---

### Trang Profile

**Mục đích:** Cung cấp cho người dùng cái nhìn tổng quan về danh tính của họ, ngân sách còn lại, phân tích chi tiêu, tóm tắt danh sách key, và biểu đồ chi tiêu hàng ngày 7 ngày — "bảng điều khiển nhìn thoáng".

**Điều kiện tiên quyết / truy cập:** Người dùng đã được xác thực. JIT provisioning đã hoàn tất. Truy cập qua liên kết điều hướng "Profile" hoặc URL gốc `/`.

**Thành phần giao diện:**

- Tiêu đề: `Hi 👋` (h1, `text-3xl font-semibold`)
- Dòng định danh: địa chỉ email dạng monospace (hoặc user ID nếu không có email), theo sau là `Badge` hiển thị role người dùng (`USER` hoặc `ADMIN`).
- **Thẻ Available Hero** (chiều rộng đầy đủ, bo góc): hiển thị một trong hai dạng:
  - Có ngân sách: tiêu đề "Available · next \<period\>" (period được phân giải từ `budgetDuration`: `24h` → "24 hours", `7d` → "7 days", `30d` → "30 days"); số dư còn lại dạng monospace cỡ lớn; nhãn phụ "of \<maxBudget\>"; thanh tiến trình ngang; hàng footer với "\<spent\> used (\<pct\>%)" ở bên trái và nhãn trạng thái ("Healthy" / "Running low" / "Almost out") ở bên phải.
  - Không có ngân sách (`max_budget = null`): tiêu đề "You have unlimited usage"; tổng chi tiêu dạng monospace cỡ lớn; nhãn phụ "used so far".
- **Thẻ Usage Chart**: tiêu đề "Last 7 days"; số lượng request và tổng chi phí ở phần đầu bên phải. Biểu đồ cột với một cột mỗi ngày UTC (chiều cao theo thang căn bậc hai, các ngày khác không được sàn ở 15% chiều cao). Ngày đỉnh được làm nổi bật bằng màu đậm hơn. Footer hiển thị "Peak day: \<day\> · \<amount\>" và "Last request: \<relative time\>".
- **Thẻ Spend Breakdown** ("Where it goes"): hai hàng — "Chat conversations" (ô màu chính) và "Direct API calls" (ô màu xanh) — mỗi hàng hiển thị số tiền USD và tỷ lệ phần trăm tổng. Nếu tổng chi tiêu là $0.00: "You haven't used anything yet this period."
- **Thẻ Your Keys**: tối đa 5 key chi tiêu cao nhất hiển thị dưới dạng danh sách thanh ngang được xếp hạng. Mỗi hàng: bí danh (alias, hoặc `unnamed` — không có dấu ngoặc đơn, theo cách render của `top-keys-card.tsx`), token che (3 ký tự đầu + 4 ký tự cuối) và chi tiêu USD. Liên kết "View all (N) →" đến trang API Keys. Nếu không có key nào: "You don't have any API keys yet. Generate one." Lưu ý: Key Table (component riêng biệt) hiển thị key không có tên là `(unnamed)` có dấu ngoặc đơn — hai component này khác nhau có chủ đích.
- **Thẻ Per-minute limits** ("Per-minute limits"): hai hàng thống kê — "tokens / minute" (giới hạn TPM) và "requests / minute" (giới hạn RPM), định dạng theo ký hiệu thu gọn (ví dụ: `10K`). Giá trị `null` hiển thị là `∞`.
- **Skeleton loaders** (khung tải) được hiển thị cho tất cả các phần trong khi `me.get` đang chờ xử lý.

**Hành vi chức năng:**

- FR-1. Khi khởi tạo, SPA phát hai truy vấn song song: `me.get` (trả về danh tính + chi tiêu + giới hạn + các key hàng đầu) và `usage.daily` với `{ days: 7 }` (trả về chuỗi chi tiêu hàng ngày).
- FR-2. `me.get` tổng hợp chi tiêu từ ba nguồn LiteLLM: hàng Customer (End-User) cho lưu lượng chat (`customer.spend`) và tổng `spend` của tất cả các key người dùng đã cấp. Tổng chi tiêu = chi tiêu chat + chi tiêu từ key đã cấp.
- FR-3. Ngưỡng tiến trình ngân sách: ≥ 90% chi tiêu → thanh màu đỏ (destructive) + nhãn "Almost out"; ≥ 70% → thanh màu hổ phách + "Running low"; dưới 70% → thanh màu chính + "Healthy".
- FR-4. Khi `limits.maxBudget` là `null`, Available Hero hiển thị dạng không giới hạn.
- FR-5. Nếu `me.get` thất bại với lỗi không phải 401, đoạn văn `"Error: <message>"` được hiển thị bằng màu đỏ (destructive); tất cả các thẻ bị ẩn.
- FR-6. Nếu `me.get` thất bại với lỗi 401, SPA điều hướng đến `/unauthorized`.
- FR-7. Biểu đồ 7 ngày dùng dữ liệu `usage.daily`; hiển thị skeleton khi đang chờ và dự phòng về chuỗi trống / giá trị không nếu truy vấn chưa phân giải.

**Trạng thái & trường hợp đặc biệt:**

- Tổng chi tiêu bằng không: AvailableHero hiển thị "$0.00 used (0%)", thanh trống, SpendBreakdown hiển thị thông báo trạng thái không.
- Ngân sách đúng bằng 100%: thanh đầy màu đỏ, trạng thái "Almost out", số dư còn lại "$0.00".
- Không có key: TopKeysCard hiển thị thông báo "Generate one"; `keysCount = 0`.
- Email vắng mặt trong JWT: dòng định danh hiển thị user ID dạng monospace.
- Giá trị `budget_duration` của LiteLLM không có trong bản đồ hiển thị: hiển thị nguyên văn (ví dụ: `90d` hiển thị là `90d`).

**Tiêu chí chấp nhận:**

- AC-1. Giả sử người dùng có `max_budget = 10`, `spend = 3.50`, `budget_duration = 30d`, khi trang Profile tải, thì thẻ hero hiển thị "Available · next 30 days", số dư còn lại "$6.50", "of $10.00", thanh ở 35%, trạng thái "Healthy".
- AC-2. Giả sử chi tiêu ≥ 90% ngân sách, khi trang Profile tải, thì thanh tiến trình có màu đỏ (destructive) và nhãn trạng thái hiển thị "Almost out". (Ở 80%, thanh là màu hổ phách chứ không phải đỏ — màu đỏ chỉ kích hoạt khi ≥ 90%.)
- AC-3. Giả sử `max_budget = null`, khi trang Profile tải, thì thẻ hero hiển thị "You have unlimited usage" cùng với tổng chi tiêu.
- AC-4. Giả sử `usage.daily` phân giải có dữ liệu, khi biểu đồ hiển thị, thì mỗi cột ngày xuất hiện và cột ngày đỉnh nổi bật về mặt hình ảnh (màu chính với độ mờ đầy đủ).
- AC-5. Giả sử người dùng đã cấp key, khi trang Profile tải, thì thẻ "Your keys" liệt kê tối đa 5 key được xếp hạng theo chi tiêu (cao nhất trước) với token che.
- AC-6. Giả sử người dùng đang chờ cấp phát, khi skeleton hồ sơ được hiển thị, thì không có giá trị dữ liệu thực nào được hiển thị và không có lỗi nào xuất hiện.

---

### API Keys — Danh sách / Bảng

**Mục đích:** Hiển thị cho người dùng tất cả API key LiteLLM đang hoạt động của họ trong bảng có thể sắp xếp, với chi tiêu theo từng key, ngân sách, giới hạn tốc độ, ngày tạo và ngày hết hạn, cùng thống kê tóm tắt tổng hợp.

**Điều kiện tiên quyết / truy cập:** Người dùng đã được xác thực. Truy cập qua liên kết điều hướng "API keys" (`/keys`).

**Thành phần giao diện:**

- Tiêu đề trang: "API keys" (h1, `text-3xl font-semibold`).
- Tiêu đề phụ: "Each key has its own budget and rate limits. Use them to call the API from your code."
- **Nút "Generate Key"** (chỉ hiển thị khi có ít nhất một key): icon `Plus` + nhãn "Generate Key", góc trên bên phải của hàng header.
- **Thanh Keys Summary** (4 thẻ thống kê, hiển thị khi có key):
  - "Active keys" — tổng số lượng.
  - "Used across keys" — tổng chi tiêu của tất cả key theo USD.
  - "Total budget" — tổng tất cả giá trị `max_budget` theo USD (hoặc "—" nếu tất cả đều là null); gợi ý hiển thị "\<spent\> of \<total\>".
  - "Expiring this week" — số key hết hạn trong vòng 7 ngày; hiển thị màu hổ phách khi > 0.
- **Key Table** (hiển thị khi có key): các cột:
  - **Name** — bí danh (alias) in đậm trên dòng đầu; token che (`3 ký tự đầu…4 ký tự cuối` của trường `token`) với `font-mono text-[11px]` trên dòng thứ hai. Nếu alias là null, hiển thị `(unnamed)` bằng màu mờ.
  - **Usage** — chi tiêu hiện tại theo USD; "of \<maxBudget\> · \<budgetDuration\>" khi có ngân sách được đặt. Thanh tiến trình nhỏ rộng 32px bên dưới (màu: chính ≤70%, hổ phách 70–89%, đỏ ≥90%).
  - **Limits** (ẩn trên màn hình nhỏ, hiển thị ở md): hai phần tử `Badge` — giới hạn TPM theo ký hiệu thu gọn với nhãn "tok/min"; giới hạn RPM với nhãn "req/min".
  - **Created** (ẩn dưới lg): ngày định dạng (ví dụ: "Jun 10, 2026").
  - **Expires** (ẩn dưới lg): ngày định dạng, hoặc "never" in nghiêng nếu `expires` là null.
  - Cột hành động không tên: nút icon `Trash2` dạng ghost với `aria-label="Revoke key"`.
- **Trạng thái trống** (hiển thị khi người dùng không có key): thẻ chiều rộng đầy đủ với nội dung căn giữa — icon, tiêu đề "Welcome — let's create your first key", đoạn văn mô tả, giải thích 3 bước ("Generate", "Use it", "Track usage"), đoạn `curl` mẫu sử dụng `VITE_LITELLM_URL` và tên model khả dụng đầu tiên, và nút lớn "Generate your first key".
- **Skeleton** hiển thị trong khi truy vấn danh sách đang chờ xử lý.

**Hành vi chức năng:**

- FR-1. Khi khởi tạo, `keys.list` được truy vấn. Với role `USER`, chỉ trả về các key thuộc về người dùng đã xác thực (`/key/list?user_id=…`). Với role `ADMIN`, tất cả key từ `/key/list` đều được trả về.
- FR-2. Giá trị token che được lấy từ trường `token` (định danh băm an toàn để lộ), không phải bí mật thô `sk-…`.
- FR-3. Màu thanh tiến trình ngân sách: màu chính (xanh) dưới 70%, hổ phách 70–89%, đỏ (destructive) ở 90%+.
- FR-4. Nếu `max_budget` là null, không có chuỗi ngân sách và không có thanh tiến trình nào được hiển thị cho hàng đó.
- FR-5. Nếu `expires` là null, cột Expires hiển thị "never" in nghiêng.
- FR-6. "Expiring this week" đếm các key có `expires` được đặt và thời gian hết hạn nằm trong vòng 7 ngày kể từ bây giờ (nhưng chưa qua).
- FR-7. Khi gặp lỗi 401 từ `keys.list`, SPA điều hướng đến `/unauthorized`.
- FR-8. Khi gặp lỗi không phải 401, đoạn lỗi nội tuyến `"Error: <message>"` được hiển thị.

**Trạng thái & trường hợp đặc biệt:**

- Không có key: thẻ trạng thái trống được hiển thị; nút "Generate Key" vắng mặt trên header (thẻ trạng thái trống có nút "Generate your first key" riêng).
- Tất cả key có ngân sách null: thẻ tóm tắt "Total budget" hiển thị "—" với gợi ý "No caps set".
- Key có chi tiêu đúng bằng `max_budget`: thanh tiến trình ở 100% chiều rộng màu đỏ (destructive).
- Trường `token` ngắn hơn 8 ký tự: hàm che trả về giá trị không thay đổi.
- Người dùng ADMIN: thấy key của tất cả người dùng trong bảng (cần xác minh: xử lý hiển thị đặc thù cho admin như hiển thị `userId` mỗi hàng chưa được triển khai trong bảng hiện tại — chỉ phạm vi dữ liệu là khác nhau).

**Tiêu chí chấp nhận:**

- AC-1. Giả sử người dùng có 2 key, khi trang Keys tải, thì bảng hiển thị 2 hàng và thẻ tóm tắt "Active keys" hiển thị "2".
- AC-2. Giả sử một key có `spend = 8`, `max_budget = 10`, khi hàng bảng hiển thị, thì cột Usage hiển thị "$8.00 of $10.00" và thanh tiến trình có màu hổ phách (80% nằm trong dải ≥70% màu hổ phách; thanh chỉ chuyển sang đỏ/destructive khi ≥90%).
- AC-3. Giả sử một key có `expires` = null, khi hàng bảng hiển thị, thì cột Expires hiển thị "never" in nghiêng.
- AC-4. Giả sử không có key nào tồn tại, khi trang Keys tải, thì thẻ trạng thái trống được hiển thị, thanh tóm tắt vắng mặt, bảng vắng mặt, và nút "Generate Key" trên header vắng mặt.
- AC-5. Giả sử lời gọi `keys.list` trả về 401, khi trang Keys tải, thì trình duyệt điều hướng đến `/unauthorized`.
- AC-6. Giả sử một key hết hạn sau 3 ngày, khi trang Keys tải, thì thẻ tóm tắt "Expiring this week" hiển thị "1" bằng màu hổ phách.

---

### Tạo / Cấp API Key

**Mục đích:** Cho phép người dùng tạo mới một API key LiteLLM với bí danh tùy chỉnh, ngân sách, giới hạn tốc độ và thời hạn hết hạn.

**Điều kiện tiên quyết / truy cập:** Người dùng đã được xác thực. Người dùng mở modal "Generate Key" từ nút trên header (khi đã có key) hoặc nút "Generate your first key" trong trạng thái trống. Modal được điều khiển bởi cờ `generateOpen` trong Zustand UI store.

**Thành phần giao diện (dialog "Generate API key"):**

- Tiêu đề dialog: "Generate API key".
- Mô tả dialog: "Use this key to call the LiteLLM proxy directly. The full value is shown once after creation."
- Trường **Alias** (`Label` "Alias", `Input` id="alias", placeholder "e.g. my-laptop", `required`, `maxLength=64`). Mặc định: trống.
- Trường **Max budget (USD)** (`Label` "Max budget (USD)", `Input` id="budget", `type="number"`, `min=0.01`, `step=0.01`). Mặc định: `10`.
- Bộ chọn **Budget period** (`Label` "Budget period", `Select`). Tùy chọn: `24h`, `7d`, `30d`. Mặc định: `30d`.
- Trường **TPM limit** (`Label` "TPM limit", `Input` id="tpm", `type="number"`, `min=1`, `step=1`). Mặc định: `10000`.
- Trường **RPM limit** (`Label` "RPM limit", `Input` id="rpm", `type="number"`, `min=1`, `step=1`). Mặc định: `60`.
- Bộ chọn **Expires** (`Label` "Expires", `Select`). Tùy chọn: `in 7d`, `in 30d`, `in 90d`, `in 180d`, `in 365d`, `Never`. Mặc định: `90d`.
- Nút footer: ghost "Cancel" (đóng modal, không mutation) và primary "Generate" (gửi form). "Generate" bị vô hiệu hóa khi trường `alias` trống hoặc mutation đang xử lý; nhãn chuyển thành "Generating…" khi đang chờ.

**Hành vi chức năng:**

- FR-1. Nhấn "Generate" gửi form, gọi mutation `keys.create` với: `alias` (đã trim), `maxBudget` (float đã phân tích), `budgetDuration`, `tpmLimit` (int đã phân tích), `rpmLimit` (int đã phân tích), `duration` (thời hạn key; giá trị `never` được gửi là `undefined` đến LiteLLM để không đặt hạn).
- FR-2. Xác thực phía server: `alias` 1–64 ký tự (bắt buộc). Tất cả các trường còn lại là tùy chọn trên đường truyền — nếu bị bỏ qua, server áp dụng các giá trị mặc định giống JIT provisioning: `maxBudget` dương ≤ 10 000 (mặc định $10); `budgetDuration` là một trong `24h|7d|30d` (mặc định `30d`); `tpmLimit` là số nguyên dương ≤ 10 000 000 (mặc định 10 000); `rpmLimit` là số nguyên dương ≤ 100 000 (mặc định 60); `duration` là một trong `7d|30d|90d|180d|365d|never`. Quy tắc xác thực chỉ áp dụng khi trường có mặt; các trường vắng mặt dùng giá trị mặc định của server.
- FR-3. Khi thành công, server trả về `{ key: "sk-…", view: KeyView }`. SPA: (a) lưu `{ alias, key }` vào state `revealedKey` của Zustand, đóng modal generate và mở modal reveal-once; (b) làm mới truy vấn `keys.list` để bảng cập nhật; (c) hiển thị toast thành công `Key "<alias>" generated`; (d) đặt lại tất cả trường form về mặc định.
- FR-4. Khi gặp lỗi, toast `"Could not generate key: <message>"` được hiển thị; modal giữ nguyên mở.
- FR-5. Nút "Cancel" đóng modal không có mutation và không đặt lại trạng thái form (trạng thái chỉ đặt lại khi tạo thành công).

**Trạng thái & trường hợp đặc biệt:**

- Alias trống: nút "Generate" bị vô hiệu hóa; không thể gửi form.
- Alias chỉ gồm khoảng trắng: sau `.trim()`, alias trống và server từ chối với lỗi xác thực.
- Để trống trường budget hoặc limit: trình duyệt chặn việc gửi form trước khi JavaScript xử lý — cả ba trường (`budget`, `tpm`, `rpm`) đều mang thuộc tính HTML5 `required`, do đó trình duyệt ngăn việc gửi form khi để trống theo cơ chế native. Luồng `Number("")` → `0` / lỗi `positive()` ở server không bị kích hoạt qua tương tác giao diện thông thường.
- LiteLLM trả về lỗi (ví dụ: ngân sách vượt giới hạn admin): toast hiển thị thông báo lỗi từ server.
- Tạo đồng thời: nút bị vô hiệu hóa trong khi đang xử lý nên tránh được gửi trùng lặp.

**Tiêu chí chấp nhận:**

- AC-1. Giả sử dialog Generate đang mở, khi người dùng để trống trường Alias, thì nút "Generate" bị vô hiệu hóa và không thể nhấn.
- AC-2. Giả sử các giá trị form hợp lệ, khi người dùng nhấn "Generate", thì nhãn nút chuyển thành "Generating…", nút bị vô hiệu hóa, và khi thành công dialog đóng lại, modal reveal mở ra.
- AC-3. Giả sử tạo key thành công, khi trang keys hiển thị lại, thì key mới xuất hiện trong bảng.
- AC-4. Giả sử gặp lỗi xác thực server, khi lời gọi create trả về, thì toast "Could not generate key: …" được hiển thị và dialog vẫn mở.
- AC-5. Giả sử nhấn nút "Cancel", khi dialog đóng, thì không có key nào được tạo và danh sách key không thay đổi.

---

### Modal Bí Mật Chỉ Hiện Một Lần (Reveal-Once)

**Mục đích:** Hiển thị giá trị đầy đủ của API key `sk-…` ngay sau khi tạo — đây là lần duy nhất bí mật có thể được truy cập. Sau khi modal bị đóng, bí mật không thể được khôi phục lại dưới bất kỳ hình thức nào.

**Điều kiện tiên quyết / truy cập:** State `revealedKey` của Zustand đã được điền (được đặt bởi lời gọi `keys.create` thành công). Modal này hiển thị ở cấp route `/keys` và hiện ra phía trên bảng key.

**Thành phần giao diện (dialog "Save your new key"):**

- Tiêu đề dialog: "Save your new key".
- Mô tả dialog: "Copy it now — you won't see the full value again. Treat it like a password."
- **Nhãn alias key**: nhãn monospace viết hoa nhỏ hiển thị alias của key.
- **Hộp hiển thị key**: container có viền màu mờ với giá trị đầy đủ `sk-…` dạng `font-mono text-sm` (bị cắt bớt nếu tràn). Nút "Copy" với icon `Copy` ở bên phải; icon và nhãn chuyển thành `Check` + "Copied" trong 2 giây sau khi ghi vào clipboard thành công.
- **Phần "How to use it"**: component `Tabs` với ba tab:
  - **curl** — đoạn `curl` dùng `VITE_LITELLM_URL` (env, mặc định `http://localhost:4000`) và ID model đầu tiên từ truy vấn `models.list` (dự phòng về `qwen2.5-3b` nếu truy vấn chưa phân giải).
  - **Python** — đoạn Python dùng SDK `openai`.
  - **JavaScript** — đoạn JavaScript/ESM dùng SDK `openai`.
  - Mỗi tab có nút "Copy" (góc trên bên phải của khối code) sao chép toàn bộ văn bản đoạn code và hiển thị "Copied" trong 2 giây.
- Nút **"I've saved it"** (footer, primary): đóng modal và xóa `revealedKey` khỏi store.

**Hành vi chức năng:**

- FR-1. Modal hiển thị ngay khi `revealedKey` khác null trong Zustand store; không thể mở lại sau khi đã xóa.
- FR-2. Đóng dialog bằng nút `×` hoặc nhấn Escape gọi `clear()`, đặt `revealedKey` về `null`. Key biến mất khỏi store và không thể khôi phục — đây là hành vi chủ đích: bí mật chỉ hiển thị một lần duy nhất và không thể xem lại sau đó.
- FR-3. Sao chép văn bản key gọi `navigator.clipboard.writeText`. Khi thành công, toast "Key copied to clipboard" được hiển thị. Khi API clipboard thất bại, toast "Clipboard write failed — copy manually" được hiển thị.
- FR-4. Sao chép đoạn code gọi `navigator.clipboard.writeText` với chuỗi đoạn code đầy đủ. Khi thành công, toast "Snippet copied" được hiển thị.
- FR-5. Truy vấn `models.list` được tải (với thời gian stale 5 phút) chỉ khi modal hiển thị (`enabled: !!revealed`). ID model đầu tiên được trả về được chèn vào cả ba đoạn code.
- FR-6. Tab hiển thị mặc định là "curl".

**Trạng thái & trường hợp đặc biệt:**

- API Clipboard không khả dụng (ngữ cảnh không an toàn / quyền bị từ chối): toast "Clipboard write failed — copy manually" xuất hiện; văn bản key vẫn hiển thị để người dùng chọn và sao chép thủ công.
- Truy vấn `models.list` chưa phân giải: các đoạn code dùng tên model dự phòng `qwen2.5-3b`.
- Người dùng đóng modal ngay mà không sao chép: key bị mất vĩnh viễn. Không có đường khôi phục nào trong giao diện.
- Làm mới trang trong khi modal đang mở: Zustand store lưu trong bộ nhớ; làm mới trang xóa sạch store, do đó key không thể khôi phục.

**Tiêu chí chấp nhận:**

- AC-1. Giả sử một key vừa được tạo, khi modal reveal xuất hiện, thì giá trị đầy đủ `sk-…` hiển thị trong hộp hiển thị key.
- AC-2. Giả sử modal đang mở, khi người dùng nhấn "Copy" bên cạnh key, thì clipboard chứa giá trị key đầy đủ, nhãn nút chuyển thành "Copied" và toast thành công được hiển thị.
- AC-3. Giả sử người dùng nhấn "I've saved it", khi modal đóng, thì key không còn có thể truy cập trong giao diện và bảng key hiển thị lại.
- AC-4. Giả sử người dùng nhấn Escape hoặc nhấn nút đóng dialog, thì modal đóng lại và key bị xóa khỏi state — key sẽ không còn hiển thị lại sau đó.
- AC-5. Giả sử modal đang mở và `models.list` đã phân giải, khi người dùng chuyển sang tab Python, thì đoạn code chứa ID của model đầu tiên (không phải chuỗi dự phòng).
- AC-6. Giả sử sao chép thành công, khi 2 giây trôi qua, thì nút "Copy" trở lại icon và nhãn mặc định.

---

### Thông Tin Key / Chi Tiết Mức Sử Dụng

**Mục đích:** Trả về bản ghi chi tiết đầy đủ cho một key cụ thể (alias, token, chi tiêu, ngân sách, giới hạn tốc độ, ngày tạo, ngày hết hạn) để hiển thị nội tuyến trong bảng hoặc cho các view chi tiết tương lai.

**Điều kiện tiên quyết / truy cập:** Yêu cầu phiên đã xác thực. Trường `token` của key (định danh an toàn) là bắt buộc. `USER` chỉ có thể xem key của chính mình; `ADMIN` có thể xem bất kỳ key nào.

**Thành phần giao diện:** Không có view chi tiết key toàn trang nào trong SPA hiện tại. Chi tiết key được hiển thị nội tuyến trong các hàng Key Table (xem phần API Keys — Danh sách / Bảng). Thủ tục `keys.info` có sẵn dưới dạng API endpoint cho sử dụng theo chương trình.

**Hành vi chức năng:**

- FR-1. `keys.info` nhận `{ token: string }` (tối thiểu 1 ký tự). Nó gọi `GET /key/info?key=<token>` trên LiteLLM.
- FR-2. Nếu key không tìm thấy (LiteLLM trả về 404), server trả về lỗi oRPC `NOT_FOUND`.
- FR-3. Nếu role người dùng đã xác thực là `USER` và `key.user_id` không khớp với `context.user.id`, server trả về lỗi `FORBIDDEN`.
- FR-4. Hình dạng `KeyView` được trả về là: `alias`, `token`, `userId`, `teamId`, `maxBudget`, `spend`, `budgetDuration`, `tpmLimit`, `rpmLimit`, `createdAt`, `expires`.

**Trạng thái & trường hợp đặc biệt:**

- Key bị xóa giữa lúc tải danh sách và lúc gửi request info: `NOT_FOUND` được trả về.
- USER cố xem key của người dùng khác: `FORBIDDEN` ngăn rò rỉ dữ liệu chéo người dùng.

**Tiêu chí chấp nhận:**

- AC-1. Giả sử USER gọi `keys.info` với token thuộc key của chính họ, thì bản ghi `KeyView` đầy đủ được trả về.
- AC-2. Giả sử USER gọi `keys.info` với token thuộc key của người dùng khác, thì lỗi `FORBIDDEN` được trả về.
- AC-3. Giả sử ADMIN gọi `keys.info` với bất kỳ token hợp lệ nào, thì bản ghi được trả về bất kể key thuộc về người dùng nào.
- AC-4. Giả sử token không tồn tại, thì lỗi `NOT_FOUND` được trả về.

---

### Thu Hồi / Xóa Key

**Mục đích:** Xóa vĩnh viễn một API key, lập tức thu hồi khả năng xác thực request đến LiteLLM proxy của nó.

**Điều kiện tiên quyết / truy cập:** Người dùng đã được xác thực. Việc thu hồi được khởi tạo từ nút icon thùng rác trong hàng Key Table. Một dialog xác nhận phải được chấp nhận trước khi tiến hành xóa.

**Thành phần giao diện (ConfirmDialog):**

- Tiêu đề dialog: `Revoke "<alias>"?` (dùng alias của key nếu được đặt, ngược lại là `"this key"`).
- Mô tả dialog: "This is immediate and irreversible. Anything using this key will start receiving 401 errors."
- Nút footer:
  - Ghost "Cancel" — đóng dialog, không mutation.
  - Destructive "Revoke" — kích hoạt mutation xóa; nhãn chuyển thành "Working…" trong khi đang xử lý và nút bị vô hiệu hóa.
- Trong quá trình mutation, nút "Cancel" cũng bị vô hiệu hóa.

**Hành vi chức năng:**

- FR-1. Nhấn icon thùng rác đặt `pendingRevoke` thành dữ liệu hàng của key trong local component state, mở ConfirmDialog.
- FR-2. Khi nhấn "Cancel" hoặc đóng dialog, `pendingRevoke` được đặt thành `null`; không có mutation nào được kích hoạt.
- FR-3. Khi xác nhận "Revoke", `keys.remove` được gọi với `{ token: pendingRevoke.token }`.
- FR-4. Phía server đối với `USER`: `keys.remove` gọi `getKeyInfo(token)` trước (LiteLLM `GET /key/info`) để kiểm tra quyền sở hữu. Nếu key không tồn tại (`NOT_FOUND` từ LiteLLM), trả về `NOT_FOUND`. Nếu `key.user_id !== context.user.id`, trả về `FORBIDDEN`. Chỉ sau đó mới gọi `POST /key/delete` với `{ keys: [token] }` trên LiteLLM.
- FR-5. Với `ADMIN`, kiểm tra quyền sở hữu bị bỏ qua và có thể xóa bất kỳ key nào.
- FR-6. Khi thành công: toast `Key "<alias|token>" revoked`; `pendingRevoke` đặt về `null` (dialog đóng); truy vấn `keys.list` bị làm mới để bảng cập nhật.
- FR-7. Khi gặp lỗi: toast `"Revoke failed: <message>"`; dialog vẫn mở; `pendingRevoke` không thay đổi.

**Trạng thái & trường hợp đặc biệt:**

- Key đã bị xóa trước khi xác nhận (phiên đồng thời): lỗi `NOT_FOUND` từ server; toast hiển thị lỗi; bảng vẫn cũ cho đến lần làm mới tiếp theo.
- Người dùng cố thu hồi key của người dùng khác qua lời gọi API trực tiếp: `FORBIDDEN` được trả về.
- Lỗi mạng trong quá trình xóa: toast lỗi được hiển thị; key vẫn xuất hiện trong bảng.
- Thu hồi key cuối cùng còn lại: bảng chuyển sang trạng thái trống sau khi `keys.list` tải lại.
- Thu hồi key đang được code sử dụng: LiteLLM lập tức từ chối các request tiếp theo với 401; không có thời gian ân hạn.

**Tiêu chí chấp nhận:**

- AC-1. Giả sử một hàng key trong bảng, khi người dùng nhấn icon thùng rác, thì ConfirmDialog xuất hiện với alias của key trong tiêu đề và cảnh báo không thể hoàn tác.
- AC-2. Giả sử ConfirmDialog đang mở, khi người dùng nhấn "Cancel", thì dialog đóng lại và key vẫn còn trong bảng.
- AC-3. Giả sử người dùng nhấn "Revoke", khi mutation đang xử lý, thì cả hai nút dialog bị vô hiệu hóa và nhãn "Revoke" hiển thị "Working…".
- AC-4. Giả sử thu hồi thành công, khi mutation hoàn tất, thì dialog đóng lại, toast thành công xuất hiện với alias key, và key không còn trong bảng.
- AC-5. Giả sử key đã bị xóa trước đó, khi mutation thu hồi trả về NOT_FOUND, thì toast lỗi được hiển thị và dialog vẫn mở.
- AC-6. Giả sử USER nhấn thu hồi trên key của chính mình, thì xóa thành công. Giả sử USER cố xóa key của người dùng khác ở cấp API, thì FORBIDDEN được trả về.

---

### Bảng Điều Khiển Mức Sử Dụng (Usage Dashboard)

**Mục đích:** Cung cấp cái nhìn toàn diện về mức sử dụng API của người dùng trong khoảng thời gian có thể chọn (7, 30 hoặc 90 ngày), bao gồm tổng chi phí, số lượng request, phân tích theo model, phân tích theo phần cứng, biểu đồ chi tiêu hàng ngày và nhật ký request gần đây.

**Điều kiện tiên quyết / truy cập:** Người dùng đã được xác thực. Truy cập qua liên kết điều hướng "Usage" (`/usage`). Tất cả dữ liệu mức sử dụng được lọc phía server theo lưu lượng của người dùng đã xác thực, khớp với `end_user === userId` (lưu lượng chat) hoặc `metadata.user_api_key_user_id === userId` (lưu lượng từ key đã cấp).

**Thành phần giao diện:**

- Tiêu đề trang: "Usage" (h1, `text-3xl font-semibold`).
- Tiêu đề phụ: "Tokens, cost, and recent requests across chat and your API keys."
- **Bộ chọn Period** (góc trên bên phải của header): nhóm nút phân đoạn với ba tùy chọn: "7 days" / "30 days" / "90 days". Period đang hoạt động có variant mặc định (đầy màu); các period không hoạt động là ghost. Mặc định: 7 days.
- **Thẻ Summary** (4 thẻ trong lưới responsive, tải lại khi period thay đổi):
  - "Total cost" — USD định dạng.
  - "Requests" — số nguyên, định dạng locale.
  - "Models used" — số lượng tên model phân biệt; gợi ý "No traffic in this period" khi bằng 0.
  - "Primary hardware" — thẻ `hardware_id` của thiết bị có nhiều request nhất trong period, dạng monospace. `Badge` hiển thị loại backend (`npu` → variant mặc định / đầy; loại khác → variant secondary). Hiển thị "—" khi không có dữ liệu phần cứng. (Yêu cầu tích hợp Langfuse; xem lưu ý bên dưới.)
- **Biểu đồ chi tiêu hàng ngày** ("Last \<N\> days"): cùng component như trên trang Profile — biểu đồ cột với số request và tổng chi phí trong header, ngày đỉnh được làm nổi bật, thống kê footer "Last request" theo thời gian tương đối.
- **Thẻ By model** ("By model"): danh sách model xếp hạng theo chi tiêu. Mỗi hàng: tên model dạng monospace; chi tiêu USD + số request bên phải; thanh ngang (tương đối so với model chi tiêu cao nhất). "No usage in this period." khi trống.
- **Thẻ By hardware** ("By hardware"): danh sách giá trị `hardware_id` xếp hạng theo chi tiêu. Mỗi hàng: hardware ID dạng monospace; badge loại backend; chi tiêu USD + số request. Màu thanh: màu chính (đầy) cho backend NPU, màu chính/55 (mờ hơn) cho các loại khác. Khi đạt giới hạn trang trace Langfuse (500 trace qua `MAX_PAGES = 5` trang × 100), ghi chú cắt bớt "(recent traces only — ask for older with a longer period)" được hiển thị. Thẻ bị ẩn hoàn toàn khi không có dữ liệu phần cứng nào được trả về (component trả về `null`).
- **Bảng Recent requests** ("Recent requests"): hiển thị tối đa 50 request từ 30 ngày qua, mới nhất trước. Cột: **When** (thời gian tương đối, ví dụ: "5 min ago", "3 hr ago"), **Model** (monospace), **Source** (badge: variant secondary với alias key cho lưu lượng `via='key'`; badge outline "chat" cho lưu lượng `via='chat'`), **Cost** (monospace USD căn phải). "No requests yet — usage will appear here as you chat or call the API." khi trống.
- **Skeleton loaders** được hiển thị độc lập cho mỗi thẻ trong khi truy vấn của nó đang chờ xử lý.

**Hành vi chức năng:**

- FR-1. Khi khởi tạo và khi period thay đổi, SPA phát bốn truy vấn song song: `usage.summary`, `usage.daily`, `usage.byModel`, `usage.byHardware` — tất cả với giá trị `days` hiện tại. `usage.recent` luôn được tải với `{ limit: 50 }` (độc lập với bộ chọn period).
- FR-2. `usage.summary` kết hợp nhật ký chi tiêu LiteLLM (cho chi phí + số request + đa dạng model) với trace Langfuse (cho thẻ `hardware_id` và `backend_type`). Nếu thông tin xác thực Langfuse chưa được cấu hình, thủ tục ném một `Error` thuần túy (không phải `LangfuseError`) — cụ thể là `new Error('LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not configured')`. `LangfuseError` chỉ được ném khi server Langfuse có thể tiếp cận nhưng trả về phản hồi HTTP không thành công. Cả hai loại lỗi đều lan truyền như lỗi oRPC chung đến client; thẻ "Primary hardware" hiển thị trạng thái lỗi.
- FR-3. `usage.daily` điền trước mỗi ngày trong period với $0.00 chi tiêu để biểu đồ luôn có đúng `days` cột, kể cả khi có khoảng trống trong nhật ký.
- FR-4. `usage.byModel` chuẩn hóa tên model bằng cách bỏ tiền tố `openai/` (ví dụ: `openai/qwen2.5:3b` → `qwen2.5:3b`).
- FR-5. `usage.byHardware` đọc các thẻ `hardware_id:` và `backend_type:` được đóng dấu trên trace Langfuse bởi hook trước khi gọi LiteLLM. `hardware_id` không xác định (không có thẻ) được nhóm dưới `"unknown"`.
- FR-6. `usage.recent` tải nhật ký 30 ngày qua, sắp xếp giảm dần theo `startTime` và cắt đến `limit`. Badge "Source" hiển thị alias key nếu nhật ký có `metadata.user_api_key_alias`; ngược lại hiển thị "key" cho lưu lượng API-key hoặc "chat" cho lưu lượng chat.
- FR-7. Nếu bất kỳ truy vấn nào trả về 401, SPA điều hướng đến `/unauthorized`.
- FR-8. Thay đổi period tái sử dụng dữ liệu đã cache trong thời gian stale của TanStack Query; các biểu đồ hiển thị lại ngay với dữ liệu của truy vấn mới khi khả dụng.

**Trạng thái & trường hợp đặc biệt:**

- Không có mức sử dụng trong period đã chọn: tất cả giá trị chi tiêu là $0.00, biểu đồ cột hiển thị thanh trống (thanh xám 4px cho ngày không), "By model" hiển thị "No usage in this period.", thẻ "By hardware" bị ẩn.
- Langfuse chưa được cấu hình: `usage.summary` và `usage.byHardware` ném lỗi server; thẻ "Primary hardware" hiển thị lỗi. SPA hiển thị đoạn lỗi chung cho lỗi truy vấn không phải 401 — không có thông báo "Langfuse not connected" chuyên biệt trong mã SPA hiện tại.
- Đạt giới hạn trang trace: thẻ "By hardware" hiển thị ghi chú cắt bớt; dữ liệu hiển thị chỉ là 500 trace gần nhất.
- Số tiền chi tiêu rất nhỏ (dưới một xu): `formatUsd` hiển thị bốn chữ số thập phân (ví dụ: `$0.0001`).
- Biểu đồ chỉ có một ngày khác không: ngày đó hiển thị ở chiều cao đầy đủ (100%); tất cả các ngày khác ở chiều cao 0 (thanh xám 4px).

**Tiêu chí chấp nhận:**

- AC-1. Giả sử trang Usage tải cho người dùng có hoạt động trong 7 ngày qua, khi trang hiển thị, thì thẻ thống kê "Total cost" hiển thị số tiền USD khác không và biểu đồ hàng ngày có 7 cột.
- AC-2. Giả sử người dùng đổi period sang "30 days", khi bộ chọn được nhấn, thì cả bốn thẻ phụ thuộc tóm tắt và biểu đồ tải lại và hiển thị lại với dữ liệu 30 ngày.
- AC-3. Giả sử người dùng đã thực hiện request bằng API-key, khi bảng Recent Requests hiển thị, thì các hàng đó có badge secondary chứa alias key (hoặc "key" nếu không có alias).
- AC-4. Giả sử trace Langfuse tồn tại với thẻ `hardware_id:npu-01` và `backend_type:npu`, khi thẻ "By hardware" hiển thị, thì `npu-01` xuất hiện với badge "npu" đầy màu.
- AC-5. Giả sử không có hoạt động trong period đã chọn, khi thẻ "By model" hiển thị, thì nó hiển thị "No usage in this period." và thẻ "By hardware" không hiển thị.
- AC-6. Giả sử bảng "Recent requests" không có dữ liệu, khi thẻ hiển thị, thì thông báo trạng thái trống được hiển thị: "No requests yet — usage will appear here as you chat or call the API."
- AC-7. Giả sử tất cả truy vấn mức sử dụng trả về 401, khi trang hiển thị, thì trình duyệt điều hướng đến `/unauthorized`.

---

### Hiển Thị Ngân Sách & Mức Sử Dụng (Cross-cutting)

**Mục đích:** Trình bày thông tin ngân sách và chi tiêu nhất quán xuyên suốt console để người dùng có thể hiểu ngay hạn mức còn lại và lịch sử tiêu thụ của mình.

**Điều kiện tiên quyết / truy cập:** Tất cả số liệu ngân sách và chi tiêu yêu cầu phiên đã xác thực và tài khoản LiteLLM đã được cấp phát thành công.

**Thành phần giao diện:** Dữ liệu ngân sách và chi tiêu xuất hiện ở ba vị trí: thẻ Available Hero (trang Profile), thanh ngân sách nội tuyến theo từng key (Key Table) và thống kê "Total budget" cùng "Used across keys" trên trang Keys. Tổng chi tiêu cũng được hiển thị trên các thẻ tóm tắt trang Usage.

**Hành vi chức năng:**

- FR-1. `me.get` tính `spend.total = spend.chat + spend.issuedKeys`. `spend.chat` được lấy từ hàng Customer (End-User) LiteLLM; `spend.issuedKeys` là tổng `spend` của kết quả `keys.list`. Trường `spend` của Internal-User không được dùng vì nó không ghi nhận lưu lượng chat trong phiên bản LiteLLM hiện tại.
- FR-2. `limits.maxBudget` và `limits.budgetDuration` đến từ hàng Internal-User (được cấp phát lúc JIT).
- FR-3. `pctSpent(spend, max)` kẹp trong [0, 100] và làm tròn đến số nguyên gần nhất. `max` null hoặc bằng không trả về 0%.
- FR-4. `formatUsd` định dạng số tiền theo ba mức: chính xác $0.00 → `$0.00`; dưới một xu (< $0.01) → 4 chữ số thập phân (ví dụ: `$0.0050`); từ $0.01 đến $0.99 → 3 chữ số thập phân (ví dụ: `$0.125`); ≥ $1.00 → 2 chữ số thập phân (ví dụ: `$1.50`). Lưu ý: giá trị $0.005 vừa là dưới một đô vừa là dưới một xu, nên nhận 4 chữ số thập phân, không phải 3.
- FR-5. `compactNumber` định dạng số nguyên lớn bằng ký hiệu thu gọn Intl (ví dụ: `10000` → `10K`). Giá trị null hiển thị là `∞`.
- FR-6. Thanh ngân sách theo từng key và thanh Available Hero chia sẻ cùng logic ngưỡng (FR-3 trong phần Trang Profile ở trên).

**Trạng thái & trường hợp đặc biệt:**

- `max_budget = null` (không giới hạn): Available Hero hiển thị dạng không giới hạn; thanh mức sử dụng theo từng key không hiển thị với key có ngân sách null; `compactNumber(null)` = `∞` cho hiển thị giới hạn tốc độ.
- Chi tiêu vượt ngân sách (ví dụ: do bùng nổ tốc độ trước khi LiteLLM áp dụng giới hạn): `pctSpent` kẹp ở 100%; thanh đầy màu đỏ; số dư còn lại hiển thị $0.00.
- Chi tiêu âm: không được mong đợi; `Math.max(0, maxBudget - spent)` ngăn giá trị còn lại âm.

**Tiêu chí chấp nhận:**

- AC-1. Giả sử `spend = 0.00005`, khi bộ định dạng USD được áp dụng, thì giá trị hiển thị là `$0.0001` (4 chữ số thập phân).
- AC-2. Giả sử `max_budget = null`, khi Available Hero hiển thị, thì dạng không giới hạn được hiển thị (không thanh tiến trình, không dòng "of").
- AC-3. Giả sử `spend = 12`, `max_budget = 10` (vượt ngân sách), khi Available Hero hiển thị, thì số dư còn lại hiển thị "$0.00" và thanh đầy màu đỏ.
- AC-4. Giả sử `tpm_limit = null`, khi thẻ Per-minute limits hiển thị, thì giá trị tokens/min hiển thị "∞".
