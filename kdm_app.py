"""
KDM - Kevin Download Manager
Main Application Runner
"""

import sys
import os
from kdm_engine import KDMEngine
from kdm_server import KDMServer
from kdm_gui import KDMApp


def main():
    engine = KDMEngine()

    # Initialize Local Bridge Server for Browser Extensions
    server = KDMServer("127.0.0.1", 59123, engine=engine)

    # Initialize GUI
    app = KDMApp(engine)
    server.settings = app.settings

    # Sync settings with engine
    engine.max_active_tasks = app.settings.get("max_active_tasks", 2)
    engine.shutdown_when_done = app.settings.get("shutdown_when_done", False)
    engine.set_speed_limit(app.settings.get("speed_limit_enabled", False), app.settings.get("speed_limit_kbps", 2048))
    engine.scheduler_enabled = app.settings.get("scheduler_enabled", False)
    engine.schedule_start_time = app.settings.get("schedule_start_time", "02:00")
    engine.schedule_stop_time = app.settings.get("schedule_stop_time", "06:00")
    engine.configure_proxy(
        app.settings.get("proxy_enabled", False),
        app.settings.get("proxy_host", ""),
        app.settings.get("proxy_port", 8080),
        app.settings.get("proxy_user", ""),
        app.settings.get("proxy_pass", "")
    )
    engine.configure_auth(app.settings.get("auth_user", ""), app.settings.get("auth_pass", ""))

    def handle_incoming_download(url: str, filename: str = "", is_video: bool = False,
                                 format_id: str = None, start_now: bool = True, metadata: dict = None):
        """Callback when browser extension catches a download link or video"""
        save_dir = app.settings.get("save_dir")

        # Auto categorize subfolders if enabled in settings
        if app.settings.get("auto_subfolders", True):
            if is_video or url.lower().endswith((".m3u8", ".mp4", ".mkv", ".webm")):
                save_dir = os.path.join(save_dir, "Videos")
            elif any((filename or "").lower().endswith(e) for e in [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"]):
                save_dir = os.path.join(save_dir, "Compressed")
            elif any((filename or "").lower().endswith(e) for e in [".exe", ".msi", ".apk", ".bin"]):
                save_dir = os.path.join(save_dir, "Programs")
            elif any((filename or "").lower().endswith(e) for e in [".pdf", ".docx", ".xlsx", ".pptx", ".txt"]):
                save_dir = os.path.join(save_dir, "Documents")

        os.makedirs(save_dir, exist_ok=True)

        if is_video:
            task = engine.create_video_task(url, save_dir, filename=filename, format_id=format_id, metadata=metadata)
        else:
            task = engine.create_http_task(url, save_dir, filename=filename, connections=app.settings.get("default_connections", 16), metadata=metadata)

        if start_now:
            engine.queue_or_start_task(task.task_id)
        else:
            task.status = "Queued"

        # Notify GUI and immediately show main KDM window to user!
        app.after(0, app._refresh_table)
        app.after(0, app.show_window)
        return {"task_id": task.task_id, "filename": task.filename}

    server.on_new_download = handle_incoming_download

    try:
        server.start_background()
        print("[OK] KDM Bridge Server started on http://127.0.0.1:59123")
    except Exception as e:
        print(f"Warning: could not bind port 59123 ({e}). Server may already be active.")

    app.on_quit_callback = lambda: server.stop()

    # If launched with Windows startup (--tray), start minimized in system tray
    if "--tray" in sys.argv or "-tray" in sys.argv:
        app.withdraw()

    # Start Tkinter GUI event loop
    app.mainloop()


if __name__ == "__main__":
    main()
