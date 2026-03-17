/**
 * Axios instance pre-configured to target the GraphRL-Sec FastAPI backend.
 *
 * All API hooks import `apiClient` from this module — changing the base URL
 * here updates every call site without hunting through the codebase.
 */

import axios from "axios";

const apiClient = axios.create({
  baseURL: "http://localhost:8000",
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

export default apiClient;
