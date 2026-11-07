document.addEventListener("DOMContentLoaded", () => {
  const statusBadge = document.getElementById("status-badge");
  const statusText = document.getElementById("status-text");
  const detectedContainer = document.getElementById("detected-container");
  const urlInput = document.getElementById("url-input");
  const btnDownload = document.getElementById("btn-download");
  const interceptToggle = document.getElementById("intercept-toggle");

  // Check KDM status
  chrome.runtime.sendMessage({ action: "CHECK_STATUS" }, (res) => {
    if (res && res.running) {
      statusBadge.classList.add("online");
      statusText.textContent = "KDM Sẵn sàng";
    } else {
      statusBadge.classList.remove("online");
      statusText.textContent = "Chưa bật KDM";
    }
  });

  // Load toggle state
  chrome.storage.local.get(["interceptEnabled"], (data) => {
    if (data.interceptEnabled !== undefined) {
      interceptToggle.checked = data.interceptEnabled;
    }
  });

  interceptToggle.addEventListener("change", () => {
    chrome.storage.local.set({ interceptEnabled: interceptToggle.checked });
  });

  // Query detected media streams on current active tab
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || !tabs[0]) return;
    const currentTab = tabs[0];

    chrome.runtime.sendMessage({ action: "GET_TAB_MEDIA", tabId: currentTab.id }, (res) => {
      if (res && res.media && res.media.length > 0) {
        renderDetectedMedia(res.media, currentTab.title);
      } else {
        detectedContainer.innerHTML = `
          <div class="no-media">Chưa thấy luồng video nào.<br>Hãy bấm <b>Play video</b> trên web để KDM bắt link!</div>
        `;
      }
    });
  });

  function renderDetectedMedia(mediaList, pageTitle) {
    detectedContainer.innerHTML = "";
    mediaList.forEach((item, idx) => {
      const row = document.createElement("div");
      row.className = "media-row";

      const title = item.isM3U8 ? "🎬 HLS Stream (.m3u8)" : item.filename;
      row.innerHTML = `
        <div class="media-info">
          <div class="media-title" title="${item.url}">${title}</div>
          <div class="media-type">${item.type}</div>
        </div>
        <button class="btn-download-media" data-index="${idx}">Tải Ngay</button>
      `;

      row.querySelector(".btn-download-media").addEventListener("click", () => {
        const cleanTitle = (pageTitle || "video").replace(/[\\/:*?"<>|]/g, "_") + ".mp4";
        chrome.runtime.sendMessage({
          action: "SEND_DOWNLOAD",
          url: item.url,
          filename: cleanTitle,
          is_video: true
        }, (resp) => {
          if (resp && resp.success) {
            alert("✓ Đã gửi sang KDM bắt đầu tải!");
          } else {
            alert("⚠️ Chưa bật phần mềm KDM trên máy!");
          }
        });
      });

      detectedContainer.appendChild(row);
    });
  }

  // Download custom URL
  btnDownload.addEventListener("click", () => {
    const url = urlInput.value.trim();
    if (!url) return;

    const isVideo = url.includes("youtube.com") || url.includes("youtu.be") ||
                    url.includes("tiktok.com") || url.includes("facebook.com") ||
                    url.includes(".m3u8") || url.includes(".mp4");

    btnDownload.textContent = "Đang gửi sang KDM...";
    chrome.runtime.sendMessage(
      {
        action: "SEND_DOWNLOAD",
        url: url,
        is_video: isVideo
      },
      (res) => {
        if (res && res.success) {
          btnDownload.textContent = "✓ Đã gửi thành công!";
          setTimeout(() => {
            btnDownload.textContent = "🚀 Tải bằng KDM";
            urlInput.value = "";
          }, 1500);
        } else {
          alert("Không thể kết nối với KDM. Hãy chắc chắn phần mềm KDM đang mở!");
          btnDownload.textContent = "🚀 Tải bằng KDM";
        }
      }
    );
  });
});
