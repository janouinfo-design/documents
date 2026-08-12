import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const http = axios.create({ baseURL: API });

export const fileUrl = (path, { download = false, filename } = {}) => {
  if (!path) return "";
  const params = new URLSearchParams();
  if (download) params.set("download", "true");
  if (filename) params.set("filename", filename);
  const qs = params.toString();
  return `${API}/files/${path}${qs ? `?${qs}` : ""}`;
};

// Resolve a media reference that may be an external url or a storage path
export const mediaSrc = (item) => {
  if (!item) return "";
  if (item.path) return fileUrl(item.path);
  return item.url || "";
};

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

// Navixy integration
export const getNavixyStatus = () => http.get("/navixy/status").then((r) => r.data);
export const navixySync = () => http.post("/navixy/sync").then((r) => r.data);

// Demo data
export const fillDemoAdmin = () => http.post("/demo/fill-admin").then((r) => r.data);

// Alerts
export const getAlerts = () => http.get("/alerts").then((r) => r.data);
export const getAlertsLog = () => http.get("/alerts/log").then((r) => r.data);
export const runAlerts = () => http.post("/alerts/run").then((r) => r.data);

// Scan intelligent de documents
export const getDocumentTypes = () => http.get("/document-types").then((r) => r.data);
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

// Enrichissement technique externe (SwissCarInfo — données officielles OFROU)
export const getTechnicalStatus = () => http.get("/technical-data/status").then((r) => r.data);
export const getConfigStatus = () => http.get("/config/status").then((r) => r.data);
export const conformityReportUrl = () => `${API}/reports/conformite.pdf`;
export const enrichTechnical = (id) =>
  http.post(`/vehicles/${id}/enrich-technical`, null, { timeout: 60000 }).then((r) => r.data);
export const applyTechnicalEnrichment = (id, payload) =>
  http.post(`/vehicles/${id}/enrich-technical/apply`, payload).then((r) => r.data);

export default http;
