import { request } from "./http";
import type { HealthStatus } from "../types/api";

export const health = () => request<HealthStatus>("/health");
