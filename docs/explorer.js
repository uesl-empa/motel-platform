/*
 * MOTEL data explorer.
 *
 * Renders the published MOTEL database from data/motel-data.js, which
 * docs/build_data.py generates from motel-db/. Every view has its own URL, so a
 * technology or a comparison can be linked from an issue or a paper:
 *
 *   #/                                        all technologies
 *   #/technology/TECH_00001                   one technology and its records
 *   #/compare?attribute=ATTR_00007&year=2030  one parameter across technologies
 *   #/sources                                 sources
 *   #/vocabulary                              attributes, carriers, scopes
 *
 * Database content is inserted with text nodes only, never as HTML.
 */
(function () {
  "use strict";

  const REPOSITORY = "https://github.com/uesl-empa/motel-platform";
  const DEFAULT_ATTRIBUTE_NAME = "Capital Expenditure Per Capacity";
  const SCOPE_TYPES = ["geographic_scope", "temporal_scope", "capacity_scope", "system_boundary"];
  const SCOPE_LABELS = {
    geographic_scope: "Region",
    temporal_scope: "Period",
    capacity_scope: "Capacity",
    system_boundary: "Boundary",
  };
  const NO_UNIT = new Set(["", "—", "-", "–"]);

  const app = document.getElementById("app");
  const tooltip = document.getElementById("tooltip");
  const nav = document.getElementById("explorer-nav");
  const data = window.MOTEL_DATA;

  // -------------------------------------------------------------------------
  // DOM and formatting helpers
  // -------------------------------------------------------------------------
  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "className") node.className = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : String(value));
    }
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  /** Add views to the page; arrays of nodes are flattened, unlike Element.append. */
  function mount(...children) {
    for (const child of children.flat(Infinity)) {
      if (child) app.append(child);
    }
  }

  function isNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  const numberFormat = new Intl.NumberFormat("en", { maximumSignificantDigits: 6 });
  const tickFormat = new Intl.NumberFormat("en", { notation: "compact", maximumSignificantDigits: 3 });
  const countFormat = new Intl.NumberFormat("en");

  function formatValue(value) {
    if (isNumber(value)) return numberFormat.format(value);
    if (Array.isArray(value)) return value.map(formatValue).join(", ");
    if (value === null || value === undefined) return "";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function unitOf(attribute) {
    const unit = attribute && attribute.unit;
    return unit && !NO_UNIT.has(unit.trim()) ? unit : "";
  }

  function compareText(a, b) {
    return String(a ?? "").localeCompare(String(b ?? ""), "en", { numeric: true, sensitivity: "base" });
  }

  function groupBy(items, key) {
    const groups = new Map();
    for (const item of items) {
      const k = key(item);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(item);
    }
    return groups;
  }

  function countBy(items, key) {
    const counts = new Map();
    for (const item of items) counts.set(key(item), (counts.get(key(item)) || 0) + 1);
    return counts;
  }

  function mostCommon(values) {
    let best = null;
    let bestCount = -1;
    for (const [value, count] of countBy(values, (v) => v)) {
      if (count > bestCount) {
        best = value;
        bestCount = count;
      }
    }
    return best;
  }

  /** A short label for a scope token: GEO_CH -> CH, BOUND_PLANT_READY -> Plant ready. */
  function shortScope(type, token) {
    if (!token) return "";
    const text = String(token).replace(/^(GEO|TIME|CAP|BOUND)_/, "");
    if (type === "geographic_scope" || /^\d/.test(text)) return text.replace(/_/g, " ");
    const words = text.replace(/_/g, " ").toLowerCase();
    return words.charAt(0).toUpperCase() + words.slice(1);
  }

  function scopeDescription(type, token) {
    return (data.scopes[type] && data.scopes[type][token]) || token;
  }

  function issueUrl(title, body) {
    return `${REPOSITORY}/issues/new?${new URLSearchParams({ title, body })}`;
  }

  function externalLink(href, text) {
    return el("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);
  }

  function sourceNode(source) {
    if (!source) return null;
    const name = source.source_name || source.id;
    return source.link && /^https?:\/\//.test(source.link) ? externalLink(source.link, name) : name;
  }

  function joinNodes(nodes, separator) {
    const out = [];
    nodes.filter(Boolean).forEach((node, index) => {
      if (index) out.push(separator);
      out.push(node);
    });
    return out;
  }

  function table(columns, rows, caption) {
    return el(
      "div",
      { className: "table-wrap" },
      el(
        "table",
        { className: "data-table" },
        caption ? el("caption", {}, caption) : null,
        el("thead", {}, el("tr", {}, columns.map((c) => el("th", { className: c.num ? "num" : null, scope: "col" }, c.label)))),
        el("tbody", {}, rows)
      )
    );
  }

  function cell(content, numeric) {
    return el("td", { className: numeric ? "num" : null }, content);
  }

  function hero(title, subtitle, breadcrumb) {
    return el(
      "header",
      { className: "explorer-hero" },
      breadcrumb ? el("p", { className: "breadcrumb" }, el("a", { href: breadcrumb.href }, `← ${breadcrumb.label}`)) : null,
      el("h1", {}, title),
      subtitle ? el("p", { className: "subtitle" }, subtitle) : null
    );
  }

  function searchBox(placeholder, onInput) {
    const input = el("input", { type: "search", placeholder, "aria-label": placeholder });
    input.addEventListener("input", () => onInput(input.value.trim().toLowerCase()));
    return input;
  }

  // -------------------------------------------------------------------------
  // Tooltip: one element, filled with text nodes
  // -------------------------------------------------------------------------
  function showTooltip(parts, event, anchor) {
    tooltip.replaceChildren(...parts);
    tooltip.hidden = false;
    const box = tooltip.getBoundingClientRect();
    let x;
    let y;
    if (event && typeof event.clientX === "number") {
      x = event.clientX + 14;
      y = event.clientY + 14;
      if (y + box.height > window.innerHeight - 8) y = event.clientY - box.height - 14;
    } else {
      const rect = anchor.getBoundingClientRect();
      x = rect.left + rect.width / 3;
      y = rect.bottom + 6;
    }
    x = Math.min(x, window.innerWidth - box.width - 8);
    tooltip.style.left = `${Math.max(8, x)}px`;
    tooltip.style.top = `${Math.max(8, y)}px`;
  }

  function hideTooltip() {
    tooltip.hidden = true;
  }

  // -------------------------------------------------------------------------
  // Indexes
  // -------------------------------------------------------------------------
  if (!data) {
    app.replaceChildren(
      el("h1", {}, "The data has not been built"),
      el("p", {}, "Run python docs/build_data.py from the repository root to generate docs/data/motel-data.js, then reload this page.")
    );
    return;
  }

  const byId = (items) => new Map(items.map((item) => [item.id, item]));
  const technologies = byId(data.technologies);
  const processes = byId(data.processes);
  const sources = byId(data.sources);
  const carriers = byId(data.carriers);
  const attributes = byId(data.attributes);
  const recordsByTech = groupBy(data.records, (record) => record.tech_id);
  const allValues = data.records.flatMap((record) => record.values.map((value) => ({ record, ...value })));
  const valueCount = countBy(allValues, (value) => value.attribute_id);
  const numericCount = countBy(allValues.filter((value) => isNumber(value.value)), (value) => value.attribute_id);

  const sourceRecords = new Map();
  for (const record of data.records) {
    for (const link of record.sources) {
      if (!sourceRecords.has(link.source_id)) sourceRecords.set(link.source_id, []);
      sourceRecords.get(link.source_id).push(record);
    }
  }

  const carrierRecords = countBy(
    data.records.flatMap((record) => [...new Set([...record.inputs, ...record.outputs].map((flow) => flow.carrier_id))]),
    (id) => id
  );

  function valueSources(record, attributeId) {
    return record.sources
      .filter((link) => link.attributes.includes(attributeId))
      .map((link) => sources.get(link.source_id))
      .filter(Boolean);
  }

  function technologyName(id) {
    const tech = technologies.get(id);
    return (tech && tech.technology_name) || id;
  }

  // -------------------------------------------------------------------------
  // View: technologies
  // -------------------------------------------------------------------------
  function renderTechnologies() {
    document.title = "MOTEL Data Explorer";
    const stats = [
      ["Technologies", technologies.size],
      ["Records", data.records.length],
      ["Values", allValues.length],
      ["Sources", sources.size],
      ["Attributes", attributes.size],
    ];

    const rows = data.technologies
      .slice()
      .sort((a, b) => compareText(a.technology_name, b.technology_name))
      .map((tech) => {
        const records = recordsByTech.get(tech.id) || [];
        const process = processes.get(tech.main_process);
        const years = [...new Set(records.flatMap((r) => r.values.map((v) => v.time_index)).filter(Boolean))].sort(compareText);
        const values = records.reduce((n, r) => n + r.values.length, 0);
        const text = [tech.technology_name, tech.technology_description, tech.technology_variant, process && process.process_name]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        const node = el(
          "tr",
          {},
          cell(el("a", { href: `#/technology/${encodeURIComponent(tech.id)}` }, tech.technology_name || tech.id)),
          cell(process ? process.process_name : ""),
          cell(countFormat.format(records.length), true),
          cell(years.join(", ")),
          cell(countFormat.format(values), true)
        );
        return { text, node };
      });

    const tbody = el("tbody");
    const count = el("p", { className: "muted small" });
    function apply(query) {
      const shown = rows.filter((row) => !query || row.text.includes(query));
      tbody.replaceChildren(...shown.map((row) => row.node));
      count.textContent = `${shown.length} of ${rows.length} technologies`;
    }

    mount(
      hero(
        "MOTEL Data Explorer",
        `Browse the technologies, parameters, and sources in the MOTEL database. Data generated ${data.generated} from motel-db.`
      ),
      el(
        "div",
        { className: "stat-grid" },
        stats.map(([label, value]) =>
          el("div", { className: "stat" }, el("span", { className: "stat-label" }, label), el("span", { className: "stat-value" }, countFormat.format(value)))
        )
      ),
      el("div", { className: "filter-row" }, el("label", {}, "Search technologies", searchBox("Name, process, or description", apply))),
      count,
      el(
        "div",
        { className: "table-wrap" },
        el(
          "table",
          { className: "data-table" },
          el(
            "thead",
            {},
            el(
              "tr",
              {},
              ["Technology", "Main process", "Records", "Years", "Values"].map((label, i) =>
                el("th", { scope: "col", className: i === 2 || i === 4 ? "num" : null }, label)
              )
            )
          ),
          tbody
        )
      ),
      el(
        "p",
        { className: "muted small" },
        "Missing a technology, a value, or a source? ",
        externalLink(
          issueUrl("Data suggestion: ", "Which technology, parameter, or source should be added or corrected?\n\n- Technology:\n- Parameter and value:\n- Source (link, page or table):\n"),
          "Suggest it on GitHub"
        ),
        "."
      )
    );
    apply("");
  }

  // -------------------------------------------------------------------------
  // View: one technology
  // -------------------------------------------------------------------------
  function renderTechnology(route) {
    const tech = technologies.get(route.id);
    if (!tech) {
      renderNotFound(`No technology with the ID ${route.id}.`);
      return;
    }
    document.title = `${tech.technology_name} · MOTEL Data Explorer`;
    const process = processes.get(tech.main_process);
    const records = recordsByTech.get(tech.id) || [];

    const meta = [
      ["Technology ID", tech.id],
      ["Variant", tech.technology_variant],
      ["Operation unit", tech.main_operation_unit],
      ["Main process", process ? process.process_name : tech.main_process],
      ["Process type", process && [process.process_type, process.process_category, process.main_sector].filter(Boolean).join(" · ")],
    ].filter(([, value]) => value);

    mount(
      hero(tech.technology_name || tech.id, tech.technology_description, { href: "#/", label: "All technologies" }),
      el("dl", { className: "meta-list" }, meta.map(([label, value]) => [el("dt", {}, label), el("dd", {}, value)])),
      el(
        "div",
        { className: "feedback" },
        el(
          "a",
          {
            className: "btn",
            href: issueUrl(
              `Data feedback: ${tech.technology_name} (${tech.id})`,
              `Technology: ${tech.technology_name} (${tech.id})\nPage: ${location.href}\n\nWhat should be corrected or added?\n\n- Record (e.g. LE_00001):\n- Parameter:\n- Suggested value or source (link, page or table):\n`
            ),
            target: "_blank",
            rel: "noopener noreferrer",
          },
          "Suggest a correction or a source"
        )
      ),
      el("h2", {}, records.length === 1 ? "1 record" : `${records.length} records`),
      records.length ? records.map(recordCard) : el("p", { className: "muted" }, "This technology has no linked records yet.")
    );
  }

  function recordCard(record) {
    const years = [...new Set(record.values.map((v) => v.time_index || ""))].sort(compareText);
    const byAttribute = groupBy(record.values, (v) => v.attribute_id);

    const rows = [...byAttribute.entries()].map(([attributeId, values]) => {
      const attribute = attributes.get(attributeId) || { id: attributeId };
      const numeric = values.some((v) => isNumber(v.value));
      const nameNode = numeric
        ? el("a", { href: `#/compare?attribute=${encodeURIComponent(attributeId)}&year=${encodeURIComponent(values.find((v) => isNumber(v.value)).time_index || "")}` }, attribute.attribute_name || attributeId)
        : attribute.attribute_name || attributeId;
      return el(
        "tr",
        {},
        cell(nameNode),
        cell(unitOf(attribute)),
        years.map((year) => {
          const matches = values.filter((v) => (v.time_index || "") === year);
          return cell(matches.map((v) => formatValue(v.value)).join("; "), true);
        }),
        cell(joinNodes(valueSources(record, attributeId).map(sourceNode), ", "))
      );
    });

    const flows = [
      ...record.inputs.map((flow) => ["Input", flow]),
      ...record.outputs.map((flow) => ["Output", flow]),
    ].map(([direction, flow]) => {
      const carrier = carriers.get(flow.carrier_id);
      return el("tr", {}, cell(direction), cell(carrier ? carrier.carrier_name : flow.carrier_id), cell(formatValue(flow.share), true), cell(flow.unit || ""));
    });

    const scopeChips = SCOPE_TYPES.filter((type) => record.scope[type]).map((type) =>
      el(
        "li",
        {},
        el("span", { className: "chip", title: scopeDescription(type, record.scope[type]) }, el("span", { className: "chip-key" }, `${SCOPE_LABELS[type]}: `), shortScope(type, record.scope[type]))
      )
    );

    return el(
      "section",
      { className: "record-card", id: record.id },
      el("h3", {}, `Record ${record.id}`),
      scopeChips.length ? el("ul", { className: "chips", "aria-label": "Scope" }, scopeChips) : null,
      rows.length
        ? table(
            [{ label: "Parameter" }, { label: "Unit" }, ...years.map((y) => ({ label: y || "No year", num: true })), { label: "Sources" }],
            rows
          )
        : el("p", { className: "muted" }, "No values recorded."),
      flows.length ? table([{ label: "Flow" }, { label: "Carrier" }, { label: "Share", num: true }, { label: "Unit" }], flows, "Energy and material balance") : null,
      record.date_created ? el("p", { className: "muted small" }, `Harmonised ${record.date_created}`) : null
    );
  }

  // -------------------------------------------------------------------------
  // View: compare one parameter across technologies
  // -------------------------------------------------------------------------
  function renderCompare(route) {
    document.title = "Compare a parameter · MOTEL Data Explorer";
    const numericAttributes = data.attributes
      .filter((attribute) => numericCount.get(attribute.id))
      .sort((a, b) => compareText(a.attribute_name, b.attribute_name));
    if (!numericAttributes.length) {
      renderNotFound("The database has no numeric values to compare yet.");
      return;
    }

    const requested = attributes.get(route.params.get("attribute"));
    const fallback = numericAttributes.find((a) => a.attribute_name === DEFAULT_ATTRIBUTE_NAME) || numericAttributes[0];
    const state = {
      attribute: requested && numericCount.get(requested.id) ? requested.id : fallback.id,
      year: route.params.get("year"),
      region: route.params.get("region") || "",
    };

    const attributeSelect = el(
      "select",
      { "aria-label": "Parameter" },
      numericAttributes.map((attribute) =>
        el("option", { value: attribute.id }, `${attribute.attribute_name}${unitOf(attribute) ? ` (${unitOf(attribute)})` : ""}`)
      )
    );
    const yearSelect = el("select", { "aria-label": "Year" });
    const regionSelect = el("select", { "aria-label": "Region" });
    const chartHolder = el("div");
    const tableHolder = el("div");

    function valuesFor(attributeId) {
      return allValues.filter((value) => value.attribute_id === attributeId);
    }

    function fillSelect(select, options, selected) {
      select.replaceChildren(...options.map(([value, label]) => el("option", { value }, label)));
      select.value = options.some(([value]) => value === selected) ? selected : options.length ? options[0][0] : "";
      return select.value;
    }

    function syncFilters() {
      const values = valuesFor(state.attribute);
      const numeric = values.filter((v) => isNumber(v.value));
      const years = [...new Set(numeric.map((v) => v.time_index || ""))].sort(compareText);
      const defaultYear = mostCommon(numeric.map((v) => v.time_index || ""));
      state.year = fillSelect(yearSelect, years.map((y) => [y, y || "No year"]), state.year ?? defaultYear);
      const regions = [...new Set(values.map((v) => v.record.scope.geographic_scope).filter(Boolean))].sort(compareText);
      state.region = fillSelect(regionSelect, [["", "All regions"], ...regions.map((r) => [r, `${shortScope("geographic_scope", r)} · ${scopeDescription("geographic_scope", r)}`])], state.region);
    }

    function update() {
      const attribute = attributes.get(state.attribute);
      const unit = unitOf(attribute);
      const inRegion = (v) => !state.region || v.record.scope.geographic_scope === state.region;
      const values = valuesFor(state.attribute).filter(inRegion);
      const points = values.filter((v) => isNumber(v.value) && (v.time_index || "") === state.year);
      const textCount = values.filter((v) => !isNumber(v.value) && (v.time_index || "") === state.year).length;

      const techCount = new Set(points.map((p) => p.record.tech_id)).size;
      const subtitle = [
        `${points.length} ${points.length === 1 ? "value" : "values"} from ${techCount} ${techCount === 1 ? "technology" : "technologies"}${state.region ? ` in ${shortScope("geographic_scope", state.region)}` : ""}.`,
        textCount ? `${textCount} text ${textCount === 1 ? "value is" : "values are"} listed in the table but not charted.` : "",
        "Hover or focus a bar for its record and sources; select it to open the technology.",
      ].filter(Boolean).join(" ");

      chartHolder.replaceChildren(
        el(
          "section",
          { className: "chart-card", "aria-label": "Chart" },
          el("h2", { className: "chart-title" }, `${attribute.attribute_name}${unit ? ` (${unit})` : ""}, ${state.year || "no year"}`),
          el("p", { className: "chart-subtitle" }, subtitle),
          attribute.attribute_description ? el("p", { className: "chart-subtitle" }, attribute.attribute_description) : null,
          points.length ? barChart(points, unit) : el("p", { className: "empty-state" }, "No numeric values for this selection.")
        )
      );

      const tableRows = values
        .slice()
        .sort((a, b) => compareText(technologyName(a.record.tech_id), technologyName(b.record.tech_id)) || compareText(a.time_index, b.time_index))
        .map((v) =>
          el(
            "tr",
            {},
            cell(el("a", { href: `#/technology/${encodeURIComponent(v.record.tech_id)}` }, technologyName(v.record.tech_id))),
            cell(v.record.id),
            cell(v.time_index || ""),
            cell(formatValue(v.value), isNumber(v.value)),
            cell(unit),
            cell(shortScope("geographic_scope", v.record.scope.geographic_scope)),
            cell(joinNodes(valueSources(v.record, state.attribute).map(sourceNode), ", "))
          )
        );
      tableHolder.replaceChildren(
        el("h2", {}, "All values"),
        table(
          [{ label: "Technology" }, { label: "Record" }, { label: "Year" }, { label: "Value", num: true }, { label: "Unit" }, { label: "Region" }, { label: "Sources" }],
          tableRows,
          `${attribute.attribute_name}: every year${state.region ? `, ${shortScope("geographic_scope", state.region)} only` : ""}`
        )
      );

      const query = new URLSearchParams({ attribute: state.attribute, year: state.year });
      if (state.region) query.set("region", state.region);
      history.replaceState(null, "", `#/compare?${query}`);
    }

    attributeSelect.value = state.attribute;
    attributeSelect.addEventListener("change", () => {
      state.attribute = attributeSelect.value;
      state.year = null;
      syncFilters();
      update();
    });
    yearSelect.addEventListener("change", () => {
      state.year = yearSelect.value;
      update();
    });
    regionSelect.addEventListener("change", () => {
      state.region = regionSelect.value;
      update();
    });

    mount(
      hero("Compare a parameter", "One parameter across every technology that reports it, for a chosen year and region."),
      el(
        "div",
        { className: "filter-row" },
        el("label", {}, "Parameter", attributeSelect),
        el("label", {}, "Year", yearSelect),
        el("label", {}, "Region", regionSelect)
      ),
      chartHolder,
      tableHolder
    );
    syncFilters();
    update();
  }

  function niceStep(span, count) {
    const raw = span / Math.max(1, count);
    const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
    const normalized = raw / magnitude;
    return (normalized < 1.5 ? 1 : normalized < 3 ? 2 : normalized < 7 ? 5 : 10) * magnitude;
  }

  /** Horizontal bars for one series: sorted, labelled at the tip, one hover target per row. */
  function barChart(points, unit) {
    const sorted = points.slice().sort((a, b) => b.value - a.value);

    // Technologies with several records in the selection are told apart by the
    // scope fields that differ between those records.
    const perTech = groupBy(sorted, (p) => p.record.tech_id);
    const detailOf = new Map();
    for (const group of perTech.values()) {
      if (group.length < 2) continue;
      const varying = SCOPE_TYPES.filter((type) => new Set(group.map((p) => p.record.scope[type] || "")).size > 1);
      for (const p of group) {
        const detail = varying.map((type) => shortScope(type, p.record.scope[type])).filter(Boolean).join(" · ");
        detailOf.set(p, detail || p.record.id);
      }
    }

    let lo = Math.min(0, ...sorted.map((p) => p.value));
    let hi = Math.max(0, ...sorted.map((p) => p.value));
    if (lo === hi) hi = lo + 1;
    const step = niceStep(hi - lo, 4);
    lo = Math.floor(lo / step) * step;
    hi = Math.ceil(hi / step) * step;
    // Room beside the bar ends for the value labels.
    const padLeft = lo < 0 ? 14 : 0;
    const padRight = hi > 0 ? 16 : 0;
    const x = (v) => padLeft + ((v - lo) / (hi - lo)) * (100 - padLeft - padRight);
    const ticks = [];
    for (let t = lo; t <= hi + step / 2; t += step) ticks.push(Math.round(t / step) * step);

    const gridLines = () =>
      ticks.map((t) => el("span", { className: t === 0 ? "grid-line zero" : "grid-line", style: `left:${x(t)}%`, "aria-hidden": "true" }));

    const rows = sorted.map((p) => {
      const tech = technologies.get(p.record.tech_id);
      const name = (tech && tech.technology_name) || p.record.tech_id;
      const detail = detailOf.get(p);
      const valueText = `${formatValue(p.value)}${unit ? ` ${unit}` : ""}`;
      const start = x(Math.min(0, p.value));
      const width = Math.abs(x(p.value) - x(0));
      const negative = p.value < 0;
      const valueStyle = negative ? `right:${100 - x(p.value)}%` : `left:${x(p.value)}%`;
      const sourceNames = valueSources(p.record, p.attribute_id).map((s) => s.source_name || s.id);

      const tooltipParts = () => [
        el("span", { className: "tooltip-value" }, valueText),
        el("span", { className: "tooltip-line" }, name),
        el("span", { className: "tooltip-line" }, `Record ${p.record.id} · ${p.time_index || "no year"}`),
        el(
          "span",
          { className: "tooltip-line" },
          SCOPE_TYPES.filter((type) => p.record.scope[type]).map((type) => shortScope(type, p.record.scope[type])).join(" · ")
        ),
        sourceNames.length ? el("span", { className: "tooltip-line" }, `Source: ${sourceNames.join(", ")}`) : null,
      ].filter(Boolean);

      const open = () => {
        location.hash = `#/technology/${encodeURIComponent(p.record.tech_id)}`;
      };

      return el(
        "div",
        {
          className: "bar-row",
          role: "listitem",
          tabindex: "0",
          "aria-label": `${name}${detail ? `, ${detail}` : ""}: ${valueText}`,
          onpointermove: (event) => showTooltip(tooltipParts(), event),
          onpointerleave: hideTooltip,
          onfocus: (event) => showTooltip(tooltipParts(), null, event.currentTarget),
          onblur: hideTooltip,
          onclick: open,
          onkeydown: (event) => {
            if (event.key === "Enter") open();
          },
        },
        el("span", { className: "bar-label", title: detail ? `${name} · ${detail}` : name }, name, detail ? el("span", { className: "bar-label-detail" }, ` · ${detail}`) : null),
        el(
          "span",
          { className: "bar-track" },
          gridLines(),
          el("span", { className: negative ? "bar negative" : "bar", style: `left:${start}%;width:${width}%` }),
          el("span", { className: "bar-value", style: valueStyle, "data-negative": negative ? "true" : null }, valueText)
        )
      );
    });

    const chart = el(
      "div",
      { className: "bar-chart" },
      el("div", { role: "list" }, rows),
      el(
        "div",
        { className: "axis-row", "aria-hidden": "true" },
        el("span"),
        el("span", { className: "axis-ticks" }, ticks.map((t) => el("span", { className: "axis-tick", style: `left:${x(t)}%` }, tickFormat.format(t))))
      )
    );
    if (typeof ResizeObserver === "function") {
      new ResizeObserver(() => placeValueLabels(chart)).observe(chart);
    }
    return chart;
  }

  /**
   * Keep every value label inside the chart: beside the bar end when it fits,
   * inside the bar when it does not, and otherwise hidden. A hidden value is
   * still in the row's tooltip and in the table below the chart.
   */
  function placeValueLabels(chart) {
    const gap = 4;
    for (const track of chart.querySelectorAll(".bar-track")) {
      const bar = track.querySelector(".bar");
      const label = track.querySelector(".bar-value");
      label.classList.remove("inside");
      label.style.visibility = "";
      label.style.right = "auto";
      const trackWidth = track.clientWidth;
      const barLeft = bar.offsetLeft;
      const barWidth = bar.offsetWidth;
      const labelWidth = label.offsetWidth;
      const negative = label.dataset.negative === "true";
      const tip = negative ? barLeft : barLeft + barWidth;
      const outside = negative ? tip - labelWidth - gap : tip + gap;
      if (outside >= 0 && outside + labelWidth <= trackWidth) {
        label.style.left = `${outside}px`;
      } else if (labelWidth + 2 * gap <= barWidth) {
        label.style.left = `${negative ? tip + gap : tip - labelWidth - gap}px`;
        label.classList.add("inside");
      } else {
        label.style.visibility = "hidden";
      }
    }
  }

  // -------------------------------------------------------------------------
  // View: sources
  // -------------------------------------------------------------------------
  function renderSources() {
    document.title = "Sources · MOTEL Data Explorer";
    const rows = data.sources
      .slice()
      .sort((a, b) => compareText(a.source_name, b.source_name))
      .map((source) => {
        const records = sourceRecords.get(source.id) || [];
        const techCount = new Set(records.map((r) => r.tech_id)).size;
        const text = [source.source_name, source.source_description, source.source_type].filter(Boolean).join(" ").toLowerCase();
        const node = el(
          "tr",
          {},
          cell([el("strong", {}, sourceNode(source)), source.source_description ? el("div", { className: "muted small" }, source.source_description) : null]),
          cell(source.source_type || ""),
          cell(source.reference_year || "", true),
          cell(source.confidence_level || ""),
          cell(source.assessment_method || ""),
          cell(countFormat.format(records.length), true),
          cell(countFormat.format(techCount), true)
        );
        return { text, node };
      });

    const tbody = el("tbody");
    const count = el("p", { className: "muted small" });
    function apply(query) {
      const shown = rows.filter((row) => !query || row.text.includes(query));
      tbody.replaceChildren(...shown.map((row) => row.node));
      count.textContent = `${shown.length} of ${rows.length} sources`;
    }

    mount(
      hero("Sources", "Every source cited by the harmonised records, with how many records and technologies use it."),
      el("div", { className: "filter-row" }, el("label", {}, "Search sources", searchBox("Name, description, or type", apply))),
      count,
      el(
        "div",
        { className: "table-wrap" },
        el(
          "table",
          { className: "data-table" },
          el(
            "thead",
            {},
            el(
              "tr",
              {},
              [["Source"], ["Type"], ["Year", true], ["Confidence"], ["Method"], ["Records", true], ["Technologies", true]].map(([label, num]) =>
                el("th", { scope: "col", className: num ? "num" : null }, label)
              )
            )
          ),
          tbody
        )
      )
    );
    apply("");
  }

  // -------------------------------------------------------------------------
  // View: vocabulary
  // -------------------------------------------------------------------------
  function renderVocabulary() {
    document.title = "Vocabulary · MOTEL Data Explorer";
    const attributeRows = data.attributes
      .slice()
      .sort((a, b) => compareText(a.attribute_name, b.attribute_name))
      .map((attribute) =>
        el(
          "tr",
          {},
          cell(numericCount.get(attribute.id) ? el("a", { href: `#/compare?attribute=${encodeURIComponent(attribute.id)}` }, attribute.attribute_name) : attribute.attribute_name),
          cell(unitOf(attribute)),
          cell(attribute.data_format || ""),
          cell(attribute.applies_to || ""),
          cell(countFormat.format(valueCount.get(attribute.id) || 0), true),
          cell(el("span", { className: "small" }, attribute.attribute_description || ""))
        )
      );

    const carrierRows = data.carriers
      .slice()
      .sort((a, b) => compareText(a.carrier_name, b.carrier_name))
      .map((carrier) =>
        el(
          "tr",
          {},
          cell(carrier.carrier_name || carrier.id),
          cell(carrier.carrier_type || ""),
          cell(carrier.carrier_category || ""),
          cell(countFormat.format(carrierRecords.get(carrier.id) || 0), true),
          cell(el("span", { className: "small" }, carrier.carrier_description || ""))
        )
      );

    const scopeTables = SCOPE_TYPES.map((type) => {
      const use = countBy(data.records.map((r) => r.scope[type]).filter(Boolean), (token) => token);
      const rows = Object.entries(data.scopes[type] || {})
        .sort(([a], [b]) => compareText(a, b))
        .map(([token, description]) => el("tr", {}, cell(token), cell(description || ""), cell(countFormat.format(use.get(token) || 0), true)));
      return [el("h3", {}, SCOPE_LABELS[type]), table([{ label: "Token" }, { label: "Description" }, { label: "Records", num: true }], rows)];
    });

    mount(
      hero("Vocabulary", "The controlled vocabularies every record is harmonised against."),
      el("h2", {}, `Attributes (${data.attributes.length})`),
      table(
        [{ label: "Attribute" }, { label: "Unit" }, { label: "Format" }, { label: "Applies to" }, { label: "Values", num: true }, { label: "Description" }],
        attributeRows
      ),
      el("h2", {}, `Carriers (${data.carriers.length})`),
      table([{ label: "Carrier" }, { label: "Type" }, { label: "Category" }, { label: "Records", num: true }, { label: "Description" }], carrierRows),
      el("h2", {}, "Scopes"),
      scopeTables
    );
  }

  function renderNotFound(message) {
    document.title = "Not found · MOTEL Data Explorer";
    mount(hero("Not found", message, { href: "#/", label: "All technologies" }));
  }

  // -------------------------------------------------------------------------
  // Routing
  // -------------------------------------------------------------------------
  const VIEWS = {
    technologies: renderTechnologies,
    technology: renderTechnology,
    compare: renderCompare,
    sources: renderSources,
    vocabulary: renderVocabulary,
  };
  let lastView = null;

  function parseHash() {
    const hash = location.hash.replace(/^#/, "") || "/";
    const [path, query = ""] = hash.split("?");
    const parts = path.split("/").filter(Boolean);
    return { view: parts[0] || "technologies", id: parts[1] ? decodeURIComponent(parts[1]) : null, params: new URLSearchParams(query) };
  }

  function render() {
    hideTooltip();
    const route = parseHash();
    const view = VIEWS[route.view] ? route.view : "technologies";
    app.replaceChildren();
    VIEWS[view](route);

    const section = view === "technology" ? "technologies" : view;
    for (const link of nav.querySelectorAll("a")) {
      if (link.dataset.view === section) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    if (lastView !== null && lastView !== `${view}/${route.id}`) {
      window.scrollTo(0, 0);
      app.focus({ preventScroll: true });
    }
    lastView = `${view}/${route.id}`;
  }

  window.addEventListener("hashchange", render);
  window.addEventListener("scroll", hideTooltip, { passive: true });
  render();
})();
