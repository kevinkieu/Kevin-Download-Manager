/**
 * KDM - Kevin Download Manager
 * Content Script: Top-Right Symmetrical Floating Download Bar & Video Sniffer
 * Positioned ABOVE the video frame on the RIGHT side (symmetrical to browser downloader)
 * Supports 1-Click Fast Download, Resolution Picker, Drag-and-Drop, and Close
 */

(function () {
  let barElement = null;
  let menuElement = null;
  let isBarDismissed = false;
  let capturedMediaList = [];

  // Dragging state
  let isDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let barStartX = 0;
  let barStartY = 0;

  function isKnownPlatform() {
    const url = window.location.href.toLowerCase();
    return (
      url.includes("youtube.com/watch") ||
      url.includes("youtu.be/") ||
      url.includes("youtube.com/shorts") ||
      url.includes("tiktok.com/") ||
      url.includes("facebook.com/") ||
      url.includes("instagram.com/")
    );
  }

  function getCleanVideoUrl(rawUrl) {
    try {
      if (rawUrl.includes("youtube.com/watch") || rawUrl.includes("youtu.be/")) {
        const u = new URL(rawUrl);
        const v = u.searchParams.get("v");
        if (v) {
          return `${u.origin}/watch?v=${v}`;
        }
      }
    } catch (e) {}
    return rawUrl;
  }

  // Find the exact video player container
  function getPlayerContainer() {
    // 1. YouTube Player
    const ytPlayer = document.querySelector("#movie_player") || document.querySelector(".html5-video-player");
    if (ytPlayer && ytPlayer.clientHeight > 150) {
      return ytPlayer;
    }

    // 2. Generic HTML5 Video container
    const videos = Array.from(document.querySelectorAll("video")).filter(v => v.clientHeight > 120);
    if (videos.length > 0) {
      const v = videos[0];
      const player = v.closest('.jwplayer, .video-js, .plyr, [class*="player"], [id*="player"]') || v.parentElement;
      if (player) {
        return player;
      }
    }

    return null;
  }

  function updateBarPosition() {
    if (!barElement || isBarDismissed) return;

    const isFullscreen = !!(document.fullscreenElement || document.webkitFullscreenElement);
    const container = getPlayerContainer();
    if (!container) return;

    if (isFullscreen) {
      // In fullscreen: anchor inside the player container at top-right
      if (barElement.parentElement !== container) {
        container.appendChild(barElement);
        if (menuElement) container.appendChild(menuElement);
      }
      barElement.style.position = "absolute";
      barElement.style.top = "12px";
      barElement.style.right = "16px";
      barElement.style.left = "auto";
      return;
    }

    // Normal mode: Anchor to document.body so it is NEVER clipped and sits ABOVE the video
    if (barElement.parentElement !== document.body) {
      document.body.appendChild(barElement);
      if (menuElement) document.body.appendChild(menuElement);
    }

    const rect = container.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    // Check if user manually dragged it
    const isManuallyDragged = sessionStorage.getItem("kdm_bar_manually_dragged") === "true";
    const savedLeft = sessionStorage.getItem("kdm_bar_drag_left");
    const savedTop = sessionStorage.getItem("kdm_bar_drag_top");

    if (isManuallyDragged && savedLeft !== null && savedTop !== null) {
      barElement.style.position = "absolute";
      barElement.style.left = savedLeft + "px";
      barElement.style.top = savedTop + "px";
      barElement.style.right = "auto";
    } else {
      // Symmetrical position: ABOVE the video on the RIGHT side!
      // Perfectly matches Cốc Cốc's toolbar height on the left without covering the video
      const barHeight = barElement.offsetHeight || 24;
      const barWidth = barElement.offsetWidth || 170;

      const videoTop = rect.top + window.scrollY;
      const videoRight = rect.right + window.scrollX;

      // Position ABOVE the video frame with a 4px gap:
      const targetTop = videoTop - barHeight - 4;
      // Align to the RIGHT side of the video (10px margin from right edge):
      const targetLeft = videoRight - barWidth - 10;

      barElement.style.position = "absolute";
      barElement.style.top = targetTop + "px";
      barElement.style.left = targetLeft + "px";
      barElement.style.right = "auto";
    }

    if (menuElement && menuElement.style.display === "block") {
      const bLeft = parseInt(barElement.style.left, 10) || 0;
      const bTop = parseInt(barElement.style.top, 10) || 0;
      const bHeight = barElement.offsetHeight || 24;
      const bWidth = barElement.offsetWidth || 170;
      const mWidth = menuElement.offsetWidth || 260;
      menuElement.style.position = "absolute";
      menuElement.style.top = (bTop + bHeight + 4) + "px";
      menuElement.style.left = Math.max(10, bLeft - mWidth + bWidth) + "px";
      menuElement.style.right = "auto";
    }
  }

  // Create or attach the floating download bar
  function showFloatingBar(mediaList = []) {
    if (isBarDismissed) return;
    if (mediaList && mediaList.length > 0) {
      capturedMediaList = mediaList;
    }

    const container = getPlayerContainer();
    if (!container) return;

    if (!barElement) {
      barElement = document.createElement("div");
      barElement.id = "kdm-video-bar";
      barElement.innerHTML = `
        <div class="kdm-drag-grip" title="Kéo thả để di chuyển vị trí">⋮⋮</div>
        <div class="kdm-main-btn" title="Bấm vào đây để tải video ngay lập tức (Chất lượng cao nhất)">
          <div class="kdm-icon">↓</div>
          <div class="kdm-text">Tải video này (KDM)</div>
        </div>
        <div class="kdm-arrow" title="Chọn độ phân giải (1080p, 720p, MP3...)">▾</div>
        <div class="kdm-close" title="Ẩn thanh này">×</div>
      `;

      menuElement = document.createElement("div");
      menuElement.id = "kdm-menu";

      // 1. Direct 1-Click Download on main button
      const mainBtn = barElement.querySelector(".kdm-main-btn");
      mainBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();

        if (capturedMediaList.length > 0) {
          triggerDirectStreamDownload(capturedMediaList[0]);
        } else {
          triggerPlatformDownload("best");
        }
        if (menuElement) menuElement.style.display = "none";
      });

      // 2. Toggle menu on arrow button
      const arrowBtn = barElement.querySelector(".kdm-arrow");
      arrowBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();

        const isCurrentlyOpen = menuElement.style.display === "block";
        if (isCurrentlyOpen) {
          menuElement.style.display = "none";
        } else {
          renderMenuContent();
          menuElement.classList.remove("kdm-hidden");
          menuElement.style.removeProperty("display");
          menuElement.style.display = "block";

          const bLeft = parseInt(barElement.style.left, 10) || barElement.offsetLeft || 0;
          const bTop = parseInt(barElement.style.top, 10) || barElement.offsetTop || 0;
          const bHeight = barElement.offsetHeight || 24;
          const bWidth = barElement.offsetWidth || 170;
          const mWidth = menuElement.offsetWidth || 260;

          menuElement.style.position = "absolute";
          menuElement.style.top = (bTop + bHeight + 4) + "px";
          menuElement.style.left = Math.max(10, bLeft - mWidth + bWidth) + "px";
          menuElement.style.right = "auto";
        }
      });

      // 3. Close button
      const closeBtn = barElement.querySelector(".kdm-close");
      const handleClose = (e) => {
        if (e) {
          e.preventDefault();
          e.stopPropagation();
          e.stopImmediatePropagation();
        }
        isBarDismissed = true;
        barElement.classList.add("kdm-hidden");
        barElement.style.setProperty("display", "none", "important");
        if (menuElement) {
          menuElement.classList.add("kdm-hidden");
          menuElement.style.setProperty("display", "none", "important");
        }
      };
      closeBtn.addEventListener("click", handleClose, true);
      closeBtn.addEventListener("mousedown", handleClose, true);

      // 4. Drag & drop support
      barElement.addEventListener("mousedown", (e) => {
        if (e.target.closest(".kdm-main-btn") || e.target.closest(".kdm-arrow") || e.target.closest(".kdm-close")) {
          return;
        }
        isDragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        barStartX = parseInt(barElement.style.left, 10) || barElement.offsetLeft || 0;
        barStartY = parseInt(barElement.style.top, 10) || barElement.offsetTop || 0;
        e.preventDefault();
        e.stopPropagation();
      });

      document.addEventListener("mousemove", (e) => {
        if (!isDragging || !barElement) return;
        const dx = e.clientX - dragStartX;
        const dy = e.clientY - dragStartY;
        const newLeft = Math.max(0, barStartX + dx);
        const newTop = Math.max(0, barStartY + dy);
        barElement.style.left = newLeft + "px";
        barElement.style.top = newTop + "px";
        barElement.style.right = "auto";
        if (menuElement && menuElement.style.display === "block") {
          const bWidth = barElement.offsetWidth || 170;
          const bHeight = barElement.offsetHeight || 24;
          const mWidth = menuElement.offsetWidth || 260;
          menuElement.style.left = Math.max(10, newLeft - mWidth + bWidth) + "px";
          menuElement.style.top = (newTop + bHeight + 4) + "px";
          menuElement.style.right = "auto";
        }
        sessionStorage.setItem("kdm_bar_manually_dragged", "true");
        sessionStorage.setItem("kdm_bar_drag_left", newLeft);
        sessionStorage.setItem("kdm_bar_drag_top", newTop);
      });

      document.addEventListener("mouseup", () => {
        isDragging = false;
      });

      // Prevent player from catching clicks inside menu
      menuElement.addEventListener("click", (e) => {
        e.stopPropagation();
      });
      menuElement.addEventListener("mousedown", (e) => {
        e.stopPropagation();
      });

      // Close menu on click outside
      document.addEventListener("click", (e) => {
        if (barElement && !barElement.contains(e.target) && menuElement && !menuElement.contains(e.target)) {
          menuElement.style.display = "none";
        }
      });

      window.addEventListener("scroll", updateBarPosition, { passive: true });
      window.addEventListener("resize", updateBarPosition, { passive: true });
      document.addEventListener("fullscreenchange", updateBarPosition);
      document.addEventListener("webkitfullscreenchange", updateBarPosition);
    }

    if (barElement.classList.contains("kdm-hidden")) {
      barElement.classList.remove("kdm-hidden");
    }
    barElement.style.removeProperty("display");
    barElement.style.display = "flex";

    updateBarPosition();
  }

  function renderMenuContent() {
    if (!menuElement) return;

    let html = `<div class="kdm-menu-header">KDM - Chọn chất lượng tải</div>`;

    // 1. Direct stream files (.m3u8, .mp4, etc.)
    if (capturedMediaList.length > 0) {
      capturedMediaList.forEach((item, idx) => {
        const shortName = item.filename.length > 30 ? item.filename.substring(0, 27) + "..." : item.filename;
        const tag = item.isM3U8 ? "🎬 HLS Stream (.m3u8)" : "📹 " + item.type;
        html += `
          <div class="kdm-menu-item kdm-stream-item" data-index="${idx}">
            <div class="kdm-item-title">${tag}</div>
            <div class="kdm-item-sub">${shortName}</div>
          </div>
        `;
      });
    }

    // 2. Options for YouTube / TikTok
    if (isKnownPlatform()) {
      html += `
        <div class="kdm-menu-item" data-action="best">🎬 Chất lượng cao nhất (Best Video)</div>
        <div class="kdm-menu-item" data-action="1080">📺 Full HD 1080p</div>
        <div class="kdm-menu-item" data-action="720">⚡ HD 720p</div>
        <div class="kdm-menu-item" data-action="audio">🎵 Tách riêng âm thanh (MP3 HQ)</div>
      `;
    }

    if (capturedMediaList.length === 0 && !isKnownPlatform()) {
      html += `
        <div class="kdm-menu-item" data-action="best">
          🎬 Tải Video trang này (Tự động quét tốt nhất)
        </div>
      `;
    }

    menuElement.innerHTML = html;

    // Attach listeners with stopPropagation
    menuElement.querySelectorAll(".kdm-stream-item").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const idx = parseInt(el.getAttribute("data-index"), 10);
        const item = capturedMediaList[idx];
        if (item) {
          triggerDirectStreamDownload(item);
        }
        menuElement.style.display = "none";
      });
    });

    menuElement.querySelectorAll("[data-action]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const action = el.getAttribute("data-action");
        triggerPlatformDownload(action);
        menuElement.style.display = "none";
      });
    });
  }

  function showNotification(text) {
    const notif = document.createElement("div");
    notif.className = "kdm-badge-notification";
    notif.textContent = text;
    document.body.appendChild(notif);
    setTimeout(() => {
      notif.style.transition = "opacity 0.4s ease";
      notif.style.opacity = "0";
      setTimeout(() => notif.remove(), 400);
    }, 3200);
  }

  function getCleanPageTitle() {
    let title = document.title || "video";
    return title.replace(/[\\/:*?"<>|]/g, "_").trim();
  }

  function triggerDirectStreamDownload(mediaItem) {
    let filename = getCleanPageTitle();
    if (!filename.toLowerCase().endsWith(".mp4")) {
      filename += ".mp4";
    }

    chrome.runtime.sendMessage(
      {
        action: "SEND_DOWNLOAD",
        url: mediaItem.url,
        filename: filename,
        is_video: true
      },
      (res) => {
        if (res && res.success) {
          showNotification("✓ Đã gửi sang KDM bắt đầu tải!");
        } else {
          showNotification("⚠️ Chưa bật phần mềm KDM trên máy!");
        }
      }
    );
  }

  function triggerPlatformDownload(action) {
    const rawUrl = window.location.href;
    const cleanUrl = getCleanVideoUrl(rawUrl);
    let format_id = null;

    if (action === "1080") format_id = "bestvideo[height<=1080]+bestaudio/best[height<=1080]";
    else if (action === "720") format_id = "bestvideo[height<=720]+bestaudio/best[height<=720]";
    else if (action === "audio") format_id = "bestaudio/best";

    chrome.runtime.sendMessage(
      {
        action: "SEND_DOWNLOAD",
        url: cleanUrl,
        filename: getCleanPageTitle() + ".mp4",
        is_video: true,
        format_id: format_id
      },
      (res) => {
        if (res && res.success) {
          showNotification("✓ Đã gửi sang KDM bắt đầu tải!");
        } else {
          showNotification("⚠️ Chưa bật phần mềm KDM trên máy!");
        }
      }
    );
  }

  // Listen for sniffed media messages from background.js
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === "MEDIA_SNIFFED") {
      showFloatingBar(msg.media);
    }
  });

  // Handle Alt (Force download with KDM) and Ctrl (Bypass KDM)
  document.addEventListener("click", (e) => {
    const link = e.target.closest("a");
    if (!link || !link.href) return;

    // Alt + Click: FORCE DOWNLOAD WITH KDM
    if (e.altKey) {
      e.preventDefault();
      e.stopPropagation();
      chrome.runtime.sendMessage({
        action: "SEND_DOWNLOAD",
        url: link.href,
        filename: link.download || ""
      });
      showNotification("⚡ Đã ép tải bằng KDM (Phím Alt)!");
      return false;
    }

    // Ctrl + Click: BYPASS KDM (Let browser download normally)
    if (e.ctrlKey) {
      chrome.runtime.sendMessage({
        action: "SET_BYPASS",
        url: link.href
      });
    }
  }, true);

  // Query background on start
  try {
    chrome.runtime.sendMessage({ action: "GET_TAB_MEDIA" }, (res) => {
      if (res && res.media && res.media.length > 0) {
        showFloatingBar(res.media);
      }
    });
  } catch (e) {}

  // Monitor DOM video elements & play events
  function hookVideoTags() {
    const videos = document.querySelectorAll("video");
    videos.forEach((v) => {
      if (!v.dataset.kdmHooked) {
        v.dataset.kdmHooked = "true";
        v.addEventListener("play", () => {
          showFloatingBar();
        });
        v.addEventListener("loadeddata", () => {
          showFloatingBar();
        });
      }
    });
    if (videos.length > 0 || isKnownPlatform()) {
      showFloatingBar();
    }
  }

  // Watch for page navigation (YouTube SPA)
  let lastHref = location.href;
  new MutationObserver(() => {
    if (location.href !== lastHref) {
      lastHref = location.href;
      isBarDismissed = false; // Reset dismissed state for the new video
      if (barElement) {
        barElement.classList.remove("kdm-hidden");
      }
      setTimeout(hookVideoTags, 600);
    } else if (!isBarDismissed) {
      updateBarPosition();
      hookVideoTags();
    }
  }).observe(document.body || document.documentElement, { childList: true, subtree: true });

  window.addEventListener("load", () => {
    setTimeout(hookVideoTags, 800);
  });
})();
