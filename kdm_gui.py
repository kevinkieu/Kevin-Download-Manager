"""
KDM - Kevin Download Manager
Desktop UI: Built with CustomTkinter (Modern IDM-Style Interface for Windows)
Supports Settings, System Tray, Resume/Pause, Multi-thread Range Visualization,
Queue & Scheduler, Speed Limiter, Batch Downloader, Clipboard Monitoring, Proxy & Auth
"""

import os
import sys
import time
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
from typing import Dict, Any, Optional, List
from PIL import Image
import pystray

from kdm_engine import KDMEngine, DownloadTask, parse_batch_pattern
from kdm_settings import KDMSettings, DEFAULT_SETTINGS

# Setup Appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


def format_size(bytes_val: int) -> str:
    if not bytes_val or bytes_val <= 0:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PB"


def format_speed(bps: float) -> str:
    if bps <= 0:
        return "0 KB/s"
    if bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    return f"{bps / (1024 * 1024):.2f} MB/s"


def format_eta(remaining_bytes: int, speed: float) -> str:
    if speed <= 0 or remaining_bytes <= 0:
        return "--:--"
    seconds = int(remaining_bytes / speed)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class KDMApp(ctk.CTk):
    def __init__(self, engine: KDMEngine):
        super().__init__()
        self.engine = engine
        self.settings = KDMSettings()

        self.title("KDM - Kevin Download Manager 1.2")
        self.geometry("1160x700")
        self.minsize(960, 580)

        # Set Window Icon
        if getattr(sys, 'frozen', False):
            base_res = sys._MEIPASS
        else:
            base_res = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_res, "kdm_extension", "icons", "icon48.png")
        if os.path.exists(icon_path):
            try:
                img = tk.PhotoImage(file=icon_path)
                self.iconphoto(False, img)
            except Exception:
                pass

        # Settings Cache
        self.default_save_dir = self.settings.get("save_dir")
        self.default_connections = self.settings.get("default_connections", 16)

        # Active filter
        self.current_filter = "ALL"

        # Tasks state
        self.task_rows: Dict[str, Dict[str, Any]] = {}
        self.selected_task_id: Optional[str] = None
        self._notified_completed_tasks = set()

        # Clipboard Monitor state
        self._last_clipboard_text = ""
        self._clipboard_dialog_open = False

        # Callbacks
        self.on_quit_callback = None

        self._build_ui()
        self._setup_system_tray(icon_path)
        self._update_statusbar_indicators()
        self._start_refresh_loop()

        # Intercept window close button [X]
        self.protocol("WM_DELETE_WINDOW", self.on_close_clicked)

    def _setup_system_tray(self, icon_path: str):
        try:
            if os.path.exists(icon_path):
                tray_img = Image.open(icon_path)
            else:
                tray_img = Image.new("RGBA", (48, 48), color=(37, 99, 235))
        except Exception:
            tray_img = Image.new("RGBA", (48, 48), color=(37, 99, 235))

        def on_show(icon, item):
            self.after(0, self.show_window)

        def on_add_url(icon, item):
            self.after(0, lambda: (self.show_window(), self.open_add_dialog()))

        def on_add_video(icon, item):
            self.after(0, lambda: (self.show_window(), self.open_video_dialog()))

        def on_add_batch(icon, item):
            self.after(0, lambda: (self.show_window(), self.open_batch_dialog()))

        def on_resume_all(icon, item):
            self.after(0, self.resume_all_tasks)

        def on_pause_all(icon, item):
            self.after(0, self.pause_all_tasks)

        def on_settings(icon, item):
            self.after(0, lambda: (self.show_window(), self.open_settings_dialog()))

        def on_exit(icon, item):
            self.after(0, self.quit_app)

        menu = pystray.Menu(
            pystray.MenuItem("Mở KDM", on_show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("➕ Thêm URL mới...", on_add_url),
            pystray.MenuItem("🎬 Tải Video YT / TikTok / Phim...", on_add_video),
            pystray.MenuItem("📦 Tải hàng loạt (Batch)...", on_add_batch),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("▶ Tiếp tục tất cả", on_resume_all),
            pystray.MenuItem("⏸ Tạm dừng tất cả", on_pause_all),
            pystray.MenuItem("⚙️ Cài đặt...", on_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Thoát hoàn toàn", on_exit)
        )

        self.tray_icon = pystray.Icon("KDM", tray_img, "KDM - Kevin Download Manager (Đang chạy nền)", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()
        self.attributes('-topmost', True)
        self.after(400, lambda: self.attributes('-topmost', False))

    def on_close_clicked(self):
        close_action = self.settings.get("close_action", "tray")
        if close_action == "tray":
            self.withdraw()
            try:
                self.tray_icon.notify(
                    "KDM vẫn đang chạy nền",
                    "KDM đã được ẩn xuống khay hệ thống (System Tray) để tiếp tục bắt link tải từ trình duyệt."
                )
            except Exception:
                pass
        else:
            self.quit_app()

    def quit_app(self):
        try:
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass

        if self.on_quit_callback:
            try:
                self.on_quit_callback()
            except Exception:
                pass

        self.destroy()
        sys.exit(0)

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # 1. Top Toolbar
        self._build_toolbar()

        # 2. Left Sidebar (Categories)
        self._build_sidebar()

        # 3. Main Download Area (Table)
        self._build_main_table()

        # 4. Bottom Statusbar
        self._build_statusbar()

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, height=54, corner_radius=0, fg_color="#181d24")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")

        # Add URL Button
        btn_add = ctk.CTkButton(toolbar, text="➕ Thêm URL", width=105, height=36,
                                fg_color="#2563eb", hover_color="#1d4ed8", font=("Segoe UI", 12, "bold"),
                                command=self.open_add_dialog)
        btn_add.pack(side="left", padx=(10, 4), pady=8)

        # Add Video Button
        btn_video = ctk.CTkButton(toolbar, text="🎬 Tải Phim / YT", width=145, height=36,
                                  fg_color="#dc2626", hover_color="#b91c1c", font=("Segoe UI", 12, "bold"),
                                  command=self.open_video_dialog)
        btn_video.pack(side="left", padx=4, pady=8)

        # Batch Download Button
        btn_batch = ctk.CTkButton(toolbar, text="📦 Tải hàng loạt", width=125, height=36,
                                  fg_color="#7c3aed", hover_color="#6d28d9", font=("Segoe UI", 12, "bold"),
                                  command=self.open_batch_dialog)
        btn_batch.pack(side="left", padx=4, pady=8)

        # Resume Button
        btn_resume = ctk.CTkButton(toolbar, text="▶ Tiếp tục", width=85, height=36,
                                   fg_color="#059669", hover_color="#047857", font=("Segoe UI", 12),
                                   command=self.resume_selected)
        btn_resume.pack(side="left", padx=4, pady=8)

        # Pause Button
        btn_pause = ctk.CTkButton(toolbar, text="⏸ Tạm dừng", width=85, height=36,
                                  fg_color="#d97706", hover_color="#b45309", font=("Segoe UI", 12),
                                  command=self.pause_selected)
        btn_pause.pack(side="left", padx=4, pady=8)

        # Stop/Delete Button
        btn_delete = ctk.CTkButton(toolbar, text="🗑️ Xóa", width=70, height=36,
                                   fg_color="#4b5563", hover_color="#374151", font=("Segoe UI", 12),
                                   command=self.delete_selected)
        btn_delete.pack(side="left", padx=4, pady=8)

        # Open File Button
        btn_open = ctk.CTkButton(toolbar, text="▶ Mở tệp", width=85, height=36,
                                 fg_color="#0284c7", hover_color="#0369a1", font=("Segoe UI", 12, "bold"),
                                 command=self.open_selected_file)
        btn_open.pack(side="left", padx=4, pady=8)

        # Open Folder Button
        btn_folder = ctk.CTkButton(toolbar, text="📁 Mở thư mục", width=105, height=36,
                                   fg_color="#374151", hover_color="#1f2937", font=("Segoe UI", 12),
                                   command=self.open_download_folder)
        btn_folder.pack(side="left", padx=4, pady=8)

        # Settings Button
        btn_settings = ctk.CTkButton(toolbar, text="⚙️ Cài đặt", width=85, height=36,
                                     fg_color="#1e293b", hover_color="#334155", font=("Segoe UI", 12, "bold"),
                                     border_width=1, border_color="#475569",
                                     command=self.open_settings_dialog)
        btn_settings.pack(side="left", padx=4, pady=8)

        # Extension Guide Button
        btn_ext = ctk.CTkButton(toolbar, text="🧩 Extension", width=115, height=36,
                                fg_color="#6366f1", hover_color="#4f46e5", font=("Segoe UI", 12, "bold"),
                                command=self.show_extension_guide)
        btn_ext.pack(side="right", padx=10, pady=8)

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#12161c")
        sidebar.grid(row=1, column=0, sticky="nsw")
        sidebar.grid_propagate(False)

        lbl_cat = ctk.CTkLabel(sidebar, text="DANH MỤC", font=("Segoe UI", 12, "bold"), text_color="#9ca3af")
        lbl_cat.pack(anchor="w", padx=16, pady=(16, 8))

        categories = [
            ("📁 Tất cả lượt tải", "ALL"),
            ("⚡ Đang tải", "DOWNLOADING"),
            ("⏳ Đang chờ hàng đợi", "QUEUED"),
            ("✓ Đã hoàn thành", "COMPLETED"),
            ("🎬 Video / Phim", "VIDEO"),
            ("📦 Tệp nén (ZIP/RAR)", "COMPRESSED"),
            ("⚙️ Ứng dụng (EXE/MSI)", "PROGRAMS"),
            ("📄 Tài liệu (PDF/DOC)", "DOCUMENTS")
        ]

        self.cat_buttons = {}
        for label, cat_key in categories:
            btn = ctk.CTkButton(
                sidebar, text=label, anchor="w", height=34,
                fg_color="#1f2937" if cat_key == "ALL" else "transparent",
                hover_color="#1f2937", font=("Segoe UI", 12),
                command=lambda k=cat_key: self.set_filter(k)
            )
            btn.pack(fill="x", padx=10, pady=2)
            self.cat_buttons[cat_key] = btn

    def _build_main_table(self):
        main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#0d1117")
        main_frame.grid(row=1, column=1, sticky="nsew")
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        self.scroll_frame = ctk.CTkScrollableFrame(main_frame, fg_color="#0d1117")
        self.scroll_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        self.empty_label = ctk.CTkLabel(
            self.scroll_frame,
            text="Chưa có lượt tải nào.\nBấm '+ Thêm URL' hoặc mở phim trên Cốc Cốc / Chrome để KDM tự bắt link!",
            font=("Segoe UI", 14), text_color="#6b7280", justify="center"
        )
        self.empty_label.pack(pady=80)

    def _build_statusbar(self):
        statusbar = ctk.CTkFrame(self, height=32, corner_radius=0, fg_color="#181d24")
        statusbar.grid(row=2, column=0, columnspan=2, sticky="ew")

        # Server status
        self.lbl_server_status = ctk.CTkLabel(statusbar, text="🟢 KDM Sẵn sàng (59123)",
                                              font=("Segoe UI", 11), text_color="#10b981")
        self.lbl_server_status.pack(side="left", padx=(12, 8))

        # Queue Status
        self.lbl_queue_status = ctk.CTkLabel(statusbar, text="📋 Hàng đợi: 2 cùng lúc",
                                             font=("Segoe UI", 11), text_color="#9ca3af")
        self.lbl_queue_status.pack(side="left", padx=8)

        # Quick Speed Limit Toggle Button
        self.btn_speed_status = ctk.CTkButton(
            statusbar, text="⚡ Giới hạn: TẮT", width=120, height=22,
            fg_color="#1f2937", hover_color="#374151", font=("Segoe UI", 10, "bold"),
            text_color="#f59e0b", border_width=1, border_color="#475569",
            command=self.quick_toggle_speed_limit
        )
        self.btn_speed_status.pack(side="left", padx=8)

        # Scheduler Status
        self.lbl_sched_status = ctk.CTkLabel(statusbar, text="⏰ Hẹn giờ: TẮT",
                                             font=("Segoe UI", 11), text_color="#9ca3af")
        self.lbl_sched_status.pack(side="left", padx=8)

        # Auto Shutdown Status
        self.lbl_shutdown_status = ctk.CTkLabel(statusbar, text="🔌 Tắt máy: TẮT",
                                                font=("Segoe UI", 11), text_color="#9ca3af")
        self.lbl_shutdown_status.pack(side="left", padx=8)

        # Total Speed
        self.lbl_total_speed = ctk.CTkLabel(statusbar, text="Tổng tốc độ: 0.0 MB/s",
                                            font=("Segoe UI", 11, "bold"), text_color="#38bdf8")
        self.lbl_total_speed.pack(side="right", padx=14)

    def _update_statusbar_indicators(self):
        """Update indicators in bottom statusbar based on settings & engine state"""
        # 1. Queue Concurrency
        max_q = self.settings.get("max_active_tasks", 2)
        self.lbl_queue_status.configure(text=f"📋 Hàng đợi: {max_q} cùng lúc")

        # 2. Speed Limit
        sp_on = self.settings.get("speed_limit_enabled", False)
        sp_kb = self.settings.get("speed_limit_kbps", 2048)
        if sp_on:
            sp_mb = sp_kb / 1024.0
            sp_str = f"{sp_mb:.1f} MB/s" if sp_mb >= 1.0 else f"{sp_kb} KB/s"
            self.btn_speed_status.configure(text=f"⚡ Giới hạn: {sp_str}", text_color="#10b981", border_color="#10b981")
        else:
            self.btn_speed_status.configure(text="⚡ Giới hạn: TẮT", text_color="#9ca3af", border_color="#475569")

        # 3. Scheduler
        sc_on = self.settings.get("scheduler_enabled", False)
        if sc_on:
            sc_start = self.settings.get("schedule_start_time", "02:00")
            sc_stop = self.settings.get("schedule_stop_time", "06:00")
            self.lbl_sched_status.configure(text=f"⏰ Hẹn giờ: {sc_start}-{sc_stop}", text_color="#38bdf8")
        else:
            self.lbl_sched_status.configure(text="⏰ Hẹn giờ: TẮT", text_color="#9ca3af")

        # 4. Auto Shutdown
        sd_on = self.settings.get("shutdown_when_done", False)
        if sd_on:
            self.lbl_shutdown_status.configure(text="🔌 Tắt máy: BẬT", text_color="#ef4444")
        else:
            self.lbl_shutdown_status.configure(text="🔌 Tắt máy: TẮT", text_color="#9ca3af")

    def quick_toggle_speed_limit(self):
        """Toggle speed limit on/off instantly from statusbar button"""
        current = self.settings.get("speed_limit_enabled", False)
        new_val = not current
        self.settings.set("speed_limit_enabled", new_val)
        kbps = self.settings.get("speed_limit_kbps", 2048)
        self.engine.set_speed_limit(new_val, kbps)
        self._update_statusbar_indicators()

    def set_filter(self, cat_key: str):
        self.current_filter = cat_key
        for k, btn in self.cat_buttons.items():
            btn.configure(fg_color="#1f2937" if k == cat_key else "transparent")
        self._refresh_table()

    # ==========================================
    # SETTINGS DIALOG (CÀI ĐẶT NHIỀU TAB)
    # ==========================================
    def open_settings_dialog(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Cài đặt hệ thống - KDM")
        dlg.geometry("640x590")
        dlg.minsize(600, 550)
        dlg.transient(self)
        dlg.grab_set()

        # Header
        ctk.CTkLabel(dlg, text="⚙️ CÀI ĐẶT KDM (Kevin Download Manager)",
                     font=("Segoe UI", 16, "bold"), text_color="#38bdf8").pack(anchor="w", padx=24, pady=(16, 8))

        tabview = ctk.CTkTabview(dlg, height=440)
        tabview.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        tab_gen = tabview.add("📁 Chung & Hàng đợi")
        tab_exts = tabview.add("📄 Loại tệp (File Types)")
        tab_sched = tabview.add("⚡ Tốc độ & Lập lịch")
        tab_proxy = tabview.add("🌐 Proxy & Xác thực")

        # -----------------------------
        # TAB 1: CHUNG & HÀNG ĐỢI
        # -----------------------------
        ctk.CTkLabel(tab_gen, text="Thư mục tải về mặc định:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        path_box = ctk.CTkFrame(tab_gen, fg_color="transparent")
        path_box.pack(fill="x", padx=10, pady=(0, 8))
        ent_save = ctk.CTkEntry(path_box, width=380)
        ent_save.insert(0, self.settings.get("save_dir"))
        ent_save.pack(side="left", fill="x", expand=True)

        def browse_save():
            d = filedialog.askdirectory(initialdir=ent_save.get())
            if d:
                ent_save.delete(0, "end")
                ent_save.insert(0, d)

        ctk.CTkButton(path_box, text="Duyệt...", width=75, command=browse_save).pack(side="right", padx=(8, 0))

        chk_sub = ctk.CTkCheckBox(tab_gen, text="Tự động phân loại thư mục con (Videos, Compressed, Programs, Documents)")
        if self.settings.get("auto_subfolders", True):
            chk_sub.select()
        else:
            chk_sub.deselect()
        chk_sub.pack(anchor="w", padx=10, pady=4)

        # Concurrency & connections
        c_row = ctk.CTkFrame(tab_gen, fg_color="transparent")
        c_row.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(c_row, text="Số tệp tải cùng lúc (Max Active Tasks):", font=("Segoe UI", 12)).pack(side="left")
        cbo_active = ctk.CTkComboBox(c_row, values=["1", "2", "3", "4", "5", "8", "10"], width=90)
        cbo_active.set(str(self.settings.get("max_active_tasks", 2)))
        cbo_active.pack(side="right")

        conn_row = ctk.CTkFrame(tab_gen, fg_color="transparent")
        conn_row.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(conn_row, text="Số luồng tăng tốc mặc định (Connections):", font=("Segoe UI", 12)).pack(side="left")
        cbo_conn = ctk.CTkComboBox(conn_row, values=["1", "4", "8", "16", "32"], width=90)
        cbo_conn.set(str(self.settings.get("default_connections", 16)))
        cbo_conn.pack(side="right")

        # Close Action
        ctk.CTkLabel(tab_gen, text="Khi bấm vào nút Đóng [X] góc phải:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        cbo_close = ctk.CTkComboBox(tab_gen, values=[
            "Ẩn xuống khay hệ thống (System Tray) - Khuyên dùng",
            "Thoát phần mềm hoàn toàn"
        ], width=480)
        current_close = self.settings.get("close_action", "tray")
        cbo_close.set("Ẩn xuống khay hệ thống (System Tray) - Khuyên dùng" if current_close == "tray" else "Thoát phần mềm hoàn toàn")
        cbo_close.pack(anchor="w", padx=10, pady=(0, 8))

        chk_startup = ctk.CTkCheckBox(tab_gen, text="Khởi động KDM cùng Windows (tự động chạy nền khi mở máy)")
        if self.settings.is_startup_enabled():
            chk_startup.select()
        else:
            chk_startup.deselect()
        chk_startup.pack(anchor="w", padx=10, pady=4)

        chk_sound = ctk.CTkCheckBox(tab_gen, text="Phát âm thanh thông báo khi tải xong tệp")
        if self.settings.get("play_sound", True):
            chk_sound.select()
        else:
            chk_sound.deselect()
        chk_sound.pack(anchor="w", padx=10, pady=4)

        chk_clip = ctk.CTkCheckBox(tab_gen, text="Tự động bắt link tải khi copy liên kết vào Clipboard (Ctrl+C)")
        if self.settings.get("clipboard_monitor", True):
            chk_clip.select()
        else:
            chk_clip.deselect()
        chk_clip.pack(anchor="w", padx=10, pady=4)

        # -----------------------------
        # TAB 2: CÁC LOẠI TỆP (FILE TYPES - CHUẨN IDM)
        # -----------------------------
        box_types = ctk.CTkFrame(tab_exts, fg_color="#161b22", corner_radius=6)
        box_types.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(box_types, text="📄 TỰ ĐỘNG BẮT ĐẦU TẢI VỀ CÁC LOẠI TẬP TIN CÓ ĐUÔI MỞ RỘNG SAU:",
                     font=("Segoe UI", 12, "bold"), text_color="#38bdf8").pack(anchor="w", padx=14, pady=(12, 4))

        guide_types = (
            "Nhập các phần mở rộng (đuôi tệp) cách nhau bởi khoảng trắng (Space).\n"
            "Khi trình duyệt bấm tải bất kỳ file nào có đuôi trong danh sách này, KDM sẽ tự động bắt link tải ngay!"
        )
        ctk.CTkLabel(box_types, text=guide_types, font=("Segoe UI", 11), text_color="#9ca3af", justify="left").pack(anchor="w", padx=14, pady=(0, 8))

        txt_exts = ctk.CTkTextbox(box_types, height=180, font=("Consolas", 12))
        txt_exts.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        txt_exts.insert("1.0", self.settings.get("intercept_extensions", DEFAULT_SETTINGS.get("intercept_extensions", "")))

        def reset_default_extensions():
            default_str = DEFAULT_SETTINGS.get("intercept_extensions", "")
            txt_exts.delete("1.0", "end")
            txt_exts.insert("1.0", default_str)

        btn_ext_row = ctk.CTkFrame(box_types, fg_color="transparent")
        btn_ext_row.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(btn_ext_row, text="↺ Khôi phục danh sách mặc định (Reset IDM)", width=240,
                      fg_color="#374151", hover_color="#4b5563", font=("Segoe UI", 11),
                      command=reset_default_extensions).pack(side="left")

        ctk.CTkLabel(btn_ext_row, text="💡 Gợi ý: Có thể thêm TORRENT, IPA, CRX, CSV... tùy ý",
                     font=("Segoe UI", 11), text_color="#10b981").pack(side="right")

        # -----------------------------
        # TAB 3: TỐC ĐỘ & LẬP LỊCH
        # -----------------------------
        # Speed Limiter Box
        box_speed = ctk.CTkFrame(tab_sched, fg_color="#161b22", corner_radius=6)
        box_speed.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(box_speed, text="⚡ GIỚI HẠN TỐC ĐỘ TẢI (SPEED LIMITER)", font=("Segoe UI", 12, "bold"), text_color="#38bdf8").pack(anchor="w", padx=14, pady=(10, 4))
        chk_speed = ctk.CTkCheckBox(box_speed, text="Bật giới hạn tốc độ tải toàn cục")
        if self.settings.get("speed_limit_enabled", False):
            chk_speed.select()
        else:
            chk_speed.deselect()
        chk_speed.pack(anchor="w", padx=14, pady=4)

        sp_row = ctk.CTkFrame(box_speed, fg_color="transparent")
        sp_row.pack(fill="x", padx=14, pady=(4, 12))
        ctk.CTkLabel(sp_row, text="Tốc độ tối đa cho phép (KB/s):", font=("Segoe UI", 12)).pack(side="left")
        ent_speed = ctk.CTkEntry(sp_row, width=120)
        ent_speed.insert(0, str(self.settings.get("speed_limit_kbps", 2048)))
        ent_speed.pack(side="right")

        # Scheduler Box
        box_sched = ctk.CTkFrame(tab_sched, fg_color="#161b22", corner_radius=6)
        box_sched.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(box_sched, text="⏰ LẬP LỊCH TẢI VỀ THEO GIỜ (SCHEDULER)", font=("Segoe UI", 12, "bold"), text_color="#38bdf8").pack(anchor="w", padx=14, pady=(10, 4))
        chk_sched = ctk.CTkCheckBox(box_sched, text="Bật hẹn giờ tự động tải trong khoảng thời gian nhất định")
        if self.settings.get("scheduler_enabled", False):
            chk_sched.select()
        else:
            chk_sched.deselect()
        chk_sched.pack(anchor="w", padx=14, pady=4)

        time_row = ctk.CTkFrame(box_sched, fg_color="transparent")
        time_row.pack(fill="x", padx=14, pady=(4, 12))
        ctk.CTkLabel(time_row, text="Bắt đầu lúc (HH:MM):", font=("Segoe UI", 11)).pack(side="left")
        ent_start_time = ctk.CTkEntry(time_row, width=80)
        ent_start_time.insert(0, self.settings.get("schedule_start_time", "02:00"))
        ent_start_time.pack(side="left", padx=(6, 16))

        ctk.CTkLabel(time_row, text="Tạm dừng lúc (HH:MM):", font=("Segoe UI", 11)).pack(side="left")
        ent_stop_time = ctk.CTkEntry(time_row, width=80)
        ent_stop_time.insert(0, self.settings.get("schedule_stop_time", "06:00"))
        ent_stop_time.pack(side="left", padx=6)

        # Auto Shutdown Box
        box_sd = ctk.CTkFrame(tab_sched, fg_color="#161b22", corner_radius=6)
        box_sd.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(box_sd, text="🔌 TỰ ĐỘNG TẮT MÁY (AUTO SHUTDOWN)", font=("Segoe UI", 12, "bold"), text_color="#ef4444").pack(anchor="w", padx=14, pady=(10, 4))
        chk_shutdown = ctk.CTkCheckBox(box_sd, text="Tự động tắt máy tính khi toàn bộ danh sách tải đã hoàn thành (Sau 60s đếm ngược)")
        if self.settings.get("shutdown_when_done", False):
            chk_shutdown.select()
        else:
            chk_shutdown.deselect()
        chk_shutdown.pack(anchor="w", padx=14, pady=(4, 12))

        # -----------------------------
        # TAB 3: PROXY & XÁC THỰC
        # -----------------------------
        box_proxy = ctk.CTkFrame(tab_proxy, fg_color="#161b22", corner_radius=6)
        box_proxy.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(box_proxy, text="🌐 CẤU HÌNH PROXY (HTTP / HTTPS / SOCKS)", font=("Segoe UI", 12, "bold"), text_color="#38bdf8").pack(anchor="w", padx=14, pady=(10, 4))
        chk_proxy = ctk.CTkCheckBox(box_proxy, text="Sử dụng Máy chủ Proxy khi tải về")
        if self.settings.get("proxy_enabled", False):
            chk_proxy.select()
        else:
            chk_proxy.deselect()
        chk_proxy.pack(anchor="w", padx=14, pady=4)

        pr_row1 = ctk.CTkFrame(box_proxy, fg_color="transparent")
        pr_row1.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(pr_row1, text="Proxy Host:", width=90, anchor="w").pack(side="left")
        ent_proxy_host = ctk.CTkEntry(pr_row1, placeholder_text="127.0.0.1 hoặc proxy.domain.com")
        ent_proxy_host.insert(0, self.settings.get("proxy_host", ""))
        ent_proxy_host.pack(side="left", fill="x", expand=True, padx=(4, 10))

        ctk.CTkLabel(pr_row1, text="Port:").pack(side="left")
        ent_proxy_port = ctk.CTkEntry(pr_row1, width=70)
        ent_proxy_port.insert(0, str(self.settings.get("proxy_port", 8080)))
        ent_proxy_port.pack(side="left", padx=(4, 0))

        pr_row2 = ctk.CTkFrame(box_proxy, fg_color="transparent")
        pr_row2.pack(fill="x", padx=14, pady=(4, 12))
        ctk.CTkLabel(pr_row2, text="Proxy User:", width=90, anchor="w").pack(side="left")
        ent_proxy_user = ctk.CTkEntry(pr_row2)
        ent_proxy_user.insert(0, self.settings.get("proxy_user", ""))
        ent_proxy_user.pack(side="left", fill="x", expand=True, padx=(4, 10))

        ctk.CTkLabel(pr_row2, text="Password:").pack(side="left")
        ent_proxy_pass = ctk.CTkEntry(pr_row2, show="*")
        ent_proxy_pass.insert(0, self.settings.get("proxy_pass", ""))
        ent_proxy_pass.pack(side="left", fill="x", expand=True, padx=(4, 0))

        box_auth = ctk.CTkFrame(tab_proxy, fg_color="#161b22", corner_radius=6)
        box_auth.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(box_auth, text="🔒 XÁC THỰC WEB (HTTP BASIC AUTH)", font=("Segoe UI", 12, "bold"), text_color="#38bdf8").pack(anchor="w", padx=14, pady=(10, 4))
        ctk.CTkLabel(box_auth, text="Dành cho các website lưu trữ yêu cầu tài khoản đăng nhập để tải:", font=("Segoe UI", 11), text_color="#9ca3af").pack(anchor="w", padx=14, pady=2)

        auth_row = ctk.CTkFrame(box_auth, fg_color="transparent")
        auth_row.pack(fill="x", padx=14, pady=(6, 12))
        ctk.CTkLabel(auth_row, text="Username:", width=80, anchor="w").pack(side="left")
        ent_auth_user = ctk.CTkEntry(auth_row)
        ent_auth_user.insert(0, self.settings.get("auth_user", ""))
        ent_auth_user.pack(side="left", fill="x", expand=True, padx=(4, 10))

        ctk.CTkLabel(auth_row, text="Password:").pack(side="left")
        ent_auth_pass = ctk.CTkEntry(auth_row, show="*")
        ent_auth_pass.insert(0, self.settings.get("auth_pass", ""))
        ent_auth_pass.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Bottom Action Buttons
        def save_settings():
            new_dir = ent_save.get().strip()
            if new_dir:
                self.settings.set("save_dir", new_dir)
                self.default_save_dir = new_dir

            self.settings.set("auto_subfolders", bool(chk_sub.get()))

            # Max active tasks
            max_act = int(cbo_active.get())
            self.settings.set("max_active_tasks", max_act)
            self.engine.max_active_tasks = max_act

            # Connections
            conn_val = int(cbo_conn.get())
            self.settings.set("default_connections", conn_val)
            self.default_connections = conn_val

            # Close Action
            is_tray = "khay hệ thống" in cbo_close.get().lower()
            self.settings.set("close_action", "tray" if is_tray else "exit")

            # Startup
            startup_val = bool(chk_startup.get())
            self.settings.set("start_with_windows", startup_val)
            self.settings.apply_startup(startup_val)

            # Sound & Clipboard
            self.settings.set("play_sound", bool(chk_sound.get()))
            self.settings.set("clipboard_monitor", bool(chk_clip.get()))

            # Speed limiter
            sp_en = bool(chk_speed.get())
            try:
                sp_kb = max(64, int(ent_speed.get().strip()))
            except ValueError:
                sp_kb = 2048
            self.settings.set("speed_limit_enabled", sp_en)
            self.settings.set("speed_limit_kbps", sp_kb)
            self.engine.set_speed_limit(sp_en, sp_kb)

            # Scheduler
            sc_en = bool(chk_sched.get())
            self.settings.set("scheduler_enabled", sc_en)
            self.settings.set("schedule_start_time", ent_start_time.get().strip())
            self.settings.set("schedule_stop_time", ent_stop_time.get().strip())
            self.engine.scheduler_enabled = sc_en
            self.engine.schedule_start_time = ent_start_time.get().strip()
            self.engine.schedule_stop_time = ent_stop_time.get().strip()

            # Shutdown
            sd_en = bool(chk_shutdown.get())
            self.settings.set("shutdown_when_done", sd_en)
            self.engine.shutdown_when_done = sd_en

            # Proxy
            pr_en = bool(chk_proxy.get())
            pr_host = ent_proxy_host.get().strip()
            try:
                pr_port = int(ent_proxy_port.get().strip())
            except ValueError:
                pr_port = 8080
            pr_user = ent_proxy_user.get().strip()
            pr_pass = ent_proxy_pass.get().strip()

            self.settings.set("proxy_enabled", pr_en)
            self.settings.set("proxy_host", pr_host)
            self.settings.set("proxy_port", pr_port)
            self.settings.set("proxy_user", pr_user)
            self.settings.set("proxy_pass", pr_pass)
            self.engine.configure_proxy(pr_en, pr_host, pr_port, pr_user, pr_pass)

            # Auth
            au_user = ent_auth_user.get().strip()
            au_pass = ent_auth_pass.get().strip()
            self.settings.set("auth_user", au_user)
            self.settings.set("auth_pass", au_pass)
            self.engine.configure_auth(au_user, au_pass)

            # File Types (Extensions - Chuẩn IDM)
            exts_val = txt_exts.get("1.0", "end").strip()
            if exts_val:
                self.settings.set("intercept_extensions", exts_val)

            # Process queue and refresh statusbar
            self.engine.process_queue()
            self._update_statusbar_indicators()

            messagebox.showinfo("Thành công", "Đã lưu toàn bộ cài đặt KDM thành công!", parent=dlg)
            dlg.destroy()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(btn_row, text="💾 Lưu Cài Đặt", fg_color="#2563eb", hover_color="#1d4ed8",
                      font=("Segoe UI", 12, "bold"), width=120, command=save_settings).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_row, text="Hủy", fg_color="#374151", width=80, command=dlg.destroy).pack(side="right")

    # ==========================================
    # BATCH DOWNLOAD DIALOG (TẢI HÀNG LOẠT)
    # ==========================================
    def open_batch_dialog(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Tải hàng loạt (Batch Download) - KDM")
        dlg.geometry("640x560")
        dlg.minsize(580, 500)
        dlg.transient(self)
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="📦 TẢI HÀNG LOẠT BẰNG DẢI MẪU (BATCH DOWNLOAD)",
                     font=("Segoe UI", 15, "bold"), text_color="#38bdf8").pack(anchor="w", padx=20, pady=(16, 4))

        guide = (
            "Nhập mẫu liên kết chứa dải số [start-end] để tạo danh sách tải tự động.\n"
            "Ví dụ:\n"
            "  • https://example.com/files/document_[01-20].pdf\n"
            "  • https://mysite.com/videos/episode_[1-12].mp4\n"
            "  • https://archive.org/data/archive_part[001-050].zip"
        )
        ctk.CTkLabel(dlg, text=guide, font=("Segoe UI", 11), text_color="#9ca3af", justify="left").pack(anchor="w", padx=20, pady=(0, 8))

        # Pattern Entry
        ctk.CTkLabel(dlg, text="Mẫu liên kết (URL Pattern):", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(6, 2))
        ent_pattern = ctk.CTkEntry(dlg, width=600, placeholder_text="https://example.com/files/part_[01-10].zip")
        ent_pattern.pack(fill="x", padx=20, pady=(0, 6))

        # Preview list & button
        preview_header = ctk.CTkFrame(dlg, fg_color="transparent")
        preview_header.pack(fill="x", padx=20, pady=(4, 2))
        lbl_preview_title = ctk.CTkLabel(preview_header, text="Xem trước danh sách (Preview):", font=("Segoe UI", 12, "bold"))
        lbl_preview_title.pack(side="left")

        txt_preview = ctk.CTkTextbox(dlg, height=130, font=("Consolas", 11))
        txt_preview.pack(fill="x", padx=20, pady=(0, 8))

        def update_preview():
            pat = ent_pattern.get().strip()
            if not pat:
                txt_preview.delete("1.0", "end")
                txt_preview.insert("1.0", "Vui lòng nhập mẫu liên kết trước.")
                return []
            urls = parse_batch_pattern(pat)
            txt_preview.delete("1.0", "end")
            preview_content = f"Tổng số liên kết sẽ tạo: {len(urls)} tệp\n" + "-" * 50 + "\n"
            preview_content += "\n".join(urls[:25])
            if len(urls) > 25:
                preview_content += f"\n... và {len(urls) - 25} tệp tiếp theo."
            txt_preview.insert("1.0", preview_content)
            return urls

        btn_preview = ctk.CTkButton(preview_header, text="🔍 Kiểm tra & Xem trước", width=160,
                                    fg_color="#4f46e5", hover_color="#4338ca", font=("Segoe UI", 11),
                                    command=update_preview)
        btn_preview.pack(side="right")

        # Save Directory
        ctk.CTkLabel(dlg, text="Lưu tại thư mục:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(6, 2))
        path_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        path_frame.pack(fill="x", padx=20, pady=(0, 8))
        ent_path = ctk.CTkEntry(path_frame, width=480)
        ent_path.insert(0, self.settings.get("save_dir"))
        ent_path.pack(side="left", fill="x", expand=True)

        def browse():
            d = filedialog.askdirectory(initialdir=ent_path.get())
            if d:
                ent_path.delete(0, "end")
                ent_path.insert(0, d)

        ctk.CTkButton(path_frame, text="Duyệt...", width=75, command=browse).pack(side="right", padx=(8, 0))

        # Connections & Mode
        opt_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        opt_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(opt_frame, text="Số luồng tải mỗi tệp:", font=("Segoe UI", 12)).pack(side="left")
        cbo_conn = ctk.CTkComboBox(opt_frame, values=["1", "4", "8", "16"], width=80)
        cbo_conn.set(str(self.default_connections))
        cbo_conn.pack(side="left", padx=(8, 20))

        chk_start_now = ctk.CTkCheckBox(opt_frame, text="Bắt đầu tải ngay (theo giới hạn hàng đợi)")
        chk_start_now.select()
        chk_start_now.pack(side="left")

        def start_batch():
            pat = ent_pattern.get().strip()
            if not pat:
                messagebox.showerror("Lỗi", "Vui lòng nhập mẫu liên kết!", parent=dlg)
                return
            urls = parse_batch_pattern(pat)
            if not urls:
                messagebox.showerror("Lỗi", "Không tạo được liên kết nào từ mẫu!", parent=dlg)
                return

            save_dir = ent_path.get().strip()
            os.makedirs(save_dir, exist_ok=True)
            conn = int(cbo_conn.get())
            start_now = bool(chk_start_now.get())

            added_count = 0
            for u in urls:
                is_video = u.lower().endswith((".mp4", ".mkv", ".webm", ".m3u8"))
                if is_video:
                    task = self.engine.create_video_task(u, save_dir)
                else:
                    task = self.engine.create_http_task(u, save_dir, connections=conn)

                if start_now:
                    self.engine.queue_or_start_task(task.task_id)
                else:
                    task.status = "Queued"
                added_count += 1

            self._refresh_table()
            messagebox.showinfo("Thành công", f"Đã thêm {added_count} tệp vào hàng đợi tải KDM!", parent=dlg)
            dlg.destroy()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(16, 16))
        ctk.CTkButton(btn_row, text="🚀 Thêm vào hàng đợi tải (Batch Queue)", fg_color="#7c3aed",
                      hover_color="#6d28d9", font=("Segoe UI", 12, "bold"), command=start_batch).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_row, text="Hủy", fg_color="#374151", width=80, command=dlg.destroy).pack(side="right")

    # ==========================================
    # ADD NEW DOWNLOAD DIALOG
    # ==========================================
    def open_add_dialog(self, initial_url: str = ""):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Thêm lượt tải mới - KDM")
        dlg.geometry("540x360")
        dlg.transient(self)
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="Địa chỉ tải về (URL):", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(16, 4))
        ent_url = ctk.CTkEntry(dlg, width=500, placeholder_text="https://...")
        ent_url.pack(padx=20, pady=4)
        if initial_url:
            ent_url.insert(0, initial_url)

        ctk.CTkLabel(dlg, text="Lưu tại thư mục:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(12, 4))
        path_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        path_frame.pack(fill="x", padx=20)
        ent_path = ctk.CTkEntry(path_frame, width=400)
        ent_path.insert(0, self.settings.get("save_dir"))
        ent_path.pack(side="left", fill="x", expand=True)

        def browse():
            d = filedialog.askdirectory(initialdir=ent_path.get())
            if d:
                ent_path.delete(0, "end")
                ent_path.insert(0, d)

        ctk.CTkButton(path_frame, text="Duyệt...", width=80, command=browse).pack(side="right", padx=(8, 0))

        # Connections selection
        conn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        conn_frame.pack(fill="x", padx=20, pady=16)
        ctk.CTkLabel(conn_frame, text="Số luồng tăng tốc (Connections):", font=("Segoe UI", 12)).pack(side="left")
        cbo_conn = ctk.CTkComboBox(conn_frame, values=["1", "4", "8", "16", "32"], width=90)
        cbo_conn.set(str(self.default_connections))
        cbo_conn.pack(side="right")

        def start_download():
            url = ent_url.get().strip()
            save_dir = ent_path.get().strip()
            conn = int(cbo_conn.get())
            if not url:
                messagebox.showerror("Lỗi", "Vui lòng nhập URL!", parent=dlg)
                return
            dlg.destroy()
            task = self.engine.create_http_task(url, save_dir, connections=conn)
            self.engine.queue_or_start_task(task.task_id)
            self._refresh_table()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(10, 0))
        ctk.CTkButton(btn_row, text="🚀 Tải ngay", fg_color="#2563eb", hover_color="#1d4ed8",
                      font=("Segoe UI", 12, "bold"), command=start_download).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_row, text="Hủy", fg_color="#374151", command=dlg.destroy).pack(side="right")

    # ==========================================
    # VIDEO (YOUTUBE / TIKTOK / PHIM) DIALOG
    # ==========================================
    def open_video_dialog(self, initial_url: str = ""):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Tải Phim / Video YouTube / TikTok / Facebook - KDM")
        dlg.geometry("580x440")
        dlg.transient(self)
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="Dán link Video / Phim / HLS .m3u8:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(16, 4))
        ent_url = ctk.CTkEntry(dlg, width=540, placeholder_text="https://...")
        ent_url.pack(padx=20, pady=4)
        if initial_url:
            ent_url.insert(0, initial_url)

        ctk.CTkLabel(dlg, text="Tên tệp muốn lưu (Ví dụ: The Pitt Tap 11.mp4):", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(10, 4))
        ent_title = ctk.CTkEntry(dlg, width=540, placeholder_text="Để trống nếu muốn tự động lấy tên từ web")
        ent_title.pack(padx=20, pady=4)

        ctk.CTkLabel(dlg, text="Tùy chọn chất lượng tải:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(10, 4))
        cbo_format = ctk.CTkComboBox(dlg, values=[
            "🎬 Video chất lượng cao nhất (Best Video + Audio)",
            "📺 Full HD 1080p",
            "⚡ HD 720p",
            "🎵 Tách riêng âm thanh (MP3 / Audio HQ)"
        ], width=540)
        cbo_format.pack(padx=20, pady=4)

        # Save location
        ctk.CTkLabel(dlg, text="Lưu tại:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(10, 4))
        path_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        path_frame.pack(fill="x", padx=20)
        ent_path = ctk.CTkEntry(path_frame, width=420)
        default_video_dir = os.path.join(self.default_save_dir, "Videos") if self.settings.get("auto_subfolders", True) else self.default_save_dir
        ent_path.insert(0, default_video_dir)
        ent_path.pack(side="left", fill="x", expand=True)

        def browse():
            d = filedialog.askdirectory(initialdir=ent_path.get())
            if d:
                ent_path.delete(0, "end")
                ent_path.insert(0, d)

        ctk.CTkButton(path_frame, text="Duyệt...", width=80, command=browse).pack(side="right", padx=(8, 0))

        def start_video():
            url = ent_url.get().strip()
            save_dir = ent_path.get().strip()
            choice = cbo_format.get()
            custom_title = ent_title.get().strip()

            if not url:
                messagebox.showerror("Lỗi", "Vui lòng nhập link video!", parent=dlg)
                return

            format_id = None
            if "1080p" in choice:
                format_id = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
            elif "720p" in choice:
                format_id = "bestvideo[height<=720]+bestaudio/best[height<=720]"
            elif "âm thanh" in choice:
                format_id = "bestaudio/best"

            filename = (custom_title + ".mp4") if (custom_title and not custom_title.endswith(".mp4")) else custom_title

            dlg.destroy()
            task = self.engine.create_video_task(url, save_dir, filename=filename, format_id=format_id)
            self.engine.queue_or_start_task(task.task_id)
            self._refresh_table()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(20, 0))
        ctk.CTkButton(btn_row, text="🚀 Bắt đầu tải Phim / Video", fg_color="#dc2626", hover_color="#b91c1c",
                      font=("Segoe UI", 12, "bold"), command=start_video).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_row, text="Hủy", fg_color="#374151", command=dlg.destroy).pack(side="right")

    # ==========================================
    # CLIPBOARD MONITORING (BẮT LINK CLIPBOARD)
    # ==========================================
    def _check_clipboard(self):
        if not self.settings.get("clipboard_monitor", True):
            return
        if self._clipboard_dialog_open:
            return

        try:
            raw_text = self.clipboard_get()
            if not raw_text or not isinstance(raw_text, str):
                return
            text = raw_text.strip()
            if not text or text == self._last_clipboard_text:
                return

            # Check if text is a valid HTTP/HTTPS URL
            if text.startswith("http://") or text.startswith("https://"):
                clean = text.split("?")[0].lower()
                DOWNLOAD_EXTS = [
                    ".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".dmg", ".pkg",
                    ".exe", ".msi", ".apk", ".bin",
                    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".m3u8",
                    ".mp3", ".wav", ".flac", ".pdf", ".epub", ".docx", ".xlsx"
                ]
                VIDEO_DOMAINS = [
                    "youtube.com", "youtu.be", "tiktok.com", "facebook.com",
                    "fb.watch", "instagram.com", "bilibili.com", "douyin.com",
                    "vimeo.com", "dailymotion.com", "x.com", "twitter.com"
                ]

                is_downloadable = any(clean.endswith(ext) for ext in DOWNLOAD_EXTS)
                is_video = any(domain in text.lower() for domain in VIDEO_DOMAINS)

                if is_downloadable or is_video:
                    self._last_clipboard_text = text
                    self._clipboard_dialog_open = True
                    self.after(100, lambda u=text, iv=is_video: self._prompt_clipboard_download(u, iv))
            else:
                self._last_clipboard_text = text
        except Exception:
            pass

    def _prompt_clipboard_download(self, url: str, is_video: bool):
        try:
            self.show_window()
            short_url = url if len(url) < 65 else url[:62] + "..."
            title = "Phát hiện liên kết tải (Clipboard)"
            msg = f"KDM vừa phát hiện liên kết trong Clipboard:\n\n{short_url}\n\nBạn có muốn tải về ngay không?"
            ans = messagebox.askyesno(title, msg, parent=self)
            if ans:
                if is_video:
                    self.open_video_dialog(url)
                else:
                    self.open_add_dialog(url)
        finally:
            self._clipboard_dialog_open = False

    # ==========================================
    # EXTENSION INSTALLATION GUIDE DIALOG
    # ==========================================
    def show_extension_guide(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Cài đặt Extension KDM (Chrome, Cốc Cốc, Edge, Firefox)")
        dlg.geometry("640x520")
        dlg.transient(self)
        dlg.grab_set()

        if getattr(sys, 'frozen', False):
            ext_dir = os.path.join(os.path.dirname(sys.executable), "kdm_extension")
            if not os.path.exists(ext_dir):
                ext_dir = os.path.join(sys._MEIPASS, "kdm_extension")
        else:
            ext_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "kdm_extension"))

        title = ctk.CTkLabel(dlg, text="🧩 Hướng Dẫn Cài Extension KDM 1.2 (IDM Style Sniffer)", font=("Segoe UI", 16, "bold"), text_color="#38bdf8")
        title.pack(anchor="w", padx=20, pady=(16, 8))

        guide_text = (
            "1. Thư mục Extension KDM của bạn nằm tại:\n"
            f"   ▶ {ext_dir}\n\n"
            "2. Cách cài đặt cho Cốc Cốc, Google Chrome, Microsoft Edge, Brave:\n"
            "   • Mở Cốc Cốc / Chrome và truy cập: coccoc://extensions (hoặc chrome://extensions/)\n"
            "   • Bật công tắc 'Chế độ dành cho nhà phát triển' (Developer mode) ở góc phải trên.\n"
            "   • Bấm vào nút 'Tải tiện ích đã giải nén' (Load unpacked) -> Chọn thư mục 'kdm_extension'.\n"
            "   • (Nếu đã cài trước đó, chỉ cần bấm biểu tượng Làm Mới 🔄 trên thẻ KDM).\n\n"
            "3. Phím tắt cao cấp như IDM:\n"
            "   • Giữ Alt + Bấm chuột vào link: Ép tải bằng KDM ngay lập tức.\n"
            "   • Giữ Ctrl + Bấm chuột vào link: Bỏ qua KDM (để trình duyệt tải bình thường).\n\n"
            "4. Cách cài đặt cho Mozilla Firefox:\n"
            "   • Mở Firefox và truy cập: about:debugging#/runtime/this-firefox\n"
            "   • Bấm 'Tải Tiện ích Tạm thời...' -> Chọn file 'kdm_extension_firefox.zip'.\n\n"
            "✓ Xong! Khi xem phim trên bất kỳ trang web nào, thanh nổi KDM sẽ tự bắt luồng m3u8/mp4 ngay trên khung phát!"
        )

        txt_box = ctk.CTkTextbox(dlg, width=600, height=350, font=("Consolas", 12))
        txt_box.pack(padx=20, pady=8)
        txt_box.insert("1.0", guide_text)
        txt_box.configure(state="disabled")

        def open_folder():
            subprocess.Popen(f'explorer "{ext_dir}"')

        btn_open = ctk.CTkButton(dlg, text="📁 Mở Thư Mục Extension KDM Trên Máy", fg_color="#2563eb", command=open_folder)
        btn_open.pack(pady=10)

    # ==========================================
    # ACTIONS ON TASKS
    # ==========================================
    def select_task(self, task_id: str):
        self.selected_task_id = task_id
        for tid, widgets in self.task_rows.items():
            card = widgets["card"]
            if tid == task_id:
                card.configure(fg_color="#1e293b", border_color="#3b82f6", border_width=1)
            else:
                card.configure(fg_color="#161b22", border_width=0)

    def resume_selected(self):
        if self.selected_task_id:
            self.engine.resume_task(self.selected_task_id)

    def pause_selected(self):
        if self.selected_task_id:
            self.engine.pause_task(self.selected_task_id)

    def resume_all_tasks(self):
        with self.engine.lock:
            for tid, t in self.engine.tasks.items():
                if t.status in ("Paused", "Queued"):
                    self.engine.resume_task(tid)

    def pause_all_tasks(self):
        with self.engine.lock:
            for tid, t in self.engine.tasks.items():
                if t.status == "Downloading":
                    self.engine.pause_task(tid)

    def open_selected_file(self):
        if self.selected_task_id:
            self.open_task_file(self.selected_task_id)
        else:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một tệp trong danh sách để mở!", parent=self)

    def open_task_file(self, task_id: str):
        task = self.engine.get_task(task_id)
        if not task:
            return

        if task.status == "Completed":
            target_path = task.target_file
            if not target_path or not os.path.exists(target_path):
                if task.save_path and task.filename:
                    candidate = os.path.join(task.save_path, task.filename)
                    if os.path.exists(candidate):
                        target_path = candidate
                        task.target_file = candidate

            if target_path and os.path.exists(target_path):
                try:
                    os.startfile(os.path.normpath(target_path))
                except Exception as e:
                    messagebox.showerror("Lỗi mở tệp", f"Không thể mở tệp:\n{e}", parent=self)
            else:
                ans = messagebox.askyesno(
                    "Không tìm thấy tệp",
                    f"Tệp '{task.filename}' không còn tồn tại trên ổ đĩa.\nTệp có thể đã bị di chuyển hoặc xóa.\n\nBạn có muốn mở thư mục lưu trữ không?",
                    parent=self
                )
                if ans:
                    target_folder = task.save_path if (task.save_path and os.path.exists(task.save_path)) else self.settings.get("save_dir")
                    if os.path.exists(target_folder):
                        os.startfile(os.path.normpath(target_folder))
        elif task.status in ("Paused", "Queued", "Error", "Stopped"):
            self.engine.resume_task(task_id)
        elif task.status == "Downloading":
            self.engine.pause_task(task_id)

    def open_task_folder(self, task_id: str):
        task = self.engine.get_task(task_id)
        if not task:
            return
        if task.target_file and os.path.exists(task.target_file):
            norm_file = os.path.normpath(task.target_file)
            subprocess.Popen(f'explorer /select,"{norm_file}"')
        elif task.save_path and os.path.exists(task.save_path):
            os.startfile(os.path.normpath(task.save_path))
        else:
            target_dir = os.path.normpath(self.settings.get("save_dir"))
            os.makedirs(target_dir, exist_ok=True)
            os.startfile(target_dir)

    def delete_task_by_id(self, task_id: str, delete_file: bool = False):
        task = self.engine.get_task(task_id)
        if not task:
            return
        title = "Xóa vĩnh viễn tệp" if delete_file else "Xác nhận xóa"
        msg = f"Bạn có chắc muốn XÓA VĨNH VIỄN tệp '{task.filename}' khỏi ổ đĩa?" if delete_file else f"Bạn có chắc muốn xóa '{task.filename}' khỏi danh sách?"
        ans = messagebox.askyesno(title, msg, parent=self)
        if ans:
            self.engine.cancel_task(task_id, delete_file=delete_file)
            if self.selected_task_id == task_id:
                self.selected_task_id = None
            self._refresh_table()

    def show_context_menu(self, event, task_id: str):
        self.select_task(task_id)
        task = self.engine.get_task(task_id)
        if not task:
            return

        menu = tk.Menu(self, tearoff=0, bg="#1e242d", fg="#ffffff", activebackground="#2563eb", activeforeground="#ffffff", font=("Segoe UI", 10))

        if task.status == "Completed":
            menu.add_command(label="▶ Mở tệp (Open)", command=lambda: self.open_task_file(task_id))

        menu.add_command(label="📁 Mở thư mục chứa (Show in Folder)", command=lambda: self.open_task_folder(task_id))
        menu.add_separator()

        if task.status in ("Paused", "Queued", "Error", "Stopped"):
            menu.add_command(label="▶ Tiếp tục tải (Resume)", command=lambda: self.engine.resume_task(task_id))
        elif task.status == "Downloading":
            menu.add_command(label="⏸ Tạm dừng (Pause)", command=lambda: self.engine.pause_task(task_id))

        menu.add_separator()
        menu.add_command(label="🗑️ Xóa khỏi danh sách", command=lambda: self.delete_task_by_id(task_id, delete_file=False))
        menu.add_command(label="❌ Xóa cả tệp trên ổ đĩa", command=lambda: self.delete_task_by_id(task_id, delete_file=True))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def delete_selected(self):
        if self.selected_task_id:
            self.delete_task_by_id(self.selected_task_id, delete_file=False)
        else:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một tệp trong danh sách để xóa!", parent=self)

    def open_download_folder(self):
        if self.selected_task_id:
            self.open_task_folder(self.selected_task_id)
            return

        target_dir = os.path.normpath(self.settings.get("save_dir"))
        os.makedirs(target_dir, exist_ok=True)
        os.startfile(target_dir)

    # ==========================================
    # TABLE & REFRESH LOGIC
    # ==========================================
    def _matches_filter(self, task: DownloadTask) -> bool:
        if self.current_filter == "ALL":
            return True
        if self.current_filter == "DOWNLOADING":
            return task.status == "Downloading"
        if self.current_filter == "QUEUED":
            return task.status == "Queued"
        if self.current_filter == "COMPLETED":
            return task.status == "Completed"
        if self.current_filter == "VIDEO":
            return task.is_video_stream or any(task.filename.lower().endswith(e) for e in [".mp4", ".mkv", ".webm", ".avi", ".mov", ".ts", ".m3u8"])
        if self.current_filter == "COMPRESSED":
            return any(task.filename.lower().endswith(e) for e in [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"])
        if self.current_filter == "PROGRAMS":
            return any(task.filename.lower().endswith(e) for e in [".exe", ".msi", ".apk", ".bin"])
        if self.current_filter == "DOCUMENTS":
            return any(task.filename.lower().endswith(e) for e in [".pdf", ".docx", ".xlsx", ".pptx", ".txt"])
        return True

    def _refresh_table(self):
        with self.engine.lock:
            tasks_list = list(self.engine.tasks.values())

        visible_tasks = [t for t in tasks_list if self._matches_filter(t)]

        if not visible_tasks:
            self.empty_label.pack(pady=80)
            for tid, widgets in list(self.task_rows.items()):
                widgets["card"].destroy()
            self.task_rows.clear()
            return

        self.empty_label.pack_forget()

        visible_ids = {t.task_id for t in visible_tasks}
        for tid in list(self.task_rows.keys()):
            if tid not in visible_ids:
                self.task_rows[tid]["card"].destroy()
                del self.task_rows[tid]

        for task in visible_tasks:
            if task.task_id not in self.task_rows:
                self._create_task_card(task)

    def _create_task_card(self, task: DownloadTask):
        card = ctk.CTkFrame(self.scroll_frame, fg_color="#161b22", corner_radius=8, height=72)
        card.pack(fill="x", pady=4, padx=4)
        card.pack_propagate(False)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 2))

        icon = "🎬 " if task.is_video_stream else "📦 "
        lbl_name = ctk.CTkLabel(header, text=f"{icon}{task.filename}", font=("Segoe UI", 13, "bold"), text_color="#f3f4f6")
        lbl_name.pack(side="left")

        lbl_status = ctk.CTkLabel(header, text=task.status, font=("Segoe UI", 11, "bold"), text_color="#38bdf8")
        lbl_status.pack(side="right")

        prog_bar = ctk.CTkProgressBar(card, height=8, corner_radius=4, progress_color="#2563eb", fg_color="#374151")
        prog_bar.pack(fill="x", padx=12, pady=4)
        prog_bar.set(0)

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.pack(fill="x", padx=12, pady=(0, 6))

        lbl_size = ctk.CTkLabel(footer, text="0 B / 0 B", font=("Segoe UI", 11), text_color="#9ca3af")
        lbl_size.pack(side="left")

        lbl_speed = ctk.CTkLabel(footer, text="0 KB/s", font=("Segoe UI", 11), text_color="#10b981")
        lbl_speed.pack(side="right", padx=(8, 0))

        lbl_eta = ctk.CTkLabel(footer, text="ETA: --:--", font=("Segoe UI", 11), text_color="#9ca3af")
        lbl_eta.pack(side="right")

        # Bind Single-click (Select), Double-click (Open file), and Right-click (Context menu)
        row_widgets = [card, header, lbl_name, lbl_status, footer, lbl_size, lbl_speed, lbl_eta]
        for w in row_widgets:
            w.bind("<Button-1>", lambda e, tid=task.task_id: self.select_task(tid))
            w.bind("<Double-Button-1>", lambda e, tid=task.task_id: self.open_task_file(tid))
            w.bind("<Button-3>", lambda e, tid=task.task_id: self.show_context_menu(e, tid))

        try:
            prog_bar.bind("<Button-1>", lambda e, tid=task.task_id: self.select_task(tid))
            prog_bar.bind("<Double-Button-1>", lambda e, tid=task.task_id: self.open_task_file(tid))
            prog_bar.bind("<Button-3>", lambda e, tid=task.task_id: self.show_context_menu(e, tid))
        except Exception:
            pass

        self.task_rows[task.task_id] = {
            "card": card,
            "lbl_name": lbl_name,
            "lbl_status": lbl_status,
            "prog_bar": prog_bar,
            "lbl_size": lbl_size,
            "lbl_speed": lbl_speed,
            "lbl_eta": lbl_eta
        }

    def _start_refresh_loop(self):
        def loop():
            clip_counter = 0
            while True:
                time.sleep(0.4)
                self.after(0, self._update_progress_ui)

                # Check clipboard every ~1.2s
                clip_counter += 1
                if clip_counter >= 3:
                    clip_counter = 0
                    self.after(0, self._check_clipboard)

        threading.Thread(target=loop, daemon=True).start()

    def _update_progress_ui(self):
        total_speed = 0.0
        with self.engine.lock:
            tasks_list = list(self.engine.tasks.values())

        if len(tasks_list) != len(self.task_rows):
            self._refresh_table()

        for task in tasks_list:
            if task.status == "Downloading":
                total_speed += task.speed

            # Auto-resolve tasks that finished merging and exist on disk
            if task.status == "Processing (Merging)..." and task.target_file and os.path.exists(task.target_file):
                base_check = os.path.splitext(task.filename)[0]
                has_temp = False
                try:
                    for f in os.listdir(task.save_path):
                        if f.startswith(base_check) and (f.endswith('.part') or f.endswith('.ytdl') or '.f' in f):
                            has_temp = True
                            break
                except Exception:
                    pass
                if not has_temp:
                    task.status = "Completed"
                    task.speed = 0.0

            # If completed, ensure total_bytes matches the real file size on disk and speed is 0
            if task.status == "Completed":
                task.speed = 0.0
                if task.target_file and os.path.exists(task.target_file):
                    actual_file_size = os.path.getsize(task.target_file)
                    if actual_file_size > 0 and task.total_bytes != actual_file_size:
                        task.total_bytes = actual_file_size
                        task.downloaded_bytes = actual_file_size

            # Play sound and notification when task completes
            if task.status == "Completed" and task.task_id not in self._notified_completed_tasks:
                self._notified_completed_tasks.add(task.task_id)
                self.settings.play_complete_sound()
                try:
                    if hasattr(self, 'tray_icon') and self.tray_icon:
                        self.tray_icon.notify("Tải xong tệp", f"Đã hoàn thành tải về: {task.filename}")
                except Exception:
                    pass

            if task.task_id in self.task_rows:
                widgets = self.task_rows[task.task_id]

                icon = "🎬 " if task.is_video_stream else "📦 "
                widgets["lbl_name"].configure(text=f"{icon}{task.filename}")

                pct = (task.downloaded_bytes / task.total_bytes) if task.total_bytes > 0 else 0.0
                widgets["prog_bar"].set(min(1.0, max(0.0, pct)))

                down_str = format_size(task.downloaded_bytes)
                tot_str = format_size(task.total_bytes)
                pct_str = f"{pct * 100:.1f}%" if task.total_bytes > 0 else ""
                widgets["lbl_size"].configure(text=f"{down_str} / {tot_str}  ({pct_str})")

                if task.status in ("Completed", "Paused", "Error", "Queued"):
                    widgets["lbl_speed"].configure(text="0 KB/s")
                    widgets["lbl_eta"].configure(text="ETA: 00:00" if task.status == "Completed" else "ETA: --:--")
                else:
                    widgets["lbl_speed"].configure(text=format_speed(task.speed))
                    rem_bytes = max(0, task.total_bytes - task.downloaded_bytes)
                    widgets["lbl_eta"].configure(text=f"ETA: {format_eta(rem_bytes, task.speed)}")

                status_color = "#38bdf8"
                display_status = task.status
                if task.status == "Completed":
                    status_color = "#10b981"
                elif task.status == "Paused":
                    status_color = "#f59e0b"
                elif task.status == "Queued":
                    status_color = "#eab308"
                    display_status = "⏳ Đang chờ hàng đợi (Queued)"
                elif task.status == "Error":
                    status_color = "#ef4444"
                    display_status = "Error (Bấm Tiếp tục để thử lại)"

                widgets["lbl_status"].configure(text=display_status, text_color=status_color)

        self.lbl_total_speed.configure(text=f"Tổng tốc độ: {format_speed(total_speed)}")
