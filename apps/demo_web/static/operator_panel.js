(() => {
  const PANEL_ID = "caliper-operator-panel";
  const STYLE_ID = "caliper-operator-panel-style";

  const randomVisitorId = () => {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return `operator-${crypto.randomUUID().slice(0, 12)}`;
    }
    return `operator-${Math.random().toString(36).slice(2, 14)}`;
  };

  const readCookie = (name) => {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : null;
  };

  const clearCookie = (name) => {
    document.cookie = `${name}=; Max-Age=0; path=/`;
  };

  const withCurrentPageUrl = (config, mutator) => {
    const current = new URL(window.location.href);
    if (config.landingPath && current.pathname !== config.landingPath) {
      current.pathname = config.landingPath;
    }
    mutator(current);
    window.location.assign(current.toString());
  };

  const ensureStyle = () => {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #${PANEL_ID} {
        position: fixed;
        right: 14px;
        bottom: 14px;
        width: min(360px, calc(100vw - 28px));
        z-index: 2147483000;
        font-family: Inter, system-ui, -apple-system, sans-serif;
        font-size: 13px;
        line-height: 1.35;
        color: #e2e8f0;
        background: rgba(15, 23, 42, 0.94);
        border: 1px solid rgba(148, 163, 184, 0.28);
        border-radius: 14px;
        box-shadow: 0 18px 42px rgba(2, 6, 23, 0.45);
        backdrop-filter: blur(4px);
      }

      #${PANEL_ID} * {
        box-sizing: border-box;
      }

      #${PANEL_ID} .op-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        padding: 10px 12px 8px;
        border-bottom: 1px solid rgba(148, 163, 184, 0.22);
      }

      #${PANEL_ID} .op-header strong {
        font-size: 13px;
        letter-spacing: 0.01em;
      }

      #${PANEL_ID} .op-body {
        padding: 10px 12px 12px;
      }

      #${PANEL_ID} .op-grid {
        display: grid;
        grid-template-columns: minmax(104px, auto) 1fr;
        gap: 6px 10px;
      }

      #${PANEL_ID} .op-label {
        color: #94a3b8;
      }

      #${PANEL_ID} .op-value {
        color: #f8fafc;
        word-break: break-word;
      }

      #${PANEL_ID} code {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 12px;
        color: #bae6fd;
        background: rgba(8, 47, 73, 0.35);
        border: 1px solid rgba(56, 189, 248, 0.22);
        border-radius: 6px;
        padding: 2px 5px;
      }

      #${PANEL_ID} .op-health[data-state="ok"] {
        color: #86efac;
      }

      #${PANEL_ID} .op-health[data-state="error"] {
        color: #fca5a5;
      }

      #${PANEL_ID} .op-actions {
        margin-top: 12px;
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
      }

      #${PANEL_ID} button {
        border: 1px solid rgba(148, 163, 184, 0.35);
        background: rgba(30, 41, 59, 0.88);
        color: #f8fafc;
        border-radius: 9px;
        padding: 8px 10px;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
      }

      #${PANEL_ID} button:hover {
        border-color: rgba(56, 189, 248, 0.65);
        background: rgba(30, 41, 59, 1);
      }

      #${PANEL_ID} .op-hint {
        margin-top: 8px;
        color: #94a3b8;
        font-size: 11px;
      }
    `;
    document.head.appendChild(style);
  };

  const setText = (root, selector, value) => {
    const element = root.querySelector(selector);
    if (element) {
      element.textContent = value || "unknown";
    }
  };

  function bootstrapLandingOperatorPanel(config = {}) {
    if (typeof document === "undefined") {
      return null;
    }

    const existing = document.getElementById(PANEL_ID);
    if (existing) {
      existing.remove();
    }

    ensureStyle();

    const panel = document.createElement("aside");
    panel.id = PANEL_ID;
    panel.innerHTML = `
      <div class="op-header">
        <strong>Caliper Operator Panel</strong>
        <span class="op-health" data-state="pending" data-ref="health">checking…</span>
      </div>
      <div class="op-body">
        <div class="op-grid">
          <span class="op-label">Topic</span><span class="op-value" data-ref="topic"></span>
          <span class="op-label">Visitor</span><span class="op-value"><code data-ref="visitor"></code></span>
          <span class="op-label">Decision</span><span class="op-value"><code data-ref="decision"></code></span>
          <span class="op-label">Arm</span><span class="op-value"><code data-ref="arm"></code></span>
          <span class="op-label">Backend</span><span class="op-value" data-ref="backend"></span>
          <span class="op-label">Telemetry</span><span class="op-value" data-ref="telemetry"></span>
        </div>
        <div class="op-actions">
          <button type="button" data-action="reset">Reset identity</button>
          <button type="button" data-action="force-new">Force new visitor</button>
        </div>
        <div class="op-hint">
          Controls reload this page with operator_action + force_new_visitor query params.
        </div>
      </div>
    `;

    document.body.appendChild(panel);

    const forceParam = config.forceVisitorQueryParam || "force_new_visitor";
    const actionParam = config.actionQueryParam || "operator_action";

    const refreshIdentityFields = () => {
      setText(panel, "[data-ref='topic']", config.topic || "(untitled demo)");
      setText(panel, "[data-ref='visitor']", readCookie("caliper_visitor_id") || config.visitorId);
      setText(panel, "[data-ref='decision']", readCookie("caliper_decision_id") || config.decisionId);
      setText(panel, "[data-ref='arm']", readCookie("caliper_arm_id") || config.armId);
      setText(panel, "[data-ref='backend']", config.backendMode || "unknown");
      setText(panel, "[data-ref='telemetry']", config.telemetryMode || "unknown");
    };

    const updateHealth = async () => {
      const healthEl = panel.querySelector("[data-ref='health']");
      if (!healthEl) {
        return;
      }

      const healthEndpoint = config.healthEndpoint || "/healthz";
      try {
        const response = await fetch(healthEndpoint, {
          method: "GET",
          credentials: "same-origin",
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`health ${response.status}`);
        }
        const payload = await response.json();
        healthEl.textContent = "healthy";
        healthEl.setAttribute("data-state", "ok");

        if (payload && typeof payload === "object") {
          if (typeof payload.backend === "string" && payload.backend) {
            setText(panel, "[data-ref='backend']", payload.backend);
          }
          if (typeof payload.telemetry_mode === "string" && payload.telemetry_mode) {
            setText(panel, "[data-ref='telemetry']", payload.telemetry_mode);
          }
        }
      } catch {
        healthEl.textContent = "unreachable";
        healthEl.setAttribute("data-state", "error");
      }
    };

    const forceNewVisitor = (actionLabel) => {
      withCurrentPageUrl(config, (url) => {
        url.searchParams.set(forceParam, "1");
        url.searchParams.set(actionParam, actionLabel);
        url.searchParams.set("visitor_id", randomVisitorId());
      });
    };

    const onPanelClick = (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      if (target.getAttribute("data-action") === "reset") {
        clearCookie("caliper_visitor_id");
        clearCookie("caliper_decision_id");
        clearCookie("caliper_arm_id");
        forceNewVisitor("reset_identity");
        return;
      }

      if (target.getAttribute("data-action") === "force-new") {
        forceNewVisitor("force_new_visitor");
      }
    };

    panel.addEventListener("click", onPanelClick);
    refreshIdentityFields();
    void updateHealth();

    const healthTimer = window.setInterval(() => {
      void updateHealth();
    }, 15_000);

    return {
      panel,
      refresh: refreshIdentityFields,
      destroy() {
        panel.removeEventListener("click", onPanelClick);
        window.clearInterval(healthTimer);
        panel.remove();
      },
    };
  }

  if (typeof window !== "undefined") {
    window.CaliperOperatorPanel = {
      bootstrapLandingOperatorPanel,
    };
  }
})();
