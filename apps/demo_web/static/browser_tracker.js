(() => {
  const DEFAULT_RETRY = {
    enabled: true,
    maxAttempts: 5,
    baseDelayMs: 400,
    maxDelayMs: 20_000,
    jitterRatio: 0.2,
    maxQueueSize: 200,
    persist: true,
  };

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const nowMs = () => Date.now();

  const randomId = () => {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    return `evt-${Math.random().toString(36).slice(2)}-${nowMs()}`;
  };

  const asNumber = (value, fallback) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return fallback;
    }
    return parsed;
  };

  const clampJitter = (value) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 0) {
      return DEFAULT_RETRY.jitterRatio;
    }
    return Math.min(1, parsed);
  };

  const safeStorage = {
    getItem(key) {
      try {
        return window.localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    setItem(key, value) {
      try {
        window.localStorage.setItem(key, value);
      } catch {
        // Best-effort persistence only.
      }
    },
    removeItem(key) {
      try {
        window.localStorage.removeItem(key);
      } catch {
        // Best-effort persistence only.
      }
    },
  };

  function createCaliperLandingTracker(options) {
    if (!options || !options.endpointPath) {
      throw new Error("createCaliperLandingTracker requires endpointPath");
    }

    const retry = {
      ...DEFAULT_RETRY,
      ...(options.retry || {}),
    };

    retry.maxAttempts = asNumber(retry.maxAttempts, DEFAULT_RETRY.maxAttempts);
    retry.baseDelayMs = asNumber(retry.baseDelayMs, DEFAULT_RETRY.baseDelayMs);
    retry.maxDelayMs = asNumber(retry.maxDelayMs, DEFAULT_RETRY.maxDelayMs);
    retry.maxQueueSize = asNumber(retry.maxQueueSize, DEFAULT_RETRY.maxQueueSize);
    retry.jitterRatio = clampJitter(retry.jitterRatio);

    const storageKey =
      options.storageKey ||
      `caliper_lp_retry_queue_v1:${options.jobId || "job"}:${options.visitorId || "visitor"}`;

    let queue = loadQueue(storageKey);
    let processorPromise = null;

    const baseMetadata = {
      ...(options.baseMetadata || {}),
      arm_id: options.armId || null,
    };

    const buildPayload = (entry) => ({
      visitor_id: options.visitorId,
      decision_id: options.decisionId,
      events: [
        {
          event_id: entry.eventId,
          event_type: entry.eventType,
          value: entry.value,
          metadata: {
            ...baseMetadata,
            ...(entry.metadata || {}),
          },
        },
      ],
    });

    const persistQueue = () => {
      if (!retry.persist) {
        return;
      }
      if (queue.length === 0) {
        safeStorage.removeItem(storageKey);
        return;
      }
      safeStorage.setItem(storageKey, JSON.stringify(queue));
    };

    const computeDelay = (attempts) => {
      const uncapped = retry.baseDelayMs * 2 ** Math.max(0, attempts - 1);
      const capped = Math.min(retry.maxDelayMs, uncapped);
      const jitter = capped * retry.jitterRatio * (Math.random() * 2 - 1);
      return Math.max(0, Math.round(capped + jitter));
    };

    const dispatch = async (entry, sendOptions = {}) => {
      const payload = buildPayload(entry);
      const body = JSON.stringify(payload);
      const preferBeacon = sendOptions.preferBeacon === true;
      const keepalive = sendOptions.keepalive === true;

      if (preferBeacon && typeof navigator !== "undefined" && navigator.sendBeacon) {
        const beaconBody = new Blob([body], { type: "application/json" });
        const accepted = navigator.sendBeacon(options.endpointPath, beaconBody);
        if (accepted) {
          return;
        }
      }

      const response = await fetch(options.endpointPath, {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body,
        credentials: "same-origin",
        cache: "no-store",
        keepalive,
      });

      if (!response.ok) {
        throw new Error(`tracker POST failed (${response.status})`);
      }
    };

    const enqueue = (entry) => {
      queue.push(entry);
      if (queue.length > retry.maxQueueSize) {
        queue = queue.slice(queue.length - retry.maxQueueSize);
      }
      persistQueue();
    };

    const ensureProcessor = () => {
      if (processorPromise) {
        return processorPromise;
      }

      processorPromise = (async () => {
        while (queue.length > 0) {
          queue.sort((a, b) => a.nextAttemptAt - b.nextAttemptAt);
          const current = queue[0];
          if (!current) {
            break;
          }

          const waitMs = current.nextAttemptAt - nowMs();
          if (waitMs > 0) {
            await sleep(waitMs);
          }

          try {
            await dispatch(current, {
              keepalive: current.keepalive,
            });
            queue.shift();
            persistQueue();
          } catch {
            current.attempts += 1;
            if (current.attempts >= retry.maxAttempts) {
              queue.shift();
              persistQueue();
              continue;
            }
            current.nextAttemptAt = nowMs() + computeDelay(current.attempts);
            persistQueue();
          }
        }
      })().finally(() => {
        processorPromise = null;
      });

      return processorPromise;
    };

    const track = async (eventType, metadata = {}, value = 1, sendOptions = {}) => {
      const entry = {
        eventId: randomId(),
        eventType,
        value: Number.isFinite(Number(value)) ? Number(value) : 1,
        metadata,
        attempts: 1,
        nextAttemptAt: nowMs() + computeDelay(1),
        createdAt: nowMs(),
        keepalive: sendOptions.keepalive === true,
      };

      try {
        await dispatch(entry, sendOptions);
      } catch (error) {
        if (!retry.enabled) {
          throw error;
        }
        enqueue(entry);
        void ensureProcessor();
      }
    };

    const flush = async () => {
      if (queue.length === 0) {
        return;
      }
      await ensureProcessor();
    };

    const tracker = {
      track,
      click: (metadata = {}, sendOptions = {}) =>
        track("click_detail", metadata, 1, sendOptions),
      timeSpent: (seconds, metadata = {}, sendOptions = {}) =>
        track("time_spent", metadata, seconds, sendOptions),
      flush,
      queueSize: () => queue.length,
    };

    if (queue.length > 0) {
      void ensureProcessor();
    }

    if (typeof window !== "undefined") {
      window.addEventListener("online", () => {
        void ensureProcessor();
      });
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
          void ensureProcessor();
        }
      });
    }

    return tracker;
  }

  function loadQueue(storageKey) {
    const raw = safeStorage.getItem(storageKey);
    if (!raw) {
      return [];
    }

    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return [];
      }

      return parsed
        .filter((entry) => entry && typeof entry.eventType === "string")
        .map((entry) => ({
          eventId: typeof entry.eventId === "string" ? entry.eventId : randomId(),
          eventType: entry.eventType,
          value: Number.isFinite(Number(entry.value)) ? Number(entry.value) : 1,
          metadata: typeof entry.metadata === "object" && entry.metadata ? entry.metadata : {},
          attempts: asNumber(entry.attempts, 1),
          nextAttemptAt: asNumber(entry.nextAttemptAt, nowMs()),
          createdAt: asNumber(entry.createdAt, nowMs()),
          keepalive: entry.keepalive === true,
        }));
    } catch {
      return [];
    }
  }

  function bindClickTracking(tracker, options = {}) {
    if (!tracker || typeof tracker.track !== "function") {
      throw new Error("bindClickTracking requires a tracker instance");
    }

    const selector = options.selector || "a[href*='/click'],[data-caliper-click]";
    const eventType = options.eventType || "click_detail";

    const onClick = (event) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }

      const matched = target.closest(selector);
      if (!matched) {
        return;
      }

      const text = (matched.textContent || "").trim().slice(0, 120);
      const classes = Array.from(matched.classList || []);
      const metadata = {
        tag: matched.tagName.toLowerCase(),
        element_id: matched.id || null,
        class_name: classes.join(" ") || null,
        text: text || null,
        href: matched.getAttribute("href"),
        caliper_click_role: matched.getAttribute("data-caliper-click") || null,
        ...(options.metadata || {}),
      };

      void tracker.track(eventType, metadata, 1, {
        keepalive: true,
      });
    };

    document.addEventListener("click", onClick);
    return () => {
      document.removeEventListener("click", onClick);
    };
  }

  function enableAutoTimeSpent(tracker, options = {}) {
    if (!tracker || typeof tracker.timeSpent !== "function") {
      throw new Error("enableAutoTimeSpent requires a tracker instance");
    }

    const minSeconds = asNumber(options.minSeconds, 1);
    const measurement = options.measurement || "visible_time";

    let visibleStartedAt = document.visibilityState === "visible" ? performance.now() : null;
    let accumulatedMs = 0;
    let flushed = false;

    const settleVisible = () => {
      if (visibleStartedAt === null) {
        return;
      }
      const current = performance.now();
      accumulatedMs += Math.max(0, current - visibleStartedAt);
      visibleStartedAt = null;
    };

    const flush = async (reason = "pagehide") => {
      if (flushed) {
        return;
      }
      settleVisible();
      const seconds = Math.round((accumulatedMs / 1000) * 1000) / 1000;
      if (seconds < minSeconds) {
        return;
      }
      flushed = true;
      await tracker.timeSpent(
        seconds,
        {
          measurement,
          reason,
          ...(options.metadata || {}),
        },
        {
          preferBeacon: true,
          keepalive: true,
        },
      );
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        if (visibleStartedAt === null) {
          visibleStartedAt = performance.now();
        }
        return;
      }
      settleVisible();
    };

    const onPageHide = () => {
      void flush("pagehide").catch(() => {
        // Best-effort in unload path.
      });
    };

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);

    return {
      flush,
      stop: async () => {
        document.removeEventListener("visibilitychange", onVisibility);
        window.removeEventListener("pagehide", onPageHide);
        await flush("stop");
      },
    };
  }

  function bootstrapLandingTelemetry(config = {}) {
    const tracker = createCaliperLandingTracker(config);
    const cleanups = [];

    if (config.enableClickTracking !== false) {
      cleanups.push(
        bindClickTracking(tracker, {
          selector: config.clickSelector,
          metadata: {
            ...(config.baseMetadata || {}),
          },
        }),
      );
    }

    let autoTime = null;
    if (config.enableAutoTimeSpent !== false) {
      autoTime = enableAutoTimeSpent(tracker, {
        ...(config.timeSpent || {}),
        metadata: {
          ...(config.baseMetadata || {}),
        },
      });
    }

    return {
      tracker,
      autoTime,
      stop: async () => {
        while (cleanups.length > 0) {
          const cleanup = cleanups.pop();
          if (typeof cleanup === "function") {
            cleanup();
          }
        }
        if (autoTime && typeof autoTime.stop === "function") {
          await autoTime.stop();
        }
        await tracker.flush();
      },
    };
  }

  const api = {
    createCaliperLandingTracker,
    bindClickTracking,
    enableAutoTimeSpent,
    bootstrapLandingTelemetry,
  };

  if (typeof window !== "undefined") {
    window.CaliperLandingTracker = api;
  }
})();
