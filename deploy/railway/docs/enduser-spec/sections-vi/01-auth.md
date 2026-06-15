## Xác thực & Truy cập Tài khoản

> **Phạm vi ghi chú – Cấu hình triển khai NuFi**
> Phần này ghi lại các tính năng xác thực đang hoạt động trong triển khai NuFi
> (NuFi Chat được phục vụ tại **https://chat.nufi.me**):
> `ALLOW_REGISTRATION=true`, `ALLOW_EMAIL_LOGIN=true`, `ALLOW_PASSWORD_RESET=false`,
> `ALLOW_SOCIAL_LOGIN=true`, `ALLOW_SOCIAL_REGISTRATION=true`.
> Đăng nhập mạng xã hội bằng **Google** **đã được bật** (`GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`
> đã được thiết lập trong triển khai) và được mô tả bên dưới. Các nhà cung cấp Social/OAuth còn lại
> (GitHub, Discord, Facebook, Apple, OpenID, SAML) **chưa được cấu hình** (không có thông tin xác thực
> client) nên được bỏ qua. Xác thực hai yếu tố (2FA) tồn tại trong code nhưng không được đề cập ở đây
> trừ khi người dùng gặp màn hình 2FA do cài đặt tài khoản của họ (cần xác minh: xác nhận xem có người
> dùng NuFi nào đã bật 2FA hay không trước khi bỏ qua luồng đó).

---

### Đăng ký

- **Mục đích:** Cho phép người dùng mới tạo tài khoản email/mật khẩu trên Nufi Chat.

- **Điều kiện tiên quyết / truy cập:**
  - `ALLOW_REGISTRATION=true` (biến môi trường server). API phản hồi với `registrationEnabled: true`
    trong payload cấu hình khởi động; route và liên kết đăng ký chỉ được hiển thị khi cờ này
    có giá trị `true`.
  - Người dùng **chưa** xác thực. Lưu ý: với route `/register`, `StartupLayout` bên ngoài được
    khởi tạo không có prop `isAuthenticated`, do đó chuyển hướng khi đã xác thực **hiện chưa được
    thực thi** — người dùng đã xác thực điều hướng đến `/register` sẽ thấy form thay vì bị
    chuyển hướng.
  - Route: `GET /register`. Được hiển thị bởi component `Registration` bên trong `StartupLayout`.

- **Thành phần giao diện:**
  - Tiêu đề trang: **"Create your account"** (`com_auth_create_account`)
  - Liên kết phụ đề: **"Already have an account?"** + liên kết **"Login"** đến `/login`
    (`com_auth_already_have_account`, `com_auth_login`)
  - Trường: **Full name** (Họ tên đầy đủ) (`com_auth_full_name`), `type="text"`, `id="name"`, `data-testid="name"`
  - Trường: **Username (optional)** (Tên người dùng - tùy chọn) (`com_auth_username`), `type="text"`, `id="username"`,
    `data-testid="username"` — tùy chọn, không có quy tắc `required`
  - Trường: **Email** (`com_auth_email`), `type="email"`, `id="email"`, `data-testid="email"`
  - Trường: **Password** (Mật khẩu) (`com_auth_password`), `type="password"`, `id="password"`,
    `data-testid="password"`
  - Trường: **Confirm password** (Xác nhận mật khẩu) (`com_auth_password_confirm`), `type="password"`,
    `id="confirm_password"`, `data-testid="confirm_password"`
  - Nút gửi: **"Continue"** (`com_auth_continue`), `aria-label="Submit registration"`,
    `variant="submit"`
  - Tất cả các trường sử dụng kiểu nhãn nổi (nhãn hiển thị phía trên ô nhập khi được focus hoặc đã điền;
    placeholder `" "` được dùng làm điểm neo hiển thị khi trạng thái peer hoạt động)
  - Các trường không hợp lệ sẽ nhận `aria-invalid="true"` và đường viền màu destructive; lỗi nội tuyến
    xuất hiện bên dưới trường dưới dạng `<span role="alert">`
  - Khi thành công, một banner xuất hiện với tông màu tím thương hiệu kèm văn bản thành công và đếm ngược
  - Form sử dụng `mode: 'onChange'` — xác thực kích hoạt mỗi lần gõ phím sau lần chạm đầu tiên

- **Hành vi chức năng:**
  1. **FR-1** Client gửi POST dữ liệu form (name, username, email, password, confirm_password,
     và tùy chọn tham số truy vấn `token` nếu URL chứa `?token=<invite>`) đến endpoint API đăng ký
     thông qua `useRegisterUserMutation`.
  2. **FR-2** Trong khi yêu cầu đang xử lý, nút gửi bị vô hiệu hóa và `Spinner` thay thế nhãn nút.
  3. **FR-3** Khi nhận được phản hồi API thành công, form bị ẩn và hiển thị banner thành công. Nội dung
     banner phụ thuộc vào việc server có cấu hình gửi email hay không:
     - Dịch vụ email đã cấu hình: **"Please check your email to verify your email address."**
       (`com_auth_registration_success_generic`)
     - Dịch vụ email chưa cấu hình: **"Registration successful."**
       (`com_auth_registration_success_insecure`)
     Cả hai biến thể đều tiếp theo là **"Redirecting in N seconds..."**
     (`com_auth_email_verification_redirecting`) với đếm ngược 3 giây.
  4. **FR-4** Sau khi đếm ngược về 0, trình duyệt điều hướng đến `/c/new` (thay thế mục lịch sử).
  5. **FR-5** Nút gửi bị vô hiệu hóa khi `Object.keys(errors).length > 0` hoặc
     `isSubmitting === true`.

- **Kiểm tra hợp lệ & lỗi:**

  | Trường | Quy tắc | Thông báo lỗi (khóa dịch → chuỗi tiếng Anh) |
  |---|---|---|
  | Full name | bắt buộc | `com_auth_name_required` → "Name is required" |
  | Full name | minLength 3 | `com_auth_name_min_length` → "Name must be at least 3 characters" |
  | Full name | maxLength 80 | `com_auth_name_max_length` → "Name must be less than 80 characters" |
  | Username | minLength 2 (khi được cung cấp) | `com_auth_username_min_length` → "Username must be at least 2 characters" |
  | Username | maxLength **80** (thực thi) | `com_auth_username_max_length` → "Username must be less than 20 characters" (**lỗi trong code**: giới hạn được thực thi là 80 ký tự nhưng thông báo lỗi ghi "20 characters") |
  | Email | bắt buộc | `com_auth_email_required` → "Email is required" |
  | Email | maxLength 120 | `com_auth_email_max_length` → "Email should not be longer than 120 characters" |
  | Email | pattern `/\S+@\S+\.\S+/` | `com_auth_email_pattern` → "You must enter a valid email address" |
  | Password | bắt buộc | `com_auth_password_required` → "Password is required" |
  | Password | minLength (mặc định 8, hoặc `minPasswordLength` từ cấu hình server) | `com_auth_password_min_length` → "Password must be at least 8 characters" |
  | Password | maxLength 128 | `com_auth_password_max_length` → "Password must be less than 128 characters" |
  | Confirm password | phải khớp với giá trị trường Password | `com_auth_password_not_match` → "Passwords do not match" |

  - Lỗi phía server (ví dụ: email trùng lặp) được trả về trong `error.response.data.message` và
    hiển thị với tiền tố **"There was an error attempting to register your account. Please
    try again."** (`com_auth_error_create`) theo sau là thông báo từ server.

- **Trường hợp đặc biệt:**
  - **Email trùng lặp:** Server trả về lỗi; thông báo lỗi từ `response.data.message`
    được hiển thị bên dưới tiền tố `com_auth_error_create`.
  - **Captcha (Turnstile):** Nếu `startupConfig.turnstile.siteKey` được thiết lập, widget
    Cloudflare Turnstile được hiển thị và nút gửi vẫn bị vô hiệu hóa cho đến khi nhận được token hợp lệ.
    Trong triển khai hiện tại của NuFi, cần xác minh xem `TURNSTILE_SITE_KEY` có được cấu hình không.
  - **Đăng ký bằng token mời:** Nếu URL chứa `?token=<value>`, token được chuyển tiếp
    đến API. Giao diện hoạt động giống nhau; mọi hạn chế bổ sung được thực thi ở phía server.
  - **Đã xác thực:** Với `/register`, chuyển hướng **không được thực thi** (outer `StartupLayout`
    không nhận prop `isAuthenticated`), nên người dùng đã xác thực vẫn thấy form đăng ký thay vì bị
    chuyển đến `/c/new`.
  - **Lỗi mạng:** `onError` của mutation kích hoạt, `isSubmitting` trở về `false`, và
    thông báo từ server được hiển thị. Không tự động thử lại.

- **Tiêu chí chấp nhận:**
  1. **AC-1** Giả sử người dùng chưa xác thực và điều hướng đến `/register`, Khi trang
     tải xong, Thì một form đăng ký được hiển thị với các trường Full name, Username, Email,
     Password, Confirm password và nút **Continue** (nút được kích hoạt khi tải trang lần đầu;
     chỉ bị vô hiệu hóa sau khi lỗi xác thực đầu tiên xảy ra).
  2. **AC-2** Giả sử người dùng gửi form với Full name ngắn hơn 3 ký tự, Khi
     trường được thay đổi, Thì lỗi nội tuyến "Name must be at least 3 characters" xuất hiện
     bên dưới trường và nút Continue vẫn bị vô hiệu hóa.
  3. **AC-3** Giả sử người dùng nhập địa chỉ email không khớp với pattern
     `\S+@\S+\.\S+`, Khi giá trị trường thay đổi, Thì "You must enter a valid email address"
     xuất hiện và form không thể gửi.
  4. **AC-4** Giả sử người dùng nhập Password ngắn hơn 8 ký tự, Khi trường được
     thay đổi, Thì "Password must be at least 8 characters" xuất hiện và form không thể gửi.
  5. **AC-5** Giả sử giá trị trường Confirm password không khớp với trường Password, Khi
     trường được thay đổi, Thì "Passwords do not match" xuất hiện và form không thể gửi.
  6. **AC-6** Giả sử tất cả các trường hợp lệ và người dùng nhấp Continue, Thì nút hiển thị
     spinner, API được gọi, và khi thành công một banner được hiển thị với thông báo thành công
     phù hợp theo sau là đếm ngược 3 giây.
  7. **AC-7** Giả sử đăng ký thành công, Khi đếm ngược 3 giây kết thúc, Thì
     trình duyệt điều hướng đến `/c/new`.
  8. **AC-8** Giả sử API đăng ký trả về lỗi email trùng lặp, Thì banner lỗi
     hiển thị "There was an error attempting to register your account. Please try again." theo sau
     là thông báo từ server, và form được kích hoạt lại.
  9. **AC-9** Giả sử người dùng đã xác thực, Khi họ điều hướng đến `/register`, Thì
     họ **không** bị chuyển hướng (chuyển hướng xác thực chưa được thực thi trên `StartupLayout`
     bên ngoài cho `/register`) — họ sẽ thấy form đăng ký. AC này **chưa được triển khai**
     như mô tả.

---

### Đăng nhập (Email / Mật khẩu)

- **Mục đích:** Cho phép người dùng đã đăng ký xác thực bằng địa chỉ email và mật khẩu.

- **Điều kiện tiên quyết / truy cập:**
  - `ALLOW_EMAIL_LOGIN=true` (biến môi trường server). API trả về `emailLoginEnabled: true`;
    component `LoginForm` chỉ được mount khi `startupConfig.emailLoginEnabled === true`.
  - Route: `GET /login`. Được hiển thị bởi component `Login` bên trong `LoginLayout` /
    `StartupLayout`.
  - Người dùng không được xác thực. Phiên đã xác thực kích hoạt chuyển hướng đến `/c/new`.

- **Thành phần giao diện:**
  - Tiêu đề trang: **"Welcome back"** (`com_auth_welcome_back`)
  - Phụ đề: **"Don't have an account?"** + liên kết **"Sign up"** đến `/register`
    (`com_auth_no_account`, `com_auth_sign_up`) — chỉ hiển thị khi `registrationEnabled` không phải
    `false`
  - Trường: **Email address** (Địa chỉ email) (`com_auth_email_address`), `type="text"`, `id="email"`,
    `autoComplete="email"`. Nhãn văn bản: "Email address" (hoặc "Username" nếu cấu hình LDAP —
    không áp dụng trong NuFi).
  - Trường: **Password** (Mật khẩu) (`com_auth_password`), `type="password"`, `id="password"`,
    `autoComplete="current-password"`
  - Liên kết: **"Forgot Password?"** (`com_auth_password_forgot`) — điều hướng đến `/forgot-password`.
    Liên kết này chỉ được hiển thị khi `startupConfig.passwordResetEnabled === true`. Trong NuFi
    (`ALLOW_PASSWORD_RESET=false`) liên kết này **không được hiển thị**.
  - Nút gửi: **"Continue"** (`com_auth_continue`), `data-testid="login-button"`,
    `variant="submit"`. Hiển thị `Spinner` trong khi gửi.
  - Banner lỗi (phía trên form): được hiển thị bởi `<ErrorMessage>` (`role="alert"`,
    `aria-live="assertive"`) khi `error != null`
  - Banner gửi lại xác minh: hiển thị khi lỗi chứa `"422"` — xem phần Kiểm tra hợp lệ.
  - Bảng bên trái (chỉ desktop): thương hiệu NuFi với văn bản **"Think it. Ask it. Done."** và
    logo `/assets/nufi-logo.svg`; ẩn trên mobile.
  - Bộ chọn giao diện (góc trên phải, mọi kích thước màn hình)

- **Hành vi chức năng:**
  1. **FR-1** Khi gửi form, client gọi `loginUser.mutate({ email, password })` thông qua
     `useLoginUserMutation`.
  2. **FR-2** Khi nhận được phản hồi API thành công với kết quả thông thường (không phải 2FA),
     `isAuthenticated` được đặt thành `true`, JWT token được lưu trong bộ nhớ và đặt làm header
     Authorization của Axios, và trình duyệt điều hướng đến `/c/new` (hoặc đến đường dẫn
     deep-link đã lưu — xem Phiên & Lưu trữ Token).
  3. **FR-3** Khi có lỗi, văn bản lỗi từ phản hồi API được đặt qua `setError`; thông báo
     lỗi được ánh xạ qua `getLoginError` sang khóa dịch và hiển thị trong banner `ErrorMessage`
     phía trên form. URL được cập nhật thành `/login` (hoặc `/login?redirect_to=<path>` nếu
     tồn tại deep link đang chờ) sử dụng `replace: true`.
  4. **FR-4** Trong khi yêu cầu đang xử lý, nút gửi bị vô hiệu hóa và hiển thị `Spinner`.
  5. **FR-5** Cloudflare Turnstile: nếu `startupConfig.turnstile.siteKey` có giá trị, widget
     phải thành công trước khi nút gửi được kích hoạt (cần xác minh: xác nhận xem Turnstile có
     đang hoạt động trong triển khai NuFi không).
  6. **FR-6** Bảo tồn deep-link: nếu trang đăng nhập được truy cập qua tham số truy vấn
     `?redirect_to=<path>` hoặc qua `location.state.redirect_to`, đường dẫn đích được lưu vào
     `sessionStorage` dưới khóa `post_login_redirect_to`. Khi đăng nhập thành công,
     `getPostLoginRedirect` phân giải đường dẫn đã lưu và điều hướng đến đó thay vì `/c/new`,
     với điều kiện đường dẫn vượt qua kiểm tra `isSafeRedirect` (phải bắt đầu bằng `/`, không phải `//`,
     và không được chứa đoạn `/login`).

- **Kiểm tra hợp lệ & lỗi:**

  | Trường | Quy tắc | Thông báo lỗi |
  |---|---|---|
  | Email | bắt buộc | `com_auth_email_required` → "Email is required" |
  | Email | maxLength 120 | `com_auth_email_max_length` → "Email should not be longer than 120 characters" |
  | Email | email hợp lệ (Zod) | `com_auth_email_pattern` → "You must enter a valid email address" |
  | Password | bắt buộc | `com_auth_password_required` → "Password is required" |
  | Password | minLength (mặc định 8) | `com_auth_password_min_length` → "Password must be at least 8 characters" |
  | Password | maxLength 128 | `com_auth_password_max_length` → "Password must be less than 128 characters" |

  Lỗi phía server được ánh xạ theo mã HTTP (qua `getLoginError`):

  | Điều kiện | Mã HTTP trong chuỗi lỗi | Thông báo lỗi (khóa → chuỗi tiếng Anh) |
  |---|---|---|
  | Thông tin sai / người dùng không tồn tại | (không có mã cụ thể — mặc định) | `com_auth_error_login` → "Unable to login with the information provided. Please check your credentials and try again." |
  | Quá nhiều lần thử | 429 | `com_auth_error_login_rl` → "Too many login attempts in a short amount of time. Please try again later." |
  | Tài khoản bị cấm | 403 | `com_auth_error_login_ban` → "Your account has been temporarily banned due to violations of our service." |
  | Lỗi server | 500 | `com_auth_error_login_server` → "There was an internal server error. Please wait a few moments and try again." |
  | Email chưa xác minh | 422 | `com_auth_error_login_unverified` → "Your account has not been verified. Please check your email for a verification link." |

  - **Tài khoản chưa xác minh (422) — giao diện bổ sung:** Khi chuỗi lỗi chứa `"422"`,
    `showResendLink` được đặt thành `true`. Một banner phụ xuất hiện bên dưới lỗi chính với
    văn bản **"Didn't receive the email?"** (`com_auth_email_verification_resend_prompt`) và nút
    **"Resend Email"** (`com_auth_email_resend_link`). Nhấp vào nút gọi
    `useResendVerificationEmail` với email hiện có trong trường form.

- **Trường hợp đặc biệt:**
  - **Gửi form trống:** Xác thực trường bắt buộc phía client kích hoạt; nút gửi không bị vô hiệu hóa
    mặc định trên form trống (chưa có `errors`), nhưng quy tắc `required` kích hoạt khi cố gửi
    và lỗi nội tuyến được hiển thị.
  - **Sai mật khẩu:** API trả về lỗi không chứa 429 / 403 / 500 / 422, nên thông báo
    mặc định `com_auth_error_login` được hiển thị.
  - **Giới hạn tốc độ (429):** Thông báo giới hạn tốc độ được hiển thị; form được kích hoạt lại để
    thử lại nhưng sẽ tiếp tục thất bại cho đến khi cửa sổ giới hạn tốc độ hết hạn.
  - **Đã xác thực:** Effect của `StartupLayout` phát hiện `isAuthenticated === true` và
    điều hướng đến `/c/new`.
  - **Cấu hình khởi động không khả dụng:** Nếu lệnh gọi API lấy cấu hình khởi động thất bại, một
    banner lỗi được hiển thị với **"There was an internal server error. Please wait a few moments and try again."**
    (`com_auth_error_login_server`) qua component `DisplayError` của `AuthLayout`.
  - **Lỗi mạng:** `loginUser.onError` kích hoạt; thông báo lỗi được hiển thị.

- **Tiêu chí chấp nhận:**
  1. **AC-1** Giả sử người dùng chưa xác thực và điều hướng đến `/login`, Khi trang tải xong,
     Thì tiêu đề "Welcome back", các trường email và password được hiển thị cùng với nút "Continue".
  2. **AC-2** Giả sử người dùng gửi form với trường email để trống, Thì lỗi nội tuyến
     "Email is required" xuất hiện và không có lệnh gọi API nào được thực hiện.
  3. **AC-3** Giả sử người dùng nhập định dạng email không hợp lệ, Thì "You must enter a valid email
     address" xuất hiện nội tuyến và form không thể gửi.
  4. **AC-4** Giả sử người dùng gửi thông tin đăng nhập hợp lệ, Khi API phản hồi thành công, Thì
     người dùng được chuyển hướng đến `/c/new` và giao diện chat chính được hiển thị.
  5. **AC-5** Giả sử người dùng gửi thông tin đăng nhập sai, Khi API phản hồi với lỗi không khớp
     422/429/403/500, Thì banner "Unable to login with the information provided.
     Please check your credentials and try again." được hiển thị.
  6. **AC-6** Giả sử API trả về 422 (email chưa xác minh), Thì thông báo lỗi tài khoản chưa xác minh
     được hiển thị VÀ banner phụ "Didn't receive the email? Resend Email" xuất hiện.
  7. **AC-7** Giả sử người dùng nhấp "Resend Email" trong banner chưa xác minh, Khi lệnh gọi
     API gửi lại thành công, Thì banner xóa đi và không có lỗi nào thêm được hiển thị.
  8. **AC-8** Giả sử người dùng truy cập `/login?redirect_to=/c/some-conversation`, Khi họ
     đăng nhập thành công, Thì họ được chuyển hướng đến `/c/some-conversation` thay vì `/c/new`.
  9. **AC-9** Giả sử API trả về mã 429, Thì thông báo lỗi "Too many login
     attempts in a short amount of time. Please try again later." được hiển thị.
  10. **AC-10** Giả sử người dùng đã xác thực, Khi họ điều hướng đến `/login`, Thì họ
      được chuyển hướng ngay đến `/c/new`.

---

### Đăng nhập bằng Google (đăng nhập mạng xã hội)

- **Mục đích:** Cho phép người dùng đăng nhập — và với người dùng lần đầu, đăng ký — bằng tài khoản
  Google thay vì email/mật khẩu, thông qua Google OAuth 2.0.

- **Điều kiện tiên quyết / truy cập:**
  - `ALLOW_SOCIAL_LOGIN=true` và đã cấu hình thông tin xác thực Google (`GOOGLE_CLIENT_ID` +
    `GOOGLE_CLIENT_SECRET`); khi đó server báo `googleLoginEnabled: true` và danh sách `socialLogins`
    có chứa `google`. Cả hai điều kiện đều đúng trong triển khai NuFi.
  - Việc tạo tài khoản hoàn toàn mới qua Google còn yêu cầu `ALLOW_SOCIAL_REGISTRATION=true`
    (đã bật trong NuFi).
  - Người dùng chưa đăng nhập.
  - Có sẵn trên cả trang đăng nhập (`/login`) và trang đăng ký (`/register`) tại
    **https://chat.nufi.me**.

- **Thành phần giao diện:**
  - Một đường phân cách hiển thị **"OR"** (`com_auth_or`) ngăn cách biểu mẫu email/mật khẩu với
    nút mạng xã hội (hiển thị vì đăng nhập bằng email cũng đang bật).
  - Nút **"Continue with Google"** (`com_auth_google_login`), `data-testid="google"`, kèm biểu tượng
    Google. Đây là một liên kết được tạo kiểu trỏ tới `{DOMAIN_SERVER}/oauth/google` — trên production
    là **https://chat.nufi.me/oauth/google**.
  - Chỉ nút Google xuất hiện — không có nút GitHub / Discord / Facebook / OpenID / SAML (các nhà cung
    cấp đó chưa được cấu hình).

- **Hành vi chức năng:**
  1. **FR-1** Khi người dùng nhấn **Continue with Google**, trình duyệt điều hướng tới endpoint
     `/oauth/google` của server; endpoint này chuyển hướng tới màn hình đồng ý (consent) OAuth của Google.
  2. **FR-2** Người dùng xác thực với Google và cấp các quyền được yêu cầu (openid, profile, email).
  3. **FR-3** Google chuyển hướng trở lại callback đã cấu hình (`GOOGLE_CALLBACK_URL` =
     `/oauth/google/callback`); server xác minh phản hồi.
  4. **FR-4** Nếu chưa có tài khoản NuFi cho email Google đó và `ALLOW_SOCIAL_REGISTRATION=true`,
     một tài khoản mới được tạo từ hồ sơ Google (tên, email, ảnh đại diện). Nếu tài khoản đã tồn tại
     **và cũng được tạo qua Google** (`provider = google`), người dùng được đăng nhập vào tài khoản
     đó. Nếu email thuộc về một **tài khoản mật khẩu** (`provider = local`), đăng nhập Google sẽ
     **bị từ chối** — xem FR-7 / trường hợp đặc biệt.
  7. **FR-7** **Không gộp tài khoản (no account linking).** Nếu đã tồn tại tài khoản cho email đó
     nhưng với nhà cung cấp đăng nhập **khác** (vd `local` cho email/mật khẩu), server trả về
     `AUTH_FAILED`. `failureRedirect` của Passport trỏ đến route phía server `/oauth/error`, route
     này chuyển hướng trình duyệt về `/login?redirect=false&error=AUTH_FAILED`. Trang Login sau đó
     phát hiện `?error=AUTH_FAILED` và hiển thị **toast** với thông báo *"Authentication failed.
     Please check your login method and try again."* (`com_auth_error_oauth_failed`). **Không có**
     trang "Authentication Failed" riêng biệt với nút "Close Window" trong luồng thất bại.
     LibreChat **không** liên kết danh tính Google với tài khoản mật khẩu sẵn có, và **không có
     tùy chọn cấu hình nào để bật việc gộp**.
     (Nguồn: `api/strategies/socialLogin.js`, `api/server/routes/oauth.js`, `client/src/components/Auth/Login.tsx`.)
  5. **FR-5** Khi thành công, server thiết lập phiên (cấp JWT) và trình duyệt vào màn hình chat tại
     `/c/new`.
  6. **FR-6** Khi thất bại, hoặc nếu người dùng hủy ở phía Google, Passport đi theo cùng luồng
     `failureRedirect` như FR-7: route `/oauth/error` phía server chuyển hướng về
     `/login?redirect=false&error=AUTH_FAILED` và trang Login hiển thị toast
     `com_auth_error_oauth_failed`. (cần xác minh thực tế trên sản phẩm đang chạy:
     xác nhận xem luồng hủy đồng ý Google có tạo ra sự khác biệt nào về toast hoặc
     chuyển hướng so với lỗi không khớp nhà cung cấp hay không.)

- **Trạng thái & trường hợp đặc biệt:**
  - **Người dùng hủy đồng ý ở Google:** không có phiên nào được tạo; trình duyệt được chuyển hướng
    về trang đăng nhập và toast `com_auth_error_oauth_failed` được hiển thị — *"Authentication
    failed. Please check your login method and try again."* (cần xác minh thực tế trên sản phẩm
    đang chạy: xác nhận xem hủy đồng ý có tạo ra trải nghiệm khác với lỗi không khớp nhà cung cấp
    hay không).
  - **Email đã đăng ký bằng email/mật khẩu (không gộp — đã xác nhận):** đăng nhập Google **bị từ
    chối**; trình duyệt được chuyển hướng về trang đăng nhập và toast *"Authentication failed.
    Please check your login method and try again."* (`com_auth_error_oauth_failed`) được hiển thị.
    Hai phương thức đăng nhập là **loại trừ lẫn nhau theo từng email** — một email đã đăng ký
    bằng mật khẩu thì không thể đăng nhập bằng Google sau đó (và ngược lại). Không có tính năng
    gộp và không có flag để bật. Đây là thiết kế có chủ đích (ngăn chiếm tài khoản qua email
    OAuth trùng khớp).
  - **Chuyển hướng toàn trang, không phải pop-up:** luồng này là điều hướng toàn trang nên trình chặn
    pop-up không liên quan.

- **Tiêu chí chấp nhận:**
  1. **AC-1** Giả sử đăng nhập Google đang bật, Khi người dùng mở `/login` hoặc `/register`, Thì một
     nút **Continue with Google** hiển thị bên dưới đường phân cách **"OR"** và không có nút nhà cung
     cấp mạng xã hội nào khác xuất hiện.
  2. **AC-2** Giả sử người dùng nhấn **Continue with Google**, Thì trình duyệt điều hướng tới
     `https://chat.nufi.me/oauth/google` rồi tới màn hình đồng ý của Google.
  3. **AC-3** Giả sử người dùng lần đầu hoàn tất đồng ý Google, Thì một tài khoản NuFi được tạo từ hồ
     sơ Google của họ và họ vào màn hình chat tại `/c/new`.
  4. **AC-4** Giả sử người dùng hiện có hoàn tất đồng ý Google, Thì họ được đăng nhập vào tài khoản của
     mình và vào `/c/new`.
  5. **AC-5** Giả sử người dùng hủy ở màn hình đồng ý của Google, Thì không có phiên nào được tạo,
     trình duyệt quay về trang Login và toast `com_auth_error_oauth_failed` được hiển thị.
  6. **AC-6** Giả sử một email đã được đăng ký bằng email/mật khẩu, Khi người dùng thử **Continue with
     Google** với chính email đó, Thì đăng nhập **bị từ chối**, trình duyệt quay về **trang Login**
     và hiển thị toast *"Authentication failed. Please check your login method and try again."*
     (`com_auth_error_oauth_failed`), và **không có tài khoản nào được liên kết hay gộp**.

---

### Đăng xuất

- **Mục đích:** Cho phép người dùng đã xác thực kết thúc phiên và quay lại trang đăng nhập.

- **Điều kiện tiên quyết / truy cập:**
  - Người dùng đã xác thực (giao diện chat chính đang hiển thị).
  - Popover Account Settings (Cài đặt tài khoản) có thể truy cập từ sidebar (phía dưới bảng điều hướng bên trái).

- **Thành phần giao diện:**
  - Kích hoạt: Nút avatar / tên người dùng trong sidebar. `data-testid="nav-user"`,
    `aria-label` = giá trị của `com_nav_account_settings`. Hiển thị avatar và tên người dùng (hoặc
    email dự phòng).
  - Các mục menu Popover (theo thứ tự): My Files, Help & FAQ (nếu được cấu hình), Console (nếu được cấu hình),
    Settings, dấu phân cách, **Log out**.
  - Mục Log out: `<Menu.MenuItem onClick={() => logout()}>` với icon `LogOut` (Lucide) và
    nhãn **"Log out"** (`com_nav_log_out`).
  - Địa chỉ email của người dùng được hiển thị ở đầu popover dưới dạng văn bản chỉ đọc.

- **Hành vi chức năng:**
  1. **FR-1** Nhấp **"Log out"** gọi `logout()` từ `useAuthContext`, hàm này gọi
     `logoutUser.mutate(undefined)` (một `POST /api/auth/logout` qua `useLogoutUserMutation`).
  2. **FR-2** Khi nhận phản hồi API đăng xuất thành công (không có `data.redirect`), `setUserContext` được
     gọi với `{ token: undefined, isAuthenticated: false, user: undefined, redirect: '/login' }`.
     JWT token bị xóa khỏi bộ nhớ và khỏi header Authorization của Axios. Trình duyệt
     điều hướng đến `/login`.
  3. **FR-3** Khi có lỗi API đăng xuất, cùng một lệnh gọi `setUserContext` được thực hiện — người dùng vẫn
     được xem là đã đăng xuất và được chuyển hướng đến `/login`.
  4. **FR-4** Nếu server trả về URL `data.redirect` (chỉ liên quan đến đăng xuất IdP qua OpenID / SAML —
     không áp dụng trong cấu hình NuFi vì Google OAuth không triển khai đăng xuất phía IdP),
     header token bị xóa ngay lập tức và `window.location.replace(data.redirect)` được gọi.

- **Kiểm tra hợp lệ & lỗi:**
  - Không cần xác thực đầu vào phía client.
  - Khi có lỗi API, người dùng vẫn được đăng xuất cục bộ và chuyển hướng đến `/login`; thông báo
    lỗi được đặt qua `doSetError` nhưng có thể không hiển thị với người dùng nếu điều hướng xảy ra
    trước khi render (cần xác minh: xác nhận xem có toast lỗi xuất hiện khi đăng xuất thất bại không).

- **Trường hợp đặc biệt:**
  - **Lỗi mạng khi đăng xuất:** Nhánh `onError` kích hoạt; người dùng vẫn được
    xác thực cục bộ và chuyển hướng đến `/login`.
  - **Đăng xuất được gọi với tham số redirect:** Signature `logout(redirect)` lưu
    đích vào `logoutRedirectRef` và sử dụng nó sau lệnh gọi API thay vì `/login`. Ví dụ,
    từ chối Điều khoản & Điều kiện gọi `logout('/login?redirect=false')`.
  - **Chưa xác thực:** Root trả về `null` nếu `!isAuthenticated`; người dùng không thể
    truy cập menu Account Settings.

- **Tiêu chí chấp nhận:**
  1. **AC-1** Giả sử người dùng đã xác thực, Khi họ nhấp vào avatar trong sidebar và
     sau đó nhấp "Log out", Thì ứng dụng gọi endpoint API đăng xuất.
  2. **AC-2** Giả sử lệnh gọi API đăng xuất thành công, Thì người dùng được chuyển hướng đến `/login`,
     JWT token bị xóa, và giao diện chat không còn truy cập được.
  3. **AC-3** Giả sử lệnh gọi API đăng xuất thất bại, Thì người dùng vẫn được chuyển hướng đến `/login` và
     được xem là đã đăng xuất.
  4. **AC-4** Giả sử người dùng đã đăng xuất và điều hướng đến `/c/new`, Thì
     `useAuthRedirect` phát hiện trạng thái chưa xác thực và chuyển hướng đến `/login` (với
     đường dẫn gốc được bảo tồn dưới dạng `redirect_to`).

---

### Phiên & Lưu trữ Token

- **Mục đích:** Duy trì phiên xác thực qua các lần tải lại trang và các tab trình duyệt mà không
  cần người dùng nhập lại thông tin đăng nhập trong thời gian phiên hoạt động.

- **Điều kiện tiên quyết / truy cập:**
  - Áp dụng cho bất kỳ người dùng nào đã xác thực sau khi đăng nhập thành công.

- **Thành phần giao diện:**
  - Không có giao diện chuyên dụng — hành vi trong suốt với người dùng.
  - Trên `/login`, một `BlinkAnimation` bao quanh logo NuFi trên mobile khi `isFetching` là `true`
    (chỉ ra rằng cấu hình khởi động đang tải).

- **Hành vi chức năng:**
  1. **FR-1** Khi mount `AuthContextProvider`, nếu không có token trong bộ nhớ, `silentRefresh`
     được gọi. Nó gọi `refreshToken.mutate(undefined)` (một `POST /api/auth/refresh`).
  2. **FR-2** Nếu API refresh trả về token hợp lệ, `setUserContext` được gọi với token mới
     và `isAuthenticated: true`. Người dùng được điều hướng đến đường dẫn deep-link đã lưu
     (từ khóa `post_login_redirect_to` trong `sessionStorage`) hoặc đến đường dẫn URL hiện tại
     (nếu an toàn), hoặc trở về `/c/new`.
  3. **FR-3** Nếu API refresh không trả về token hoặc xảy ra lỗi, người dùng được điều hướng đến
     `buildLoginRedirectUrl()` (tức là `/login?redirect_to=<current-path>` cho các đường dẫn được bảo vệ).
  4. **FR-4** JWT access token được lưu **chỉ trong bộ nhớ** (React state), không lưu trong
     `localStorage` hay `sessionStorage`. Điều này có nghĩa là đóng tất cả các tab sẽ kết thúc
     thời gian tồn tại của token.
  5. **FR-5** Refresh token được quản lý phía server qua cookie HTTP-only có tên `refreshToken`.
     Tùy chọn cookie: `httpOnly: true`, `secure` (tùy theo protocol), `sameSite` từ biến
     môi trường `COOKIE_SAMESITE` (mặc định `strict`). Thời gian hết hạn được đặt theo từng
     người dùng tại `refreshTokenExpires` (không có giá trị cố định duy nhất).
  6. **FR-6** Bất kỳ lần thử truy cập chưa xác thực nào vào một route được bảo vệ đều kích hoạt
     `useAuthRedirect`, hàm này gọi `buildLoginRedirectUrl(location.pathname, location.search, location.hash)`
     và điều hướng đến đó sau khoảng thời gian chờ 300 ms.
  7. **FR-7** Lần tải cấu hình khởi động bị giới hạn: khi người dùng đã xác thực,
     `StartupLayout` chỉ tải cấu hình khởi động nếu `startupConfig === null` (tức là lần tải đầu tiên).

- **Trường hợp đặc biệt:**
  - **Tải lại trang:** `silentRefresh` kích hoạt khi mount. Nếu cookie refresh token phía server
    vẫn còn hiệu lực, phiên được khôi phục trong suốt và người dùng đến trang họ đang xem
    (hoặc `/c/new`).
  - **Refresh token hết hạn:** `silentRefresh` không trả về token; người dùng được chuyển hướng đến
    `/login?redirect_to=<current-path>`, bảo tồn đích dự định của họ.
  - **Nhiều tab:** Mỗi tab chạy `silentRefresh` độc lập. Nếu refresh token bị thu hồi ở một tab
    (đăng xuất), các lần refresh tiếp theo ở các tab khác sẽ thất bại và chuyển hướng các tab đó
    về `/login`.
  - **Redirect bên ngoài (đăng xuất OpenID/SAML):** Không áp dụng trong cấu hình NuFi (Google OAuth
    không triển khai đăng xuất phía IdP).

- **Tiêu chí chấp nhận:**
  1. **AC-1** Giả sử người dùng đã xác thực và tải lại trang, Khi trang được mount, Thì
     một silent token refresh được thực hiện và người dùng vẫn ở giao diện chat mà không
     bị chuyển hướng đến đăng nhập.
  2. **AC-2** Giả sử refresh token của người dùng đã hết hạn và họ tải lại trang, Thì họ được
     chuyển hướng đến `/login?redirect_to=<original-path>`.
  3. **AC-3** Giả sử người dùng chưa xác thực điều hướng trực tiếp đến `/c/some-id`, Thì họ được
     chuyển hướng đến `/login?redirect_to=%2Fc%2Fsome-id` sau tối đa 300 ms.
  4. **AC-4** Giả sử người dùng đăng nhập từ URL trong AC-3, Khi đăng nhập thành công, Thì họ được
     điều hướng đến `/c/some-id`.

---

### Đặt lại Mật khẩu

- **Mục đích:** Cho phép người dùng quên mật khẩu đặt lại qua liên kết gửi email.

> **Ghi chú triển khai NuFi:** `ALLOW_PASSWORD_RESET=false` trong `.env.example` của NuFi. Với cài đặt
> này, `passwordResetEnabled` là `false` trong cấu hình khởi động. Kết quả là:
> - Liên kết **"Forgot Password?"** **không được hiển thị** trong `LoginForm`
>   (được kiểm soát bởi `startupConfig.passwordResetEnabled`).
> - Các route `/forgot-password` và `/reset-password` vẫn tồn tại trong router và các
>   component của chúng sẽ render nếu truy cập trực tiếp bằng URL.
>
> **Phạm vi kiểm thử:** Trừ khi NuFi kích hoạt tính năng này, tester cần xác minh rằng liên kết
> "Forgot Password?" không có trong form đăng nhập và không có đường dẫn đặt lại mật khẩu nào
> được hiển thị trong giao diện. Các chi tiết chức năng bên dưới mô tả triển khai cơ bản để
> tham khảo và sử dụng nếu tính năng được kích hoạt trong tương lai.

- **Điều kiện tiên quyết / truy cập:**
  - `ALLOW_PASSWORD_RESET=true` (biến môi trường server, `passwordResetEnabled: true` trong cấu hình khởi động) —
    **hiện chưa được kích hoạt trong NuFi**.
  - Server phải có cấu hình gửi email (`emailEnabled: true`) để liên kết được gửi
    qua email; nếu không cấu hình, liên kết reset được trả về trực tiếp trong phản hồi API và
    hiển thị trên màn hình (cần xác minh: cấu hình email của NuFi).
  - Các route: `/forgot-password` (Yêu cầu reset), `/reset-password?token=<t>&userId=<id>` (Đặt
    mật khẩu mới).

#### Đặt lại Mật khẩu — Yêu cầu

- **Thành phần giao diện:**
  - Tiêu đề trang: **"Reset your password"** (`com_auth_reset_password`)
  - Trường: **Email address** (Địa chỉ email) (`com_auth_email_address`), `type="email"`, `id="email"`,
    `autoComplete="off"`
  - Nút gửi: **"Continue"** (`aria-label="Continue with password reset"`)
  - Liên kết: **"Back to Login"** (`com_auth_back_to_login`) — điều hướng đến trang đăng nhập

- **Hành vi chức năng:**
  1. **FR-1** Khi gửi, gọi `useRequestPasswordResetMutation` với email được cung cấp.
  2. **FR-2** Khi thành công (dịch vụ email đã cấu hình): tiêu đề thay đổi thành **"Email Sent"**
     (`com_auth_reset_password_link_sent`) và form được thay thế bằng panel thành công hiển thị
     **"If an account with that email exists, an email with password reset instructions has been
     sent. Please make sure to check your spam folder."** (`com_auth_reset_password_if_email_exists`)
     cùng liên kết **"Back to Login"**.
  3. **FR-3** Khi thành công (dịch vụ email chưa cấu hình): phản hồi API bao gồm `data.link`;
     tiêu đề thay đổi thành **"Reset your password"** và một liên kết trực tiếp **"Click HERE to
     reset your password."** được hiển thị (HERE là neo liên kết, hiển thị viết hoa qua
     `com_auth_here`; văn bản đầy đủ được ghép từ `com_auth_click` + `com_auth_here` +
     `com_auth_to_reset_your_password`).
  4. **FR-4** Khi có lỗi: nội dung panel thành công giống như FR-2 được hiển thị (cố tình mơ hồ, để
     tránh tiết lộ xem có tài khoản nào tồn tại cho email đã cho không).
  5. **FR-5** Trong khi yêu cầu đang xử lý, nút gửi bị vô hiệu hóa và hiển thị `Spinner`.

- **Kiểm tra hợp lệ & lỗi:**

  | Trường | Quy tắc | Thông báo lỗi |
  |---|---|---|
  | Email | bắt buộc | `com_auth_email_required` → "Email is required" |
  | Email | minLength 3 | `com_auth_email_min_length` → "Email must be at least 6 characters" |
  | Email | maxLength 120 | `com_auth_email_max_length` → "Email should not be longer than 120 characters" |
  | Email | pattern `/\S+@\S+\.\S+/` | `com_auth_email_pattern` → "You must enter a valid email address" |

  Nút gửi bị vô hiệu hóa khi `errors.email` có giá trị truthy hoặc `isLoading` là `true`.

#### Đặt lại Mật khẩu — Đặt Mật khẩu Mới

- **Thành phần giao diện:**
  - Tiêu đề trang: **"Reset your password"** (`com_auth_reset_password`; thay đổi thành
    **"Password Reset Success"** khi thành công)
  - Trường ẩn: `token` và `userId` (đọc từ tham số truy vấn `?token=` và `?userId=`)
  - Trường: **Password** (Mật khẩu) (`com_auth_password`), `type="password"`, `id="password"`,
    `autoComplete="current-password"`
  - Trường: **Confirm password** (Xác nhận mật khẩu) (`com_auth_password_confirm`), `type="password"`,
    `id="confirm_password"`
  - Nút gửi: **"Continue"** (`aria-label` = `com_auth_submit_registration`), bị vô hiệu hóa
    khi `errors.password` hoặc `errors.confirm_password` có giá trị truthy, hoặc trong khi gửi
  - Khi thành công: một banner với **"You may now login with your new password."**
    (`com_auth_login_with_new_password`) và nút **"Continue"** điều hướng đến `/login`

- **Hành vi chức năng:**
  1. **FR-1** Khi gửi, gọi `useResetPasswordMutation` với `{ token, userId, password,
     confirm_password }`.
  2. **FR-2** Khi có lỗi, đặt trạng thái lỗi thành `'com_auth_error_invalid_reset_token'`, khiến
     `DisplayError` của `AuthLayout` hiển thị: **"This password reset token is no longer
     valid."** (`com_auth_error_invalid_reset_token`) với liên kết **"Click here"**
     (`com_auth_click_here`) đến `/forgot-password`.
  3. **FR-3** Khi thành công, form được thay thế bằng banner thành công (trạng thái thành công FR-1
     của `ResetPassword`).

- **Kiểm tra hợp lệ & lỗi:**

  | Trường | Quy tắc | Thông báo lỗi |
  |---|---|---|
  | Password | bắt buộc | `com_auth_password_required` → "Password is required" |
  | Password | minLength (mặc định 8) | `com_auth_password_min_length` → "Password must be at least 8 characters" |
  | Password | maxLength 128 | `com_auth_password_max_length` → "Password must be less than 128 characters" |
  | Confirm password | phải khớp với Password | `com_auth_password_not_match` → "Passwords do not match" |
  | token (ẩn) | bắt buộc | Hard-coded: "Unable to process: No valid reset token" |
  | userId (ẩn) | bắt buộc | Hard-coded: "Unable to process: No valid user id" |

  Khóa `com_auth_error_invalid_reset_token` đơn lẻ hiển thị: **"This password reset token is no
  longer valid."** Banner đầy đủ được `AuthLayout` ghép từ ba khóa dịch:
  `com_auth_error_invalid_reset_token` + `<Link>` với `com_auth_click_here` ("Click here") +
  `com_auth_to_try_again` ("to try again."), tạo ra văn bản hoàn chỉnh:
  **"This password reset token is no longer valid. Click here to try again."**

- **Trường hợp đặc biệt:**
  - **Token không hợp lệ hoặc đã hết hạn:** API trả về lỗi; banner `com_auth_error_invalid_reset_token`
    được hiển thị với liên kết quay lại `/forgot-password`.
  - **Thiếu token/userId trong URL:** Quy tắc required của trường ẩn kích hoạt phía client; nút
    gửi có thể được kích hoạt nhưng việc gửi form sẽ hiển thị lỗi nội tuyến "Unable to process: No valid
    reset token" / "No valid user id".
  - **Đặt lại mật khẩu không được bật (`ALLOW_PASSWORD_RESET=false`):** Liên kết "Forgot Password?" bị
    ẩn trên trang đăng nhập. Các route vẫn có thể truy cập bằng URL trực tiếp nhưng tính năng không
    được hiển thị với người dùng.

- **Tiêu chí chấp nhận (khi tính năng được bật):**
  1. **AC-1** Giả sử `passwordResetEnabled` là `true`, Khi người dùng xem trang đăng nhập, Thì
     liên kết "Forgot Password?" hiển thị bên dưới trường mật khẩu.
  2. **AC-2** Giả sử `passwordResetEnabled` là `false` (mặc định NuFi), Khi người dùng xem
     trang đăng nhập, Thì không có liên kết "Forgot Password?" nào hiện diện.
  3. **AC-3** Giả sử người dùng điều hướng đến `/forgot-password` và gửi email hợp lệ, Thì
     form được thay thế bằng panel thành công "Email Sent" bất kể email có tồn tại không
     (không liệt kê tài khoản).
  4. **AC-4** Giả sử người dùng gửi định dạng email không hợp lệ trên `/forgot-password`, Thì
     lỗi "You must enter a valid email address" xuất hiện và không có lệnh gọi API nào được thực hiện.
  5. **AC-5** Giả sử người dùng theo liên kết reset và token hợp lệ, Khi họ gửi
     mật khẩu mới khớp nhau, Thì banner thành công "You may now login with your new password."
     được hiển thị với nút điều hướng đến `/login`.
  6. **AC-6** Giả sử người dùng theo liên kết reset và token đã hết hạn, Khi họ gửi
     form, Thì banner lỗi "This password reset token is no longer valid. Click here
     to try again." được hiển thị.
  7. **AC-7** Giả sử người dùng gửi form mật khẩu mới với mật khẩu không khớp, Thì
     "Passwords do not match" xuất hiện và form không thể gửi.

---

### Xác minh Email

- **Mục đích:** Xác nhận địa chỉ email của người dùng sau khi đăng ký khi server có cấu hình
  gửi email.

- **Điều kiện tiên quyết / truy cập:**
  - Được kích hoạt tự động khi người dùng nhấp vào liên kết xác minh trong email xác nhận đăng ký.
  - Route: `/verify?token=<token>&email=<email>`
  - Áp dụng khi `emailEnabled: true` trên server (tức là `EMAIL_SERVICE` hoặc `EMAIL_HOST` +
    `EMAIL_USERNAME` + `EMAIL_PASSWORD` + `EMAIL_FROM` đều được cấu hình).
  - Nếu không cấu hình gửi email, đăng ký hoàn tất mà không cần xác minh
    và người dùng được chuyển hướng đến `/c/new` trực tiếp. (cần xác minh: xác nhận cấu hình dịch vụ email của NuFi.)

- **Thành phần giao diện:**
  - Bố cục toàn màn hình căn giữa (không có sidebar, không có nav).
  - Trong khi xác minh: tiêu đề **"Verifying your email, please wait"**
    (`com_auth_email_verification_in_progress`) với `Spinner`.
  - Khi thành công: tiêu đề **"Email verified successfully 🎉"**
    (`com_auth_email_verification_success`) với văn bản đếm ngược **"Redirecting in N seconds..."**.
  - Khi thất bại: tiêu đề **"Email verification failed 😢"** (`com_auth_email_verification_failed`)
    với tùy chọn gửi lại.
  - Nhắc gửi lại: **"Didn't receive the email?"** + nút **"Resend Email"**
    (`com_auth_email_resend_link`).
  - Bộ chọn giao diện (góc dưới bên trái).

- **Hành vi chức năng:**
  1. **FR-1** Khi mount, nếu cả tham số truy vấn `token` và `email` đều có mặt, gọi
     `useVerifyEmailMutation({ email, token })`.
  2. **FR-2** Khi thành công, hiển thị tiêu đề thành công và bắt đầu đếm ngược 3 giây, sau đó
     điều hướng đến `/c/new`.
  3. **FR-3** Khi có lỗi, hiển thị tiêu đề thất bại và nút "Resend Email".
  4. **FR-4** Nếu `email` có mặt nhưng `token` bị thiếu, hiển thị **"Verification failed, token
     missing 😢"** (`com_auth_email_verification_failed_token_missing`) và nút gửi lại.
  5. **FR-5** Nếu cả `token` và `email` đều không có mặt, hiển thị **"Invalid email verification 🤨"**
     (`com_auth_email_verification_invalid`) và nút gửi lại.
  6. **FR-6** Nhấp **"Resend Email"** gọi `useResendVerificationEmail({ email })`. Khi
     thành công: tiêu đề thay đổi thành **"Verification email resent successfully 📧"**
     (`com_auth_email_resent_success`) và đếm ngược 3 giây bắt đầu. Khi có lỗi: tiêu đề
     thay đổi thành **"Failed to resend verification email 😢"** (`com_auth_email_resent_failed`).

- **Kiểm tra hợp lệ & lỗi:** Không có đầu vào form; tất cả xác thực ở phía server trên token.

- **Trường hợp đặc biệt:**
  - **Token đã xác minh / đã hết hạn:** API trả về lỗi; tiêu đề thất bại và nút gửi lại
    được hiển thị.
  - **Người dùng nhấp liên kết xác minh hai lần:** Lần gọi thứ hai sẽ thất bại (token đã được sử dụng);
    tùy chọn gửi lại được cung cấp.
  - **Dịch vụ email chưa cấu hình:** Thông báo `com_auth_registration_success_insecure` được
    hiển thị sau khi đăng ký, và không có email xác minh nào được gửi; màn hình này không bao giờ đạt đến.

- **Tiêu chí chấp nhận:**
  1. **AC-1** Giả sử URL hợp lệ `?token=<t>&email=<e>`, Khi trang `/verify` tải, Thì
     spinner và văn bản "Verifying your email, please wait" được hiển thị trong khi lệnh gọi API
     đang xử lý.
  2. **AC-2** Giả sử API xác minh trả về thành công, Thì tiêu đề "Email verified
     successfully" được hiển thị và sau 3 giây trình duyệt điều hướng đến `/c/new`.
  3. **AC-3** Giả sử API xác minh trả về lỗi, Thì tiêu đề "Email verification failed"
     và nút "Resend Email" được hiển thị.
  4. **AC-4** Giả sử URL thiếu tham số `token`, Thì tiêu đề "Verification failed,
     token missing" và nút "Resend Email" được hiển thị mà không thực hiện lệnh gọi API xác minh.
  5. **AC-5** Giả sử người dùng nhấp "Resend Email" và API gửi lại thành công, Thì tiêu đề
     thay đổi thành "Verification email resent successfully" và chuyển hướng 3 giây đến `/c/new`
     bắt đầu.

---

### Tóm tắt Tổng hợp Lỗi Xác thực

Phần này tổng hợp tất cả thông báo xác thực phía client được sử dụng trên các màn hình auth để
tiện tham khảo trong QA.

- **Mẫu hiển thị lỗi:** Lỗi nội tuyến được hiển thị dưới dạng `<span role="alert" className="...
  text-destructive">` ngay bên dưới trường không hợp lệ. Form Đăng ký đánh giá trên
  mỗi thay đổi (`mode: 'onChange'`); form Đăng nhập đánh giá khi gửi.
- **Lỗi banner** (phía trên form) sử dụng `<div role="alert" aria-live="assertive">` với
  đường viền và nền màu đỏ/destructive.
- **Banner thành công** sử dụng đường viền và nền màu tím thương hiệu.
- **Lỗi phía server** được hiển thị qua một trong các cách: (a) banner `ErrorMessage` được khóa
  theo chuỗi dịch, (b) trạng thái `errorMessage` trong Registration được thêm tiền tố
  `com_auth_error_create`, hoặc (c) component `DisplayError` của `AuthLayout` cho lỗi token.

Tất cả thông báo lỗi đều có thể bản địa hóa. Các chuỗi tiếng Anh được liệt kê trong các bảng trên là
giá trị mặc định từ `/client/src/locales/en/translation.json`.
