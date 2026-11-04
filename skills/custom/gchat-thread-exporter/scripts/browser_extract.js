/**
 * Zero-API-Key Browser DevTools Extractor for Google Chat Threads.
 *
 * Usage:
 * 1. Open the target thread URL in Chrome/Edge (logged in), e.g.:
 *    https://chat.google.com/u/0/app/chat/AAAA9sg0Pfc/topic/K2bBfiSrccc
 * 2. Open DevTools (F12 or Ctrl+Shift+I -> Console), paste this script, press Enter.
 * 3. Wait a few seconds while it scrolls up to load all replies and captures images.
 * 4. It automatically downloads `gchat-thread-<id>.json`.
 * 5. Convert to Markdown + local images folder:
 *    python3 scripts/export_gchat_thread.py --from-browser-json ~/Downloads/gchat-thread-<id>.json
 */
(async function exportGoogleChatThreadFromDOM() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function collectCandidateDocs() {
    const docs = [document];
    for (const frame of Array.from(document.querySelectorAll("iframe"))) {
      try {
        if (frame.contentDocument) docs.push(frame.contentDocument);
      } catch (_) {
        // Cross-origin frame; ignore
      }
    }
    return docs;
  }

  function findMessageNodes(doc) {
    const selectors = [
      '[data-message-id]',
      'c-wiz[data-p*="spaces/"]',
      '[role="listitem"][data-id]',
      'div[jscontroller][data-topic-id] [data-message-id]',
    ];
    for (const sel of selectors) {
      const found = Array.from(doc.querySelectorAll(sel)).filter(
        (el) => (el.innerText || "").trim().length > 0 || el.querySelector("img")
      );
      if (found.length > 0) return found;
    }
    return [];
  }

  const docs = collectCandidateDocs();
  let activeDoc = document;
  let bestNodes = [];
  for (const d of docs) {
    const nodes = findMessageNodes(d);
    if (nodes.length > bestNodes.length) {
      bestNodes = nodes;
      activeDoc = d;
    }
  }

  if (bestNodes.length === 0) {
    console.error(
      "[GChat Exporter] Không tìm thấy tin nhắn trên trang hiện tại. Hãy mở trực tiếp link thread (/topic/<ID>) và đợi trang tải xong."
    );
    return;
  }

  // Locate scrollable parent to load lazy-loaded earlier messages in the thread
  function findScrollableParent(el) {
    let cur = el ? el.parentElement : null;
    while (cur) {
      const style = activeDoc.defaultView.getComputedStyle(cur);
      if (/(auto|scroll)/.test(style.overflowY) && cur.scrollHeight > cur.clientHeight + 40) {
        return cur;
      }
      cur = cur.parentElement;
    }
    return null;
  }

  const scroller = findScrollableParent(bestNodes[0]);
  if (scroller) {
    console.log("[GChat Exporter] Đang cuộn lên đầu thread để tải toàn bộ lịch sử tin nhắn...");
    let stableRounds = 0;
    let prevCount = 0;
    for (let i = 0; i < 25; i++) {
      scroller.scrollTop = 0;
      await sleep(650);
      // Click "Load more" / collapsed replies buttons inside the thread if present
      const expandBtns = Array.from(activeDoc.querySelectorAll('button, [role="button"]')).filter((b) => {
        const t = (b.innerText || "").toLowerCase();
        return (
          /replies|phản hồi|xem thêm|more messages|load more|\d+\s+more/i.test(t) &&
          !b.closest('[aria-label*="navigation" i]')
        );
      });
      for (const btn of expandBtns.slice(0, 3)) {
        try {
          btn.click();
          await sleep(400);
        } catch (_) {}
      }
      const curCount = findMessageNodes(activeDoc).length;
      if (curCount === prevCount) {
        stableRounds++;
        if (stableRounds >= 3) break;
      } else {
        stableRounds = 0;
        prevCount = curCount;
      }
    }
    scroller.scrollTop = scroller.scrollHeight;
    await sleep(400);
  }

  const messageNodes = findMessageNodes(activeDoc);
  console.log(`[GChat Exporter] Đã thu thập ${messageNodes.length} khối tin nhắn. Đang trích xuất nội dung & hình ảnh...`);

  async function blobToDataURL(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  async function fetchImageAsDataURL(src) {
    try {
      const resp = await fetch(src, { credentials: "include" });
      if (!resp.ok) return null;
      const blob = await resp.blob();
      if (blob.size < 80) return null;
      return await blobToDataURL(blob);
    } catch (_) {
      return null;
    }
  }

  function isAvatarOrEmojiImage(img) {
    const src = img.currentSrc || img.src || "";
    const alt = (img.alt || "").toLowerCase();
    const w = img.naturalWidth || img.width || 0;
    const h = img.naturalHeight || img.height || 0;
    if (!src) return true;
    if (src.includes("fonts.gstatic.com") || src.includes("/emoji/")) return true;
    if (src.includes("/a/") && src.includes("googleusercontent.com") && w > 0 && w <= 64 && h <= 64) {
      return true; // user avatar
    }
    if (img.closest('[aria-label*="avatar" i], [data-member-id] img')) return true;
    if (w > 0 && w <= 28 && h > 0 && h <= 28 && alt.length <= 4) return true;
    return false;
  }

  let lastSender = "Unknown";
  const messages = [];

  for (const node of messageNodes) {
    const senderEl = node.querySelector(
      '[data-sender-name], [data-name], span[dir="auto"][data-hovercard-id], [aria-label][data-member-id]'
    );
    const senderText =
      (senderEl && (senderEl.getAttribute("data-sender-name") || senderEl.innerText || "").trim()) ||
      lastSender;
    if (senderText && senderText !== "Unknown") lastSender = senderText;

    const timeEl = node.querySelector("time, [data-absolute-timestamp], span[aria-label*=':']");
    const timestamp =
      (timeEl &&
        (timeEl.getAttribute("datetime") ||
          timeEl.getAttribute("title") ||
          timeEl.getAttribute("aria-label") ||
          timeEl.innerText ||
          "").trim()) ||
      "";

    // Extract main message body text cleanly
    const bodyEl =
      node.querySelector('[data-message-text], [dir="auto"].Zc1Emd, .DTp27d, [jsname="bgckF"]') || node;
    let text = (bodyEl.innerText || "").trim();
    if (bodyEl === node && senderText && text.startsWith(senderText)) {
      text = text.slice(senderText.length).trim();
    }

    const images = [];
    const seenSrc = new Set();
    for (const img of Array.from(node.querySelectorAll("img"))) {
      if (isAvatarOrEmojiImage(img)) continue;
      // Prefer full-res parent anchor href if pointing to image download/preview
      const parentLink = img.closest("a[href]");
      const src = img.currentSrc || img.src;
      if (!src || seenSrc.has(src)) continue;
      seenSrc.add(src);

      const dataUrl = await fetchImageAsDataURL(src);
      images.push({
        alt: img.alt || img.title || "image",
        src: (parentLink && parentLink.href) || src,
        data_url: dataUrl,
      });
    }

    if (!text && images.length === 0) continue;

    messages.push({
      message_id: node.getAttribute("data-message-id") || "",
      sender: senderText,
      timestamp,
      text,
      images,
    });
  }

  const url = window.location.href;
  const match = url.match(/\/app\/chat\/([^/?#]+)\/(?:topic|thread)\/([^/?#]+)/);
  const spaceId = match ? match[1] : "unknown-space";
  const threadId = match ? match[2] : "thread";
  const payload = {
    exported_at: new Date().toISOString(),
    url,
    title: document.title,
    space_id: `spaces/${spaceId}`,
    thread_id: `spaces/${spaceId}/threads/${threadId}`,
    messages,
  };

  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `gchat-thread-${threadId}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();

  console.log(
    `[GChat Exporter] Hoàn tất! Đã tải xuống gchat-thread-${threadId}.json (${messages.length} tin nhắn).`
  );
})();
