export interface TaskBody {
  kind: string;
  payload: Record<string, unknown>;
  dedupe_key?: string;
  priority?: number;
}

export interface ProgressEvent {
  stage: string;
  percent: number | null;
  message: string;
  meta?: Record<string, unknown> | null;
  at: number;
}

export interface TaskProgress {
  task_id: number;
  status: string;
  progress: number;
  stage: string | null;
  progress_meta?: Record<string, unknown> | null;
  events: ProgressEvent[];
}

export class MediaClient {
  constructor(
    private readonly baseUrl = "http://127.0.0.1:8765",
    private readonly token?: string,
  ) {}

  private headers(extra: Record<string, string> = {}): Record<string, string> {
    if (this.token) {
      return { ...extra, Authorization: `Bearer ${this.token}` };
    }
    return extra;
  }

  async enqueue(
    kind: string,
    payload: Record<string, unknown>,
    dedupeKey?: string,
    priority = 0,
  ): Promise<unknown> {
    const body: TaskBody = { kind, payload, dedupe_key: dedupeKey, priority };
    const response = await fetch(`${this.baseUrl}/tasks`, {
      method: "POST",
      headers: this.headers({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    return response.json();
  }

  async task(id: number | string): Promise<unknown> {
    const response = await fetch(`${this.baseUrl}/tasks/${id}`, {
      headers: this.headers(),
    });
    return response.json();
  }

  async taskProgress(id: number | string): Promise<TaskProgress> {
    const response = await fetch(`${this.baseUrl}/tasks/${id}/progress`, {
      headers: this.headers(),
    });
    return response.json();
  }

  async taskEvents(
    id: number | string,
    after = 0,
    timeout = 0,
  ): Promise<{ events: ProgressEvent[]; next: number }> {
    const params = new URLSearchParams({ after: String(after) });
    if (timeout > 0) {
      params.set("timeout", String(timeout));
    }
    const response = await fetch(
      `${this.baseUrl}/tasks/${id}/events?${params}`,
      { headers: this.headers() },
    );
    return response.json();
  }

  async watchProgress(
    id: number | string,
    onProgress: (snapshot: TaskProgress) => void,
    intervalMs = 500,
    signal?: AbortSignal,
  ): Promise<void> {
    while (!signal?.aborted) {
      const snapshot = await this.taskProgress(id);
      onProgress(snapshot);
      if (["succeeded", "failed", "cancelled"].includes(snapshot.status)) {
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  }

  async depsStatus(): Promise<unknown> {
    const response = await fetch(`${this.baseUrl}/deps/status`, {
      headers: this.headers(),
    });
    return response.json();
  }

  async formats(): Promise<unknown> {
    const response = await fetch(`${this.baseUrl}/formats`, {
      headers: this.headers(),
    });
    return response.json();
  }

  async depsProgress(): Promise<unknown> {
    const response = await fetch(`${this.baseUrl}/deps/progress`, {
      headers: this.headers(),
    });
    return response.json();
  }

  async installDeps(): Promise<unknown> {
    const response = await fetch(`${this.baseUrl}/deps/install`, {
      method: "POST",
      headers: this.headers(),
    });
    return response.json();
  }
}
