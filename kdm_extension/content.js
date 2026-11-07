/**
 * KDM - Kevin Download Manager
 * Content Script: Compact, Top-Left Floating Download Bar & Universal Video Sniffer
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

  // Find the exact video player container to anchor the bar inside
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
        const pos = window.getComputedStyle(player).position;
        if (pos === "static") {
          player.style.position = "relative";
        }
        return player;
      }
    }

    return null;
  }

  // Create or attach the floating download bar
  function showFloatingBar(mediaList = []) {
    if (isBarDismissed) return;
    if (mediaList && mediaList.length > 0) {
      capturedMediaList = mediaList;
    }

    const container = getPlayerContainer();

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
          menuElement.style.position = "absolute";
          menuElement.style.left = (barElement.offsetLeft || 10) + "px";
          menuElement.style.top = (barElement.offsetTop + 32) + "px";
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
        barStartX = barElement.offsetLeft;
        barStartY = barElement.offsetTop;
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
        if (menuElement) {
          menuElement.style.left = newLeft + "px";
          menuElement.style.top = (newTop + 32) + "px";
          menuElement.style.right = "auto";
        }
        sessionStorage.setItem("kdm_bar_left", newLeft);
        sessionStorage.setItem("kdm_bar_top", newTop);
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
    }

    // Anchor to player container if found, otherwise body
    const targetParent = container || document.body;
    if (barElement.parentElement !== targetParent) {
      targetParent.appendChild(barElement);
      targetParent.appendChild(menuElement);
    }

    // Default position: Top-Left (above video playback area, matching Cốc Cốc / IDM style)
    const savedLeft = sessionStorage.getItem("kdm_bar_left");
    const savedTop = sessionStorage.getItem("kdm_bar_top");

    if (savedLeft !== null && savedTop !== null) {
      barElement.style.position = container ? "absolute" : "fixed";
      barElement.style.left = savedLeft + "px";
      barElement.style.top = savedTop + "px";
      barElement.style.right = "auto";
    } else {
      barElement.style.position = container ? "absolute" : "fixed";
      barElement.style.left = "10px";
      barElement.style.top = "6px";
      barElement.style.right = "auto";
    }

    if (barElement.classList.contains("kdm-hidden")) {
      barElement.classList.remove("kdm-hidden");
    }
    barElement.style.removeProperty("display");
    barElement.style.display = "flex";
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
      hookVideoTags();
    }
  }).observe(document.body || document.documentElement, { childList: true, subtree: true });

  window.addEventListener("load", () => {
    setTimeout(hookVideoTags, 800);
  });
})();
