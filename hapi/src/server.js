"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");
const Hapi = require("@hapi/hapi");

const VALID_VERSIONS = new Set(["2.5", "3.0", "V3_grid"]);
const RADAR_IDS = new Set([
  "ade", "adw", "bks", "bpk", "cly", "cve", "cvw", "dce", "dcn", "fhe", "fhw",
  "fir", "gbr", "hal", "han", "hok", "hkw", "ice", "icw", "inv", "jme", "kap",
  "ker", "kod", "ksr", "lyr", "mcm", "pgr", "pyk", "rkn", "san", "sas", "sch",
  "sps", "sto", "sye", "sys", "tig", "unw", "wal", "zho"
]);
const BEAM_IDS = ["a", "b", "c", "d", "e", "f", "g", "h"];

const config = {
  host: process.env.HAPI_HOST || "127.0.0.1",
  port: parseInt(process.env.HAPI_PORT || "43100", 10),
  zenodoApiBaseUrl: process.env.ZENODO_API_BASE_URL || "https://zenodo.org",
  zenodoRequestTimeoutMs: parseInt(process.env.ZENODO_REQUEST_TIMEOUT_MS || "30000", 10),
  zenodoCacheTtlMs: parseInt(process.env.ZENODO_CACHE_TTL_MS || "900000", 10),
  zenodoRecordPageSize: parseInt(process.env.ZENODO_RECORD_PAGE_SIZE || "25", 10),
  zenodoInventoryNorthFile: process.env.ZENODO_INVENTORY_NORTH_FILE || "/project/superdarn/www/config/zenodo_inventory_north.json",
  zenodoInventorySouthFile: process.env.ZENODO_INVENTORY_SOUTH_FILE || "/project/superdarn/www/config/zenodo_inventory_south.json"
};

const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const recordCache = new Map();

function badRequest(message) {
  const error = new Error(message);
  error.statusCode = 400;
  return error;
}

function notFound(message) {
  const error = new Error(message);
  error.statusCode = 404;
  return error;
}

function validateRequest(query) {
  const ver = String(query.ver || "");
  const rdr = String(query.rdr || "").toLowerCase();
  const yr = String(query.yr || "");
  const mo = String(query.mo || "");
  const dayRaw = String(query.day || "");

  if (!VALID_VERSIONS.has(ver)) {
    throw badRequest("Invalid ver. Expected one of 2.5, 3.0, V3_grid.");
  }
  if (!RADAR_IDS.has(rdr)) {
    throw badRequest("Invalid rdr.");
  }
  if (!/^\d{4}$/.test(yr)) {
    throw badRequest("Invalid yr.");
  }
  if (!/^\d{1,2}$/.test(mo)) {
    throw badRequest("Invalid mo.");
  }
  if (!/^\d{1,8}$/.test(dayRaw)) {
    throw badRequest("Invalid day.");
  }

  const monthNum = parseInt(mo, 10);
  if (monthNum < 1 || monthNum > 12) {
    throw badRequest("Invalid mo.");
  }

  const dayNum = dayRaw.length === 8 ? parseInt(dayRaw.slice(6, 8), 10) : parseInt(dayRaw, 10);
  if (dayNum < 1 || dayNum > 31) {
    throw badRequest("Invalid day.");
  }

  const month = String(monthNum).padStart(2, "0");
  const day = String(dayNum).padStart(2, "0");
  const dateStr = `${yr}${month}${day}`;

  return {
    ver,
    rdr,
    yr,
    mo: month,
    day,
    dateStr,
    monthLabel: `${yr}-${monthNames[monthNum - 1]}`
  };
}

function getRecordTitle(ver, monthLabel) {
  if (ver === "V3_grid") {
    return `SuperDARN Grid data in netCDF format (${monthLabel})`;
  }
  return `SuperDARN data in netCDF format (${monthLabel})`;
}

function getFitFormats(ver) {
  if (ver === "2.5") {
    return ["v2.5", "fitacf2"];
  }
  return ["v3.0.despeckled", "despeck.fitacf3", "fitacf3", "v3.0"];
}

function getGridFormats() {
  return ["v3.0.grid", "fitacf3.grid"];
}

function buildCandidateFileNames(requested) {
  const { ver, dateStr, rdr } = requested;
  const candidates = [];
  const pushFormatCandidates = (format) => {
    candidates.push(`${dateStr}.${rdr}.${format}.nc`);
    for (const beam of BEAM_IDS) {
      candidates.push(`${dateStr}.${rdr}.${beam}.${format}.nc`);
    }
  };

  if (ver === "V3_grid") {
    for (const format of getGridFormats()) {
      pushFormatCandidates(format);
    }
    return candidates;
  }

  for (const format of getFitFormats(ver)) {
    pushFormatCandidates(format);
  }
  return candidates;
}

function sortRecordsNewestFirst(records) {
  return [...records].sort((left, right) => {
    const leftTime = Date.parse(left.updated || left.created || 0);
    const rightTime = Date.parse(right.updated || right.created || 0);
    return rightTime - leftTime;
  });
}

async function fetchJson(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.zenodoRequestTimeoutMs);
  try {
    const response = await fetch(url, {
      headers: {
        accept: "application/json",
        "user-agent": "superdarn-zenodo-hapi/0.1.0"
      },
      signal: controller.signal
    });
    if (!response.ok) {
      throw new Error(`Zenodo request failed with status ${response.status}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function getZenodoRecords(title) {
  const cached = recordCache.get(title);
  const now = Date.now();
  if (cached && cached.expiresAt > now) {
    return cached.records;
  }

  const url = new URL("/api/records", config.zenodoApiBaseUrl);
  url.searchParams.set("q", `"${title}"`);
  url.searchParams.set("all_versions", "1");
  url.searchParams.set("size", String(config.zenodoRecordPageSize));

  const payload = await fetchJson(url);
  const records = payload?.hits?.hits || [];
  recordCache.set(title, {
    expiresAt: now + config.zenodoCacheTtlMs,
    records
  });
  return records;
}

function findExactFileMatch(records, candidateFileNames) {
  const orderedRecords = sortRecordsNewestFirst(records);
  for (const candidate of candidateFileNames) {
    for (const record of orderedRecords) {
      const files = Array.isArray(record.files) ? record.files : [];
      const match = files.find((file) => file.key === candidate && file.links && file.links.self);
      if (match) {
        return {
          url: match.links.self,
          fileName: match.key,
          recordId: record.id,
          recordTitle: record.title || record.metadata?.title || "",
          matchType: "exact-file"
        };
      }
    }
  }
  return null;
}

function findDailyZipMatch(records, dateStr) {
  const orderedRecords = sortRecordsNewestFirst(records);
  const dailyZipName = `${dateStr}.nc.zip`;
  for (const record of orderedRecords) {
    const files = Array.isArray(record.files) ? record.files : [];
    const match = files.find((file) => file.key === dailyZipName && file.links && file.links.self);
    if (match) {
      return {
        url: match.links.self,
        fileName: match.key,
        recordId: record.id,
        recordTitle: record.title || record.metadata?.title || "",
        matchType: "daily-zip"
      };
    }
  }
  return null;
}

async function resolveZenodoRedirect(query) {
  const requested = validateRequest(query);
  const title = getRecordTitle(requested.ver, requested.monthLabel);
  const records = await getZenodoRecords(title);

  if (!records.length) {
    throw notFound(`No Zenodo records found for ${title}.`);
  }

  const exactMatch = findExactFileMatch(records, buildCandidateFileNames(requested));
  if (exactMatch) {
    return exactMatch;
  }

  if (requested.ver !== "V3_grid") {
    const dailyZipMatch = findDailyZipMatch(records, requested.dateStr);
    if (dailyZipMatch) {
      return dailyZipMatch;
    }
  }

  throw notFound(`No Zenodo file found for ${requested.dateStr} ${requested.rdr} ${requested.ver}.`);
}

async function readInventoryFile(filePath) {
  const payload = await fs.readFile(filePath, "utf8");
  return JSON.parse(payload);
}

function makeErrorResponse(request, h, error) {
  const statusCode = error.statusCode || 500;
  const payload = {
    error: statusCode >= 500 ? "Internal Server Error" : "Bad Request",
    message: error.message
  };
  if (statusCode === 404) {
    payload.error = "Not Found";
  }
  return h.response(payload).code(statusCode);
}

async function buildServer() {
  const server = Hapi.server({
    host: config.host,
    port: config.port,
    routes: {
      cors: true
    }
  });

  server.route({
    method: "GET",
    path: "/healthz",
    handler: () => ({
      status: "ok",
      service: "superdarn-zenodo-hapi"
    })
  });

  server.route({
    method: "GET",
    path: "/zenodo_inventory_north",
    handler: async (request, h) => {
      try {
        return await readInventoryFile(config.zenodoInventoryNorthFile);
      } catch (error) {
        return makeErrorResponse(request, h, error);
      }
    }
  });

  server.route({
    method: "GET",
    path: "/zenodo_inventory_south",
    handler: async (request, h) => {
      try {
        return await readInventoryFile(config.zenodoInventorySouthFile);
      } catch (error) {
        return makeErrorResponse(request, h, error);
      }
    }
  });

  server.route({
    method: "GET",
    path: "/apl_superdarn_data",
    handler: async (request, h) => {
      try {
        const redirect = await resolveZenodoRedirect(request.query);
        return h.redirect(redirect.url).temporary().header("X-SuperDARN-Zenodo-Match", redirect.matchType).header("X-SuperDARN-Zenodo-File", redirect.fileName).header("X-SuperDARN-Zenodo-Record", String(redirect.recordId));
      } catch (error) {
        return makeErrorResponse(request, h, error);
      }
    }
  });

  return server;
}

async function main() {
  const server = await buildServer();
  await server.start();
  console.log(`superdarn-zenodo-hapi listening on http://${config.host}:${config.port}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
