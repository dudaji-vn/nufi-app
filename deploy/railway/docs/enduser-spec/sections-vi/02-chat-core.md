## Chat Core — Cuộc trò chuyện & Nhắn tin

Phần này mô tả hành vi hiển thị phía người dùng cuối của vòng lặp chat cốt lõi trong NuFi Chat: bắt đầu cuộc trò chuyện, soạn và gửi tin nhắn, nhận phản hồi phát trực tuyến, và tất cả các thao tác trên từng tin nhắn. Tất cả các mô tả đều dựa trên mã nguồn của nhánh LibreChat tại `/Users/sun/Workspace/DudajiVN/LibreChat`.

---

### Cuộc trò chuyện mới / Màn hình khởi đầu

- **Mục đích:** Cung cấp điểm vào thân thiện khi chưa có cuộc trò chuyện nào đang hoạt động, và cho phép người dùng bắt đầu cuộc trò chuyện mới bất cứ lúc nào.

- **Điều kiện tiên quyết / truy cập:** Bất kỳ người dùng đã xác thực. Được hiển thị tự động khi tải trang lần đầu và bất cứ khi nào URL là `/c/new` hoặc không có `conversationId` (xem `ChatView.tsx` dòng 64–66: `isLandingPage` là true khi `messagesTree` rỗng và `conversationId === Constants.NEW_CONVO || !conversationId`).

- **Thành phần giao diện:**
  - **Văn bản chào mừng** (`Landing.tsx` dòng 135–138): được hiển thị bởi `SplitText` với hiệu ứng xuất hiện từng từ (`easeOutCubic`, độ trễ 50 ms mỗi từ). Khi `startupConfig.interface.customWelcome` là một chuỗi, nó được sử dụng như nguyên bản, trừ trường hợp chuỗi đó chứa token mẫu `{{user.name}}` — khi đó tên người dùng sẽ được thay thế vào vị trí đó; nếu không, lời chào theo thời gian trong ngày được thêm vào kèm `, <user.name>` nếu người dùng đã đặt tên. NuFi Chat đặt `customWelcome: "Welcome to Nufi Chat."` (không có token `{{user.name}}`), vì vậy lời chào luôn là **"Welcome to Nufi Chat."** (không có biến thể theo thời gian trong ngày, không thêm tên người dùng).
  - **Biểu tượng endpoint** (`Landing.tsx` dòng 147–167): biểu tượng bo góc 41×41 px cho endpoint/agent đang hoạt động, được hiển thị bởi `ConvoIcon`.
  - **Biểu tượng sinh nhật tùy chọn** (chỉ hiển thị khi `startupConfig.showBirthdayIcon` là true; không dự kiến trong cấu hình mặc định của NuFi).
  - **Văn bản mô tả** (chỉ hiển thị khi thực thể đang hoạt động có trường `description` hoặc `greeting`; không áp dụng cho endpoint "Nufi" thông thường).
  - **Biểu mẫu nhập chat** (`ChatView.tsx` dòng 102): được đặt bên dưới lời chào. Khi `centerFormOnLanding` là true (`ChatForm.tsx` dòng 233–238), một khoảng cách đáy bổ sung được áp dụng trên trang khởi đầu. Điểm chuyển bố cục từ căn giữa sang căn dưới cùng được điều khiển bởi `isLandingPage` (thay đổi khi có tin nhắn xuất hiện), không phải trực tiếp bởi `isSubmitting`.
  - **Conversation Starters** (`ConversationStarters.tsx`, `ChatView.tsx` dòng 103): chỉ hiển thị khi agent/assistant đang hoạt động có `conversation_starters`. Không có cho endpoint "Nufi" cơ sở.
  - **Footer** (`Footer.tsx`): hiển thị "NUFI \<VERSION\>" (hoặc `config.customFooter` nếu được đặt). Ẩn trên thiết bị di động (`sm:flex`). Hiển thị liên kết chính sách bảo mật và điều khoản dịch vụ nếu được cấu hình.
  - **Nút "New Chat"** (thanh bên, `NewChat.tsx` `aria-label="com_ui_new_chat"`): biểu tượng bút chì `NewChatIcon`. Ctrl/Cmd+Click mở `/c/new` trong tab trình duyệt mới.

- **Hành vi chức năng:**
  - FR-1. Khi người dùng điều hướng đến `/c/new` hoặc nhấp "New Chat", `ChatView` hiển thị thành phần `Landing` và `ChatForm` thay vì `MessagesView`.
  - FR-2. Văn bản chào mừng "Welcome to Nufi Chat." được hiển thị với hiệu ứng hoạt hình xuất hiện từng chữ/từ (SplitText).
  - FR-3. Nếu thực thể được giải quyết có trường `name` không rỗng, tên đó được hiển thị thay cho lời chào; nếu nó còn có `description` hoặc `greeting`, văn bản đó xuất hiện bên dưới biểu tượng.
  - FR-4. Nhấp "New Chat" xóa bộ đệm tin nhắn của cuộc trò chuyện trước (`clearMessagesCache`) và gọi `newConversation()`, sau đó điều hướng đến `/c/new`.
  - FR-5. Ctrl/Cmd+nhấp "New Chat" mở `/c/new` trong tab mới mà không xóa phiên hiện tại.

- **Trạng thái & trường hợp đặc biệt:**
  - Khi `messagesTree` đang được tải cho một `conversationId` hiện có, một `<Spinner>` căn giữa được hiển thị thay vì màn hình khởi đầu hoặc màn hình tin nhắn.
  - Nếu `conversationId` khác null nhưng `messagesTree` vẫn rỗng và đang tải, `isNavigating` là true và spinner được hiển thị (ngăn màn hình khởi đầu xuất hiện thoáng qua).
  - Trên thiết bị di động (`max-width: 768px`), thanh bên bị thu gọn; nút "New Chat" bị ẩn (`max-md:hidden`). Cuộc trò chuyện mới được bắt đầu từ menu `OpenSidebar`.

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử người dùng đã đăng nhập điều hướng đến `/c/new`, khi trang hiển thị, thì văn bản "Welcome to Nufi Chat." xuất hiện trong khu vực khởi đầu với hiệu ứng hoạt hình vào.
  - AC-2. Giả sử người dùng đang ở trang trò chuyện có tin nhắn, khi họ nhấp "New Chat", thì URL thay đổi thành `/c/new` và màn hình khởi đầu được hiển thị.
  - AC-3. Giả sử người dùng Ctrl/Cmd+nhấp "New Chat", khi trình duyệt xử lý lần nhấp, thì `/c/new` mở trong tab mới và tab hiện tại không thay đổi.
  - AC-4. Giả sử một cuộc trò chuyện đang tải (spinner hiển thị), khi tải hoàn tất với tin nhắn, thì màn hình khởi đầu không xuất hiện thoáng qua trước khi MessagesView xuất hiện.

---

### Soạn & Gửi tin nhắn

- **Mục đích:** Cho phép người dùng nhập tin nhắn và gửi đến mô hình.

- **Điều kiện tiên quyết / truy cập:** Người dùng đã xác thực với ít nhất một endpoint được cấu hình. Endpoint "Nufi" phải khả dụng. Đầu vào bị vô hiệu hóa (`disableInputs`) khi `requiresKey` là true (cần khóa API nhưng bị thiếu) hoặc khi một assistant không hợp lệ được chọn.

- **Thành phần giao diện:**
  - **Textarea tin nhắn** (`ChatForm.tsx` dòng 303): `TextareaAutosize`, `id="main-textarea"`, `data-testid="text-input"`, `aria-label` → `com_ui_message_input`. Bắt đầu ở chiều cao 44 px, mở rộng tối đa 45 vh (di động) / 55 vh (máy tính để bàn).
  - **Nút Thu gọn/Mở rộng** (`CollapseChat`, `ChatForm.tsx` dòng 333): xuất hiện khi textarea vượt quá 3 hàng hiển thị; thu gọn textarea về `max-h-[52px]` với mặt nạ mờ dần.
  - **Nút Đính kèm tệp** (`AttachFileChat`, `ChatForm.tsx` dòng 348): biểu tượng ghim giấy ở góc dưới bên trái.
  - **Nút Gửi** (`SendButton.tsx`, `id="send-button"`, `data-testid="send-button"`, `aria-label` → `com_nav_send_message`): hình tròn có viền đầy màu với `SendIcon` (24 px). Trạng thái vô hiệu hóa: `opacity-10`, `cursor-not-allowed`.
  - **Nút Dừng** (`StopButton.tsx`, `aria-label` → `com_nav_stop_generating`): thay thế nút Gửi trong khi đang gửi; hình tròn với biểu tượng hình vuông đầy (hình chữ nhật 10×10 px trong viewbox 24×24).
  - **Hàng Badge** (`BadgeRow`): badge tính năng tạm thời (ví dụ: tìm kiếm web) hiển thị cho các endpoint không phải agents/assistants.
  - **Ghi âm** (`AudioRecorder`): chỉ hiển thị khi cài đặt `SpeechToText` được bật.
  - **Chuyển đổi Temporary Chat** (`TemporaryChat.tsx`): biểu tượng `MessageCircleDashed`, `aria-label` → `com_ui_temporary`. Hiển thị trong tiêu đề chỉ khi cuộc trò chuyện không có tin nhắn và không đang gửi.

- **Hành vi chức năng:**
  - FR-1. **Enter để gửi (mặc định):** Khi atom lưu trữ `enterToSend` là `true` (mặc định, được lưu trong localStorage là `'enterToSend'`), nhấn `Enter` mà không có `Shift` gọi `submitButtonRef.current?.click()` để gửi biểu mẫu. Nhấn `Shift+Enter` chèn xuống dòng mới.
  - FR-2. **Enter để gửi bị tắt:** Khi `enterToSend` là `false`, nhấn `Enter` chèn xuống dòng mới. `Ctrl/Cmd+Enter` gửi bất kể cài đặt `enterToSend`.
  - FR-3. **Bảo vệ IME/Bố cục:** Khi quá trình bố cục IME đang hoạt động (`isComposing.current`, `e.key === 'Process'`, hoặc `e.keyCode === 229`), Enter không gửi. Điều này ngăn việc gửi nhầm trong khi nhập CJK.
  - FR-4. **Trạng thái nút Gửi:** Nút gửi bị vô hiệu hóa khi: (a) `text.trim()` rỗng — được kiểm tra bên trong `SendButton.tsx:44` qua `!content`; hoặc (b) `filesLoading` là true, (c) `isSubmitting` là true, (d) `disableInputs` là true, hoặc (e) `isNotAppendable` là true — các điều kiện (b)–(e) được truyền qua prop `disabled` từ `ChatForm.tsx:386`.
  - FR-5. **Hiển thị nút Dừng:** Trong khi `isSubmitting && showStopButton` là true, nút Dừng được hiển thị thay cho nút Gửi. `showStopButton` là atom Recoil theo từng index (`store.showStopButtonByIndex(index)`).
  - FR-6. **Tự động lưu:** Hook `useAutoSave` lưu trữ bản nháp văn bản và các tệp đính kèm cho `conversationId` hiện tại trong khi soạn. Bản nháp được khôi phục nếu người dùng điều hướng đi và quay lại trước khi gửi.
  - FR-7. **Chế độ Temporary Chat:** Khi được bật (viền và nền tím: `border-violet-800/60 bg-violet-950/10`), cuộc trò chuyện không được lưu vào lịch sử. Chuyển đổi chỉ có thể truy cập trước khi tin nhắn đầu tiên được gửi.
  - FR-8. **Hỗ trợ RTL:** Khi `chatDirection` là `'rtl'`, hàng flex bị đảo ngược và văn bản căn phải.
  - FR-9. **Ctrl/Cmd+Enter trong chế độ chỉnh sửa:** Trong biểu mẫu chỉnh sửa tin nhắn (`EditMessage.tsx` dòng 134), `Ctrl/Cmd+Enter` kích hoạt Save & Submit, và `Ctrl/Cmd+S` kích hoạt Save only.

- **Trạng thái & trường hợp đặc biệt:**
  - Văn bản rỗng: Nút Gửi bị vô hiệu hóa; nhấn Enter không có tác dụng.
  - Đang tải tệp: Nút Gửi hiển thị `disabled` cho đến khi `filesLoading` trở thành false.
  - Đang gửi: textarea vẫn được bật trong khi gửi (`disabled={disableInputs || isNotAppendable}` trong `ChatForm.tsx:310` — `isSubmitting` không có trong biểu thức đó); chỉ có trình xử lý keydown Enter bị bỏ qua tại `if (e.key === 'Enter' && isSubmitting) return;` (`useTextarea.ts:147`).
  - Tin nhắn rất dài (>3 hàng hiển thị): Nút Thu gọn xuất hiện; khi thu gọn, textarea hiển thị gradient mờ dần.
  - Yêu cầu khóa API: cả textarea và nút gửi đều bị vô hiệu hóa; `cursor-not-allowed` được hiển thị.

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử textarea rỗng, khi người dùng nhấn Enter, thì không có tin nhắn nào được gửi và nút gửi vẫn bị vô hiệu hóa.
  - AC-2. Giả sử `enterToSend` là true và textarea có văn bản, khi người dùng nhấn Enter (không có Shift), thì tin nhắn được gửi.
  - AC-3. Giả sử `enterToSend` là true và textarea có văn bản, khi người dùng nhấn Shift+Enter, thì xuống dòng mới được chèn và không có gửi nào xảy ra.
  - AC-4. Giả sử `enterToSend` là false và textarea có văn bản, khi người dùng nhấn Ctrl/Cmd+Enter, thì tin nhắn được gửi.
  - AC-5. Giả sử một quá trình tạo đang diễn ra, khi người dùng nhìn vào khu vực nhập, thì nút Dừng (biểu tượng hình vuông đầy) hiển thị thay cho nút Gửi.
  - AC-6. Giả sử Temporary Chat được bật trước khi gửi bất kỳ tin nhắn nào, khi tin nhắn được gửi, thì cuộc trò chuyện không được lưu vào lịch sử và khung nhập hiển thị viền tím.

---

### Phản hồi phát trực tuyến & Hiển thị trực tiếp

- **Mục đích:** Hiển thị phản hồi của mô hình từng token một khi được tạo, cung cấp phản hồi theo thời gian thực.

- **Điều kiện tiên quyết / truy cập:** Một tin nhắn đã được gửi. Endpoint được chọn phải có thể truy cập. Luồng SSE phải được thiết lập.

- **Thành phần giao diện:**
  - **Con trỏ phát trực tuyến / chỉ báo đang suy nghĩ** (`Markdown.tsx` dòng 66–73): khi `content === ''` (đang khởi tạo), một `<span className="result-thinking">` được hiển thị như một trình giữ chỗ nhấp nháy.
  - **Bong bóng tin nhắn:** tin nhắn assistant mới nhất được cập nhật dần trong `MessagesView` qua `MultiMessage` → `Message` → `MessageRender` → `MessageContent`.
  - **PlaceholderRow** (`ui/PlaceholderRow.tsx`): hiển thị trong `MessageRender` (`dòng 237–239`) trong khi `hasNoChildren && isSubmitting`; thay thế hàng nút hover trong quá trình tạo để bố cục không bị dịch chuyển.

- **Hành vi chức năng:**
  - FR-1. **Lựa chọn giao thức SSE (`useAdaptiveSSE.ts`):** Đối với tất cả các endpoint không phải Assistants (bao gồm "Nufi"), đường dẫn **SSE có thể tiếp tục** (`useResumableSSE`) đang hoạt động. Đối với các endpoint Assistants, `useSSE` tiêu chuẩn đang hoạt động. Cả hai hook luôn được mount để tuân thủ quy tắc Hooks của React; hook không hoạt động nhận submission là `null` để ở trạng thái không làm gì.
  - FR-2. **Tiếp tục sau điều hướng:** `useResumeOnLoad` (được gọi trong `ChatView.tsx` dòng 61) phát hiện một công việc đang hoạt động cho `conversationId` hiện tại sau khi điều hướng và tiếp tục phát trực tuyến. Nó chờ cho đến khi `!isLoading` để tránh điều kiện tranh chấp.
  - FR-3. **Markdown được hiển thị trực tiếp:** Khi token đến, thành phần `Markdown` hiển thị lại với chuỗi `content` đang phát triển. `rehype-highlight` tô sáng cú pháp mã; `rehype-katex` / `remark-math` hiển thị LaTeX (khi cài đặt `LaTeXParsing` được bật); `remark-gfm` hỗ trợ bảng, gạch ngang và danh sách nhiệm vụ.
  - FR-4. **Tự động cuộn trong khi phát trực tuyến:** `useMessageScrolling` gọi `scrollToBottom()` trên mỗi lần cập nhật cây trong khi `isSubmitting && abortScroll !== true`. Nếu người dùng cuộn lên thủ công, `abortScroll` được đặt thành true và tự động cuộn dừng.
  - FR-5. **Ghi nhớ:** `MessageRender` sử dụng bộ so sánh tùy chỉnh `areMessageRenderPropsEqual` để chỉ tin nhắn đang phát trực tuyến tích cực mới hiển thị lại trên mỗi sự kiện SSE; các tin nhắn cũ hơn trong luồng vẫn ổn định.
  - FR-6. **Phát lại chuyển văn bản thành giọng nói:** Khi cả `TextToSpeech` và `automaticPlayback` đều true, `StreamAudio` tự động phát âm thanh phản hồi của assistant.

- **Trạng thái & trường hợp đặc biệt:**
  - Mạng ngắt giữa chừng: cơ chế SSE có thể tiếp tục theo dõi một `streamId`; nếu người dùng tải lại hoặc điều hướng đi và quay lại, `useResumeOnLoad` cố gắng kết nối lại với công việc đang diễn ra.
  - Token đầu tiên rỗng: span nhấp nháy `result-thinking` được hiển thị cho đến khi chunk nội dung khác rỗng đầu tiên đến.
  - Lỗi từ máy chủ: `message.error = true` được đặt; văn bản tin nhắn hiển thị lỗi; chỉ một nút Regenerate được hiển thị thay cho hàng nút hover đầy đủ (`HoverButtons.tsx` dòng 162–176).
  - Phản hồi rất dài: khung chứa tin nhắn có thể cuộn; nút chevron `ScrollToBottom` xuất hiện khi người dùng cuộn lên đủ xa để phần tử sentinel `messagesEndRef` rời khỏi viewport (ngưỡng IntersectionObserver 0.85).

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử một tin nhắn đã được gửi, khi token đầu tiên đến, thì chỉ báo nhấp nháy `result-thinking` biến mất và văn bản bắt đầu hiển thị.
  - AC-2. Giả sử phản hồi đang phát trực tuyến, khi người dùng cuộn lên, thì tự động cuộn dừng và nút chevron "cuộn xuống dưới" xuất hiện.
  - AC-3. Giả sử phản hồi đang phát trực tuyến và người dùng ở dưới cùng, khi token mới đến, thì viewport tự động cuộn để hiển thị nội dung mới.
  - AC-4. Giả sử người dùng điều hướng đi giữa chừng phát trực tuyến và quay lại cùng cuộc trò chuyện, khi trang tải, thì phát trực tuyến tiếp tục từ điểm đã dừng (đường dẫn SSE có thể tiếp tục).
  - AC-5. Giả sử xảy ra lỗi máy chủ, khi lỗi được nhận, thì tin nhắn assistant hiển thị văn bản lỗi và một nút Regenerate; không có nút hover nào khác được hiển thị.

---

### Dừng quá trình tạo

- **Mục đích:** Cho phép người dùng dừng ngay lập tức phản hồi AI đang diễn ra.

- **Điều kiện tiên quyết / truy cập:** Một quá trình tạo đang diễn ra (`isSubmitting === true && showStopButton === true`).

- **Thành phần giao diện:**
  - **Nút Dừng** (`StopButton.tsx`): thay thế nút Gửi; hình tròn, `aria-label` → `com_nav_stop_generating`; biểu tượng là hình vuông đầy 10×10 (`rect` SVG, `className="icon-lg text-surface-primary"`). Tooltip hiển thị nhãn đã được dịch khi di chuột qua.

- **Hành vi chức năng:**
  - FR-1. Nhấp nút Dừng gọi `setShowStopButton(false)` rồi `stop(e)` (tức là `handleStopGenerating`), gửi tín hiệu hủy đến luồng backend.
  - FR-2. Sau khi dừng, `isSubmitting` trở thành false. Nút Dừng được thay thế bởi nút Gửi.
  - FR-3. Tin nhắn được gửi một phần vẫn còn trong cuộc trò chuyện; nó không bị xóa. Nó có thể mang `unfinished: true` hoặc `finish_reason` khác `'stop'`, làm cho nút **Continue** đủ điều kiện xuất hiện.

- **Trạng thái & trường hợp đặc biệt:**
  - Nhấp đúp: Nút tự ẩn ngay sau lần nhấp đầu tiên (`setShowStopButton(false)`), ngăn nhấp lần hai.
  - Phản hồi rất nhanh: Nếu phản hồi hoàn tất trước khi người dùng nhấp Dừng, nút tự nhiên chuyển về Gửi.
  - Mạng đã mất: Tín hiệu hủy được gửi; UI chuyển sang trạng thái rảnh ngay cả khi máy chủ không xác nhận.

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử một quá trình tạo đang phát trực tuyến, khi người dùng nhấp nút Dừng, thì nút Dừng biến mất và nút Gửi xuất hiện lại trong một chu kỳ hiển thị.
  - AC-2. Giả sử nút Dừng đã được nhấp, khi UI ổn định, thì tin nhắn assistant được tạo một phần hiển thị và không bị xóa.
  - AC-3. Giả sử nút Dừng được nhấp, khi phản hồi bị cắt giữa câu, thì nút Continue hiển thị trên tin nhắn assistant cuối cùng (xem phần Continue).

---

### Tạo lại phản hồi

- **Mục đích:** Yêu cầu phản hồi mới cho cùng một lượt người dùng, loại bỏ tin nhắn assistant hiện tại.

- **Điều kiện tiên quyết / truy cập:** Tin nhắn phải là tin nhắn assistant (`isCreatedByUser === false`). `regenerateEnabled` là true khi: không phải tin nhắn người dùng, không phải kết quả tìm kiếm, không đang chỉnh sửa, không đang gửi, và endpoint là một trong: `openAI`, `custom`, `google`, `agents`, `bedrock`, `anthropic`, `azureOpenAI` (xem `useGenerationsByLatest.ts` dòng 46–59). "Nufi" sử dụng loại endpoint `custom`, vì vậy tạo lại được hỗ trợ.

- **Thành phần giao diện:**
  - **Nút Regenerate** (`HoverButtons.tsx` dòng 252–260): `RegenerateIcon` (19 px), `title` → `com_ui_regenerate`. Các nút hover bị ẩn ở `md:opacity-0` và hiển thị khi `group-hover` / `group-focus-within` / `group-[.final-completion]`. Nút Regenerate có class `active` nên có thể luôn hiển thị trên tin nhắn cuối cùng.

- **Hành vi chức năng:**
  - FR-1. Nhấp Regenerate gọi `regenerateMessage()` → `handleRegenerateMessage()` gọi `ask()` với ngữ cảnh của tin nhắn người dùng cha. Một phản hồi phát trực tuyến mới thay thế tin nhắn assistant hiện tại.
  - FR-2. Phản hồi cũ không bị xóa khỏi lịch sử; cây cuộc trò chuyện phân nhánh (một nút anh em được tạo ra). Thành phần `SiblingSwitch` (`SiblingSwitch.tsx`) cho phép điều hướng giữa phản hồi gốc và phản hồi được tạo lại.
  - FR-3. Regenerate bị vô hiệu hóa (`regenerateEnabled = false`) trong khi `isSubmitting` là true, ngăn các lần gửi đồng thời.

- **Trạng thái & trường hợp đặc biệt:**
  - Nhiều lần tạo lại: mỗi lần tạo ra một nhánh anh em; `siblingCount` tăng. `SiblingSwitch` hiển thị điều hướng `<idx>/<total>`.
  - Tin nhắn lỗi: khi `message.error === true`, một nút Regenerate được hiển thị đơn độc mà không có các nút hover khác (`HoverButtons.tsx` dòng 162–176).
  - Endpoint không hỗ trợ phân nhánh (ví dụ: Assistants): `branchingSupported` là false; nút Regenerate bị ẩn.

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử tin nhắn assistant cuối cùng hiển thị và không có quá trình tạo nào đang diễn ra, khi người dùng di chuột qua tin nhắn và nhấp Regenerate, thì một phản hồi phát trực tuyến mới bắt đầu.
  - AC-2. Giả sử một lần tạo lại hoàn tất, khi người dùng nhìn vào tin nhắn, thì bộ chuyển đổi anh em (`1/2`, `2/2`, v.v.) hiển thị để điều hướng giữa các phản hồi.
  - AC-3. Giả sử một quá trình tạo đang diễn ra, khi người dùng di chuột qua bất kỳ tin nhắn nào, thì nút Regenerate không thể nhấp/không hiển thị (opacity-0 hoặc disabled).

---

### Chỉnh sửa tin nhắn đã gửi & Gửi lại

- **Mục đích:** Cho phép người dùng sửa một tin nhắn đã gửi trước đó và chạy lại cuộc trò chuyện từ điểm đó.

- **Điều kiện tiên quyết / truy cập:** Nút `isEditableEndpoint` phải là true (cùng danh sách endpoint như Regenerate; "Nufi"/custom đủ điều kiện). `hideEditButton` là false (không đang gửi, không phải lỗi, không phải kết quả tìm kiếm). Cả tin nhắn người dùng và tin nhắn assistant đều có thể được chỉnh sửa.

- **Thành phần giao diện:**
  - **Nút Edit** (`HoverButtons.tsx` dòng 223–235): `EditIcon` (19 px), `id="edit-<messageId>"`, `title` → `com_ui_edit`. Ẩn/vô hiệu hóa qua `isVisible={!hideEditButton}`. Trạng thái active khi `isEditing === true`.
  - **Textarea chỉnh sửa** (`EditMessage.tsx` dòng 160): `TextareaAutosize`, `data-testid="message-text-editor"`, `aria-label` → `com_ui_message_input`. Chiều cao tối đa 65 vh (di động) / 75 vh (máy tính để bàn). Được focus và con trỏ đặt ở cuối khi mount.
  - **Nút Save & Submit** (`EditMessage.tsx` dòng 184): nhãn `com_ui_save_submit`. Tooltip: `Ctrl + Enter / ⌘ + Enter`. Bị vô hiệu hóa trong khi `isSubmitting`.
  - **Nút Save** (`EditMessage.tsx` dòng 196): nhãn `com_ui_save`. Phím tắt thực tế là **`Ctrl/Cmd+S`** (`EditMessage.tsx:138`). Lưu ý: tooltip hiển thị trong giao diện (prop `description` tại `EditMessage.tsx:195`) sai khi ghi `"Shift + Enter"` — không khớp với phím tắt thực tế. Người kiểm thử nên sử dụng `Ctrl/Cmd+S` và chú ý rằng tooltip hiển thị không chính xác.
  - **Nút Cancel** (`EditMessage.tsx` dòng 207): nhãn `com_ui_cancel`. Tooltip: `Esc`.

- **Hành vi chức năng:**
  - FR-1. Nhấp Edit vào chế độ chỉnh sửa (`enterEdit()`). Nội dung tin nhắn được thay thế bởi một `TextareaAutosize` có thể chỉnh sửa được điền sẵn văn bản tin nhắn hiện tại.
  - FR-2. **Save & Submit** (tin nhắn người dùng): gọi `ask()` với `{ text: newText, parentMessageId, conversationId }`, ghi đè các tệp và kỹ năng thủ công từ tin nhắn gốc. `setSiblingIdx(siblingIdx - 1)` phân nhánh cây. Phím tắt là `Ctrl/Cmd+Enter`.
  - FR-3. **Save & Submit** (tin nhắn assistant): gọi `ask()` với tin nhắn người dùng cha, truyền `editedText`, `editedMessageId`, `isRegenerate: true`, `isEdited: true`. Phím tắt giống nhau.
  - FR-4. **Save only** (không gửi lại): gọi `updateMessageMutation.mutate()` để lưu văn bản đã chỉnh sửa vào cơ sở dữ liệu mà không kích hoạt quá trình tạo mới. Phím tắt là `Ctrl/Cmd+S`.
  - FR-5. **Cancel**: gọi `enterEdit(true)` khôi phục hiển thị gốc. Phím tắt: `Escape`.
  - FR-6. Chỉnh sửa một tin nhắn không phải tin nhắn mới nhất tạo ra một nhánh; `SiblingSwitch` cho phép điều hướng giữa bản gốc và nhánh đã chỉnh sửa.

- **Trạng thái & trường hợp đặc biệt:**
  - Nhấp Edit lại khi đang trong chế độ chỉnh sửa: `onEdit` phát hiện `isEditing === true` và gọi `enterEdit(true)` (hủy).
  - Gửi tin nhắn khác trong khi đang mở chỉnh sửa: `isSubmitting` trở thành true, vô hiệu hóa nút Save & Submit.
  - Văn bản gốc rất dài: textarea được cuộn sẵn đến cuối; max-height ngăn tràn trang.
  - Chỉnh sửa rỗng: "Save & Submit" xác thực `required: true`; gửi văn bản rỗng bị ngăn bởi react-hook-form.

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử một tin nhắn người dùng đang hiển thị, khi người dùng nhấp Edit, thì văn bản tin nhắn trở thành có thể chỉnh sửa trong một textarea được focus ở cuối.
  - AC-2. Giả sử textarea chỉnh sửa đang mở với văn bản đã sửa, khi người dùng nhấn Ctrl/Cmd+Enter, thì tin nhắn đã chỉnh sửa được gửi và một phản hồi assistant mới phát trực tuyến.
  - AC-3. Giả sử textarea chỉnh sửa đang mở, khi người dùng nhấn Escape, thì textarea đóng lại và văn bản tin nhắn gốc được khôi phục.
  - AC-4. Giả sử một tin nhắn assistant được chỉnh sửa và Save & Submit được nhấp, thì một phản hồi assistant mới được tạo ra sử dụng cùng lời nhắc người dùng cha với văn bản assistant đã chỉnh sửa được chèn vào.
  - AC-5. Giả sử Save (không Submit) được nhấp trên bất kỳ tin nhắn nào, khi lưu hoàn tất, thì văn bản tin nhắn được cập nhật tại chỗ và không có quá trình tạo mới nào được kích hoạt.

---

### Tiếp tục phản hồi bị cắt ngắn

- **Mục đích:** Yêu cầu mô hình tiếp tục tạo từ nơi phản hồi bị cắt ngắn kết thúc (ví dụ: sau khi đạt giới hạn token hoặc sau khi Dừng).

- **Điều kiện tiên quyết / truy cập:** `continueSupported` là true. Từ `useGenerationsByLatest.ts` dòng 38–44: tin nhắn phải là mới nhất (`latestMessageId === messageId`), `finish_reason` phải được đặt và không được là `'stop'`, không đang chỉnh sửa (`!isEditing`), không phải kết quả tìm kiếm (`!searchResult`), và `isEditableEndpoint` phải là true. Không có kiểm tra `!isSubmitting` trong `continueSupported` — nút Continue có thể xuất hiện ngay cả khi một yêu cầu khác đang diễn ra.

- **Thành phần giao diện:**
  - **Nút Continue** (`HoverButtons.tsx` dòng 263–271): `ContinueIcon` (xoay 180°, `className="w-19 h-19 -rotate-180"`), `title` → `com_ui_continue`. Chỉ hiển thị khi `continueSupported` là true.

- **Hành vi chức năng:**
  - FR-1. Nhấp Continue gọi `handleContinue(e)`, gửi yêu cầu tiếp tục đến backend bằng ngữ cảnh cuộc trò chuyện hiện có. Phản hồi tiếp tục từ điểm bị cắt ngắn.
  - FR-2. Khi một lần tiếp tục hoàn tất với `finish_reason === 'stop'`, nút Continue biến mất.
  - FR-3. Phần tiếp tục được thêm vào (hoặc thay thế, tùy thuộc vào xử lý backend) tin nhắn assistant hiện có.

- **Trạng thái & trường hợp đặc biệt:**
  - Nếu người dùng chỉnh sửa một tin nhắn, `isEditing` trở thành true và Continue bị ẩn.
  - Nếu một yêu cầu khác đang diễn ra, `continueSupported` đánh giá là false vì `latestMessageId` thay đổi.

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử một tin nhắn assistant có `finish_reason` khác `'stop'` (ví dụ: `'length'`), khi người dùng di chuột qua tin nhắn đó, thì nút Continue hiển thị.
  - AC-2. Giả sử người dùng nhấp Continue, khi phần tiếp tục kết thúc với `finish_reason === 'stop'`, thì nút Continue biến mất.
  - AC-3. Giả sử một tin nhắn hoàn thành bình thường (`finish_reason === 'stop'`), khi người dùng di chuột qua, thì nút Continue không được hiển thị.

---

### Sao chép tin nhắn

- **Mục đích:** Cho phép người dùng sao chép toàn bộ nội dung văn bản của bất kỳ tin nhắn nào vào clipboard hệ thống.

- **Điều kiện tiên quyết / truy cập:** Bất kỳ tin nhắn nào đã được hiển thị (người dùng hoặc assistant).

- **Thành phần giao diện:**
  - **Nút Copy** (`HoverButtons.tsx` dòng 209–220): biểu tượng `Clipboard` (19 px) ở trạng thái rảnh; biểu tượng `CheckMark` (18×18 px) sau khi sao chép. Tiêu đề chuyển đổi giữa `com_ui_copy_to_clipboard` và `com_ui_copied_to_clipboard`. Có `className="ml-0 flex items-center gap-1.5 text-xs"`.

- **Hành vi chức năng:**
  - FR-1. Nhấp nút gọi `copyToClipboard(setIsCopied)`. Toàn bộ văn bản tin nhắn được trích xuất bởi `extractMessageContent(message)` (`HoverButtons.tsx` dòng 40–70), xử lý ba dạng nội dung: `string` thuần túy, mảng các phần nội dung (trích xuất các trường `text` và `think`), và trường `message.text` kế thừa.
  - FR-2. Khi sao chép thành công, `setIsCopied(true)` được gọi, chuyển biểu tượng sang CheckMark. Biểu tượng trở về Clipboard sau một khoảng thời gian ngắn (cần xác minh thủ công trên sản phẩm đang chạy: thời gian chờ được quản lý bên trong `useCopyToClipboard`, không thấy được từ `HoverButtons.tsx`).
  - FR-3. Nút copy luôn hiển thị trên tin nhắn mới nhất; trên các tin nhắn cũ hơn, nó bị ẩn ở `md:opacity-0` và hiển thị khi di chuột/focus.

- **Trạng thái & trường hợp đặc biệt:**
  - Tin nhắn có nội dung hỗn hợp (văn bản + khối think): tất cả các phần văn bản được nối theo thứ tự.
  - Tin nhắn đang phát trực tuyến: Copy khả dụng; nội dung một phần cho đến thời điểm đó được sao chép.
  - Clipboard API không khả dụng (không phải HTTPS hoặc quyền bị từ chối): lỗi được xử lý nội bộ (cần xác minh thủ công trên sản phẩm đang chạy: khối catch nằm bên trong hook `copyToClipboard` và không thấy được từ `HoverButtons.tsx`).

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử một tin nhắn assistant đã được hiển thị, khi người dùng nhấp nút Copy, thì biểu tượng CheckMark xuất hiện xác nhận sao chép.
  - AC-2. Giả sử nút Copy đã được nhấp, khi một lúc trôi qua, thì biểu tượng trở về biểu tượng Clipboard.
  - AC-3. Giả sử một tin nhắn nhiều phần (văn bản + khối lý luận), khi được sao chép, thì clipboard chứa tất cả các phần văn bản được nối.

---

### Phân nhánh cuộc trò chuyện

- **Mục đích:** Tạo một nhánh cuộc trò chuyện độc lập mới bắt đầu từ một tin nhắn được chọn, giữ nguyên cuộc trò chuyện gốc.

- **Điều kiện tiên quyết / truy cập:** `forkingSupported` là true (`useGenerationsByLatest.ts` dòng 68): endpoint không được là endpoint Assistants, và tin nhắn không được là kết quả tìm kiếm. `conversationId` và `messageId` phải không rỗng (`Fork.tsx` dòng 269).

- **Thành phần giao diện:**
  - **Nút Fork** (`Fork.tsx` dòng 332): biểu tượng `GitFork` (19 px, từ `lucide-react`), `aria-label` → `com_ui_fork_open_menu`. Kiểu nút hover (ẩn ở `md:opacity-0`, hiển thị khi group-hover).
  - **Popover tùy chọn Fork** (`Fork.tsx` dòng 356–443): thẻ bo góc rộng 240 px với ba nút chế độ fork cộng hai checkbox:
    - **"Visible messages only" (`ForkOptions.DIRECT_PATH`)**: biểu tượng `GitCommit` xoay 90°; chỉ sao chép đường dẫn trực tiếp của các tin nhắn dẫn đến tin nhắn được chọn.
    - **"Include related branches" (`ForkOptions.INCLUDE_BRANCHES`)**: biểu tượng `GitBranchPlus` xoay 180°; bao gồm tất cả các nhánh anh em cho đến tin nhắn được chọn.
    - **"Include all to/from here" (`ForkOptions.TARGET_LEVEL`)**: biểu tượng `ListTree`; bao gồm tất cả tin nhắn ở cùng mức độ sâu. Được gắn nhãn "(default)" trong thẻ hover.
    - **Checkbox "Split at target"** (`id="split-target-checkbox"`): khi được chọn, fork bắt đầu từ tin nhắn được chọn thay vì bao gồm nó.
    - **Checkbox "Remember"** (`id="remember-checkbox"`): khi được chọn, lưu chế độ fork đã chọn làm mặc định toàn cục và bỏ qua popover trong các lần fork sau.

- **Hành vi chức năng:**
  - FR-1. Nếu `rememberGlobal` là true (từ `store.rememberDefaultFork`), nhấp nút Fork ngay lập tức thực hiện fork sử dụng `forkSetting` đã lưu, bỏ qua popover.
  - FR-2. Nếu không, nhấp nút Fork bật/tắt popover tùy chọn.
  - FR-3. Chọn một tùy chọn fork gọi `forkConvo.mutate({ messageId, conversationId, option, splitAtTarget, latestMessageId })`.
  - FR-4. Khi thành công, người dùng được điều hướng đến cuộc trò chuyện đã phân nhánh mới (`navigateToConvo(data.conversation)`) và một toast thành công (`com_ui_fork_success`) được hiển thị.
  - FR-5. Một toast thông tin (`com_ui_fork_processing`) được hiển thị trong khi mutation đang diễn ra.
  - FR-6. Khi xảy ra lỗi giới hạn tốc độ (HTTP 429), một toast lỗi (`com_ui_fork_error_rate_limit`) được hiển thị. Các lỗi khác hiển thị `com_ui_fork_error`.

- **Trạng thái & trường hợp đặc biệt:**
  - Endpoint Assistants: Nút Fork không được hiển thị.
  - Trong khi đang gửi: Nút Fork hiển thị nhưng nhóm nút hover có `md:opacity-0` trên các tin nhắn không phải cuối; người dùng phải di chuột để hiển thị nó.
  - Remember được chọn trong phiên: một toast thông báo người dùng (`com_ui_fork_remember_checked`).

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử một cuộc trò chuyện có tin nhắn, khi người dùng di chuột qua tin nhắn không phải Assistants và nhấp Fork, thì một popover với ba tùy chọn chế độ fork xuất hiện.
  - AC-2. Giả sử người dùng chọn một chế độ fork, khi fork thành công, thì trình duyệt điều hướng đến cuộc trò chuyện đã phân nhánh mới và một toast thành công được hiển thị.
  - AC-3. Giả sử checkbox "Remember" được chọn và một chế độ fork được chọn, khi người dùng sau đó nhấp Fork trên bất kỳ tin nhắn nào, thì fork thực hiện ngay mà không hiển thị popover.
  - AC-4. Giả sử xảy ra lỗi giới hạn tốc độ, khi fork thất bại, thì toast lỗi `com_ui_fork_error_rate_limit` được hiển thị và người dùng vẫn ở cuộc trò chuyện hiện tại.

---

### Phản hồi về tin nhắn (Thích / Không thích)

- **Mục đích:** Thu thập phản hồi định tính của người dùng về các phản hồi assistant cho mục đích kiểm duyệt hoặc cải thiện.

- **Điều kiện tiên quyết / truy cập:** `handleFeedback` không phải null VÀ `isCreatedByUser` là false (phản hồi chỉ dành cho tin nhắn assistant, `HoverButtons.tsx` dòng 247–249).

- **Thành phần giao diện:**
  - **Nút Thumbs Up** (`Feedback.tsx` dòng 149): `ThumbUpIcon` (19 px), `title` → `com_ui_feedback_positive`, `aria-pressed` phản ánh đánh giá hiện tại.
  - **Nút Thumbs Down** (`Feedback.tsx` dòng 181): `ThumbDownIcon` (19 px), `title` → `com_ui_feedback_negative`, `aria-pressed` phản ánh đánh giá hiện tại.
  - **Popover tag** (Ariakit `Popover`, `gutter={8}`): xuất hiện khi nhấp lần đầu vào một trong hai nút khi chưa có đánh giá nào được ghi. Chứa danh sách các mục `FeedbackOptionButton` với biểu tượng và nhãn đã được dịch từ `getTagsForRating('thumbsUp')` / `getTagsForRating('thumbsDown')`.
  - **Hộp thoại "More information"** (`OGDialog`, `Feedback.tsx` dòng 316): hiển thị khi tag "Other" được chọn. Chứa một `textarea` (tối đa 500 ký tự, `placeholder` → `com_ui_feedback_placeholder`) cộng các nút "Delete" (`variant="destructive"`) và "Save" (`variant="submit"`, bị vô hiệu hóa cho đến khi văn bản không rỗng).
  - **Nút hợp nhất đơn** (`renderSingleFeedbackButton`): khi một đánh giá được ghi, cả hai nút thumbs hợp nhất thành một nút active duy nhất chỉ hiển thị biểu tượng đã chọn.

- **Hành vi chức năng:**
  - FR-1. Nhấp lần đầu Thumbs Up (chưa có đánh giá): popover tag mở cho các tag tích cực.
  - FR-2. Nhấp lần đầu Thumbs Down (chưa có đánh giá): popover tag mở cho các tag tiêu cực.
  - FR-3. Chọn tag không phải "other" từ popover: gọi `onFeedback({ rating, tag })`, đóng popover, lưu trữ phản hồi qua `handleFeedback`. Nhóm hai nút hợp nhất thành một nút active.
  - FR-4. Chọn tag "other": ghi lại đánh giá và mở hộp thoại văn bản cho ngữ cảnh bổ sung.
  - FR-5. Nhấp Thumbs Up lại khi đã đánh giá thumbs-up: xóa phản hồi (`onFeedback(undefined)`).
  - FR-6. Nhấp Thumbs Down lại khi đã đánh giá thumbs-down: mở hộp thoại văn bản (chỉnh sửa lại phản hồi tiêu cực).
  - FR-7. Trong hộp thoại, "Save" bị vô hiệu hóa cho đến khi trường văn bản tự do không rỗng (cho tag "other"). "Delete" xóa đánh giá hoàn toàn.
  - FR-8. Trạng thái phản hồi (đối tượng `TFeedback` với `rating`, `tag`, `text` tùy chọn) được truyền lên và lưu trữ theo từng tin nhắn.

- **Trạng thái & trường hợp đặc biệt:**
  - Nút hover bị ẩn cho đến khi di chuột: trên các tin nhắn không phải cuối, toàn bộ hàng hover là `md:opacity-0`; các nút phản hồi tuân theo các quy tắc hiển thị tương tự.
  - Prop `initialFeedback` được đồng bộ qua `useEffect`: nếu máy chủ trả về trạng thái phản hồi đã cập nhật, trạng thái cục bộ được cập nhật.
  - Lưu hộp thoại với văn bản rỗng: nút bị vô hiệu hóa; phản hồi không được truyền.
  - Chuyển đổi nhanh: mỗi lần nhấp đồng bộ cập nhật trạng thái cục bộ và gọi `handleFeedback`; điều kiện tranh chấp khó xảy ra nhưng lần gọi cuối cùng thắng.

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử một tin nhắn assistant chưa có phản hồi, khi người dùng nhấp Thumbs Up, thì một popover chọn tag xuất hiện với các tùy chọn tag tích cực.
  - AC-2. Giả sử người dùng chọn một tag từ popover, khi popover đóng, thì một nút Thumbs Up active duy nhất được hiển thị và phản hồi được ghi lại.
  - AC-3. Giả sử nút Thumbs Up active đang hiển thị, khi người dùng nhấp lại, thì phản hồi được xóa và cả hai nút Thumbs Up/Down xuất hiện lại.
  - AC-4. Giả sử người dùng chọn tag "Other" từ popover Thumbs Down, khi hộp thoại mở, thì nút Save bị vô hiệu hóa cho đến khi người dùng nhập vào vùng văn bản.
  - AC-5. Giả sử người dùng nhấp "Delete" trong hộp thoại phản hồi, khi nó đóng, thì đánh giá được xóa và hàng hai nút được khôi phục.

---

### Hiển thị Markdown & Khối mã

- **Mục đích:** Hiển thị phản hồi AI với định dạng phong phú: tiêu đề, danh sách, bảng, mã nội tuyến, khối mã có viền với tô sáng cú pháp, toán học LaTeX, và hơn thế nữa.

- **Điều kiện tiên quyết / truy cập:** Bất kỳ tin nhắn assistant nào. Tin nhắn người dùng được hiển thị dưới dạng văn bản thuần túy (chúng sử dụng `MarkdownLite` hoặc trình hiển thị đơn giản hơn; cần xác minh: kiểm tra `MessageContent.tsx` cho đường dẫn hiển thị tin nhắn người dùng).

- **Thành phần giao diện:**
  - **Thành phần Markdown** (`Markdown.tsx`): `ReactMarkdown` với ngăn xếp plugin remark/rehype:
    - `remark-gfm`: GitHub Flavored Markdown (bảng, danh sách nhiệm vụ, gạch ngang, autolinks).
    - `remark-math` + `rehype-katex`: toán học LaTeX (`$...$` nội tuyến bị vô hiệu hóa qua `singleDollarTextMath: false`; toán học hiển thị `$$...$$` được bật).
    - `remark-supersub`: chỉ số trên/chỉ số dưới.
    - `remark-directive` + `artifactPlugin`: khối artifact.
    - `mcpUIResourcePlugin`: thẻ/băng chuyền tài nguyên MCP UI.
    - `unicodeCitation`: hiển thị trích dẫn.
    - `rehype-highlight`: tô sáng cú pháp với tự động phát hiện ngôn ngữ (`detect: true`), sử dụng một tập con ngôn ngữ highlight.js.
  - **CodeBlock** (`CodeBlock.tsx`): được hiển thị bởi ghi đè thành phần `code`. Bao gồm mỗi khối mã có viền trong một `div.rounded-md.border.border-border.bg-card`.
  - **CodeBar** (`CodeBar.tsx`): thanh trên cùng của mỗi khối mã hiển thị tên ngôn ngữ, `LangIcon` tùy chọn, nút "Copy code", và tùy chọn nút "Run".
  - **Nút Copy code** (`CopyButton`, `CodeBar.tsx` dòng 28): `label` → `com_ui_copy_code`. Sử dụng `useCopyCode(codeRef)` để ghi `textContent` của phần tử code vào clipboard.
  - **FloatingCodeBar** (`FloatingCodeBar.tsx`): một bản sao dính của CodeBar nổi ở đỉnh khối mã khi người dùng cuộn khối ra ngoài tầm nhìn trong khi di chuột qua (`showFloating = isHovered && !isCodeBarVisible` từ `CodeBlock.tsx` dòng 99).
  - **Trình giữ chỗ Thinking/initializing**: khi `content === ''`, một hoạt hình nhấp nháy `<span className="result-thinking">` được hiển thị.
  - **MarkdownErrorBoundary** (`MarkdownErrorBoundary.tsx`): bao gồm trình hiển thị; khi có lỗi, chuyển về hiển thị văn bản thô.

- **Hành vi chức năng:**
  - FR-1. Các khối mã có viền được hiển thị với tô sáng cú pháp. Ngôn ngữ được hiển thị trong CodeBar.
  - FR-2. Nhấp "Copy code" trong CodeBar sao chép văn bản mã thô vào clipboard. Trạng thái `isCopied` thoáng qua hiển thị biểu tượng xác nhận.
  - FR-3. Khi người dùng di chuột qua khối mã và cuộn cho đến khi CodeBar ra ngoài màn hình, một CodeBar nổi trùng lặp xuất hiện cố định ở đỉnh khối.
  - FR-4. Toán học LaTeX (dấu đô đôi `$$...$$`) được hiển thị bởi KaTeX khi `LaTeXParsing` được bật (cài đặt người dùng, mặc định: **true**, được lưu trong localStorage với key `'LaTeXParsing'` — xác nhận tại `store/settings.ts:45`).
  - FR-5. Khi thực thi mã được bật (`allowExecution === true`) cho một khối, nút `RunCode` xuất hiện trong CodeBar. Kết quả thực thi xuất hiện trong một phần đầu ra có viền bên dưới mã, với `ResultSwitcher` cho nhiều lần chạy.
  - FR-6. Các artifact (`artifactPlugin`) được hiển thị nội tuyến khi assistant tạo ra các chỉ thị artifact; nhấp vào artifact mở bảng điều khiển bên Artifacts.
  - FR-7. Khi xảy ra lỗi hiển thị, `MarkdownErrorBoundary` hiển thị nội dung thô dưới dạng văn bản thuần túy và ghi lại lỗi.

- **Trạng thái & trường hợp đặc biệt:**
  - Khối mã không có thẻ ngôn ngữ: `rehype-highlight` cố gắng tự động phát hiện.
  - Khối mã rất dài: `div` bên trong là `overflow-y-auto`; khối cuộn độc lập.
  - LaTeX có lỗi cú pháp: KaTeX có thể hiển thị một span lỗi nội tuyến; phần còn lại của tin nhắn tiếp tục hiển thị.
  - Phát trực tuyến giữa chừng khối mã: bộ phân tích markdown có thể hiển thị mã không đầy đủ trước khi dấu ba gạch ngược đóng đến. Khối một phần được hiển thị theo khả năng tốt nhất.

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử một tin nhắn assistant chứa khối mã có viền được gắn nhãn `python`, khi hiển thị, thì khối hiển thị nhãn "python" và mã được tô sáng cú pháp.
  - AC-2. Giả sử một khối mã đã được hiển thị, khi người dùng nhấp "Copy code", thì clipboard chứa văn bản mã thô.
  - AC-3. Giả sử CodeBar của khối mã bị cuộn ra ngoài tầm nhìn trong khi người dùng di chuột qua khối, khi IntersectionObserver kích hoạt, thì FloatingCodeBar xuất hiện ở đỉnh khối.
  - AC-4. Giả sử một tin nhắn assistant chứa bảng GFM, khi hiển thị, thì bảng xuất hiện với các hàng và cột đúng (không phải cú pháp Markdown thô).
  - AC-5. Giả sử LaTeX được bật và phản hồi chứa `$$E=mc^2$$`, khi hiển thị, thì một phương trình được định dạng KaTeX được hiển thị.

---

### Hành vi tự động cuộn

- **Mục đích:** Giữ tầm nhìn của người dùng ở dưới cùng của cuộc trò chuyện trong khi phát trực tuyến; hiện lại điều khiển "cuộn xuống dưới" khi người dùng cuộn lên.

- **Điều kiện tiên quyết / truy cập:** `MessagesView` đã được hiển thị (tức là có ít nhất một tin nhắn hoặc đang được tạo).

- **Thành phần giao diện:**
  - **Khung chứa cuộn** (`MessagesView.tsx` dòng 42–59): `div` với `overflow-y: auto`, `height: 100%`. Được quan sát bởi `debouncedHandleScroll`.
  - **Sentinel `messagesEndRef`** (`MessagesView.tsx` dòng 76): `id="messages-end"`, một div chiều cao 0 ở cuối danh sách tin nhắn được sử dụng làm mục tiêu `IntersectionObserver`.
  - **Nút ScrollToBottom** (`ScrollToBottom.tsx`): biểu tượng `ChevronDown` (16×16 px), `aria-label` → `com_ui_scroll_to_bottom`. Được định vị tuyệt đối ở `bottom-5`, căn `right` trong `md:max-w-3xl xl:max-w-4xl`. Hiển thị/ẩn qua `CSSTransition` (className `scroll-animation`, 300 ms vào / 250 ms ra). Chỉ hiển thị khi cả `showScrollButton` và `scrollButtonPreference` đều true.
  - **Cài đặt `scrollButtonPreference`** (`store.showScrollButton`): tùy chọn người dùng kiểm soát việc nút có được hiển thị hay không.

- **Hành vi chức năng:**
  - FR-1. **Trong khi phát trực tuyến:** `useMessageScrolling` gọi `scrollToBottom()` trên mỗi lần cập nhật `messagesTree` khi `isSubmitting && abortScroll !== true`. Hàm cuộn được **throttle** ở mức 145 ms qua `lodash/throttle` (không phải debounce) bên trong `useScrollToRef.ts`.
  - FR-2. **Người dùng cuộn lên trong khi phát trực tuyến:** Sự kiện wheel trên bất kỳ thành phần `Message` nào (handler `onWheel`, `Message.tsx:17` / `MessageParts.tsx:103`) kích hoạt `handleScroll` trong `useMessageHelpers.tsx:84–99` gọi `setAbortScroll(true)`, dừng tự động cuộn. (Lưu ý: handler `onScroll` của khung chứa cuộn ngoài chỉ tính toán lại `showScrollButton` và không đặt `abortScroll`.) Nút `ScrollToBottom` xuất hiện khi sentinel rời khỏi viewport (ngưỡng IntersectionObserver 0.85, debounce 150 ms).
  - FR-3. **Nhấp ScrollToBottom:** Gọi `handleSmoothToRef` cuộn mượt đến `messagesEndRef` và gọi `setAbortScroll(false)`, kích hoạt lại tự động cuộn.
  - FR-4. **Điều hướng cuộc trò chuyện:** Khi `autoScroll` được bật và `conversationId` thay đổi (không phải `NEW_CONVO`), `scrollToBottom()` được gọi một lần để nhảy đến cuối cuộc trò chuyện đã tải.
  - FR-5. **Tùy chọn nút cuộn:** Nếu `scrollButtonPreference` là false, nút `ScrollToBottom` không bao giờ được hiển thị bất kể vị trí cuộn.

- **Trạng thái & trường hợp đặc biệt:**
  - Phát trực tuyến rất nhanh: nhiều lần gọi `scrollToBottom()` được hợp nhất bởi throttling (145 ms) để tránh giật.
  - Trang khởi đầu: `MessagesView` không được hiển thị; không có logic cuộn nào áp dụng.
  - Cuộc trò chuyện ngắn vừa với màn hình: `messagesEndRef` luôn trong viewport; `showScrollButton` vẫn là false.

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử một phản hồi đang phát trực tuyến, khi người dùng ở dưới cùng của tầm nhìn, thì viewport tự động cuộn để hiển thị token mới khi chúng đến.
  - AC-2. Giả sử một phản hồi đang phát trực tuyến, khi người dùng cuộn lên, thì tự động cuộn dừng và nút cuộn xuống dưới `ChevronDown` xuất hiện.
  - AC-3. Giả sử nút cuộn xuống dưới hiển thị, khi người dùng nhấp nó, thì viewport cuộn mượt đến tin nhắn mới nhất và tự động cuộn tiếp tục.
  - AC-4. Giả sử người dùng điều hướng đến một cuộc trò chuyện hiện có có nhiều tin nhắn, khi trang tải, thì viewport được định vị ở dưới cùng của cuộc trò chuyện.
  - AC-5. Giả sử người dùng đã tắt nút cuộn trong cài đặt, khi họ cuộn lên trong khi phát trực tuyến, thì nút cuộn xuống dưới không xuất hiện.

---

### Tự động đặt tiêu đề cuộc trò chuyện

- **Mục đích:** Tự động gán tiêu đề mô tả cho cuộc trò chuyện mới sau lần trao đổi đầu tiên, để cuộc trò chuyện có thể được nhận diện trong lịch sử thanh bên.

- **Điều kiện tiên quyết / truy cập:** `titleConvo: true` trong cấu hình máy chủ NuFi. Cuộc trò chuyện phải có ít nhất một lần trao đổi hoàn chỉnh. Việc tạo tiêu đề chạy phía máy chủ (route API `/conversation/title`, được gọi qua `dataService.genTitle`).

- **Thành phần giao diện:**
  - **Tiêu đề cuộc trò chuyện trong thanh bên**: được cập nhật tại chỗ ngay khi query tiêu đề giải quyết. Tài liệu (`<title>`) cũng được cập nhật nếu cuộc trò chuyện hiện đang hoạt động (`window.location.pathname.includes(conversationId)`, `queries.ts` dòng 121).
  - **Không có spinner hay trình giữ chỗ hiển thị** trong khu vực tiêu đề trong khi tạo (cập nhật tiêu đề im lặng, chạy nền).

- **Hành vi chức năng:**
  - FR-1. Sau khi phản hồi đầu tiên của cuộc trò chuyện mới hoàn tất, `conversationId` được thêm vào `titleQueue`.
  - FR-2. Khi cuộc trò chuyện "sẵn sàng" (luồng đã kết thúc), `setReadyToFetch` chuyển ID vào batch React Query (`useQueries`, `queries.ts` dòng 95–106), gọi `genTitle` cho mỗi cuộc trò chuyện đang chờ.
  - FR-3. Khi thành công, tiêu đề được ghi vào bộ đệm cuộc trò chuyện (`queryClient.setQueryData`) và được truyền đến tất cả danh sách query qua `updateConvoInAllQueries`. Thanh bên cập nhật mà không cần tải lại toàn bộ.
  - FR-4. Nếu `genTitle` trả về lỗi, cuộc trò chuyện được đánh dấu là đã xử lý và không có lần thử lại nào (`staleTime: Infinity`, `retry: false`). Cuộc trò chuyện giữ tiêu đề mặc định (thường là vài từ đầu tiên của tin nhắn người dùng, hoặc "New Chat"; cần xác minh: logic tiêu đề mặc định nằm phía máy chủ).
  - FR-5. `<title>` tài liệu được cập nhật thành tiêu đề đã tạo chỉ cho cuộc trò chuyện hiện đang hoạt động.

- **Trạng thái & trường hợp đặc biệt:**
  - Tin nhắn đầu tiên rất dài: tiêu đề đã tạo là một tóm tắt phía máy chủ; độ dài được kiểm soát bởi mô hình và bất kỳ system prompt nào. Máy khách nhận một chuỗi thuần túy.
  - Lỗi mạng trong khi tạo tiêu đề: thất bại im lặng; không thử lại; không có lỗi hiển thị với người dùng.
  - Nhiều tab: cập nhật tiêu đề trong một tab không được truyền đến các tab khác (không có phát sóng xuyên tab ở tầng máy khách).
  - Cuộc trò chuyện đã tiếp tục (điều hướng trở lại cuộc trò chuyện hiện có): tiêu đề đã được đặt; không có lần gọi `genTitle` mới nào được thực hiện vì ID không có trong hàng đợi.

- **Tiêu chí chấp nhận:**
  - AC-1. Giả sử một cuộc trò chuyện mới được bắt đầu và phản hồi assistant đầu tiên hoàn tất, khi một lúc trôi qua, thì cuộc trò chuyện trong thanh bên thay đổi từ tiêu đề giữ chỗ sang tiêu đề mô tả được tạo tự động.
  - AC-2. Giả sử tự động đặt tiêu đề giải quyết thành công, khi người dùng đang xem cuộc trò chuyện đó, thì tiêu đề tab trình duyệt cũng cập nhật thành tiêu đề đã tạo.
  - AC-3. Giả sử lần gọi API tiêu đề thất bại (ví dụ: lỗi mạng), thì không có lỗi nào được hiển thị với người dùng và tiêu đề thanh bên vẫn không thay đổi (không thử lại vô hạn).
  - AC-4. Giả sử người dùng điều hướng rời khỏi cuộc trò chuyện trong khi tiêu đề đang được tạo, khi tiêu đề giải quyết, thì chỉ mục thanh bên được cập nhật (tiêu đề tài liệu không được thay đổi cho cuộc trò chuyện không hoạt động).
