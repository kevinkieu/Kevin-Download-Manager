/**
 * KDM - Kevin Download Manager
 * Background Service Worker & Universal Network Sniffer (IDM Style)
 */

const KDM_SERVER = "http://127.0.0.1:59123";

// Default file extensions to capture from direct browser downloads (IDM Standard)
const DEFAULT_EXTENSIONS_STR = "3GP 7Z AAC ACE AIF APK ARJ ASF AVI BIN BZ2 DMG DOC DOCX EPUB EXE FLAC FLV GZ GZIP IMG ISO LZH M4A M4V MKV MOV MP3 MP4 MPA MPE MPEG MPG MSI MSU OGG OGV PDF PKG PLJ PPS PPT PPTX QT RA RAR RM RMVB SEA SIT SITX TAR TIF TIFF TORRENT TS VOB WAV WEBM WMA WMV Z ZIP";

let activeExtensions = new Set();

function updateActiveExtensions(extStr) {
  if (!extStr || typeof extStr !== "string") extStr = DEFAULT_EXTENSIONS_STR;
  activeExtensions.clear();
  const tokens = extStr.replace(/,/g, " ").split(/\s+/);
  for (let t of tokens) {
    t = t.trim().toLowerCase().replace(/^\./, "");
    if (t) {
      activeExtensions.add(t);
    }
  }
}

// Initialize active extensions
updateActiveExtensions(DEFAULT_EXTENSIONS_STR);
chrome.storage.local.get(["interceptExtensions"], (data) => {
  if (data && data.interceptExtensions) {
    updateActiveExtensions(data.interceptExtensions);
  }
});

// Store detected media streams per Tab ID: { [tabId]: Array<{ url, type, filename, size }> }
const tabMediaMap = {};
const bypassUrls = {};

// Clean up tabs when closed or navigated
chrome.tabs.onRemoved.addListener((tabId) => {
  delete tabMediaMap[tabId];
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading") {
    tabMediaMap[tabId] = [];
    chrome.action.setBadgeText({ tabId, text: "" });
  }
});

// Initialize settings
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({
    interceptEnabled: true,
    showVideoBadge: true
  });

  // Create Context Menus
  chrome.contextMenus.create({
    id: "kdm_download_link",
    title: "Tải bằng KDM (Download with KDM)",
    contexts: ["link", "video", "audio", "image"]
  });

  chrome.contextMenus.create({
    id: "kdm_download_page_video",
    title: "Tải Video / Phim trang này bằng KDM",
    contexts: ["page"]
  });
});

// Handle Context Menu Clicks
chrome.contextMenus.onClicked.addListener((info, tab) => {
  let targetUrl = info.linkUrl || info.srcUrl;

  if (info.menuItemId === "kdm_download_page_video") {
    // Check if we captured any media stream for this tab
    const detected = tabMediaMap[tab.id] || [];
    if (detected.length > 0) {
      const media = detected[0];
      sendToKDM(media.url, media.filename, true);
      return;
    }
    // Fallback to tab page URL (yt-dlp can parse page)
    sendToKDM(tab.url, (tab.title || "video").replace(/[\\/:*?"<>|]/g, "_") + ".mp4", true);
    return;
  }

  if (targetUrl) {
    const isVideo = isMediaUrl(targetUrl);
    sendToKDM(targetUrl, "", isVideo);
  }
});

function isMediaUrl(url) {
  if (!url) return false;
  const clean = url.split("?")[0].toLowerCase();
  return clean.endsWith(".m3u8") || clean.endsWith(".mp4") || clean.endsWith(".mkv") ||
         clean.endsWith(".webm") || clean.endsWith(".ts") || clean.endsWith(".mpd") ||
         clean.endsWith(".flv") || clean.endsWith(".avi") || clean.endsWith(".mov");
}

function extractFilenameFromUrl(url) {
  try {
    const clean = url.split("?")[0].split("#")[0];
    const base = clean.split("/").pop();
    if (base && base.includes(".")) {
      return decodeURIComponent(base);
    }
  } catch (e) {}
  return "video_stream.mp4";
}

// ============================================================
// UNIVERSAL MEDIA STREAM SNIFFER (IDM NETWORK INSPECTOR)
// ============================================================
chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    // Ignore non-tab requests (e.g. extension internal requests)
    if (details.tabId < 0) return;

    const url = details.url;
    let contentType = "";
    let contentLength = 0;

    if (details.responseHeaders) {
      for (const h of details.responseHeaders) {
        const name = h.name.toLowerCase();
        if (name === "content-type") {
          contentType = (h.value || "").toLowerCase();
        } else if (name === "content-length") {
          contentLength = parseInt(h.value, 10) || 0;
        }
      }
    }

    const isVideoMime = contentType.startsWith("video/") ||
                        contentType.includes("mpegurl") ||
                        contentType.includes("application/vnd.apple.mpegurl") ||
                        contentType.includes("application/x-mpegurl") ||
                        contentType.includes("application/dash+xml");

    const isVideoExtension = isMediaUrl(url);

    if (isVideoMime || isVideoExtension) {
      // Filter out tiny audio or tracking beacons (< 50KB unless it's an m3u8 playlist)
      const isM3U8 = url.includes(".m3u8") || contentType.includes("mpegurl");
      if (!isM3U8 && contentLength > 0 && contentLength < 50000) {
        return;
      }

      if (!tabMediaMap[details.tabId]) {
        tabMediaMap[details.tabId] = [];
      }

      // Check for duplicates
      const exists = tabMediaMap[details.tabId].some(m => m.url === url);
      if (!exists) {
        // If it's a ts segment and we already have an m3u8 playlist, ignore individual TS chunks
        if (url.includes(".ts") && tabMediaMap[details.tabId].some(m => m.isM3U8)) {
          return;
        }

        const mediaItem = {
          url: url,
          type: isM3U8 ? "HLS Stream (.m3u8)" : (contentType || "Video Stream"),
          filename: extractFilenameFromUrl(url),
          isM3U8: isM3U8,
          timestamp: Date.now()
        };

        // If it's m3u8, put it at the very top (highest priority for full movie download)
        if (isM3U8) {
          tabMediaMap[details.tabId].unshift(mediaItem);
        } else {
          tabMediaMap[details.tabId].push(mediaItem);
        }

        // Limit to 10 recent media files per tab
        if (tabMediaMap[details.tabId].length > 10) {
          tabMediaMap[details.tabId].pop();
        }

        // Show badge on Extension Icon: "1", "2"...
        const count = tabMediaMap[details.tabId].length;
        chrome.action.setBadgeText({ tabId: details.tabId, text: count.toString() });
        chrome.action.setBadgeBackgroundColor({ tabId: details.tabId, color: "#2563eb" });

        // Notify content script in the tab so it can display the floating download bar
        chrome.tabs.sendMessage(details.tabId, {
          action: "MEDIA_SNIFFED",
          media: tabMediaMap[details.tabId]
        }).catch(() => {
          // Content script may not be ready yet
        });
      }
    }
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"]
);

// Check if KDM Server is reachable & sync custom extensions
async function isKDMRunning() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1200);
    const res = await fetch(`${KDM_SERVER}/status`, { signal: controller.signal });
    clearTimeout(timeoutId);
    if (res.ok) {
      try {
        const data = await res.json();
        if (data && data.intercept_extensions) {
          updateActiveExtensions(data.intercept_extensions);
          chrome.storage.local.set({ interceptExtensions: data.intercept_extensions });
        }
      } catch (e) {}
      return true;
    }
    return false;
  } catch (e) {
    return false;
  }
}

// Send download task to KDM desktop app
async function sendToKDM(url, filename = "", is_video = false, format_id = null, referrer = "") {
  try {
    const res = await fetch(`${KDM_SERVER}/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url,
        filename: filename,
        is_video: is_video,
        format_id: format_id,
        referrer: referrer,
        start_now: true
      })
    });
    return await res.json();
  } catch (e) {
    console.error("KDM is not running:", e);
    return { error: "KDM is not running. Please start KDM first." };
  }
}

function extractFileExtension(filename, url) {
  let name = (filename || "").trim();
  if (!name && url) {
    try {
      name = new URL(url).pathname.split("/").pop() || "";
    } catch (e) {}
  }
  const clean = name.split("?")[0].split("#")[0];
  if (clean.includes(".")) {
    return clean.split(".").pop().toLowerCase();
  }
  return "";
}

// Intercept browser file downloads
chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  chrome.storage.local.get(["interceptEnabled"], async (data) => {
    if (data.interceptEnabled === false) {
      suggest();
      return;
    }

    const itemUrl = item.finalUrl || item.url;
    // Check if user bypassed this download with Ctrl + Click
    if (bypassUrls[itemUrl] && (Date.now() - bypassUrls[itemUrl] < 15000)) {
      delete bypassUrls[itemUrl];
      suggest();
      return;
    }

    const ext = extractFileExtension(item.filename, itemUrl);
    const shouldIntercept = activeExtensions.has(ext);

    if (shouldIntercept) {
      const running = await isKDMRunning();
      if (running) {
        chrome.downloads.cancel(item.id);
        chrome.downloads.erase({ id: item.id });
        sendToKDM(item.finalUrl || item.url, item.filename, false, null, item.referrer || "");
        return;
      }
    }

    suggest();
  });
  return true;
});

// Messages from content scripts & popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "GET_EXTENSIONS") {
    chrome.storage.local.get(["interceptExtensions"], (data) => {
      sendResponse({ extensions: data.interceptExtensions || DEFAULT_EXTENSIONS_STR });
    });
    return true;
  }

  if (request.action === "UPDATE_EXTENSIONS") {
    if (request.extensions) {
      updateActiveExtensions(request.extensions);
      chrome.storage.local.set({ interceptExtensions: request.extensions });
    }
    sendResponse({ success: true, count: activeExtensions.size });
    return true;
  }
  if (request.action === "SET_BYPASS") {
    bypassUrls[request.url] = Date.now();
    sendResponse({ success: true });
    return true;
  }

  if (request.action === "CHECK_STATUS") {
    isKDMRunning().then(running => sendResponse({ running }));
    return true;
  }

  if (request.action === "GET_TAB_MEDIA") {
    const tabId = request.tabId || (sender.tab && sender.tab.id);
    const media = (tabId && tabMediaMap[tabId]) ? tabMediaMap[tabId] : [];
    sendResponse({ media });
    return true;
  }

  if (request.action === "SEND_DOWNLOAD") {
    const referrer = request.referrer || (sender.tab ? sender.tab.url : "");
    sendToKDM(request.url, request.filename, request.is_video, request.format_id, referrer)
      .then(result => sendResponse(result));
    return true;
  }

  if (request.action === "GET_VIDEO_INFO") {
    fetch(`${KDM_SERVER}/video_info`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: request.url })
    })
      .then(res => res.json())
      .then(data => sendResponse(data))
      .catch(err => sendResponse({ error: err.toString() }));
    return true;
  }
});
