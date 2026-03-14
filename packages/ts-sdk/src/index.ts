export type CaliperHealth = {
  status: "ok";
  profile: string;
};

export class CaliperClient {
  constructor(private readonly baseUrl: string) {}

  async healthz(): Promise<CaliperHealth> {
    const response = await fetch(`${this.baseUrl}/healthz`);
    if (!response.ok) {
      throw new Error(`healthz failed: ${response.status}`);
    }
    return (await response.json()) as CaliperHealth;
  }
}
