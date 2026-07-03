// Typed HTTP client for the control API

export class ControlApiClient {
  constructor(private baseUrl: string) {}

  async getModels(): Promise<unknown> {
    throw new Error("not implemented");
  }
}

