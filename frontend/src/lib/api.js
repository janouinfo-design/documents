import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const TOKEN_KEY = "lt_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

// Vue client (superadmin uniquement — le backend vérifie le rôle côté serveur)
const ACTING_KEY = "lt_acting_tenant";
export const getActingTenant = () => {
  try {
    return JSON.parse(localStorage.getItem(ACTING_KEY)) || null;
  } catch {
    return null;
  }
};
export const setActingTenant = (t) =>
  t ? localStorage.setItem(ACTING_KEY, JSON.stringify(t)) : localStorage.removeItem(ACTING_KEY);

const http = axios.create({ baseURL: API });
http.interceptors.request.use((config) => {
  const t = getToken();
  if (t) config.headers.Authorization = `Bearer ${t}`;
  const acting = getActingTenant();
  if (acting?.id) config.headers["X-Acting-Tenant"] = acting.id;
  return config;
});
http.interceptors.response.use(
  (r) => r,
  (error) => {
    const url = String(error?.config?.url || "");
    if (error?.response?.status === 401 && !url.includes("/auth/login")
        && !url.includes("/auth/change-password") && !url.includes("/auth/navixy/exchange")) {
      setToken(null);
      if (!window.location.pathname.startsWith("/login")) window.location.assign("/login");
    }
    return Promise.reject(error);
  }
);

// Jeton fichier court (scope=file, 10 min) — le JWT de session n'est JAMAIS mis en URL
let fileToken = null;
export const refreshFileToken = () => {
  const acting = getActingTenant();
  return http
    .get("/auth/file-token", { params: acting?.id ? { acting_tenant: acting.id } : {} })
    .then((r) => {
      fileToken = r.data.token;
      return fileToken;
    });
};
export const clearFileToken = () => {
  fileToken = null;
};

const withToken = (url) => {
  if (!fileToken) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(fileToken)}`;
};

// Authentification
export const authLogin = (email, password) =>
  http.post("/auth/login", { email, password }).then((r) => r.data);
export const authMe = () => http.get("/auth/me").then((r) => r.data);
export const exchangeNavixy = (session_key) =>
  http.post("/auth/navixy/exchange", { session_key }).then((r) => r.data);
export const authLogout = () => http.post("/auth/logout").then((r) => r.data);
export const authChangePassword = (current_password, new_password) =>
  http.post("/auth/change-password", { current_password, new_password }).then((r) => r.data);

export const fileUrl = (path, { download = false, filename } = {}) => {
  if (!path) return "";
  const params = new URLSearchParams();
  if (download) params.set("download", "true");
  if (filename) params.set("filename", filename);
  const qs = params.toString();
  return withToken(`${API}/files/${path}${qs ? `?${qs}` : ""}`);
};

// Resolve a media reference that may be an external url or a storage path
export const mediaSrc = (item) => {
  if (!item) return "";
  if (item.path) return fileUrl(item.path);
  return item.url || "";
};

// Ajoute le jeton aux URLs de photos stockées pointant vers /api/files
export const photoSrc = (url) => (url && url.includes("/api/files/") ? withToken(url) : url);

// Vehicles
export const getVehicles = () => http.get("/vehicles").then((r) => r.data);
export const getVehicle = (id) => http.get(`/vehicles/${id}`).then((r) => r.data);
export const createVehicle = (data) => http.post("/vehicles", data).then((r) => r.data);
export const updateVehicle = (id, data) => http.put(`/vehicles/${id}`, data).then((r) => r.data);
export const deleteVehicle = (id) => http.delete(`/vehicles/${id}`).then((r) => r.data);

// Documents
export const getDocuments = (id) => http.get(`/vehicles/${id}/documents`).then((r) => r.data);
export const deleteDocument = (docId) => http.delete(`/documents/${docId}`).then((r) => r.data);
export const uploadDocument = (vehicleId, file, folder, onProgress) => {
  const form = new FormData();
  form.append("file", file);
  form.append("folder", folder);
  return http
    .post(`/vehicles/${vehicleId}/documents`, form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: onProgress,
    })
    .then((r) => r.data);
};

// Generic upload (photos / inspection media)
export const uploadFile = (file, vehicleId = "misc") => {
  const form = new FormData();
  form.append("file", file);
  form.append("vehicle_id", vehicleId);
  return http
    .post("/upload", form, { headers: { "Content-Type": "multipart/form-data" } })
    .then((r) => r.data);
};

// Inspections
export const getInspections = (id) => http.get(`/vehicles/${id}/inspections`).then((r) => r.data);
export const createInspection = (id, data) =>
  http.post(`/vehicles/${id}/inspections`, data).then((r) => r.data);
export const deleteInspection = (insId) => http.delete(`/inspections/${insId}`).then((r) => r.data);

// Dashboard & timeline
export const getDashboard = () => http.get("/dashboard").then((r) => r.data);
export const getTimeline = () => http.get("/timeline").then((r) => r.data);

// Échéances — moteur central V2 (étape 4) + seuils par client
export const getDeadlines = (params = {}) => http.get("/deadlines", { params }).then((r) => r.data);
export const getDeadlineSettings = () => http.get("/settings/deadlines").then((r) => r.data);
export const putDeadlineSettings = (data) => http.put("/settings/deadlines", data).then((r) => r.data);

// Coûts — moteur central dérivé des documents V2 + legacy (dual-read)
export const getCosts = (params = {}) => http.get("/costs", { params }).then((r) => r.data);
export const getVehicleCosts = (id) => http.get(`/vehicles/${id}/costs`).then((r) => r.data);

// Synchronisation télématique
export const getNavixyStatus = () => http.get("/navixy/status").then((r) => r.data);
export const navixySync = () => http.post("/navixy/sync").then((r) => r.data);

// Alerts
export const getAlerts = () => http.get("/alerts").then((r) => r.data);
export const getAlertsLog = () => http.get("/alerts/log").then((r) => r.data);
export const runAlerts = () => http.post("/alerts/run").then((r) => r.data);

// Scan intelligent de documents
export const getDocumentTypes = () => http.get("/document-types").then((r) => r.data);
export const getDocumentExtraction = (docId) =>
  http.get(`/documents/${docId}/extraction`).then((r) => r.data);

export const suggestReservoir = (vehicleId) =>
  http.post(`/vehicles/${vehicleId}/reservoir/suggest`).then((r) => r.data);

export const applyReservoir = (vehicleId, valueL) =>
  http.post(`/vehicles/${vehicleId}/reservoir/apply`, { value_l: valueL }).then((r) => r.data);

export const suggestConso = (vehicleId) =>
  http.post(`/vehicles/${vehicleId}/conso/suggest`).then((r) => r.data);

export const applyConso = (vehicleId, payload) =>
  http.post(`/vehicles/${vehicleId}/conso/apply`, payload).then((r) => r.data);

export const pushVehicleNavixy = (vehicleId) =>
  http.post(`/vehicles/${vehicleId}/navixy/push`).then((r) => r.data);

export const scanVehicleDocument = (vehicleId, files, { documentType, documentId, asPdf } = {}) => {
  const form = new FormData();
  (files || []).forEach((f) => form.append("files", f));
  if (documentType) form.append("document_type", documentType);
  if (documentId) form.append("document_id", documentId);
  if (asPdf) form.append("as_pdf", "1");
  return http
    .post(`/vehicles/${vehicleId}/documents/scan`, form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 180000,
    })
    .then((r) => r.data);
};
export const validateScannedDocument = (docId, payload) =>
  http.post(`/documents/${docId}/validate`, payload).then((r) => r.data);
export const getFieldMeta = (id) => http.get(`/vehicles/${id}/field-meta`).then((r) => r.data);
export const getVehicleHistory = (id) => http.get(`/vehicles/${id}/history`).then((r) => r.data);

// Enrichissement technique — base officielle ASTRA/OFROU (locale, sans clé)
export const getTechnicalStatus = () => http.get("/technical-data/status").then((r) => r.data);
export const getConfigStatus = () => http.get("/config/status").then((r) => r.data);
export const getAstraStatus = () => http.get("/astra/status").then((r) => r.data);
export const astraImport = () => http.post("/astra/import").then((r) => r.data);
export const enrichFleet = () =>
  http.post("/vehicles/enrich-technical/batch", null, { timeout: 120000 }).then((r) => r.data);
export const revertTechnicalField = (id, field) =>
  http.post(`/vehicles/${id}/enrich-technical/revert`, { field }).then((r) => r.data);
export const getConsumptionRanking = () =>
  http.get("/fleet/consumption-ranking").then((r) => r.data);
export const getIntegrity = (params = {}) =>
  http.get("/fleet/integrity", { params }).then((r) => r.data);
export const getLinkSuggestions = () =>
  http.get("/integrations/navixy/link-suggestions").then((r) => r.data);
export const linkNavixyVehicle = (vehicleId, externalVehicleId) =>
  http.post("/integrations/navixy/link", { vehicle_id: vehicleId, external_vehicle_id: externalVehicleId }).then((r) => r.data);
export const createNavixyVehicle = (vehicleId, confirm = false) =>
  http.post("/integrations/navixy/create-vehicle", { vehicle_id: vehicleId, confirm }).then((r) => r.data);
export const conformityReportUrl = () => withToken(`${API}/reports/conformite.pdf`);
export const costsCsvUrl = () => withToken(`${API}/reports/couts.csv`);
export const vehicleReportUrl = (id) => withToken(`${API}/reports/vehicule/${id}.pdf`);
export const enrichTechnical = (id) =>
  http.post(`/vehicles/${id}/enrich-technical`, null, { timeout: 60000 }).then((r) => r.data);
export const applyTechnicalEnrichment = (id, payload) =>
  http.post(`/vehicles/${id}/enrich-technical/apply`, payload).then((r) => r.data);

// Console Super Admin
export const adminOverview = () => http.get("/admin/overview").then((r) => r.data);
export const adminCreateTenant = (data) => http.post("/admin/tenants", data).then((r) => r.data);
export const adminUpdateTenant = (tid, data) => http.put(`/admin/tenants/${tid}`, data).then((r) => r.data);
export const adminListUsers = (tid) => http.get(`/admin/tenants/${tid}/users`).then((r) => r.data);
export const adminCreateUser = (tid, data) => http.post(`/admin/tenants/${tid}/users`, data).then((r) => r.data);
export const adminUpdateUser = (uid, data) => http.put(`/admin/users/${uid}`, data).then((r) => r.data);
export const adminGetIntegration = (tid) => http.get(`/admin/tenants/${tid}/integration`).then((r) => r.data);
export const adminUpdateIntegration = (tid, data) =>
  http.put(`/admin/tenants/${tid}/integration`, data).then((r) => r.data);

// Documents V2 — page centrale, fiche, catégories, profils
export const getAllDocuments = (params = {}) => http.get("/documents", { params }).then((r) => r.data);
export const updateDocument = (docId, data) => http.patch(`/documents/${docId}`, data).then((r) => r.data);
export const getDocCategories = () => http.get("/doc-categories").then((r) => r.data);
export const createDocCategory = (data) => http.post("/doc-categories", data).then((r) => r.data);
export const updateDocCategory = (id, data) => http.put(`/doc-categories/${id}`, data).then((r) => r.data);
export const deleteDocCategory = (id) => http.delete(`/doc-categories/${id}`).then((r) => r.data);
export const getDocRequirements = () => http.get("/doc-requirements").then((r) => r.data);
export const putDocRequirements = (profil, categories) =>
  http.put("/doc-requirements", { profil, categories }).then((r) => r.data);
export const getVehicleDocConformity = (id) =>
  http.get(`/vehicles/${id}/conformite-documents`).then((r) => r.data);

export default http;
