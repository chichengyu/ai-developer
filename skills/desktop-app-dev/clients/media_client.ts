export interface TaskBody {
  kind: string;
  payload: Record<string, unknown>;
  dedupe_key?: string;
  priority?: number;
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

  async depsStatus(): Promise<unknown> {
    const response = await fetch(`${this.baseUrl}/deps/status`, {
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
