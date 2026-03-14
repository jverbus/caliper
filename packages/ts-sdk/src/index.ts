export type HttpMethod = "GET" | "POST" | "PATCH";

export type CaliperHealth = {
  status: "ok" | "ready";
};

export type JsonRecord = Record<string, unknown>;

export type JobCreateResponse = {
  job_id: string;
  status: string;
  created_at: string;
};

export type ArmBulkRegisterResponse = {
  workspace_id: string;
  job_id: string;
  registered_count: number;
  arms: JsonRecord[];
};

export type AssignResult = {
  decision_id: string;
  workspace_id: string;
  job_id: string;
  unit_id: string;
  arm_id: string;
  propensity: number;
  [key: string]: unknown;
};

export type ReportPayload = {
  report_id: string;
  workspace_id: string;
  job_id: string;
  [key: string]: unknown;
};

export class CaliperClient {
  private readonly baseUrl: string;
  private readonly defaultHeaders: Record<string, string>;

  constructor(options: { baseUrl: string; apiToken?: string }) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.defaultHeaders = { "Content-Type": "application/json" };
    if (options.apiToken) {
      this.defaultHeaders.Authorization = `Bearer ${options.apiToken}`;
    }
  }

  private async request<T>(method: HttpMethod, path: string, body?: JsonRecord): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: this.defaultHeaders,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`${method} ${path} failed: ${response.status} ${detail}`);
    }

    return (await response.json()) as T;
  }

  async healthz(): Promise<CaliperHealth> {
    return this.request<CaliperHealth>("GET", "/healthz");
  }

  async createJob(payload: JsonRecord): Promise<JobCreateResponse> {
    return this.request<JobCreateResponse>("POST", "/v1/jobs", payload);
  }

  async getJob(jobId: string): Promise<JsonRecord> {
    return this.request<JsonRecord>("GET", `/v1/jobs/${jobId}`);
  }

  async updateJob(jobId: string, patch: JsonRecord): Promise<JsonRecord> {
    return this.request<JsonRecord>("PATCH", `/v1/jobs/${jobId}`, patch);
  }

  async addArms(jobId: string, payload: JsonRecord): Promise<ArmBulkRegisterResponse> {
    return this.request<ArmBulkRegisterResponse>("POST", `/v1/jobs/${jobId}/arms:batch_register`, payload);
  }

  async assign(payload: JsonRecord): Promise<AssignResult> {
    return this.request<AssignResult>("POST", "/v1/assign", payload);
  }

  async logExposure(payload: JsonRecord): Promise<JsonRecord> {
    return this.request<JsonRecord>("POST", "/v1/exposures", payload);
  }

  async logOutcome(payload: JsonRecord): Promise<JsonRecord> {
    return this.request<JsonRecord>("POST", "/v1/outcomes", payload);
  }

  async generateReport(jobId: string, payload: JsonRecord): Promise<ReportPayload> {
    return this.request<ReportPayload>("POST", `/v1/jobs/${jobId}/reports:generate`, payload);
  }

  async latestReport(jobId: string, workspaceId: string): Promise<ReportPayload> {
    return this.request<ReportPayload>("GET", `/v1/jobs/${jobId}/reports/latest?workspace_id=${encodeURIComponent(workspaceId)}`);
  }
}
