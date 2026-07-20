## Menu Tài Khoản, Cài Đặt & Liên Kết Console

Phần này mô tả menu dropdown tài khoản, tất cả các tab cài đặt hiển thị với người dùng cuối của NuFi Chat, cũng như liên kết Console dẫn tới NuFi Console. Tất cả nội dung đều được căn cứ vào mã nguồn trong thư mục `client/src/components/Nav/` và cấu hình triển khai NuFi tại `librechat.yaml`.

---

### Menu Dropdown Tài Khoản

- **Mục đích:** Cung cấp cho người dùng đã đăng nhập quyền truy cập nhanh vào tệp, trợ giúp, NuFi Console, cài đặt ứng dụng và đăng xuất — mà không cần rời khỏi cuộc trò chuyện đang mở.
- **Điều kiện tiên quyết / truy cập:** Người dùng phải đã đăng nhập. Nút dropdown (`data-testid="nav-user"`) xuất hiện ở cuối thanh sidebar bên trái. Nút này luôn hiển thị khi sidebar đang mở rộng; khi sidebar thu gọn, chỉ hiển thị biểu tượng avatar.
- **Thành phần giao diện:**
  - **Nút Avatar + tên hiển thị** — kích hoạt menu. Hiển thị avatar người dùng (32 px khi mở rộng, 28 px khi thu gọn) và tên (`user.name`, nếu không có thì dùng `user.username`, sau đó là chuỗi đã dịch "User").
  - **Địa chỉ email** (ghi chú chỉ đọc ở đầu menu, `role="note"`)
  - **Hàng số dư** (chỉ đọc, định dạng `Balance: <số nguyên có dấu phân cách hàng nghìn theo locale>` ví dụ `Balance: 1,234`, được định dạng qua `Intl.NumberFormat`) — chỉ hiển thị khi `startupConfig.balance.enabled === true` VÀ truy vấn số dư trả về dữ liệu. NuFi không cấu hình tính năng này; không hiển thị.
  - **My Files** — mở modal My Files (`com_nav_my_files`).
  - **Help & FAQ** — mở `startupConfig.helpAndFaqURL` trong tab mới (`com_nav_help_faq`). Chỉ hiển thị khi `helpAndFaqURL !== '/'`; NuFi không đặt `HELP_AND_FAQ_URL`, nên giá trị mặc định `https://librechat.ai` được dùng và mục này hiển thị.
  - **Console** — mở URL NuFi Console (`com` — nhãn là chuỗi ký tự `"Console"` được đặt cứng trong `AccountSettings.tsx`). Chỉ xuất hiện khi `startupConfig.interface.customConsole.externalUrl` là chuỗi khác rỗng. NuFi thiết lập giá trị này qua `CONSOLE_URL`.
  - **Settings** — mở modal Settings (`com_nav_settings`).
  - **Log out** — gọi `logout()` (`com_nav_log_out`).
- **Hành vi chức năng:**
  1. FR-1: Nhấp vào nút avatar/tên sẽ mở Menu ariakit; nhấp ra ngoài hoặc nhấn Escape sẽ đóng menu.
  2. FR-2: "My Files" hiển thị `MyFilesModal` ngay tại chỗ (không điều hướng sang trang khác).
  3. FR-3: "Help & FAQ" gọi `window.open(helpAndFaqURL, '_blank')`.
  4. FR-4: "Console" gọi `window.open(externalUrl, openNewTab === false ? '_self' : '_blank')`. NuFi đặt `openNewTab: true` trong `librechat.yaml`, do đó liên kết luôn mở trong tab trình duyệt mới.
  5. FR-5: "Settings" đặt `showSettings = true`, hiển thị hộp thoại `<Settings>`.
  6. FR-6: "Log out" gọi hàm `logout()` của auth context.
- **Trạng thái & trường hợp đặc biệt:**
  - Mục Console hoàn toàn vắng mặt khỏi DOM khi biến môi trường `CONSOLE_URL` rỗng hoặc chưa được đặt; `resolveExternalUrl` trong gói data-schemas thay thế biến môi trường lúc khởi động server, và phía client chỉ render mục này khi `externalUrl` có giá trị thực (truthy).
  - Hàng số dư bị ẩn trong NuFi (tính năng số dư chưa được cấu hình).
  - Help & FAQ hiển thị trừ khi `HELP_AND_FAQ_URL=/` được đặt tường minh.
  - Vị trí hiển thị menu: căn phải khi sidebar thu gọn, căn dưới trong các trường hợp còn lại.
- **Tiêu chí chấp nhận:**
  1. AC-1: Giả sử người dùng đã đăng nhập và `CONSOLE_URL` đã được đặt, khi mở menu dropdown tài khoản, thì mục "Console" có biểu tượng dashboard phải xuất hiện trong menu.
  2. AC-2: Giả sử `CONSOLE_URL` rỗng hoặc chưa được đặt, khi mở menu dropdown tài khoản, thì không có mục "Console" nào xuất hiện.
  3. AC-3: Giả sử người dùng nhấp vào "Console", khi trình xử lý sự kiện click kích hoạt, thì trình duyệt phải mở URL đã cấu hình trong một tab mới (không phải tab hiện tại).
  4. AC-4: Giả sử người dùng nhấp vào "Log out", khi hành động hoàn tất, thì phiên đăng nhập bị kết thúc và người dùng được chuyển hướng đến trang đăng nhập.
  5. AC-5: Giả sử sidebar đang thu gọn, khi người dùng tương tác với nút tài khoản, thì menu mở ra bên phải nút (không phải phía trên).

---

### Hộp Thoại Settings — Tổng Quan Các Tab

Hộp thoại Settings hiển thị các tab sau. Phần lớn luôn hiện diện; hai tab có điều kiện:

| Tab | Khóa nhãn | Luôn hiển thị? | Điều kiện |
|---|---|---|---|
| General | `com_nav_setting_general` | Có | — |
| Chat | `com_nav_setting_chat` | Có | — |
| Commands | `com_nav_commands` | Có | — |
| Speech | `com_nav_setting_speech` | Có | — |
| Data | `com_nav_setting_data` | Có | — |
| Account | `com_nav_setting_account` | Có | — |
| **Personalization** | `com_nav_setting_personalization` | **Không** | Hiển thị khi `hasAnyPersonalizationFeature` là true — hiện tương đương với việc người dùng có quyền `MEMORIES OPT_OUT` (`usePersonalizationAccess`). NuFi không cấu hình mục `memory:`; việc tab này xuất hiện hay không phụ thuộc vào việc vai trò mặc định có cấp quyền `MEMORIES OPT_OUT` (cần xác minh trên sản phẩm đang chạy: xác nhận xem tab Personalization có hiển thị với người dùng NuFi tiêu chuẩn không). |
| **Balance** | `com_nav_setting_balance` | **Không** | Hiển thị khi `startupConfig?.balance?.enabled` là true. Không áp dụng cho NuFi (tính năng số dư chưa được cấu hình); tab này vắng mặt. |

Các phần dưới đây mô tả chi tiết từng tab.

---

### Hộp Thoại Settings — Tab General (Cài Đặt Chung)

- **Mục đích:** Điều chỉnh các tùy chọn hiển thị toàn cục: giao diện (theme), ngôn ngữ giao diện và một số hành vi liên quan đến sidebar/cuộn trang. Các cài đặt này được lưu lại qua các phiên (ngôn ngữ lưu trong cookie; theme/các toggle lưu trong Recoil/localStorage).
- **Điều kiện tiên quyết / truy cập:** Người dùng mở Settings từ menu dropdown tài khoản. Tab "General" (biểu tượng bánh răng, nhãn `com_nav_setting_general`) là tab được kích hoạt mặc định.
- **Thành phần giao diện:**
  - **Theme** (`com_nav_theme`) — dropdown gồm ba tùy chọn: "System" (`com_nav_theme_system`), "Dark" (`com_nav_theme_dark`), "Light" (`com_nav_theme_light`). Chiều rộng 180 px.
  - **Language** (`com_nav_language`) — dropdown liệt kê 42 giá trị ngôn ngữ (Auto, English, Chinese Simplified, Chinese Traditional, Arabic, Bosnian, Danish, German, Spanish, Catalan, Estonian, Persian, French, Hebrew, Hungarian, Armenian, Icelandic, Italian, Norwegian Bokmål, Norwegian Nynorsk, Polish, Brazilian Portuguese, Portuguese, Russian, Slovak, Japanese, Georgian, Czech, Swedish, Korean, Lithuanian, Latvian, Vietnamese, Thai, Turkish, Uyghur, Dutch, Indonesian, Finnish, Slovenian, Tibetan, Ukrainian). Mặc định là "Auto" (dùng `navigator.language`). Chiều cao hiển thị tối đa 256 px / 60 vh.
  - **Render user messages as markdown** (`com_nav_user_msg_markdown`) — công tắc toggle.
  - **Auto-Scroll to latest message on chat open** (`com_nav_auto_scroll`) — công tắc toggle.
  - **Keep screen awake during response generation** (`com_nav_keep_screen_awake`) — công tắc toggle.
  - **Switch to Chat History on new chat** (`com_nav_new_chat_switch_to_history`) — công tắc toggle.
  - **Archived chats** (`com_nav_archived_chats`) — hàng có nút "Manage" (`com_ui_manage`) để mở hộp thoại `ArchivedChatsTable`.
- **Hành vi chức năng:**
  1. FR-1: Chọn theme sẽ áp dụng ngay lập tức (qua `ThemeContext.setTheme`); không cần nhấn nút lưu.
  2. FR-2: Chọn ngôn ngữ sẽ đặt `document.documentElement.lang`, cập nhật Recoil atom `lang`, và ghi cookie `lang` có thời hạn 365 ngày. Khi chọn "Auto", giá trị được áp dụng là `navigator.language`.
  3. FR-3: Mỗi công tắc toggle đọc từ và ghi vào Recoil atom tương ứng; trạng thái được lưu qua localStorage sau khi tải lại trang.
  4. FR-4: Nhấp "Manage" bên cạnh "Archived chats" mở hộp thoại toàn màn hình liệt kê các cuộc trò chuyện đã lưu trữ cùng các tùy chọn khôi phục và xóa.
- **Trạng thái & trường hợp đặc biệt:**
  - Language "Auto": khi người dùng chọn "Auto", hàm `changeLang` phân giải `navigator.language` thành mã locale thực tế (ví dụ `en-US`) và lưu giá trị đó vào Recoil atom. Ở lần render tiếp theo, dropdown hiển thị nhãn locale đã phân giải (ví dụ "English") — **không phải** "Auto". Tùy chọn "Auto" vẫn còn trong danh sách nhưng không còn là lựa chọn đang hoạt động sau khi đã được chọn một lần.
  - Trên màn hình nhỏ (`max-width: 767px`) danh sách tab hiển thị nằm ngang ở đầu hộp thoại; trên màn hình lớn hơn, hiển thị dọc ở thanh sidebar bên trái.
- **Tiêu chí chấp nhận:**
  1. AC-1: Giả sử người dùng chọn "Dark" từ dropdown Theme, khi thực hiện lựa chọn, thì trang chuyển sang chế độ tối ngay lập tức mà không cần tải lại trang.
  2. AC-2: Giả sử người dùng chọn "Vietnamese" từ dropdown Language, khi hộp thoại được đóng và mở lại, thì "Vietnamese" vẫn được chọn (đã lưu trong cookie).
  3. AC-3: Giả sử người dùng bật "Render user messages as markdown", khi một tin nhắn người dùng chứa `**bold**` được gửi, thì tin nhắn hiển thị sẽ có chữ in đậm.
  4. AC-4: Giả sử người dùng nhấp "Manage" bên cạnh "Archived chats", khi hộp thoại mở ra, thì nó liệt kê tất cả cuộc trò chuyện đã lưu trữ.

---

### Hộp Thoại Settings — Tab Chat

- **Mục đích:** Điều chỉnh hành vi hiển thị và nhập liệu trong mỗi cuộc trò chuyện: cỡ chữ, chiều văn bản, một tập hợp các toggle UX, chế độ trình soạn thảo prompt nâng cao, và các tùy chọn mặc định khi phân nhánh hội thoại.
- **Điều kiện tiên quyết / truy cập:** Người dùng chọn tab "Chat" (biểu tượng ô chat vuông, nhãn `com_nav_setting_chat`) trong hộp thoại Settings.
- **Thành phần giao diện:**
  - **Message Font Size** (`com_nav_font_size`) — dropdown: "Extra Small", "Small", "Medium", "Large", "Extra Large" (giá trị CSS từ `text-xs` đến `text-xl`). Chiều rộng 150 px.
  - **Chat direction** (`com_nav_chat_direction`) — nút chuyển đổi giữa `ltr` (trái sang phải) và `rtl` (phải sang trái). Mặc định LTR.
  - **Always make new prompt versions production** (`com_nav_always_make_prod`) — công tắc toggle.
  - **Send prompts on select** (`com_nav_auto_send_prompts`) — công tắc toggle (tooltip: `com_nav_auto_send_prompts_desc`).
  - **Press Enter to send messages** (`com_nav_enter_to_send`) — công tắc toggle (tooltip: `com_nav_info_enter_to_send`).
  - **Maximize chat space** (`com_nav_maximize_chat_space`) — công tắc toggle.
  - **Center Chat Input on Welcome Screen** (`com_nav_center_chat_input`) — công tắc toggle.
  - **Open Thinking Dropdowns by Default** (`com_nav_show_thinking`) — công tắc toggle.
  - **Auto-expand tool details** (`com_nav_auto_expand_tools`) — công tắc toggle.
  - **Parsing LaTeX in messages (may affect performance)** (`com_nav_latex_parsing`) — công tắc toggle (tooltip: `com_nav_info_latex_parsing`).
  - **Save drafts locally** (`com_nav_save_drafts`) — công tắc toggle (tooltip: `com_nav_info_save_draft`).
  - **Scroll to the end button** (`com_nav_scroll_button`) — công tắc toggle.
  - **Save badges state** (`com_nav_save_badges_state`) — công tắc toggle (tooltip: `com_nav_info_save_badges_state`).
  - **Enable switching Endpoints mid-conversation** (`com_nav_modular_chat`) — công tắc toggle.
  - **Temporary Chat by default** (`com_nav_default_temporary_chat`) — công tắc toggle (tooltip: `com_nav_info_default_temporary_chat`).
  - **Advanced prompts editor** (`com_nav_advanced_prompts`) — công tắc toggle (tooltip: `com_nav_advanced_prompts_desc`). Chuyển đổi trình soạn thảo prompt giữa chế độ Đơn giản và Nâng cao.
  - **Use default fork option** (`com_ui_fork_default`) — công tắc toggle. Khi bật, hiển thị thêm dropdown "Default fork option".
  - **Default fork option** (`com_ui_fork_change_default`) — dropdown (chỉ hiển thị khi "Use default fork option" đang bật): "Visible messages only" (`com_ui_fork_visible`), "Include branches" (`com_ui_fork_branches`), "All messages to target level" (`com_ui_fork_all_target`). Tooltip: `com_nav_info_fork_change_default`.
  - **Start fork here** (`com_ui_fork_split_target_setting`) — công tắc toggle (tooltip: `com_nav_info_fork_split_target_setting`).
- **Hành vi chức năng:**
  1. FR-1: Thay đổi cỡ chữ sẽ áp dụng class Tailwind tương ứng cho nội dung tin nhắn ngay lập tức.
  2. FR-2: Chuyển đổi chiều văn bản sẽ thay đổi thuộc tính `dir="ltr"` hoặc `dir="rtl"` của vùng chat.
  3. FR-3: Khi "Use default fork option" bị tắt, dropdown "Default fork option" bị ẩn.
  4. FR-4: Tất cả các toggle đều lưu vào Recoil atom tương ứng, được sao lưu bởi localStorage.
- **Trạng thái & trường hợp đặc biệt:**
  - "Start fork here" luôn hiển thị bất kể trạng thái của "Use default fork option".
  - Tắt "Advanced prompts editor" sẽ tự động đặt "Always make new prompt versions production" thành `true` (tác dụng phụ trong `AdvancedPrompts.handleChange`).
- **Tiêu chí chấp nhận:**
  1. AC-1: Giả sử người dùng đặt cỡ chữ thành "Large", khi phản hồi chat được hiển thị, thì văn bản tin nhắn sử dụng class CSS `text-lg`.
  2. AC-2: Giả sử người dùng bật "Use default fork option", khi cài đặt đang hoạt động, thì dropdown "Default fork option" xuất hiện bên dưới.
  3. AC-3: Giả sử "Press Enter to send messages" đang tắt, khi người dùng nhấn Enter trong ô nhập chat, thì tin nhắn không được gửi đi (yêu cầu Shift+Enter hoặc nút gửi).

---

### Hộp Thoại Settings — Tab Commands (Lệnh)

- **Mục đích:** Cho phép người dùng bật hoặc tắt các tiền tố phím tắt kích hoạt hành động chat đặc biệt. Mỗi lệnh được kích hoạt bằng một ký tự cụ thể ở đầu tin nhắn.
- **Điều kiện tiên quyết / truy cập:** Người dùng chọn tab "Commands" (biểu tượng lệnh, nhãn `com_nav_commands`) trong hộp thoại Settings. Lệnh `+` chỉ hiển thị khi người dùng có quyền `MULTI_CONVO USE`; lệnh `/` chỉ hiển thị khi người dùng có quyền `PROMPTS USE`.
- **Thành phần giao diện:**
  - Tiêu đề mục "Chat Commands" (`com_nav_chat_commands`) với thẻ thông tin khi di chuột qua.
  - **@ Command** (`com_nav_at_command_description`): "Toggle command '@' for switching endpoints, models, presets, etc." — công tắc toggle.
  - **+ Command** (`com_nav_plus_command_description`): "Toggle command '+' for adding a multi-response setting" — công tắc toggle (hiển thị với người dùng có quyền `MULTI_CONVO`).
  - **/ Command** (`com_nav_slash_command_description`): "Toggle command '/' for selecting a prompt via keyboard" — công tắc toggle (hiển thị với người dùng có quyền `PROMPTS`).
- **Hành vi chức năng:**
  1. FR-1: Tắt lệnh `@` sẽ ngăn bộ chọn model/endpoint xuất hiện khi người dùng gõ `@` ở đầu tin nhắn.
  2. FR-2: Tắt lệnh `+` sẽ ngăn bảng đa phản hồi được kích hoạt bởi `+`.
  3. FR-3: Tắt lệnh `/` sẽ ngăn lớp phủ chọn prompt xuất hiện khi gõ `/`.
- **Trạng thái & trường hợp đặc biệt:**
  - Các hàng lệnh `+` và `/` được hiển thị có điều kiện dựa trên quyền; người dùng không có quyền `MULTI_CONVO USE` sẽ không thấy toggle `+`.
  - NuFi khai báo cả `multiConvo: true` và `prompts: true` trong `librechat.yaml`, vì vậy cả ba toggle lệnh đều phải hiển thị với người dùng tiêu chuẩn (cần xác minh trên sản phẩm đang chạy: xác nhận vai trò người dùng mặc định có cấp quyền `MULTI_CONVO USE` và `PROMPTS USE` không).
- **Tiêu chí chấp nhận:**
  1. AC-1: Giả sử toggle lệnh `@` đang tắt, khi người dùng gõ `@` ở đầu ô nhập tin nhắn, thì bộ chọn endpoint/model không xuất hiện.
  2. AC-2: Giả sử người dùng không có quyền `MULTI_CONVO USE`, khi tab Commands được mở, thì hàng lệnh `+` không có mặt.

---

### Hộp Thoại Settings — Tab Speech (Giọng Nói)

- **Mục đích:** Cấu hình hành vi Nhận dạng Giọng nói (STT) và Chuyển văn bản thành Giọng nói (TTS). Tab này luôn hiển thị trong hộp thoại Settings (không bị kiểm soát bởi feature flag phía server trong danh sách tab). Tuy nhiên, **NuFi không cấu hình backend giọng nói**, do đó STT và TTS sẽ không hoạt động trừ khi có engine tương thích.
- **Điều kiện tiên quyết / truy cập:** Người dùng chọn tab "Speech" (biểu tượng giọng nói, nhãn `com_nav_setting_speech`). Tab được render vô điều kiện trong `Settings.tsx`.
- **Thành phần giao diện — Chế độ Simple (mặc định):**
  - Hàng chuyển chế độ: "Simple" (biểu tượng bóng đèn) / "Advanced" (biểu tượng bánh răng).
  - **Speech to Text** (`SpeechToTextSwitch`) — toggle chính cho STT.
  - **STT Engine** (`EngineSTTDropdown`) — dropdown chọn backend STT.
  - **STT Language** (`LanguageSTTDropdown`) — chọn ngôn ngữ nhận dạng.
  - **Text to Speech** (`TextToSpeechSwitch`) — toggle chính cho TTS.
  - **TTS Engine** (`EngineTTSDropdown`) — dropdown chọn backend TTS.
  - **Voice** (`VoiceDropdown`) — chọn giọng đọc cho engine TTS.
- **Thành phần giao diện — Chế độ Advanced (điều khiển bổ sung):**
  - **Conversation Mode** (`ConversationModeSwitch`) — bật vòng lặp hội thoại giọng nói liên tục.
  - **Auto-Transcribe Audio** (`AutoTranscribeAudioSwitch`) — tự động phiên âm đầu vào từ microphone.
  - **Decibel Threshold** (`DecibelSelector`) — chỉ hiển thị khi Auto-Transcribe đang bật; đặt ngưỡng im lặng.
  - **Auto-Send Text** (`AutoSendTextSelector`) — kiểm soát việc văn bản được phiên âm có được gửi tự động hay không.
  - **Automatic Playback** (`AutomaticPlaybackSwitch`) — tự động phát phản hồi TTS.
  - **Cloud/browser voices** (`CloudBrowserVoicesSwitch`) — chỉ hiển thị khi `engineTTS === 'browser'`.
  - **Playback Rate** (`PlaybackRate`) — thanh trượt hoặc bộ chọn tốc độ phát TTS.
  - **Cache TTS** (`CacheTTSSwitch`) — lưu cache phản hồi âm thanh TTS trong trình duyệt (`tts-responses` Cache Storage).
- **Hành vi chức năng:**
  1. FR-1: Khi tab được mount, component lấy `customConfigSpeech` từ server; nếu phản hồi không phải `not_found`, các giá trị của nó được áp dụng làm mặc định chỉ khi chưa có tùy chọn người dùng trong localStorage.
  2. FR-2: Chuyển sang chế độ Advanced đặt Recoil atom `advancedMode` thành `true`, lưu lại qua các phiên.
  3. FR-3: Nếu giá trị `engineTTS` được lưu không phải `'browser'` hoặc `'external'` (ví dụ: `'edge'` đã lỗi thời), nó sẽ được reset về `'browser'` một cách thầm lặng.
- **Trạng thái & trường hợp đặc biệt:**
  - **Lưu ý về triển khai NuFi:** NuFi không cấu hình backend giọng nói (không có mục `speech:` trong `librechat.yaml`). Tab vẫn hiển thị, nhưng các toggle STT và TTS sẽ không có hiệu lực trừ khi trình duyệt của người dùng hỗ trợ Web Speech API cho chế độ TTS/STT trên trình duyệt. (cần xác minh trên sản phẩm đang chạy: xác nhận liệu tính năng giọng nói gốc của trình duyệt có khả dụng với người dùng cuối hay không, hoặc tab này cần được ghi chú là không hoạt động trong NuFi.)
- **Tiêu chí chấp nhận:**
  1. AC-1: Giả sử tab Speech đang mở, khi người dùng nhấp "Advanced", thì các điều khiển bổ sung (Conversation Mode, Auto-Transcribe, v.v.) xuất hiện.
  2. AC-2: Giả sử engine TTS là "browser", khi người dùng xem tab Advanced, thì công tắc "Cloud/browser voices" hiển thị.
  3. AC-3: Giả sử NuFi không có backend giọng nói được cấu hình, khi người dùng bật Speech to Text, thì hệ thống không gây ra lỗi không được xử lý (cần xác minh trên sản phẩm đang chạy: xác nhận ứng dụng xử lý lỗi một cách ổn thỏa khi không có backend giọng nói nào đang hoạt động).

---

### Hộp Thoại Settings — Tab Data Controls (Kiểm Soát Dữ Liệu)

- **Mục đích:** Quản lý dữ liệu hội thoại, các liên kết chia sẻ, thông tin xác thực API và bộ nhớ đệm trình duyệt. Tất cả hành động trong tab này đều không thể hoàn tác hoặc có tác động đáng kể; các thao tác phá hủy dữ liệu đều yêu cầu xác nhận tường minh.
- **Điều kiện tiên quyết / truy cập:** Người dùng chọn tab "Data" (biểu tượng dữ liệu, nhãn `com_nav_setting_data`) trong hộp thoại Settings.
- **Thành phần giao diện:**
  - **Import conversation** (`com_ui_import_conversation_info`) — nhãn + nút "Import" có biểu tượng tải lên. Mở `<input type="file" accept=".json">` ẩn để chọn tệp JSON xuất theo định dạng LibreChat.
  - **Shared links** (`com_nav_shared_links`) — nhãn + nút "Manage". Mở bảng dữ liệu phân trang các liên kết chia sẻ công khai với các cột: Name (có thể sắp xếp, nhấp để mở liên kết ngoài), Date (có thể sắp xếp), Actions (mở chat nguồn, xóa). Hỗ trợ tìm kiếm/lọc và cuộn vô hạn (kích thước trang 25).
  - **Agent API Keys** (`com_ui_agent_api_keys`) — nhãn + nút "Manage". Chỉ hiển thị khi người dùng có quyền `REMOTE_AGENTS USE`. Mở hộp thoại liệt kê các API key hiện có (tên, tiền tố key, ngày tạo, ngày sử dụng lần cuối) với các tùy chọn tạo mới và xóa.
  - **Revoke all user provided credentials** (`com_ui_revoke_info`) — nhãn + nút "Revoke" (phá hủy). Kích hoạt hộp thoại xác nhận trước khi gọi `useRevokeAllUserKeysMutation`.
  - **Delete cache storage** (`com_nav_delete_cache_storage`) — nhãn + nút "Delete" (phá hủy). Xóa `tts-responses` Cache Storage của trình duyệt. Nút bị vô hiệu hóa khi cache trống.
  - **Clear all chats** (`com_nav_clear_all_chats`) — nhãn + nút "Delete" (phá hủy). Mở hộp thoại xác nhận trước khi gọi `useClearConversationsMutation`, xóa tất cả cuộc trò chuyện phía server.
- **Hành vi chức năng:**
  1. FR-1: "Import" chỉ chấp nhận tệp `.json`. Kích thước tệp được kiểm tra so với `startupConfig.conversationImportMaxFileSize`; nếu vượt quá, hiển thị thông báo lỗi toast. Khi thành công hiển thị toast thành công; khi loại tệp không hợp lệ hiển thị `com_ui_import_conversation_file_type_error`.
  2. FR-2: "Manage" (Shared links) lấy dữ liệu theo kiểu lười biếng (chỉ khi hộp thoại đang mở, `enabled: isOpen`). Xóa một liên kết hiển thị hộp thoại xác nhận riêng có tiêu đề liên kết trước khi gọi `useDeleteSharedLinkMutation`.
  3. FR-3: "Manage" (Agent API Keys) chỉ hiển thị key đầy đủ một lần tại thời điểm tạo; sau khi đóng hộp thoại, key đầy đủ không thể xem lại (chỉ lưu tiền tố).
  4. FR-4: "Revoke" (thông tin xác thực) yêu cầu xác nhận; khi thành công đóng hộp thoại cha nếu prop `setDialogOpen` được cung cấp.
  5. FR-5: "Delete" (cache) bị vô hiệu hóa khi `caches.open('tts-responses')` trả về không có mục nào; được kích hoạt lại ngay khi có mục tồn tại.
  6. FR-6: "Clear all chats" — sau khi xóa phía server, `clearAllConversationStorage()` được gọi phía client và một cuộc trò chuyện mới trống được tạo qua `newConversation()`.
- **Trạng thái & trường hợp đặc biệt:**
  - Tất cả các nút phá hủy đều mở modal với mẫu xác nhận/hủy bỏ trước khi thực thi; nhấp ra ngoài trạng thái xác nhận ClearChats cũng hủy bỏ thao tác (qua `useOnClickOutside`).
  - Mục Agent API Keys bị ẩn khi người dùng thiếu quyền `REMOTE_AGENTS USE`. NuFi bật `agents: true` trong `librechat.yaml`; quyền hiệu lực phụ thuộc vào cấu hình vai trò người dùng (cần xác minh trên sản phẩm đang chạy: xác nhận vai trò người dùng mặc định có cấp quyền `REMOTE_AGENTS USE` không).
  - Bảng Shared links hiển thị thông báo trạng thái trống khi không có liên kết công khai nào.
  - Import bị vô hiệu hóa trong khi tải lên đang tiến hành (spinner thay thế biểu tượng import).
- **Tiêu chí chấp nhận:**
  1. AC-1: Giả sử người dùng chọn tệp `.json` lớn hơn `conversationImportMaxFileSize` của server, khi tệp được chọn, thì hiển thị toast lỗi có kích thước tối đa và không thực hiện tải lên.
  2. AC-2: Giả sử người dùng nhấp "Delete" (Clear all chats) và xác nhận, khi mutation thành công, thì danh sách hội thoại trong sidebar trống và một chat trống mới được bắt đầu.
  3. AC-3: Giả sử TTS cache trống, khi tab Data được mở, thì nút "Delete" trong hàng "Delete cache storage" bị vô hiệu hóa.
  4. AC-4: Giả sử người dùng tạo Agent API Key, khi hộp thoại tạo mới hiển thị lần đầu, thì key đầy đủ hiển thị và có thể sao chép; khi hộp thoại đóng và mở lại, chỉ hiển thị tiền tố key.
  5. AC-5: Giả sử người dùng nhấp "Revoke" (thông tin xác thực) và xác nhận, khi mutation thành công, thì tất cả thông tin xác thực API bên thứ ba được lưu trữ bị xóa khỏi server.

---

### Hộp Thoại Settings — Tab Account (Tài Khoản)

- **Mục đích:** Quản lý cài đặt hồ sơ cá nhân, ảnh đại diện, xác thực hai yếu tố và xóa tài khoản vĩnh viễn.
- **Điều kiện tiên quyết / truy cập:** Người dùng chọn tab "Account" (biểu tượng người dùng, nhãn `com_nav_setting_account`) trong hộp thoại Settings.
- **Thành phần giao diện:**
  - **Display username in messages** (`com_nav_user_name_display`) — công tắc toggle với thẻ thông tin khi di chuột (`com_nav_info_user_name_display`). Kiểm soát việc hiển thị tên người dùng hay nhãn chung "User" phía trên tin nhắn trong chat.
  - **Profile Picture** (`com_nav_profile_picture`) — nhãn + nút "Change Picture" (có biểu tượng ảnh tệp). Mở hộp thoại trình chỉnh sửa avatar.
    - Hộp thoại trình chỉnh sửa avatar: vùng kéo-thả (chấp nhận `.png`, `.jpg`, `.jpeg`; kích thước tối đa từ `fileConfig.avatarSizeLimit`, mặc định hiển thị 2 MB). Sau khi chọn tệp: xem trước hình tròn 280×280 (`AvatarEditor`), thanh trượt Zoom (1–5×, bước 0,1) với nút Zoom In / Zoom Out, nút Xoay 90°, nút Reset. Các nút hành động: Cancel (đặt lại trạng thái ảnh) và Upload (đăng dưới dạng `multipart/form-data` với `manual=true`).
  - **Two-factor authentication** (`com_ui_2fa_setup` / `com_ui_2fa_disable`) — chỉ hiển thị khi `user.provider === 'local'`. Toggle mở hộp thoại trình hướng dẫn 2FA.
    - Các giai đoạn của trình hướng dẫn thiết lập: Setup → Scan QR → Verify → Backup. **Không có thanh tiến trình hiển thị trong quá trình thiết lập ban đầu** (khi `twoFactorEnabled` là `false`). Thanh tiến trình trong tiêu đề hộp thoại chỉ được render khi người dùng đã bật 2FA (`twoFactorEnabled === true`) và đang thực hiện luồng cập nhật hoặc xác nhận lại.
    - Giai đoạn vô hiệu hóa: yêu cầu nhập mã TOTP hiện tại hoặc mã dự phòng.
  - **Backup Codes** (`com_ui_backup_codes`) — chỉ hiển thị khi `user.provider === 'local'` VÀ `user.twoFactorEnabled === true`. Nút "Manage" mở hộp thoại mã dự phòng hiển thị tất cả 10 mã dự phòng với trạng thái đã dùng/chưa dùng và hành động "Regenerate backup codes" (yêu cầu xác minh TOTP hoặc mã dự phòng).
  - **Delete account** (`com_nav_delete_account`) — hiển thị khi `startupConfig.allowAccountDeletion !== false`. Nhãn + nút "Delete" (phá hủy). Mở hộp thoại xác nhận yêu cầu người dùng nhập địa chỉ email trước khi nút xóa được mở khóa. Nếu 2FA đang bật, cũng yêu cầu mã TOTP 6 chữ số hoặc mã dự phòng 8 ký tự.
- **Hành vi chức năng:**
  1. FR-1: Toggle "Display username in messages" ghi vào Recoil atom `UsernameDisplay`; thay đổi phản ánh ngay lập tức trong mọi cuộc trò chuyện đang mở.
  2. FR-2: "Change Picture" — tải lên ảnh cập nhật `user.avatar` trong Recoil atom `user` qua `useUploadAvatarMutation`; avatar trong nút tài khoản cập nhật mà không cần tải lại trang.
  3. FR-3: Thiết lập 2FA — nhấp toggle mở trình hướng dẫn ở giai đoạn "Setup", tạo mã QR (`useEnableTwoFactorMutation`). Người dùng quét bằng ứng dụng xác thực, nhập mã 6 chữ số để xác minh (`useVerifyTwoFactorMutation`), sau đó xác nhận (`useConfirmTwoFactorMutation`). Sau khi xác nhận, mã dự phòng được hiển thị và có thể tải xuống dưới dạng `backup-codes.txt`. Đóng hộp thoại giữa chừng sẽ kích hoạt `disable2FAMutate` để hoàn tác secret đang chờ xử lý.
  4. FR-4: Vô hiệu hóa 2FA — nhập mã TOTP hoặc mã dự phòng hợp lệ gọi `useDisableTwoFactorMutation`; khi thành công `user.twoFactorEnabled` được đặt thành `false` trong Recoil và trình hướng dẫn reset về giai đoạn thiết lập.
  5. FR-5: Xóa tài khoản — nút xóa trong hộp thoại xác nhận bị khóa (biểu tượng ổ khóa, độ mờ 30%) cho đến khi email đã nhập khớp với `user.email` (không phân biệt chữ hoa/thường). Nếu 2FA đang bật, trường TOTP/dự phòng cũng phải được điền đầy đủ. Khi thành công, `logout()` được gọi tự động.
- **Trạng thái & trường hợp đặc biệt:**
  - Các hàng "Two-factor authentication" và "Backup Codes" bị ẩn với người dùng xác thực qua OAuth (`user.provider !== 'local'`). NuFi sử dụng xác thực cục bộ theo mặc định; không có nhà cung cấp OAuth nào (`google`, `github`, v.v.) được cấu hình trong `librechat.yaml`. Nếu môi trường triển khai Railway không đặt biến môi trường OAuth (`GOOGLE_CLIENT_ID`, v.v.), xác thực cục bộ là cơ chế duy nhất và cả hai hàng đều hiển thị với tất cả người dùng. (cần xác minh trên sản phẩm đang chạy: xác nhận không có biến môi trường OAuth nào đang hoạt động trên Railway.)
  - "Delete account" bị ẩn khi biến môi trường `ALLOW_ACCOUNT_DELETION` được đặt tường minh thành `false`. NuFi không đặt biến này, vì vậy giá trị mặc định (`true`) được áp dụng và tùy chọn này hiển thị.
  - Tải lên avatar bị từ chối nếu tệp vượt quá `fileConfig.avatarSizeLimit`; một toast lỗi hiển thị giới hạn dưới dạng dễ đọc.
  - Đóng hộp thoại avatar mà không tải lên sẽ reset tất cả trạng thái trình chỉnh sửa (tỷ lệ, góc xoay, vị trí, ảnh đã chọn).
- **Tiêu chí chấp nhận:**
  1. AC-1: Giả sử "Display username in messages" đang bật, khi một tin nhắn người dùng hiển thị trong chat, thì tên người dùng xuất hiện phía trên bong bóng tin nhắn.
  2. AC-2: Giả sử người dùng tải lên avatar `.jpg` hợp lệ và nhấp "Upload", khi mutation thành công, thì avatar hiển thị trong nút dropdown tài khoản được cập nhật thành ảnh mới.
  3. AC-3: Giả sử người dùng chưa bật 2FA, khi họ nhấp toggle 2FA, thì hộp thoại trình hướng dẫn 4 giai đoạn mở ra ở giai đoạn "Setup".
  4. AC-4: Giả sử người dùng mở hộp thoại Delete Account và nhập email sai, khi họ xem nút xóa, thì nút hiển thị biểu tượng ổ khóa và bị vô hiệu hóa.
  5. AC-5: Giả sử người dùng nhập đúng email và (nếu 2FA đang hoạt động) nhập mã TOTP hợp lệ, khi họ nhấp nút xóa, thì tài khoản bị xóa vĩnh viễn và người dùng bị đăng xuất.
  6. AC-6: Giả sử `ALLOW_ACCOUNT_DELETION` không được đặt trong môi trường NuFi (mặc định), khi tab Account được mở, thì hàng "Delete account" hiển thị.

---

### Hành Vi Liên Kết Console

- **Mục đích:** Cung cấp điểm vào trực tiếp từ NuFi Chat vào NuFi Console (giao diện quản trị / thanh toán / quản lý dự án) mà không yêu cầu người dùng phải nhớ một URL riêng.
- **Điều kiện tiên quyết / truy cập:** Biến môi trường `CONSOLE_URL` phải được đặt trong triển khai NuFi (được cấu hình trong `docker-compose.yml` dưới dạng `CONSOLE_URL: ${CONSOLE_URL:-}`). Khi được đặt, giá trị được nội suy lúc khởi động server bởi `resolveExternalUrl` trong `packages/data-schemas/src/app/interface.ts` và chuyển đến client qua `startupConfig.interface.customConsole.externalUrl`. Người dùng phải đã đăng nhập và menu dropdown tài khoản phải đang mở.
- **Thành phần giao diện:**
  - Mục menu được gắn nhãn `"Console"` (chuỗi ký tự, không được dịch) với biểu tượng `LayoutDashboard` (Lucide).
  - Mục này xuất hiện trong menu dropdown tài khoản, giữa "Help & FAQ" (khi có) và "Settings".
- **Hành vi chức năng:**
  1. FR-1: Khi `startupConfig.interface.customConsole.externalUrl` là chuỗi khác rỗng, mục menu Console được render.
  2. FR-2: Nhấp vào mục sẽ gọi `window.open(externalUrl, '_blank')` vì `openNewTab` là `true` trong `librechat.yaml`. Tab NuFi Chat hiện tại vẫn giữ nguyên — Console **luôn mở trong tab trình duyệt mới**.
  3. FR-3: Nếu `openNewTab` được đặt thành `false` trong `librechat.yaml`, URL sẽ mở trong cùng tab (`'_self'`). NuFi đặt `openNewTab: true`, vì vậy nhánh này không hoạt động.
  4. FR-4: `CONSOLE_URL` được truyền qua Docker Compose từ môi trường máy chủ. Nếu biến vắng mặt trên máy chủ, `CONSOLE_URL` giải thành chuỗi rỗng, `resolveExternalUrl` trả về đối tượng có `externalUrl` là `""`, và điều kiện phía client `startupConfig?.interface?.customConsole?.externalUrl` là falsy — mục không được render.
- **Trạng thái & trường hợp đặc biệt:**
  - Khi `CONSOLE_URL` rỗng, mục Console hoàn toàn không có trong DOM (không chỉ bị ẩn); không có fallback hay tooltip nào được hiển thị.
  - Nhãn được đặt cứng là chuỗi `"Console"` trong `AccountSettings.tsx` (không phải khóa dịch thuật); nó sẽ không thay đổi theo cài đặt ngôn ngữ của người dùng.
  - Không có liên kết quay lại trong ứng dụng từ Console về NuFi Chat; người dùng quay lại tab chat bằng cách quản lý tab trình duyệt thông thường.
- **Tiêu chí chấp nhận:**
  1. AC-1: Giả sử `CONSOLE_URL=https://console.nufi.me` được đặt, khi người dùng mở menu dropdown tài khoản, thì mục "Console" có biểu tượng dashboard xuất hiện trong menu.
  2. AC-2: Giả sử người dùng nhấp "Console", khi trình duyệt xử lý lượt nhấp, thì `https://console.nufi.me` mở trong một tab trình duyệt mới và tab NuFi Chat vẫn đang hoạt động.
  3. AC-3: Giả sử `CONSOLE_URL` rỗng hoặc chưa được đặt, khi người dùng mở menu dropdown tài khoản, thì không có mục "Console" nào tồn tại ở bất kỳ đâu trong DOM của dropdown.
  4. AC-4: Giả sử ngôn ngữ giao diện của người dùng được đặt thành tiếng Việt, khi menu dropdown tài khoản được mở, thì mục vẫn hiển thị nhãn tiếng Anh "Console" (không được dịch).
