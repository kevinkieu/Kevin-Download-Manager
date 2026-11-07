"""
KDM - Kevin Download Manager
Core Download Engine: Multi-threaded HTTP Range Downloader & Video Extractor (yt-dlp)
"""

import os
import sys
import time
import math
import json
import re
import urllib.parse
import threading
import requests
from typing import Callable, Optional, Dict, List, Any
import yt_dlp

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = None

if getattr(sys, 'frozen', False):
    if not FFMPEG_PATH or not os.path.exists(FFMPEG_PATH):
        c1 = os.path.join(sys._MEIPASS, "ffmpeg.exe")
        c2 = os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe")
        if os.path.exists(c1):
            FFMPEG_PATH = c1
        elif os.path.exists(c2):
            FFMPEG_PATH = c2


def sanitize_video_url(url: str) -> str:
    """Clean URLs like YouTube Mix/Playlist to download only the active single video"""
    if not url:
        return url
    if "youtube.com/watch" in url or "youtu.be/" in url:
        try:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            if 'v' in qs:
                clean_query = urllib.parse.urlencode({'v': qs['v'][0]})
                return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, ''))
        except Exception:
            pass
    return url


def parse_batch_pattern(pattern: str) -> List[str]:
    """Parse batch patterns like https://example.com/file_[01-20].zip into a list of URLs"""
    m = re.search(r'\[(\d+)-(\d+)\]', pattern)
    if m:
        s_str, e_str = m.group(1), m.group(2)
        s, e = int(s_str), int(e_str)
        pad = len(s_str)
        step = 1 if s <= e else -1
        urls = [pattern[:m.start()] + str(i).zfill(pad) + pattern[m.end():] for i in range(s, e + step, step)]
        return urls
    return [pattern]


class DownloadTask:
    """Represents a download task (HTTP Multi-segment or Video Stream)"""
    def __init__(self, task_id: str, url: str, save_path: str, filename: str,
                 connections: int = 8, is_video_stream: bool = False,
                 video_format_id: Optional[str] = None, metadata: Optional[Dict] = None):
        self.task_id = task_id
        self.url = url
        self.save_path = save_path
        self.filename = filename
        self.target_file = os.path.join(save_path, filename)
        self.state_file = self.target_file + ".kdm_state"
        self.connections = max(1, min(32, connections))
        self.is_video_stream = is_video_stream
        self.video_format_id = video_format_id
        self.metadata = metadata or {}

        # Progress stats
        self.total_bytes = 0
        self.downloaded_bytes = 0
        self.speed = 0.0  # bytes/sec
        self.status = "Queued"  # Queued, Downloading, Paused, Completed, Error
        self.error_message = ""
        self.part_progress = []  # [{start, end, downloaded, active}]

        # Control flags
        self._pause_flag = threading.Event()
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Speed calculation
        self._last_speed_check_time = time.time()
        self._last_downloaded_bytes = 0

        # Callbacks
        self.on_progress: Optional[Callable[['DownloadTask'], None]] = None
        self.on_complete: Optional[Callable[['DownloadTask'], None]] = None
        self.on_error: Optional[Callable[['DownloadTask', str], None]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "url": self.url,
            "filename": self.filename,
            "target_file": self.target_file,
            "total_bytes": self.total_bytes,
            "downloaded_bytes": self.downloaded_bytes,
            "speed": self.speed,
            "status": self.status,
            "connections": self.connections,
            "is_video_stream": self.is_video_stream,
            "error_message": self.error_message
        }


class KDMEngine:
    """Core Manager that handles queues, multi-threading, speed limits, and yt-dlp tasks"""
    def __init__(self):
        self.tasks: Dict[str, DownloadTask] = {}
        self.lock = threading.Lock()

        # 1. Concurrency Queue
        self.max_active_tasks = 2
        self.shutdown_when_done = False

        # 2. Speed Limiter
        self.speed_limit_enabled = False
        self.speed_limit_bps = 0

        # 3. Scheduler
        self.scheduler_enabled = False
        self.schedule_start_time = "02:00"
        self.schedule_stop_time = "06:00"
        self._last_scheduled_start = ""
        self._last_scheduled_stop = ""

        # 4. Proxy & Auth
        self.proxy_config = None
        self.auth_credentials = None

        # Start Scheduler loop
        threading.Thread(target=self._run_scheduler_loop, daemon=True).start()

    def set_speed_limit(self, enabled: bool, kbps: int = 2048):
        self.speed_limit_enabled = enabled
        self.speed_limit_bps = max(0, kbps * 1024)

    def configure_proxy(self, enabled: bool, host: str, port: int, user: str = "", password: str = ""):
        if enabled and host and port > 0:
            auth_str = f"{user}:{password}@" if user else ""
            p_url = f"http://{auth_str}{host}:{port}"
            self.proxy_config = {"http": p_url, "https": p_url}
        else:
            self.proxy_config = None

    def configure_auth(self, user: str, password: str):
        if user:
            self.auth_credentials = (user, password)
        else:
            self.auth_credentials = None

    def queue_or_start_task(self, task_id: str):
        task = self.get_task(task_id)
        if not task:
            return
        with self.lock:
            active_count = sum(1 for t in self.tasks.values() if t.status == "Downloading")
        if active_count < self.max_active_tasks:
            self.start_task(task_id)
        else:
            task.status = "Queued"
            if task.on_progress:
                task.on_progress(task)

    def process_queue(self):
        with self.lock:
            active_count = sum(1 for t in self.tasks.values() if t.status == "Downloading")
            queued = [t for t in self.tasks.values() if t.status == "Queued"]

        while active_count < self.max_active_tasks and queued:
            next_task = queued.pop(0)
            self.start_task(next_task.task_id)
            active_count += 1

        if self.shutdown_when_done:
            with self.lock:
                has_active = any(t.status in ("Downloading", "Queued") for t in self.tasks.values())
                all_done = len(self.tasks) > 0 and all(t.status == "Completed" for t in self.tasks.values())
            if not has_active and all_done:
                self.trigger_shutdown()

    def trigger_shutdown(self):
        try:
            import subprocess
            subprocess.Popen('shutdown /s /t 60 /c "KDM: Toàn bộ lượt tải đã hoàn thành. Máy tính sẽ tắt sau 60 giây. Mở cmd gõ shutdown /a để hủy."', shell=True)
        except Exception as e:
            print(f"Shutdown trigger error: {e}")

    def cancel_shutdown(self):
        try:
            import subprocess
            subprocess.Popen('shutdown /a', shell=True)
        except Exception:
            pass

    def _run_scheduler_loop(self):
        while True:
            time.sleep(3)
            if not self.scheduler_enabled:
                continue
            now_hm = time.strftime("%H:%M")
            if now_hm == self.schedule_start_time and self._last_scheduled_start != now_hm:
                self._last_scheduled_start = now_hm
                with self.lock:
                    targets = [t.task_id for t in self.tasks.values() if t.status in ("Paused", "Queued")]
                for tid in targets:
                    self.resume_task(tid)
            elif now_hm == self.schedule_stop_time and self._last_scheduled_stop != now_hm:
                self._last_scheduled_stop = now_hm
                with self.lock:
                    downloading = [t.task_id for t in self.tasks.values() if t.status == "Downloading"]
                for tid in downloading:
                    self.pause_task(tid)

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        with self.lock:
            return self.tasks.get(task_id)

    def create_http_task(self, url: str, save_path: str, filename: Optional[str] = None,
                         connections: int = 8, metadata: Optional[Dict] = None) -> DownloadTask:
        os.makedirs(save_path, exist_ok=True)
        task_id = f"kdm_{int(time.time() * 1000)}"
        
        # Probe headers to get filename and size if not provided
        if not filename:
            filename = self._guess_filename(url)

        task = DownloadTask(task_id, url, save_path, filename, connections=connections, is_video_stream=False, metadata=metadata)
        with self.lock:
            self.tasks[task_id] = task
        return task

    def create_video_task(self, url: str, save_path: str, filename: Optional[str] = None,
                          format_id: Optional[str] = None, metadata: Optional[Dict] = None) -> DownloadTask:
        os.makedirs(save_path, exist_ok=True)
        task_id = f"kdm_vid_{int(time.time() * 1000)}"
        clean_url = sanitize_video_url(url)
        if not filename:
            filename = "Video_Download.mp4"

        task = DownloadTask(task_id, clean_url, save_path, filename, connections=1,
                            is_video_stream=True, video_format_id=format_id, metadata=metadata)
        with self.lock:
            self.tasks[task_id] = task
        return task

    def start_task(self, task_id: str):
        task = self.get_task(task_id)
        if not task:
            return
        if task.status == "Downloading":
            return

        task._pause_flag.clear()
        task._stop_flag.clear()
        task.status = "Downloading"

        if task.is_video_stream:
            task._thread = threading.Thread(target=self._run_video_download, args=(task,), daemon=True)
        else:
            task._thread = threading.Thread(target=self._run_http_download, args=(task,), daemon=True)
        task._thread.start()

    def pause_task(self, task_id: str):
        task = self.get_task(task_id)
        if task and task.status == "Downloading":
            task._pause_flag.set()
            task.status = "Paused"
            task.speed = 0.0
            if task.on_progress:
                task.on_progress(task)

    def resume_task(self, task_id: str):
        task = self.get_task(task_id)
        if not task:
            return
        if task.status in ("Paused", "Error", "Stopped", "Queued"):
            task.error_message = ""
            self.start_task(task_id)

    def cancel_task(self, task_id: str, delete_file: bool = False):
        task = self.get_task(task_id)
        if not task:
            return
        task._stop_flag.set()
        task.status = "Stopped"
        if delete_file:
            try:
                if os.path.exists(task.target_file):
                    os.remove(task.target_file)
                if os.path.exists(task.state_file):
                    os.remove(task.state_file)
            except Exception:
                pass
        with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]

    def _guess_filename(self, url: str) -> str:
        try:
            head = requests.head(url, allow_redirects=True, timeout=5)
            # Check Content-Disposition
            cd = head.headers.get("content-disposition", "")
            if "filename=" in cd:
                fname = cd.split("filename=")[-1].strip().strip('"\'')
                if fname:
                    return fname
            # Extract from final URL path
            clean_url = head.url.split("?")[0].split("#")[0]
            basename = os.path.basename(clean_url)
            if basename and "." in basename:
                return basename
        except Exception:
            pass

        clean_url = url.split("?")[0].split("#")[0]
        basename = os.path.basename(clean_url)
        return basename if basename else "download.dat"

    # ==========================================
    # HTTP MULTI-SEGMENT ACCELERATOR
    # ==========================================
    def _run_http_download(self, task: DownloadTask):
        try:
            # 1. Probe server for Range support & Content-Length using a small range probe
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KDM/1.0", "Range": "bytes=0-0"}
            resp = requests.get(task.url, headers=headers, proxies=self.proxy_config, auth=self.auth_credentials, allow_redirects=True, timeout=10)
            
            accept_ranges = resp.status_code == 206
            content_length = 0

            if accept_ranges:
                cr = resp.headers.get("Content-Range", "")
                if "/" in cr:
                    try:
                        content_length = int(cr.split("/")[-1])
                    except Exception:
                        content_length = 0
            if content_length == 0:
                content_length = int(resp.headers.get("Content-Length", 0))

            task.total_bytes = content_length

            # Check if resumption state exists
            segments = []
            if os.path.exists(task.state_file):
                try:
                    with open(task.state_file, "r") as sf:
                        state_data = json.load(sf)
                        if state_data.get("total_bytes") == content_length and len(state_data.get("segments", [])) > 0:
                            segments = state_data["segments"]
                except Exception:
                    segments = []

            # Initialize file allocation and segments if new
            if not segments:
                if content_length > 0 and accept_ranges and task.connections > 1:
                    # Multi-segmented setup
                    # Pre-allocate file directly to target size
                    with open(task.target_file, "wb") as f:
                        if content_length > 0:
                            f.seek(content_length - 1)
                            f.write(b'\0')

                    chunk_size = math.ceil(content_length / task.connections)
                    for i in range(task.connections):
                        s_start = i * chunk_size
                        s_end = min((i + 1) * chunk_size - 1, content_length - 1)
                        if s_start <= s_end:
                            segments.append({
                                "id": i,
                                "start": s_start,
                                "end": s_end,
                                "curr": s_start,
                                "done": False
                            })
                else:
                    # Single stream fallback
                    segments.append({
                        "id": 0,
                        "start": 0,
                        "end": content_length - 1 if content_length > 0 else -1,
                        "curr": 0,
                        "done": False
                    })
                    if not os.path.exists(task.target_file):
                        with open(task.target_file, "wb") as f:
                            pass

            # Calculate already downloaded bytes
            task.downloaded_bytes = sum(s["curr"] - s["start"] for s in segments)
            task.part_progress = segments

            # Worker threads for downloading segments
            threads = []
            file_lock = threading.Lock()
            state_lock = threading.Lock()

            def save_state():
                with state_lock:
                    try:
                        with open(task.state_file, "w") as sf:
                            json.dump({"total_bytes": task.total_bytes, "segments": segments}, sf)
                    except Exception:
                        pass

            def worker(seg):
                worker_session = requests.Session()
                if self.proxy_config:
                    worker_session.proxies = self.proxy_config
                if self.auth_credentials:
                    worker_session.auth = self.auth_credentials

                while seg["curr"] <= seg["end"] or (seg["end"] == -1 and not seg["done"]):
                    if task._pause_flag.is_set() or task._stop_flag.is_set():
                        break

                    req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KDM/1.0"}
                    if seg["end"] != -1:
                        req_headers["Range"] = f"bytes={seg['curr']}-{seg['end']}"

                    try:
                        with worker_session.get(task.url, headers=req_headers, stream=True, timeout=15) as r:
                            if r.status_code not in (200, 206):
                                time.sleep(1)
                                continue

                            for chunk in r.iter_content(chunk_size=65536):
                                if task._pause_flag.is_set() or task._stop_flag.is_set():
                                    break
                                if not chunk:
                                    continue

                                chunk_len = len(chunk)
                                with file_lock:
                                    with open(task.target_file, "r+b") as out_f:
                                        out_f.seek(seg["curr"])
                                        out_f.write(chunk)

                                seg["curr"] += chunk_len
                                with self.lock:
                                    task.downloaded_bytes += chunk_len

                                # Speed limiter throttle
                                if self.speed_limit_enabled and self.speed_limit_bps > 0:
                                    target_bps = max(2048, self.speed_limit_bps / max(1, len(threads)))
                                    time.sleep(chunk_len / target_bps)

                    except Exception as ex:
                        if task._pause_flag.is_set() or task._stop_flag.is_set():
                            break
                        time.sleep(1)

                if seg["end"] != -1 and seg["curr"] > seg["end"]:
                    seg["done"] = True
                elif seg["end"] == -1:
                    seg["done"] = True

            # Launch workers
            for s in segments:
                if not s["done"]:
                    t = threading.Thread(target=worker, args=(s,), daemon=True)
                    threads.append(t)
                    t.start()

            # Monitor loop: calculate speed and state save
            last_calc_time = time.time()
            last_calc_bytes = task.downloaded_bytes

            while any(t.is_alive() for t in threads):
                time.sleep(0.5)
                now = time.time()
                elapsed = now - last_calc_time
                if elapsed >= 0.5:
                    delta_bytes = task.downloaded_bytes - last_calc_bytes
                    task.speed = max(0.0, delta_bytes / elapsed)
                    last_calc_time = now
                    last_calc_bytes = task.downloaded_bytes
                    save_state()
                    if task.on_progress:
                        task.on_progress(task)

                if task._pause_flag.is_set() or task._stop_flag.is_set():
                    break

            # Wait for all threads to terminate
            for t in threads:
                t.join(timeout=2.0)

            save_state()

            if task._pause_flag.is_set():
                task.status = "Paused"
                task.speed = 0.0
                if task.on_progress:
                    task.on_progress(task)
                return

            if task._stop_flag.is_set():
                task.status = "Stopped"
                task.speed = 0.0
                return

            # Check if all completed
            if all(s.get("done", False) for s in segments) or (task.total_bytes > 0 and task.downloaded_bytes >= task.total_bytes):
                task.status = "Completed"
                task.downloaded_bytes = task.total_bytes if task.total_bytes > 0 else task.downloaded_bytes
                task.speed = 0.0
                if os.path.exists(task.state_file):
                    try:
                        os.remove(task.state_file)
                    except Exception:
                        pass
                if task.on_complete:
                    task.on_complete(task)
            else:
                task.status = "Paused"

        except Exception as e:
            task.status = "Error"
            task.error_message = str(e)
            if task.on_error:
                task.on_error(task, str(e))
        finally:
            self.process_queue()

    # ==========================================
    # VIDEO STREAM / YT-DLP DOWNLOADER
    # ==========================================
    @staticmethod
    def extract_video_info(url: str) -> Dict[str, Any]:
        """Extract title, thumbnail, and available formats from YouTube, TikTok, Facebook, etc."""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        if FFMPEG_PATH:
            ydl_opts['ffmpeg_location'] = FFMPEG_PATH

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            raw_formats = info.get('formats', [])
            for f in raw_formats:
                resolution = f.get('resolution') or f"{f.get('width', '')}x{f.get('height', '')}"
                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')
                ext = f.get('ext', 'mp4')
                format_note = f.get('format_note', '')
                filesize = f.get('filesize') or f.get('filesize_approx') or 0

                # Filter out useless storyboards
                if vcodec == 'none' and acodec == 'none':
                    continue

                is_video = vcodec != 'none'
                is_audio_only = vcodec == 'none' and acodec != 'none'

                label = f"{resolution} ({ext})" if is_video else f"Audio ({ext}) - {format_note or 'HQ'}"
                if format_note and is_video:
                    label += f" [{format_note}]"

                formats.append({
                    "format_id": f.get('format_id'),
                    "ext": ext,
                    "resolution": resolution,
                    "height": f.get('height', 0),
                    "is_video": is_video,
                    "is_audio_only": is_audio_only,
                    "filesize": filesize,
                    "label": label
                })

            return {
                "title": info.get('title', 'Video'),
                "thumbnail": info.get('thumbnail', ''),
                "duration": info.get('duration', 0),
                "uploader": info.get('uploader', ''),
                "extractor": info.get('extractor_key', 'generic'),
                "formats": formats
            }

    def _run_video_download(self, task: DownloadTask):
        try:
            import re
            last_check_time = time.time()
            last_bytes = 0

            # Determine clean base name from task.filename
            raw_filename = task.filename or ""
            clean_name = re.sub(r'[\\/:*?"<>|]', '_', raw_filename).strip()
            base_name, orig_ext = os.path.splitext(clean_name)
            
            # Check if filename is generic (e.g. index.m3u8 produces 'index')
            GENERIC_NAMES = {"index", "master", "playlist", "video", "videoplayback", "video_download", "video_stream"}
            is_generic = (not base_name) or (base_name.lower() in GENERIC_NAMES)

            stream_totals = {}
            stream_downloaded = {}

            def ydl_progress_hook(d):
                nonlocal last_check_time, last_bytes
                if task._stop_flag.is_set():
                    raise Exception("Download cancelled by user")

                if d['status'] == 'downloading':
                    task.status = "Downloading"
                    st_name = d.get('filename') or 'stream'
                    total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                    downloaded = d.get('downloaded_bytes') or 0

                    if total > 0:
                        stream_totals[st_name] = total
                    if downloaded > 0:
                        stream_downloaded[st_name] = downloaded

                    comb_total = sum(stream_totals.values())
                    comb_downloaded = sum(stream_downloaded.values())

                    now = time.time()
                    elapsed = now - last_check_time
                    if elapsed >= 0.5:
                        delta = comb_downloaded - last_bytes
                        task.speed = max(0.0, delta / elapsed)
                        last_check_time = now
                        last_bytes = comb_downloaded

                    if comb_total > 0:
                        task.total_bytes = comb_total
                    if comb_downloaded > 0:
                        task.downloaded_bytes = comb_downloaded

                    if task.on_progress:
                        task.on_progress(task)

                elif d['status'] == 'finished':
                    task.status = "Processing (Merging)..."
                    if task.on_progress:
                        task.on_progress(task)

            def ydl_postprocessor_hook(d):
                if d.get('status') == 'started':
                    task.status = "Processing (Merging)..."
                    if task.on_progress:
                        task.on_progress(task)

            ydl_opts = {
                'noplaylist': True,
                'extract_flat': False,
                'retries': 25,
                'fragment_retries': 25,
                'skip_unavailable_fragments': True,
                'continuedl': True,
                'socket_timeout': 30,
                'progress_hooks': [ydl_progress_hook],
                'postprocessor_hooks': [ydl_postprocessor_hook],
                'quiet': True,
                'no_warnings': True,
            }
            if FFMPEG_PATH:
                ydl_opts['ffmpeg_location'] = FFMPEG_PATH

            # Speed limiter for video downloads
            if self.speed_limit_enabled and self.speed_limit_bps > 0:
                ydl_opts['ratelimit'] = self.speed_limit_bps

            # Proxy & Authentication
            if self.proxy_config:
                p_url = self.proxy_config.get('http') or self.proxy_config.get('https')
                if p_url:
                    ydl_opts['proxy'] = p_url
            if self.auth_credentials:
                ydl_opts['username'] = self.auth_credentials[0]
                ydl_opts['password'] = self.auth_credentials[1]

            # If user or extension gave a specific movie name, enforce it in output template!
            if not is_generic:
                ydl_opts['outtmpl'] = os.path.join(task.save_path, f"{base_name}.%(ext)s")
            else:
                ydl_opts['outtmpl'] = os.path.join(task.save_path, "%(title)s.%(ext)s")

            # Support Referer header (crucial for Vietnamese movie streaming sites)
            referrer = task.metadata.get("referrer") or task.metadata.get("Referer")
            if referrer:
                ydl_opts['http_headers'] = {
                    'Referer': referrer,
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }

            if task.video_format_id:
                ydl_opts['format'] = f"{task.video_format_id}+bestaudio/best"
            else:
                # Default format: for m3u8 or generic stream, 'best' is safe and merges properly
                ydl_opts['format'] = 'bestvideo+bestaudio/best/bestvideo*+bestaudio*'

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(task.url, download=True)
                downloaded_file = ydl.prepare_filename(info)

                # Locate actual file on disk (handling ffmpeg remuxing to .mp4 or .mkv)
                real_file = downloaded_file
                if not os.path.exists(real_file):
                    for possible_ext in ['.mp4', '.mkv', '.webm', '.ts', '.m4a']:
                        alt = os.path.splitext(downloaded_file)[0] + possible_ext
                        if os.path.exists(alt):
                            real_file = alt
                            break

                # Ensure final file has the meaningful movie title instead of "index.mp4"
                if not is_generic and os.path.exists(real_file):
                    actual_ext = os.path.splitext(real_file)[1] or ".mp4"
                    target_file = os.path.join(task.save_path, f"{base_name}{actual_ext}")
                    if os.path.abspath(real_file) != os.path.abspath(target_file):
                        try:
                            if os.path.exists(target_file):
                                os.remove(target_file)
                            os.rename(real_file, target_file)
                            real_file = target_file
                        except Exception as ren_err:
                            print(f"Rename warning: {ren_err}")

                task.target_file = real_file
                task.filename = os.path.basename(real_file)

                # Update to the 100% exact real merged size on disk
                if os.path.exists(real_file):
                    actual_file_size = os.path.getsize(real_file)
                    task.total_bytes = actual_file_size
                    task.downloaded_bytes = actual_file_size

            task.status = "Completed"
            task.speed = 0.0
            if task.on_progress:
                task.on_progress(task)
            if task.on_complete:
                task.on_complete(task)

        except Exception as e:
            if task._stop_flag.is_set():
                task.status = "Stopped"
            else:
                task.status = "Error"
                task.error_message = str(e)
                if task.on_error:
                    task.on_error(task, str(e))
        finally:
            self.process_queue()
