(() => {
  "use strict";

  const data = window.CHARGEFORWARD_DATA;
  const liveData = window.CHARGEFORWARD_LIVE;
  if (!data) {
    document.documentElement.classList.add("data-error");
    return;
  }

  const NS = "http://www.w3.org/2000/svg";
  const colors = {
    acid: "#d5ff46",
    orange: "#ff6b3d",
    violet: "#a69cff",
    blue: "#75d9ff",
    white: "#fffef8",
    muted: "rgba(255,255,255,.42)",
    grid: "rgba(255,255,255,.09)",
  };

  const modelNames = {
    poisson_glm: "Poisson GLM",
    lag_12_baseline: "Prior-year baseline",
    gradient_boosting: "Gradient boosting",
    random_forest: "Random Forest",
    negative_binomial: "Negative Binomial",
  };

  const metricMeta = {
    rmse: { title: "Root mean squared error", label: "RMSE", note: "Penalizes large misses more heavily. Lower is better.", better: "lower", decimals: 2 },
    mae: { title: "Mean absolute error", label: "MAE", note: "Average absolute miss in registration transactions. Lower is better.", better: "lower", decimals: 2 },
    wape_pct: { title: "Weighted absolute percentage error", label: "WAPE", note: "Absolute error divided by total observed activity. Lower is better.", better: "lower", decimals: 2, suffix: "%" },
    r2: { title: "Coefficient of determination", label: "R²", note: "Share of variance captured relative to the mean. Higher is better.", better: "higher", decimals: 4 },
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const createSvg = (tag, attrs = {}, text = "") => {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text) node.textContent = text;
    return node;
  };
  const setSvg = (svg, width, height) => {
    svg.replaceChildren();
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("preserveAspectRatio", "none");
  };
  const pathFrom = (points) => points.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const formatNumber = (value, decimals = 0) => Number(value).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

  function setupChrome() {
    const header = $(".site-header");
    const progress = $("#scroll-progress");
    const update = () => {
      const max = document.documentElement.scrollHeight - innerHeight;
      progress.style.width = `${max > 0 ? (scrollY / max) * 100 : 0}%`;
      header.classList.toggle("scrolled", scrollY > 24);
    };
    addEventListener("scroll", update, { passive: true });
    update();

    const toggle = $(".nav-toggle");
    const closeNav = () => {
      document.body.classList.remove("nav-open");
      toggle.setAttribute("aria-expanded", "false");
    };
    toggle.addEventListener("click", () => {
      const open = !document.body.classList.contains("nav-open");
      document.body.classList.toggle("nav-open", open);
      toggle.setAttribute("aria-expanded", String(open));
    });
    $$("#site-nav a").forEach((link) => link.addEventListener("click", closeNav));
    addEventListener("keydown", (event) => { if (event.key === "Escape") closeNav(); });
  }

  function setupReveal() {
    const items = $$(".reveal");
    if (!("IntersectionObserver" in window)) {
      items.forEach((item) => item.classList.add("visible"));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.09, rootMargin: "0px 0px -35px" });
    items.forEach((item, index) => {
      item.style.transitionDelay = `${Math.min(index % 4, 3) * 55}ms`;
      observer.observe(item);
    });
  }

  function setupCounters() {
    const counters = $$("[data-count]");
    const animate = (node) => {
      const target = Number(node.dataset.count);
      const decimals = Number(node.dataset.decimals || 0);
      const suffix = node.dataset.suffix || "";
      const start = performance.now();
      const duration = 1150;
      const frame = (now) => {
        const elapsed = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - elapsed, 4);
        node.textContent = `${formatNumber(target * eased, decimals)}${suffix}`;
        if (elapsed < 1) requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
    };
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          animate(entry.target);
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: .5 });
    counters.forEach((counter) => observer.observe(counter));
  }

  function drawHeroChart() {
    const svg = $("#hero-chart");
    const width = 680;
    const height = 330;
    const pad = { top: 38, right: 28, bottom: 45, left: 45 };
    setSvg(svg, width, height);
    const rows = data.temporalRobustness;
    const periods = [...new Set(rows.map((row) => row.evaluation_end))];
    const max = Math.max(...rows.map((row) => row.rmse)) * 1.13;
    const x = (index) => pad.left + index * ((width - pad.left - pad.right) / (periods.length - 1));
    const y = (value) => height - pad.bottom - (value / max) * (height - pad.top - pad.bottom);

    [0, .25, .5, .75, 1].forEach((fraction) => {
      const yy = y(max * fraction);
      svg.append(createSvg("line", { x1: pad.left, y1: yy, x2: width - pad.right, y2: yy, stroke: colors.grid }));
      svg.append(createSvg("text", { x: pad.left - 10, y: yy + 3, "text-anchor": "end", fill: colors.muted, "font-size": 8, "font-family": "DM Mono, monospace" }, Math.round(max * fraction)));
    });
    periods.forEach((period, index) => {
      svg.append(createSvg("text", { x: x(index), y: height - 15, "text-anchor": "middle", fill: colors.muted, "font-size": 8, "font-family": "DM Mono, monospace" }, `${period.slice(2, 4)}/${String(Number(period.slice(2, 4)) + 1).padStart(2, "0")}`));
    });

    const series = [
      ["lag_12_baseline", colors.violet, .5],
      ["random_forest", colors.orange, .7],
      ["poisson_glm", colors.acid, 1],
    ];
    series.forEach(([model, color, opacity]) => {
      const values = periods.map((period) => rows.find((row) => row.model === model && row.evaluation_end === period));
      const points = values.map((row, index) => [x(index), y(row.rmse)]);
      svg.append(createSvg("path", { d: pathFrom(points), fill: "none", stroke: color, "stroke-width": model === "poisson_glm" ? 3 : 1.5, opacity }));
      points.forEach(([cx, cy], index) => {
        svg.append(createSvg("circle", { cx, cy, r: model === "poisson_glm" ? 4 : 2.5, fill: color, opacity }));
        if (model === "poisson_glm" && index === points.length - 1) {
          svg.append(createSvg("circle", { cx, cy, r: 10, fill: "none", stroke: color, opacity: .25 }));
        }
      });
    });
    svg.append(createSvg("text", { x: pad.left, y: 16, fill: colors.muted, "font-size": 8, "font-family": "DM Mono, monospace", "letter-spacing": 1 }, "RMSE / LOWER IS BETTER"));
  }

  function drawModelChart(metric = "rmse") {
    const svg = $("#model-chart");
    const width = 760;
    const height = 450;
    const pad = { top: 32, right: 76, bottom: 35, left: 170 };
    setSvg(svg, width, height);
    const meta = metricMeta[metric];
    const rows = [...data.modelScores].sort((a, b) => meta.better === "lower" ? a[metric] - b[metric] : b[metric] - a[metric]);
    const max = Math.max(...rows.map((row) => row[metric])) * 1.14;
    const plotWidth = width - pad.left - pad.right;
    const rowGap = (height - pad.top - pad.bottom) / rows.length;
    const barHeight = Math.min(37, rowGap * .5);

    [0, .25, .5, .75, 1].forEach((fraction) => {
      const xx = pad.left + plotWidth * fraction;
      svg.append(createSvg("line", { x1: xx, y1: pad.top, x2: xx, y2: height - pad.bottom, class: "svg-grid" }));
      svg.append(createSvg("text", { x: xx, y: height - 10, "text-anchor": "middle", class: "svg-axis" }, (max * fraction).toFixed(metric === "r2" ? 2 : 0)));
    });
    rows.forEach((row, index) => {
      const group = createSvg("g", { class: "model-group" });
      const yy = pad.top + rowGap * index + (rowGap - barHeight) / 2;
      const barWidth = Math.max(2, (row[metric] / max) * plotWidth);
      const isWinner = index === 0;
      const isBaseline = row.model === "lag_12_baseline";
      const color = isWinner ? colors.acid : isBaseline ? colors.violet : row.model === "random_forest" ? colors.orange : colors.blue;
      group.append(createSvg("text", { x: pad.left - 15, y: yy + barHeight / 2 + 4, "text-anchor": "end", class: "svg-label" }, modelNames[row.model] || row.model));
      group.append(createSvg("rect", { x: pad.left, y: yy, width: barWidth, height: barHeight, fill: color, opacity: isWinner ? 1 : .58, class: "model-bar" }));
      group.append(createSvg("text", { x: Math.min(pad.left + barWidth + 10, width - 50), y: yy + barHeight / 2 + 4, class: "svg-value" }, `${Number(row[metric]).toFixed(meta.decimals)}${meta.suffix || ""}`));
      if (isWinner) group.append(createSvg("text", { x: pad.left + 8, y: yy + barHeight / 2 + 3, fill: "#0b0c0b", "font-size": 7, "font-family": "DM Mono, monospace", "font-weight": 700 }, "BEST"));
      svg.append(group);
    });
    $("#model-metric-title").textContent = meta.title;
    $("#model-definition").innerHTML = `<span>${meta.label}</span> ${meta.note}`;
  }

  function setupModelControls() {
    $$(".metric-toggle").forEach((button) => {
      button.addEventListener("click", () => {
        $$(".metric-toggle").forEach((item) => item.classList.toggle("active", item === button));
        drawModelChart(button.dataset.metric);
      });
    });
  }

  function setupCountyExplorer() {
    const select = $("#county-select");
    [...data.countyErrors]
      .sort((a, b) => b.total_transactions - a.total_transactions)
      .forEach((row) => {
        const option = document.createElement("option");
        option.value = row.County;
        option.textContent = `${row.County} County`;
        select.append(option);
      });
    select.value = "King";
    select.addEventListener("change", () => drawCounty(select.value));
  }

  function drawCounty(county) {
    const metrics = data.countyErrors.find((row) => row.County === county);
    const rows = data.predictionIntervals.filter((row) => row.County === county).sort((a, b) => String(a.Date).localeCompare(String(b.Date)));
    if (!metrics || !rows.length) return;

    $("#county-baseline").textContent = metrics.lag_12_baseline_rmse.toFixed(1);
    $("#county-poisson").textContent = metrics.poisson_glm_rmse.toFixed(1);
    $("#county-rf").textContent = metrics.random_forest_rmse.toFixed(1);
    const rfChange = metrics.ml_improvement_vs_baseline_pct;
    const statChange = metrics.statistical_improvement_vs_baseline_pct;
    $("#county-verdict").innerHTML = `In <strong>${county}</strong>, Random Forest ${rfChange >= 0 ? "reduced" : "increased"} RMSE by <strong>${Math.abs(rfChange).toFixed(1)}%</strong>; Poisson ${statChange >= 0 ? "reduced" : "increased"} it by <strong>${Math.abs(statChange).toFixed(1)}%</strong> versus the seasonal baseline.`;

    const svg = $("#county-chart");
    const width = 800;
    const height = 430;
    const pad = { top: 20, right: 22, bottom: 55, left: 58 };
    setSvg(svg, width, height);
    const max = Math.max(...rows.flatMap((row) => [row.actual, row.upper_80])) * 1.1;
    const x = (index) => pad.left + index * ((width - pad.left - pad.right) / (rows.length - 1));
    const y = (value) => height - pad.bottom - (value / max) * (height - pad.top - pad.bottom);

    [0, .25, .5, .75, 1].forEach((fraction) => {
      const yy = y(max * fraction);
      svg.append(createSvg("line", { x1: pad.left, y1: yy, x2: width - pad.right, y2: yy, class: "svg-grid" }));
      svg.append(createSvg("text", { x: pad.left - 10, y: yy + 3, "text-anchor": "end", class: "svg-axis" }, Math.round(max * fraction)));
    });
    rows.forEach((row, index) => {
      const date = new Date(`${row.Date}T00:00:00`);
      svg.append(createSvg("text", { x: x(index), y: height - 24, "text-anchor": "middle", class: "svg-axis", transform: `rotate(-38 ${x(index)} ${height - 24})` }, date.toLocaleDateString("en-US", { month: "short" })));
    });

    const top = rows.map((row, index) => [x(index), y(row.upper_80)]);
    const bottom = rows.map((row, index) => [x(index), y(row.lower_80)]).reverse();
    svg.append(createSvg("path", { d: `${pathFrom(top)} ${bottom.map(([px, py]) => `L${px.toFixed(2)},${py.toFixed(2)}`).join(" ")} Z`, fill: "rgba(117,217,255,.12)", stroke: "none" }));
    const actual = rows.map((row, index) => [x(index), y(row.actual)]);
    const predicted = rows.map((row, index) => [x(index), y(row.prediction)]);
    svg.append(createSvg("path", { d: pathFrom(predicted), fill: "none", stroke: colors.orange, "stroke-width": 2 }));
    svg.append(createSvg("path", { d: pathFrom(actual), fill: "none", stroke: colors.acid, "stroke-width": 2.5 }));

    const tooltip = $("#county-tooltip");
    rows.forEach((row, index) => {
      svg.append(createSvg("circle", { cx: x(index), cy: y(row.actual), r: 3.8, fill: colors.acid }));
      const hit = createSvg("rect", { x: x(index) - 23, y: pad.top, width: 46, height: height - pad.top - pad.bottom, fill: "transparent", tabindex: 0, "aria-label": `${row.Date}: actual ${Math.round(row.actual)}, prediction ${Math.round(row.prediction)}` });
      const show = (event) => {
        const host = $(".county-chart-wrap").getBoundingClientRect();
        const pointX = event.clientX || host.left + (x(index) / width) * host.width;
        const pointY = event.clientY || host.top + (y(row.actual) / height) * host.height;
        tooltip.innerHTML = `<strong>${new Date(`${row.Date}T00:00:00`).toLocaleDateString("en-US", { month: "short", year: "numeric" })}</strong><br>Actual: ${formatNumber(row.actual)}<br>Prediction: ${formatNumber(row.prediction)}<br>80% interval: ${formatNumber(row.lower_80)}–${formatNumber(row.upper_80)}`;
        tooltip.style.display = "block";
        tooltip.style.left = `${Math.min(pointX - host.left + 12, host.width - 175)}px`;
        tooltip.style.top = `${Math.max(55, pointY - host.top - 85)}px`;
      };
      hit.addEventListener("pointermove", show);
      hit.addEventListener("focus", show);
      hit.addEventListener("pointerleave", () => { tooltip.style.display = "none"; });
      hit.addEventListener("blur", () => { tooltip.style.display = "none"; });
      svg.append(hit);
    });
  }

  function setupRange() {
    const slider = $("#range-slider");
    const update = () => {
      const threshold = Number(slider.value);
      $("#range-output").textContent = `${threshold} miles`;
      const progress = ((threshold - 150) / 150) * 100;
      slider.style.background = `linear-gradient(90deg, ${colors.acid} 0 ${progress}%, rgba(255,255,255,.15) ${progress}%)`;
      const mapping = { all: "all", BEV: "bev", PHEV: "phev" };
      Object.entries(mapping).forEach(([sourceType, targetType]) => {
        const row = data.rangeSensitivity.find((item) => item.vehicle_type === sourceType && item.threshold_miles === threshold);
        const value = row.share_below_pct;
        $(`#range-${targetType}`).textContent = `${value.toFixed(value === 100 ? 0 : 1)}%`;
        $(`.range-ring[data-type="${targetType}"]`).style.setProperty("--value", `${value}%`);
      });
    };
    slider.addEventListener("input", update);
    update();
  }

  function drawStability() {
    const svg = $("#stability-chart");
    const width = 760;
    const height = 450;
    const pad = { top: 30, right: 24, bottom: 55, left: 55 };
    setSvg(svg, width, height);
    const rows = data.temporalRobustness;
    const periods = [...new Set(rows.map((row) => row.evaluation_end))];
    const max = Math.max(...rows.map((row) => row.rmse)) * 1.12;
    const x = (index) => pad.left + index * ((width - pad.left - pad.right) / (periods.length - 1));
    const y = (value) => height - pad.bottom - (value / max) * (height - pad.top - pad.bottom);
    [0, .25, .5, .75, 1].forEach((fraction) => {
      const yy = y(max * fraction);
      svg.append(createSvg("line", { x1: pad.left, y1: yy, x2: width - pad.right, y2: yy, class: "svg-grid" }));
      svg.append(createSvg("text", { x: pad.left - 9, y: yy + 3, "text-anchor": "end", class: "svg-axis" }, Math.round(max * fraction)));
    });
    periods.forEach((period, index) => svg.append(createSvg("text", { x: x(index), y: height - 18, "text-anchor": "middle", class: "svg-axis" }, `${Number(period.slice(0,4)) - 1}–${period.slice(2,4)}`)));
    [["poisson_glm", colors.acid], ["random_forest", colors.orange], ["lag_12_baseline", colors.violet]].forEach(([model, color]) => {
      const modelRows = periods.map((period) => rows.find((row) => row.model === model && row.evaluation_end === period));
      const points = modelRows.map((row, index) => [x(index), y(row.rmse)]);
      svg.append(createSvg("path", { d: pathFrom(points), fill: "none", stroke: color, "stroke-width": 2.5 }));
      points.forEach(([cx, cy], index) => {
        svg.append(createSvg("circle", { cx, cy, r: 4.5, fill: "#151715", stroke: color, "stroke-width": 2.5 }));
        if (modelRows[index].rmse === Math.min(...rows.filter((row) => row.evaluation_end === periods[index]).map((row) => row.rmse))) {
          svg.append(createSvg("circle", { cx, cy, r: 10, fill: "none", stroke: color, opacity: .25 }));
        }
      });
    });
  }

  function setupTabs() {
    const tabs = $$(".lab-tab");
    const activate = (tab) => {
      tabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", String(active));
        $(`#panel-${item.dataset.panel}`).hidden = !active;
      });
      if (tab.dataset.panel === "county") drawCounty($("#county-select").value);
      if (tab.dataset.panel === "stability") drawStability();
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => activate(tab));
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
        event.preventDefault();
        const next = (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
        tabs[next].focus();
        activate(tabs[next]);
      });
    });
  }

  function setupResize() {
    let timeout;
    addEventListener("resize", () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        drawHeroChart();
        const activeMetric = $(".metric-toggle.active")?.dataset.metric || "rmse";
        drawModelChart(activeMetric);
        if (!$("#panel-county").hidden) drawCounty($("#county-select").value);
        if (!$("#panel-stability").hidden) drawStability();
      }, 140);
    });
  }

  function setupLiveExplorer() {
    const section = $("#live");
    if (!section) return;
    if (!liveData) {
      section.classList.add("live-unavailable");
      $("#live-map-note").textContent = "The current-data bundle could not be loaded. Historical model evidence remains available below.";
      return;
    }

    const totals = liveData.stateTotals;
    $("#live-ev-total").textContent = formatNumber(totals.ev_stock);
    $("#live-transaction-total").textContent = formatNumber(totals.recent_ev_transactions);
    $("#live-station-total").textContent = formatNumber(totals.public_stations);
    $("#live-port-total").textContent = formatNumber(totals.public_ports);
    $("#live-version").textContent = liveData.sourceVersion.slice(0, 10);

    const freshness = (source, fallback) => {
      const raw = source?.rows_updated_at || source?.last_updated;
      if (!raw) return fallback;
      const date = new Date(raw);
      return Number.isNaN(date.valueOf()) ? fallback : date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    };
    $("#live-ev-date").textContent = freshness(liveData.sources.ev_population, "Source date unavailable");
    $("#live-registration-date").textContent = `${liveData.latestRegistrationMonth || "Latest month unavailable"} data`;
    $("#live-charger-date").textContent = freshness(liveData.sources.charging_inventory, "Source date unavailable");
    $$('[data-live-status]').forEach((node) => {
      const status = liveData.sources[node.dataset.liveStatus]?.status || "unknown";
      node.classList.add(status);
      node.title = status;
    });

    const svg = $("#live-map");
    const tooltip = $("#live-map-tooltip");
    const width = 760;
    const height = 455;
    const bounds = { west: -125.0, east: -116.75, south: 45.45, north: 49.15 };
    const project = (longitude, latitude) => [
      30 + ((longitude - bounds.west) / (bounds.east - bounds.west)) * (width - 60),
      24 + ((bounds.north - latitude) / (bounds.north - bounds.south)) * (height - 48),
    ];
    const outlineCoordinates = [
      [-124.72, 48.38], [-124.55, 47.10], [-124.08, 46.25], [-123.15, 46.18],
      [-122.77, 45.56], [-116.98, 45.56], [-116.92, 49.00], [-123.25, 49.00],
      [-123.13, 48.63], [-122.72, 48.42], [-122.57, 48.05], [-122.31, 47.72],
      [-122.55, 47.32], [-123.05, 47.08], [-123.93, 47.34], [-124.38, 47.86],
    ];
    const outline = outlineCoordinates.map(([lon, lat], index) => {
      const [x, y] = project(lon, lat);
      return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    svg.append(createSvg("path", { d: `${outline} Z`, class: "wa-outline" }));

    liveData.stations.forEach((station) => {
      const longitude = Number(station.Longitude);
      const latitude = Number(station.Latitude);
      if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return;
      const [cx, cy] = project(longitude, latitude);
      const fast = Number(station.DC_Fast_Ports) > 0;
      const circle = createSvg("circle", {
        cx,
        cy,
        r: Math.min(5.5, 1.25 + Math.sqrt(Number(station.Ports) || 1) * .55),
        fill: fast ? colors.acid : colors.blue,
        opacity: fast ? .72 : .34,
        class: "station-point",
        tabindex: 0,
        "data-county": station.County,
        "aria-label": `${station.Station_Name}, ${station.County} County, ${station.Ports} ports`,
      });
      const show = (event) => {
        const host = svg.getBoundingClientRect();
        const pointX = event.clientX || host.left + (cx / width) * host.width;
        const pointY = event.clientY || host.top + (cy / height) * host.height;
        tooltip.innerHTML = `<strong>${station.Station_Name}</strong>${station.County} County · ${formatNumber(station.Ports)} port${Number(station.Ports) === 1 ? "" : "s"}<br>${fast ? `${formatNumber(station.DC_Fast_Ports)} DC-fast capable` : "No DC-fast connector recorded"}<br>${station.Network || "Network not listed"}`;
        tooltip.style.display = "block";
        tooltip.style.left = `${Math.min(Math.max(8, pointX - host.left + 10), host.width - 200)}px`;
        tooltip.style.top = `${Math.min(Math.max(8, pointY - host.top - 78), host.height - 105)}px`;
      };
      circle.addEventListener("pointermove", show);
      circle.addEventListener("focus", show);
      circle.addEventListener("pointerleave", () => { tooltip.style.display = "none"; });
      circle.addEventListener("blur", () => { tooltip.style.display = "none"; });
      circle.addEventListener("click", () => selectCounty(station.County));
      svg.append(circle);
    });

    let currentMetric = "Opportunity_Score";
    let selectedCounty = null;
    const metricMetaLive = {
      Opportunity_Score: { suffix: " / 100", decimals: 1 },
      EVs_Per_Port: { suffix: " EVs", decimals: 1 },
      Registration_Growth_Pct: { suffix: "%", decimals: 1 },
    };

    function renderRankings() {
      const meta = metricMetaLive[currentMetric];
      const rows = [...liveData.counties]
        .filter((row) => row[currentMetric] != null && Number.isFinite(Number(row[currentMetric])))
        .sort((a, b) => Number(b[currentMetric]) - Number(a[currentMetric]));
      const max = Math.max(...rows.map((row) => Number(row[currentMetric])), 1);
      const list = $("#county-rank-list");
      list.replaceChildren();
      rows.forEach((row, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `rank-row${selectedCounty === row.County ? " active" : ""}`;
        button.innerHTML = `<i>${String(index + 1).padStart(2, "0")}</i><span>${row.County}</span><div class="rank-bar"><b style="--rank-width:${Math.max(2, Number(row[currentMetric]) / max * 100)}%"></b></div><strong>${formatNumber(row[currentMetric], meta.decimals)}${meta.suffix}</strong>`;
        button.addEventListener("click", () => selectCounty(row.County));
        list.append(button);
      });
    }

    function selectCounty(county) {
      selectedCounty = county;
      const row = liveData.counties.find((item) => item.County === county);
      if (!row) return;
      $$(".station-point", svg).forEach((point) => point.classList.toggle("dimmed", point.dataset.county !== county));
      const visibleStations = liveData.stations.filter((station) => station.County === county).length;
      $("#live-map-title").textContent = `${county} County · ${formatNumber(visibleStations)} mapped stations`;
      $("#county-detail").innerHTML = `<h3>${county} County <span>#${row.Opportunity_Rank} signal</span></h3><div class="county-detail-grid"><div><span>EVS / PORT</span><strong>${row.EVs_Per_Port == null ? "—" : formatNumber(row.EVs_Per_Port, 1)}</strong></div><div><span>12M GROWTH</span><strong>${row.Registration_Growth_Pct == null ? "—" : `${formatNumber(row.Registration_Growth_Pct, 1)}%`}</strong></div><div><span>DC FAST SHARE</span><strong>${row.DC_Fast_Share_Pct == null ? "—" : `${formatNumber(row.DC_Fast_Share_Pct, 1)}%`}</strong></div></div><p>${formatNumber(row.EV_Stock)} registered EVs · ${formatNumber(row.Recent_EV_Transactions)} latest 12-month transactions · ${formatNumber(row.Public_Ports)} mapped public ports.</p>`;
      renderRankings();
    }

    $$("[data-live-metric]").forEach((button) => button.addEventListener("click", () => {
      currentMetric = button.dataset.liveMetric;
      $$("[data-live-metric]").forEach((item) => item.classList.toggle("active", item === button));
      renderRankings();
    }));
    $("#live-reset").addEventListener("click", () => {
      selectedCounty = null;
      $$(".station-point", svg).forEach((point) => point.classList.remove("dimmed"));
      $("#live-map-title").textContent = `${formatNumber(liveData.stations.length)} mapped stations`;
      $("#county-detail").innerHTML = "<p>Select a county to inspect its demand, supply, growth, and charging mix.</p>";
      renderRankings();
    });

    $("#live-map-title").textContent = `${formatNumber(liveData.stations.length)} mapped stations`;
    renderRankings();
    selectCounty(liveData.counties[0]?.County);
  }

  setupChrome();
  setupReveal();
  setupCounters();
  setupModelControls();
  setupCountyExplorer();
  setupRange();
  setupTabs();
  setupLiveExplorer();
  drawHeroChart();
  drawModelChart();
  setupResize();
})();
