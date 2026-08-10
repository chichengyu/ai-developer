"""Composable browser stealth patch bank with fingerprint-aware values.

Each patch is a self-contained init-script fragment. Patches are rendered
from a fingerprint value map so languages, timezone, screen, hardware,
WebGL, and `userAgentData` stay consistent with the active binding.
`compose_patches()` returns a single JavaScript payload;
`apply_patch_bank()` injects it into a Playwright/Patchright context or
page. Selenium can execute the same payload through CDP.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_FINGERPRINT_VALUES: dict[str, Any] = {
    "languages": ["zh-CN", "zh", "en-US", "en"],
    "language": "zh-CN",
    "locale": "zh-CN",
    "timezone_id": "Asia/Shanghai",
    "timezone_offset": -480,
    "browser_kind": "chrome",
    "screen_width": 1920,
    "screen_height": 1080,
    "screen_avail_width": 1920,
    "screen_avail_height": 1040,
    "screen_avail_top": 0,
    "outer_width": 1920,
    "outer_height": 1080,
    "device_pixel_ratio": 1,
    "color_depth": 24,
    "is_extended": False,
    "hardware_concurrency": 8,
    "device_memory": 8,
    "max_touch_points": 0,
    "platform": "Win32",
    "platform_version": "10.0.0",
    "architecture": "x86",
    "bitness": "64",
    "model": "",
    "oscpu": "Windows NT 10.0; Win64; x64",
    "vendor": "Google Inc.",
    "product_sub": "20030107",
    "app_version": (
        "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "pdf_viewer_enabled": True,
    "canvas_seed": 0,
    "webgl_vendor": "Intel Inc.",
    "webgl_renderer": (
        "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"
    ),
    "ua_data_brands": [
        {"brand": "Chromium", "version": "126"},
        {"brand": "Google Chrome", "version": "126"},
        {"brand": "Not=A?Brand", "version": "99"},
    ],
    "ua_data_platform": "Windows",
    "ua_data_mobile": False,
    "ua_full_version": "126.0.0.0",
    "full_version_list": [
        {"brand": "Chromium", "version": "126.0.0.0"},
        {"brand": "Google Chrome", "version": "126.0.0.0"},
        {"brand": "Not=A?Brand", "version": "99.0.0.0"},
    ],
    "webgl2_available": True,
    "latitude": 31.2304,
    "longitude": 121.4737,
    "speech_voices": [
        {"name": "Microsoft Huihui Desktop", "lang": "zh-CN", "localService": True},
        {"name": "Google US English", "lang": "en-US", "localService": True},
    ],
}

_FAMILY_SKIPS: dict[str, tuple[str, ...]] = {
    "firefox": ("chrome", "user_agent_data", "pdf_viewer"),
    "safari": ("chrome", "user_agent_data", "pdf_viewer"),
    "webkit": ("chrome", "user_agent_data", "pdf_viewer"),
}

PATCH_NAMES = (
    "webdriver",
    "chrome",
    "plugins",
    "permissions",
    "languages_timezone",
    "hardware",
    "navigator",
    "screen",
    "window_geometry",
    "network",
    "storage_estimate",
    "performance_timing",
    "battery",
    "canvas",
    "offscreen_canvas",
    "webgl",
    "webgl2",
    "user_agent_data",
    "media_devices",
    "media_capabilities",
    "wake_lock",
    "audio_context",
    "audio_deep",
    "geolocation",
    "webrtc",
    "match_media",
    "fonts",
    "iframe",
    "device_orientation",
    "event_native",
    "visibility_focus",
    "automation_markers",
    "webgl_deep",
    "speech_synthesis",
    "date_timezone",
    "pdf_viewer",
)

PATCHES: dict[str, str] = {
    "webdriver": """
    Object.defineProperty(navigator, "webdriver", {get: () => false});
    Object.defineProperty(Navigator.prototype, "webdriver", {get: () => false});
    """,
    "chrome": """
    if (__BROWSER_KIND_JSON__ === "chrome" || __BROWSER_KIND_JSON__ === "edge") {
    window.chrome = window.chrome || {};
    window.chrome.runtime = window.chrome.runtime || {
      id: undefined,
      connect: () => ({
        postMessage: () => {},
        disconnect: () => {},
        onMessage: {addListener: () => {}},
        onDisconnect: {addListener: () => {}}
      }),
      sendMessage: () => {},
      getManifest: () => ({})
    };
    window.chrome.loadTimes = window.chrome.loadTimes || (() => ({
      commitLoadTime: 1, requestTime: 0, startLoadTime: 1
    }));
    window.chrome.csi = window.chrome.csi || (() => ({startE: 1}));
    window.chrome.app = window.chrome.app || {isInstalled: false};
    window.chrome.webstore = window.chrome.webstore || {install: () => {}};
    }
    """,
    "plugins": """
    if (__BROWSER_KIND_JSON__ === "chrome" || __BROWSER_KIND_JSON__ === "edge") {
    const plugins = [1,2,3,4,5].map(i => ({
      name: `Plugin ${i}`, description: `Plugin ${i}`,
      filename: `plugin${i}.dll`, length: 1
    }));
    plugins.item = i => plugins[i] || null;
    plugins.namedItem = n => plugins.find(p => p.name === n) || null;
    plugins.refresh = () => undefined;
    Object.defineProperty(navigator, "plugins", {get: () => plugins});
    Object.defineProperty(navigator, "mimeTypes", {
      get: () => {
        const types = [
          {type: "application/pdf", suffixes: "pdf", description: "PDF"},
          {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"}
        ];
        types.item = i => types[i] || null;
        types.namedItem = n => types.find(t => t.type === n) || null;
        return types;
      }
    });
    }
    """,
    "permissions": """
    const originalQuery = navigator.permissions && navigator.permissions.query;
    if (originalQuery) {
      navigator.permissions.query = (parameters) => {
        if (parameters && parameters.name === "notifications") {
          return Promise.resolve({
            state: typeof Notification !== "undefined" ? Notification.permission : "denied",
            onchange: null
          });
        }
        if (parameters && parameters.name === "clipboard-read") {
          return Promise.resolve({state: "prompt", onchange: null});
        }
        return originalQuery(parameters);
      };
    }
    """,
    "languages_timezone": """
    const languages = __LANGUAGES_JSON__;
    Object.defineProperty(navigator, "languages", {get: () => languages});
    Object.defineProperty(navigator, "language", {get: () => __LANGUAGE_JSON__});
    if (window.Intl && Intl.DateTimeFormat) {
      const originalResolved = Intl.DateTimeFormat.prototype.resolvedOptions;
      Intl.DateTimeFormat.prototype.resolvedOptions = function() {
        const result = originalResolved.call(this);
        result.timeZone = __TIMEZONE_JSON__;
        return result;
      };
      const originalFormat = Intl.DateTimeFormat.prototype.format;
      Intl.DateTimeFormat.prototype.format = function(value) {
        const result = originalFormat.call(this, value);
        const offset = __TIMEZONE_OFFSET__;
        const sign = offset <= 0 ? "+" : "-";
        const abs = Math.abs(offset);
        const hours = String(Math.floor(abs / 60)).padStart(2, "0");
        const minutes = String(abs % 60).padStart(2, "0");
        return result.replace(/GMT[+-][0-9:]+/, `GMT${sign}${hours}${minutes}`);
      };
    }
    """,
    "hardware": """
    Object.defineProperty(navigator, "hardwareConcurrency", {get: () => __HARDWARE_CONCURRENCY__});
    if (__BROWSER_KIND_JSON__ === "chrome" || __BROWSER_KIND_JSON__ === "edge") {
      Object.defineProperty(navigator, "deviceMemory", {get: () => __DEVICE_MEMORY__});
    }
    Object.defineProperty(navigator, "maxTouchPoints", {get: () => __MAX_TOUCH_POINTS__});
    """,
    "navigator": """
    try { Object.defineProperty(navigator, "platform", {get: () => __PLATFORM_JSON__}); } catch (e) {}
    try { Object.defineProperty(navigator, "appName", {get: () => "Netscape"}); } catch (e) {}
    try { Object.defineProperty(navigator, "appCodeName", {get: () => "Mozilla"}); } catch (e) {}
    try { Object.defineProperty(navigator, "product", {get: () => "Gecko"}); } catch (e) {}
    try { Object.defineProperty(navigator, "vendorSub", {get: () => ""}); } catch (e) {}
    try { Object.defineProperty(navigator, "oscpu", {get: () => __OSCPU_JSON__}); } catch (e) {}
    try { Object.defineProperty(navigator, "vendor", {get: () => __VENDOR_JSON__}); } catch (e) {}
    try { Object.defineProperty(navigator, "productSub", {get: () => __PRODUCT_SUB_JSON__}); } catch (e) {}
    try { Object.defineProperty(navigator, "appVersion", {get: () => __APP_VERSION_JSON__}); } catch (e) {}
    try { Object.defineProperty(navigator, "userAgent", {get: () => __USER_AGENT_JSON__}); } catch (e) {}
    """,
    "screen": """
    Object.defineProperty(screen, "width", {get: () => __SCREEN_WIDTH__});
    Object.defineProperty(screen, "height", {get: () => __SCREEN_HEIGHT__});
    Object.defineProperty(screen, "availWidth", {get: () => __SCREEN_AVAIL_WIDTH__});
    Object.defineProperty(screen, "availHeight", {get: () => __SCREEN_AVAIL_HEIGHT__});
    Object.defineProperty(screen, "availLeft", {get: () => 0});
    Object.defineProperty(screen, "availTop", {get: () => __SCREEN_AVAIL_TOP__});
    Object.defineProperty(screen, "colorDepth", {get: () => __COLOR_DEPTH__});
    Object.defineProperty(screen, "pixelDepth", {get: () => __COLOR_DEPTH__});
    Object.defineProperty(screen, "isExtended", {get: () => __IS_EXTENDED__});
    Object.defineProperty(window, "outerWidth", {get: () => __OUTER_WIDTH__});
    Object.defineProperty(window, "outerHeight", {get: () => __OUTER_HEIGHT__});
    Object.defineProperty(window, "devicePixelRatio", {get: () => __DEVICE_PIXEL_RATIO__});
    if (screen.orientation && screen.orientation.lock) {
      const originalLock = screen.orientation.lock.bind(screen.orientation);
      screen.orientation.lock = async (orientation) => {
        Object.defineProperty(screen.orientation, "type", {get: () => orientation});
        return originalLock(orientation);
      };
    }
    if (screen.orientation && !screen.orientation.type) {
      Object.defineProperty(screen.orientation, "type", {get: () => "landscape-primary"});
    }
    """,
    "window_geometry": """
    const winWidth = __OUTER_WIDTH__;
    const winHeight = __OUTER_HEIGHT__;
    try { Object.defineProperty(window, "innerWidth", {get: () => winWidth}); } catch (e) {}
    try { Object.defineProperty(window, "innerHeight", {get: () => winHeight - 40}); } catch (e) {}
    try { Object.defineProperty(window, "screenX", {get: () => 0}); } catch (e) {}
    try { Object.defineProperty(window, "screenY", {get: () => 0}); } catch (e) {}
    try { Object.defineProperty(window, "screenLeft", {get: () => 0}); } catch (e) {}
    try { Object.defineProperty(window, "screenTop", {get: () => 0}); } catch (e) {}
    try {
      if (window.visualViewport) {
        Object.defineProperty(window.visualViewport, "width", {get: () => winWidth});
        Object.defineProperty(window.visualViewport, "height", {get: () => winHeight - 40});
        Object.defineProperty(window.visualViewport, "offsetLeft", {get: () => 0});
        Object.defineProperty(window.visualViewport, "offsetTop", {get: () => 0});
      }
    } catch (e) {}
    """,
    "network": """
    if (navigator.connection) {
      Object.defineProperty(navigator.connection, "effectiveType", {get: () => "4g"});
      Object.defineProperty(navigator.connection, "rtt", {get: () => 50});
      Object.defineProperty(navigator.connection, "downlink", {get: () => 10});
      Object.defineProperty(navigator.connection, "saveData", {get: () => false});
    }
    try { Object.defineProperty(navigator, "onLine", {get: () => true}); } catch (e) {}
    try { Object.defineProperty(navigator, "doNotTrack", {get: () => "1"}); } catch (e) {}
    try { Object.defineProperty(navigator, "cookieEnabled", {get: () => true}); } catch (e) {}
    """,
    "storage_estimate": """
    if (navigator.storage && navigator.storage.estimate) {
      navigator.storage.estimate = () => Promise.resolve({
        quota: 1073741824,
        usage: 5242880,
        usageDetails: {
          caches: 0,
          indexedDB: 5242880,
          serviceWorkerRegistrations: 0
        }
      });
    }
    """,
    "performance_timing": """
    try {
      if (window.performance) {
        const timeOrigin = performance.timeOrigin || (Date.now() - performance.now());
        Object.defineProperty(performance, "timeOrigin", {get: () => timeOrigin});
        if (performance.timing) {
          const timing = performance.timing;
          Object.defineProperty(timing, "navigationStart", {get: () => timeOrigin});
          Object.defineProperty(timing, "fetchStart", {get: () => timeOrigin + 3});
          Object.defineProperty(timing, "domContentLoadedEventEnd", {get: () => timeOrigin + 650});
          Object.defineProperty(timing, "loadEventEnd", {get: () => timeOrigin + 1100});
        }
      }
    } catch (e) {}
    """,
    "battery": """
    if (navigator.getBattery) {
      navigator.getBattery = () => Promise.resolve({
        charging: true, chargingTime: 0, dischargingTime: Infinity, level: 1,
        addEventListener: () => {}, removeEventListener: () => {}
      });
    }
    """,
    "canvas": """
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const originalToBlob = HTMLCanvasElement.prototype.toBlob;
    const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    const originalMeasureText = CanvasRenderingContext2D.prototype.measureText;
    HTMLCanvasElement.prototype.toDataURL = function(...args) {
      if (this.width > 0 && this.height > 0) {
        const ctx = this.getContext("2d");
        if (ctx) {
          ctx.fillStyle = "rgba(0,0,0,0.001)";
          ctx.fillRect(0, 0, 1, 1);
        }
      }
      return originalToDataURL.apply(this, args);
    };
    HTMLCanvasElement.prototype.toBlob = function(callback, ...args) {
      if (this.width > 0 && this.height > 0) {
        const ctx = this.getContext("2d");
        if (ctx) {
          ctx.fillStyle = "rgba(0,0,0,0.001)";
          ctx.fillRect(0, 0, 1, 1);
        }
      }
      return originalToBlob.call(this, callback, ...args);
    };
    CanvasRenderingContext2D.prototype.getImageData = function(x, y, w, h) {
      const data = originalGetImageData.call(this, x, y, w, h);
      const noise = (x * 31 + y * 17 + w * 7 + h * 11 + __CANVAS_SEED__) % 4;
      if (noise && data.data.length) {
        data.data[0] = (data.data[0] + noise) & 255;
      }
      return data;
    };
    CanvasRenderingContext2D.prototype.measureText = function(text) {
      const result = originalMeasureText.call(this, text);
      if (result && result.width) {
        Object.defineProperty(result, "width", {value: result.width + 0.0001});
      }
      return result;
    };
    """,
    "offscreen_canvas": """
    if (typeof OffscreenCanvas !== "undefined") {
      const originalConvert = OffscreenCanvas.prototype.convertToBlob;
      OffscreenCanvas.prototype.convertToBlob = async function(...args) {
        if (this.width > 0 && this.height > 0) {
          const ctx = this.getContext("2d");
          if (ctx) {
            ctx.fillStyle = "rgba(0,0,0,0.001)";
            ctx.fillRect(0, 0, 1, 1);
            const data = ctx.getImageData(0, 0, 1, 1);
            if (data && data.data.length) {
              data.data[0] = (data.data[0] + __CANVAS_SEED__) & 255;
            }
          }
        }
        return originalConvert.apply(this, args);
      };
    }
    """,
    "webgl": """
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
      if (parameter === 37445) return __WEBGL_VENDOR_JSON__;
      if (parameter === 37446) return __WEBGL_RENDERER_JSON__;
      return getParameter.call(this, parameter);
    };
    const getExtension = WebGLRenderingContext.prototype.getExtension;
    WebGLRenderingContext.prototype.getExtension = function(name) {
      const extension = getExtension.call(this, name);
      if (extension && name === "WEBGL_debug_renderer_info") {
        extension.UNMASKED_VENDOR_WEBGL = __WEBGL_VENDOR_JSON__;
        extension.UNMASKED_RENDERER_WEBGL = __WEBGL_RENDERER_JSON__;
      }
      return extension;
    };
    """,
    "webgl2": """
    if (typeof WebGL2RenderingContext !== "undefined") {
      const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
      WebGL2RenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return __WEBGL_VENDOR_JSON__;
        if (parameter === 37446) return __WEBGL_RENDERER_JSON__;
        return getParameter2.call(this, parameter);
      };
      const getExtension2 = WebGL2RenderingContext.prototype.getExtension;
      WebGL2RenderingContext.prototype.getExtension = function(name) {
        const extension = getExtension2.call(this, name);
        if (extension && name === "WEBGL_debug_renderer_info") {
          extension.UNMASKED_VENDOR_WEBGL = __WEBGL_VENDOR_JSON__;
          extension.UNMASKED_RENDERER_WEBGL = __WEBGL_RENDERER_JSON__;
        }
        return extension;
      };
    }
    """,
    "user_agent_data": """
    if (__BROWSER_KIND_JSON__ === "chrome" || __BROWSER_KIND_JSON__ === "edge") {
    const uaBrands = __UA_DATA_BRANDS_JSON__;
    const uaPlatform = __UA_DATA_PLATFORM_JSON__;
    const uaMobile = __UA_DATA_MOBILE__;
    const uaFullVersion = __UA_FULL_VERSION_JSON__;
    const fullVersionList = __FULL_VERSION_LIST_JSON__;
    const uaData = {
      brands: uaBrands,
      mobile: uaMobile,
      platform: uaPlatform,
      getHighEntropyValues: () => Promise.resolve({
        architecture: __ARCHITECTURE_JSON__,
        bitness: __BITNESS_JSON__,
        model: __MODEL_JSON__,
        platformVersion: __PLATFORM_VERSION_JSON__,
        uaFullVersion: uaFullVersion,
        fullVersionList: fullVersionList
      }),
      toJSON: () => ({brands: uaBrands, mobile: uaMobile, platform: uaPlatform})
    };
    try {
      Object.defineProperty(navigator, "userAgentData", {get: () => uaData});
    } catch (e) {
      try { navigator.userAgentData = uaData; } catch (e2) {}
    }
    }
    """,
    "media_devices": """
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
      navigator.mediaDevices.enumerateDevices = () => Promise.resolve([
        {deviceId: "audioinput:1", kind: "audioinput", label: "Microphone", groupId: "g1"},
        {deviceId: "videoinput:1", kind: "videoinput", label: "Camera", groupId: "g2"},
        {deviceId: "audiooutput:1", kind: "audiooutput", label: "Speakers", groupId: "g1"}
      ]);
    }
    """,
    "media_capabilities": """
    if (window.MediaCapabilities && MediaCapabilities.decodingInfo) {
      const originalDecodingInfo = MediaCapabilities.decodingInfo.bind(MediaCapabilities);
      MediaCapabilities.decodingInfo = async (info) => {
        try {
          const result = await originalDecodingInfo(info);
          if (result) {
            result.smooth = true;
            result.powerEfficient = true;
          }
          return result;
        } catch (e) {
          return {supported: true, smooth: true, powerEfficient: true};
        }
      };
    }
    """,
    "wake_lock": """
    if (navigator.wakeLock && navigator.wakeLock.request) {
      const originalWakeLock = navigator.wakeLock.request.bind(navigator.wakeLock);
      navigator.wakeLock.request = async (type) => {
        try {
          return await originalWakeLock(type);
        } catch (e) {
          return {
            type: type || "screen",
            released: false,
            addEventListener: () => {},
            removeEventListener: () => {}
          };
        }
      };
    }
    """,
    "audio_context": """
    if (typeof AudioContext !== "undefined") {
      Object.defineProperty(AudioContext.prototype, "sampleRate", {get: () => 48000});
      Object.defineProperty(AudioContext.prototype, "state", {get: () => "running"});
      Object.defineProperty(AudioContext.prototype, "baseLatency", {get: () => 0.005});
      Object.defineProperty(AudioContext.prototype, "outputLatency", {get: () => 0.01});
      const originalGetOutputTimestamp = AudioContext.prototype.getOutputTimestamp;
      AudioContext.prototype.getOutputTimestamp = function() {
        return {contextTime: this.currentTime, performanceTime: performance.now()};
      };
    }
    """,
    "audio_deep": """
    if (typeof AnalyserNode !== "undefined") {
      const originalFloat = AnalyserNode.prototype.getFloatFrequencyData;
      const originalByte = AnalyserNode.prototype.getByteFrequencyData;
      AnalyserNode.prototype.getFloatFrequencyData = function(array) {
        originalFloat.call(this, array);
        const seed = this.context ? Math.round(this.context.sampleRate || 48000) : 48000;
        for (let i = 0; i < array.length; i++) {
          array[i] += ((i * 7 + seed) % 5) / 1000;
        }
      };
      AnalyserNode.prototype.getByteFrequencyData = function(array) {
        originalByte.call(this, array);
        const seed = this.context ? Math.round(this.context.sampleRate || 48000) : 48000;
        for (let i = 0; i < array.length; i++) {
          array[i] = (array[i] + ((i * 3 + seed) % 2)) & 255;
        }
      };
    }
    if (typeof AudioBuffer !== "undefined") {
      const originalGetChannelData = AudioBuffer.prototype.getChannelData;
      AudioBuffer.prototype.getChannelData = function(channel) {
        const data = originalGetChannelData.call(this, channel);
        return data;
      };
    }
    """,
    "geolocation": """
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition = (success, error, options) => {
        success({
          coords: {
            latitude: __LATITUDE__, longitude: __LONGITUDE__, accuracy: 10,
            altitude: null, altitudeAccuracy: null,
            heading: null, speed: null
          },
          timestamp: Date.now()
        });
      };
      navigator.geolocation.watchPosition = (success, error, options) => {
        navigator.geolocation.getCurrentPosition(success, error, options);
        return 0;
      };
    }
    """,
    "webrtc": """
    if (typeof RTCPeerConnection !== "undefined") {
      const originalCreateDataChannel = RTCPeerConnection.prototype.createDataChannel;
      RTCPeerConnection.prototype.createDataChannel = function(...args) {
        const channel = originalCreateDataChannel.apply(this, args);
        return channel;
      };
      const originalSetLocalDescription = RTCPeerConnection.prototype.setLocalDescription;
      RTCPeerConnection.prototype.setLocalDescription = function(description, ...args) {
        if (description && description.sdp) {
          description.sdp = String(description.sdp)
            .replace(/a=ice-ufrag:[^\\r\\n]+/g, "a=ice-ufrag:ztR8F6xNsQ")
            .replace(/a=ice-pwd:[^\\r\\n]+/g, "a=ice-pwd:9bJ1O1E8zK4pP2Q0")
            .replace(/a=candidate:[^\\r\\n]+/g, "a=candidate:0 1 udp 2122260223 10.0.0.1 51472 typ host");
        }
        return originalSetLocalDescription.call(this, description, ...args);
      };
    }
    """,
    "match_media": """
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = (query) => {
      const media = originalMatchMedia(query);
      if (query.includes("prefers-reduced-motion")) {
        Object.defineProperty(media, "matches", {get: () => false});
      }
      if (query.includes("prefers-color-scheme")) {
        Object.defineProperty(media, "matches", {get: () => true});
      }
      return media;
    };
    """,
    "fonts": """
    if (document.fonts && document.fonts.check) {
      const originalCheck = document.fonts.check.bind(document.fonts);
      document.fonts.check = (font, text) => {
        try { return originalCheck(font, text); } catch (e) { return true; }
      };
    }
    """,
    "iframe": """
    const originalDescriptor = Object.getOwnPropertyDescriptor(
      HTMLIFrameElement.prototype, "contentWindow"
    );
    if (originalDescriptor && originalDescriptor.get) {
      const originalGetter = originalDescriptor.get;
      Object.defineProperty(HTMLIFrameElement.prototype, "contentWindow", {
        get() {
          const win = originalGetter.call(this);
          if (win && !win.__stealthPatched) {
            try {
              Object.defineProperty(win, "__stealthPatched", {value: true});
              Object.defineProperty(win.navigator, "webdriver", {get: () => undefined});
            } catch (e) {}
          }
          return win;
        }
      });
    }
    """,
    "device_orientation": """
    if (window.DeviceOrientationEvent && DeviceOrientationEvent.requestPermission) {
      DeviceOrientationEvent.requestPermission = () => Promise.resolve("granted");
    }
    if (window.DeviceMotionEvent && DeviceMotionEvent.requestPermission) {
      DeviceMotionEvent.requestPermission = () => Promise.resolve("granted");
    }
    """,
    "event_native": """
    const eventTypeNames = [
      "Event", "MouseEvent", "KeyboardEvent", "PointerEvent", "TouchEvent",
      "WheelEvent", "InputEvent", "FocusEvent", "ClipboardEvent"
    ];
    for (const name of eventTypeNames) {
      const eventType = window[name];
      if (eventType && eventType.prototype) {
        try {
          Object.defineProperty(eventType.prototype, "isTrusted", {
            get: () => true,
            configurable: true
          });
        } catch (e) {}
      }
    }
    """,
    "visibility_focus": """
    try { Object.defineProperty(document, "visibilityState", {get: () => "visible"}); } catch (e) {}
    try { Object.defineProperty(document, "hidden", {get: () => false}); } catch (e) {}
    try { document.hasFocus = () => true; } catch (e) {}
    try {
      Object.defineProperty(document, "webkitVisibilityState", {get: () => "visible"});
      Object.defineProperty(document, "webkitHidden", {get: () => false});
    } catch (e) {}
    """,
    "automation_markers": """
    const automationMarkers = [
      "cdc_adoQpoasnfa76pfcZLmcfl_Array",
      "cdc_adoQpoasnfa76pfcZLmcfl_Promise",
      "cdc_adoQpoasnfa76pfcZLmcfl_Symbol",
      "$cdc_asdjflasutopfhvcZLmcfl_",
      "__webdriver_evaluate",
      "__selenium_evaluate",
      "__webdriver_unwrap",
      "__selenium_unwrap",
      "__lastWatirAlert",
      "__lastWatirConfirm",
      "__lastWatirPrompt",
      "__fxdriver_evaluate",
      "__fxdriver_unwrap",
      "_Selenium_IDE_Recorder",
      "_selenium",
      "domAutomation",
      "domAutomationController",
      "callPhantom",
      "_phantom"
    ];
    for (const key of automationMarkers) {
      try { delete window[key]; } catch (e) {}
      try { delete document[key]; } catch (e) {}
    }
    try { Object.defineProperty(navigator, "webdriver", {get: () => false}); } catch (e) {}
    """,
    "webgl_deep": """
    if (typeof WebGLRenderingContext !== "undefined") {
      const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
      WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return __WEBGL_VENDOR_JSON__;
        if (parameter === 37446) return __WEBGL_RENDERER_JSON__;
        if (parameter === 3379) return [16384, 16384];
        if (parameter === 3386) return [16384, 16384];
        if (parameter === 3411) return 16384;
        return originalGetParameter.call(this, parameter);
      };
    }
    """,
    "speech_synthesis": """
    if (window.speechSynthesis && speechSynthesis.getVoices) {
      const originalGetVoices = speechSynthesis.getVoices.bind(speechSynthesis);
      speechSynthesis.getVoices = () => {
        const voices = originalGetVoices();
        if (voices && voices.length) return voices;
        const fallbackVoices = __SPEECH_VOICES_JSON__;
        return fallbackVoices.map((voice, index) => ({
          name: voice.name,
          lang: voice.lang,
          localService: true,
          default: index === 0,
          voiceURI: voice.name
        }));
      };
    }
    """,
    "date_timezone": """
    const originalGetTimezoneOffset = Date.prototype.getTimezoneOffset;
    Date.prototype.getTimezoneOffset = function() {
      return __TIMEZONE_OFFSET__;
    };
    const timezoneSuffix = (() => {
      const offset = __TIMEZONE_OFFSET__;
      const sign = offset <= 0 ? "+" : "-";
      const abs = Math.abs(offset);
      const hours = String(Math.floor(abs / 60)).padStart(2, "0");
      const minutes = String(abs % 60).padStart(2, "0");
      return `GMT${sign}${hours}${minutes}`;
    })();
    const originalToString = Date.prototype.toString;
    Date.prototype.toString = function() {
      return originalToString.call(this).replace(/GMT[+-]\\d{4}/, timezoneSuffix);
    };
    const originalToTimeString = Date.prototype.toTimeString;
    Date.prototype.toTimeString = function() {
      return originalToTimeString.call(this).replace(/GMT[+-]\\d{4}/, timezoneSuffix);
    };
    """,
    "pdf_viewer": """
    if (__BROWSER_KIND_JSON__ === "chrome" || __BROWSER_KIND_JSON__ === "edge") {
      Object.defineProperty(navigator, "pdfViewerEnabled", {
        get: () => __PDF_VIEWER_ENABLED__
      });
    }
    """,
}


def _values(values: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(DEFAULT_FINGERPRINT_VALUES)
    if values:
        merged.update(values)
    if merged.get("user_agent") is None:
        merged["user_agent"] = merged["app_version"]
    return merged


def _render_patch(name: str, values: dict[str, Any]) -> str:
    source = PATCHES[name]
    replacements = {
        "__LANGUAGES_JSON__": json.dumps(values.get("languages") or [], ensure_ascii=False),
        "__LANGUAGE_JSON__": json.dumps(str(values.get("language") or "zh-CN"), ensure_ascii=False),
        "__TIMEZONE_JSON__": json.dumps(str(values.get("timezone_id") or "Asia/Shanghai")),
        "__HARDWARE_CONCURRENCY__": str(int(values.get("hardware_concurrency") or 8)),
        "__DEVICE_MEMORY__": str(int(values.get("device_memory") or 8)),
        "__MAX_TOUCH_POINTS__": str(int(values.get("max_touch_points") or 0)),
        "__BROWSER_KIND_JSON__": json.dumps(str(values.get("browser_kind") or "chrome")),
        "__PLATFORM_JSON__": json.dumps(str(values.get("platform") or "Win32")),
        "__PLATFORM_VERSION_JSON__": json.dumps(
            str(values.get("platform_version") or "10.0.0")
        ),
        "__ARCHITECTURE_JSON__": json.dumps(str(values.get("architecture") or "x86")),
        "__BITNESS_JSON__": json.dumps(str(values.get("bitness") or "64")),
        "__MODEL_JSON__": json.dumps(str(values.get("model") or "")),
        "__PDF_VIEWER_ENABLED__": (
            "true" if bool(values.get("pdf_viewer_enabled", True)) else "false"
        ),
        "__OSCPU_JSON__": json.dumps(str(values.get("oscpu") or "")),
        "__VENDOR_JSON__": json.dumps(str(values.get("vendor") or "Google Inc.")),
        "__PRODUCT_SUB_JSON__": json.dumps(str(values.get("product_sub") or "20030107")),
        "__APP_VERSION_JSON__": json.dumps(str(values.get("app_version") or "")),
        "__USER_AGENT_JSON__": json.dumps(str(values.get("user_agent") or "")),
        "__SCREEN_WIDTH__": str(int(values.get("screen_width") or 1920)),
        "__SCREEN_HEIGHT__": str(int(values.get("screen_height") or 1080)),
        "__SCREEN_AVAIL_WIDTH__": str(int(values.get("screen_avail_width") or 1920)),
        "__SCREEN_AVAIL_HEIGHT__": str(int(values.get("screen_avail_height") or 1040)),
        "__SCREEN_AVAIL_TOP__": str(int(values.get("screen_avail_top") or 0)),
        "__OUTER_WIDTH__": str(int(values.get("outer_width") or 1920)),
        "__OUTER_HEIGHT__": str(int(values.get("outer_height") or 1080)),
        "__DEVICE_PIXEL_RATIO__": str(float(values.get("device_pixel_ratio") or 1)),
        "__COLOR_DEPTH__": str(int(values.get("color_depth") or 24)),
        "__IS_EXTENDED__": (
            "true" if bool(values.get("is_extended")) else "false"
        ),
        "__CANVAS_SEED__": str(int(values.get("canvas_seed") or 0)),
        "__WEBGL_VENDOR_JSON__": json.dumps(str(values.get("webgl_vendor") or "Intel Inc.")),
        "__WEBGL_RENDERER_JSON__": json.dumps(
            str(values.get("webgl_renderer") or "Intel Iris OpenGL Engine")
        ),
        "__UA_DATA_BRANDS_JSON__": json.dumps(
            values.get("ua_data_brands")
            or [{"brand": "Chromium", "version": "126"}],
            ensure_ascii=False,
        ),
        "__UA_DATA_PLATFORM_JSON__": json.dumps(
            str(values.get("ua_data_platform") or "Windows")
        ),
        "__UA_DATA_MOBILE__": "true" if bool(values.get("ua_data_mobile")) else "false",
        "__UA_FULL_VERSION_JSON__": json.dumps(
            str(values.get("ua_full_version") or "126.0.0.0")
        ),
        "__FULL_VERSION_LIST_JSON__": json.dumps(
            values.get("full_version_list")
            or [
                {"brand": "Chromium", "version": "126.0.0.0"},
                {"brand": "Google Chrome", "version": "126.0.0.0"},
            ],
            ensure_ascii=False,
        ),
        "__SPEECH_VOICES_JSON__": json.dumps(
            values.get("speech_voices")
            or [
                {"name": "Microsoft Huihui Desktop", "lang": "zh-CN", "localService": True},
                {"name": "Google US English", "lang": "en-US", "localService": True},
            ],
            ensure_ascii=False,
        ),
        "__LATITUDE__": str(float(values.get("latitude") or 31.2304)),
        "__LONGITUDE__": str(float(values.get("longitude") or 121.4737)),
        "__TIMEZONE_OFFSET__": str(int(values.get("timezone_offset") or -480)),
    }
    for token, value in replacements.items():
        source = source.replace(token, value)
    return source


def compose_patches(
    names: list[str] | tuple[str, ...] | None = None,
    *,
    extra_js: str = "",
    values: dict[str, Any] | None = None,
) -> str:
    """Compose a stealth init script from named patches and fingerprint values."""
    fingerprint = _values(values)
    if names is None:
        family = str(fingerprint.get("browser_kind") or "chrome").lower()
        skip = set(_FAMILY_SKIPS.get(family, ()))
        selected = tuple(name for name in PATCH_NAMES if name not in skip)
    else:
        selected = tuple(names)
    fragments = [
        f"try {{\n{_render_patch(name, fingerprint)}\n}} catch (e) {{}}"
        for name in selected
        if name in PATCHES
    ]
    return "\n".join(
        [
            "(() => {",
            *fragments,
            extra_js,
            "})();",
        ]
    )


def apply_patch_bank(
    context: Any,
    page: Any | None = None,
    names: list[str] | tuple[str, ...] | None = None,
    values: dict[str, Any] | None = None,
) -> str:
    payload = compose_patches(names, values=values)
    add_init_script = getattr(context, "add_init_script", None)
    if add_init_script is not None:
        add_init_script(payload)
    if page is not None:
        add_page_script = getattr(page, "add_init_script", None)
        if add_page_script is not None:
            add_page_script(payload)
    return payload


if __name__ == "__main__":
    payload = compose_patches(["webdriver", "navigator", "user_agent_data"])
    print(len(payload))
