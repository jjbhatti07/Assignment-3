(() => {
  const PANEL_ID = "ai-email-responder-panel";
  const LAUNCHER_ID = "ai-email-responder-launcher";

  let lastCaptured = null;

  function cleanText(value) {
    return (value || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function getSubject() {
    const selectors = [
      'h2.hP',
      '[role="main"] h2.hP',
      '[role="main"] h2',
      'h2[data-thread-perm-id]',
      'h2'
    ];

    for (const selector of selectors) {
      const el = document.querySelector(selector);
      const text = cleanText(el?.innerText || el?.textContent);
      if (text) return text;
    }

    return "";
  }

  function getSender() {
    const selectors = [
      '.gD[email]',
      '.gD',
      '[email]',
      '[data-hovercard-id^="mailto:"]'
    ];

    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (!el) continue;

      const email = el.getAttribute("email");
      if (email) return email;

      const text = cleanText(el.innerText || el.textContent);
      if (text) return text;
    }

    return "";
  }

  function getBody() {
    const messageNodes = Array.from(
      document.querySelectorAll(".a3s.aiL")
    );

    if (messageNodes.length > 0) {
      return messageNodes
        .map(el => cleanText(el.innerText || el.textContent))
        .filter(Boolean)
        .join("\n\n");
    }

    const genericNodes = Array.from(
      document.querySelectorAll('[role="main"] .ii.gt')
    );

    if (genericNodes.length > 0) {
      return genericNodes
        .map(el => cleanText(el.innerText || el.textContent))
        .filter(Boolean)
        .join("\n\n");
    }

    const main = document.querySelector('[role="main"]');

    if (main) {
      return cleanText(main.innerText || main.textContent);
    }

    return "";
  }

  function captureEmail() {
    const email = {
      subject: getSubject(),
      sender: getSender(),
      body: getBody(),
      url: window.location.href,
      capturedAt: new Date().toISOString()
    };

    if (!email.body || email.body.length < 10) {
      throw new Error(
        "No email text detected. Open an email message first."
      );
    }

    lastCaptured = email;
    return email;
  }

  async function getApiUrl() {
    const data = await chrome.storage.local.get({
      apiUrl: "http://127.0.0.1:5002"
    });

    return String(data.apiUrl).replace(/\/$/, "");
  }

  function createLauncher() {
    if (document.getElementById(LAUNCHER_ID)) {
      return;
    }

    const launcher = document.createElement("button");

    launcher.id = LAUNCHER_ID;
    launcher.textContent = "✉ AI Reply";
    launcher.title = "Open Gmail AI Email Responder";

    launcher.addEventListener("click", () => {
      ensurePanel();
    });

    document.body.appendChild(launcher);
  }

  function ensurePanel() {
    let panel = document.getElementById(PANEL_ID);

    if (panel) {
      return panel;
    }

    panel = document.createElement("div");
    panel.id = PANEL_ID;

    panel.innerHTML = `
      <div class="air-header">
        <div>
          <div class="air-title">AI Email Responder</div>
          <div class="air-subtitle">Generate a suggested reply</div>
        </div>

        <button
          class="air-close"
          type="button"
          title="Close"
        >
          ×
        </button>
      </div>

      <div class="air-body">

        <div
          class="air-status"
          data-role="status"
        >
          Open an email and click Generate Reply.
        </div>

        <div class="air-email-preview">
          <div>
            <strong>Subject:</strong>
            <span data-role="subject">Not captured</span>
          </div>

          <div>
            <strong>Sender:</strong>
            <span data-role="sender">Not captured</span>
          </div>
        </div>

        <button
          class="air-primary"
          data-role="generate"
          type="button"
        >
          Generate Reply
        </button>

        <textarea
          class="air-output"
          data-role="output"
          placeholder="AI suggested response will appear here..."
        ></textarea>

        <div class="air-actions">

          <button
            type="button"
            data-role="copy"
          >
            Copy Reply
          </button>

          <button
            type="button"
            data-role="capture"
          >
            Capture Email
          </button>

        </div>

      </div>
    `;

    document.body.appendChild(panel);

    panel
      .querySelector(".air-close")
      .addEventListener("click", () => {
        panel.remove();
      });

    panel
      .querySelector('[data-role="capture"]')
      .addEventListener("click", () => {
        const status = panel.querySelector('[data-role="status"]');

        try {
          const email = captureEmail();

          updatePreview(panel, email);

          status.textContent =
            "Email captured successfully.";
        } catch (error) {
          status.textContent = error.message;
        }
      });

    panel
      .querySelector('[data-role="generate"]')
      .addEventListener("click", generateReply);

    panel
      .querySelector('[data-role="copy"]')
      .addEventListener("click", async () => {
        const output =
          panel.querySelector('[data-role="output"]');

        if (!output.value.trim()) {
          return;
        }

        await navigator.clipboard.writeText(output.value);

        panel.querySelector('[data-role="status"]')
          .textContent = "Suggested reply copied.";
      });

    return panel;
  }

  function updatePreview(panel, email) {
    panel.querySelector('[data-role="subject"]')
      .textContent = email.subject || "No subject";

    panel.querySelector('[data-role="sender"]')
      .textContent = email.sender || "Unknown sender";
  }

  async function generateReply() {
    const panel = ensurePanel();

    const status =
      panel.querySelector('[data-role="status"]');

    const output =
      panel.querySelector('[data-role="output"]');

    const button =
      panel.querySelector('[data-role="generate"]');

    button.disabled = true;
    output.value = "";

    status.textContent = "Capturing opened email...";

    try {
      const email = captureEmail();

      updatePreview(panel, email);

      status.textContent =
        "Sending email to AI service...";

      const apiUrl = await getApiUrl();

      const response = await fetch(
        `${apiUrl}/generate-reply`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify(email)
        }
      );

      const payload = await response.json();

      if (!response.ok) {
        throw new Error(
          payload.error ||
          `Request failed (${response.status})`
        );
      }

      output.value = payload.reply || "";

      status.textContent =
        "AI suggested response generated successfully.";

    } catch (error) {
      console.error(
        "Gmail AI Responder error:",
        error
      );

      status.textContent =
        error.message ||
        "Unable to generate response.";

    } finally {
      button.disabled = false;
    }
  }

  // Extension popup can ask content script to capture.
  chrome.runtime.onMessage.addListener(
    (message, sender, sendResponse) => {
      if (message?.type !== "CAPTURE_EMAIL") {
        return;
      }

      try {
        const email = captureEmail();

        const panel = ensurePanel();

        updatePreview(panel, email);

        panel.querySelector(
          '[data-role="status"]'
        ).textContent =
          "Email captured successfully.";

        sendResponse({
          ok: true,
          subject: email.subject
        });

      } catch (error) {
        sendResponse({
          ok: false,
          error: error.message
        });
      }

      return true;
    }
  );

  // Always provide a visible launcher on Gmail.
  function initialize() {
    createLauncher();
  }

  // Gmail is a single-page application.
  // Keep watching for page changes.
  const observer = new MutationObserver(() => {
    if (!document.getElementById(LAUNCHER_ID)) {
      createLauncher();
    }
  });

  observer.observe(
    document.documentElement,
    {
      childList: true,
      subtree: true
    }
  );

  initialize();
})();
